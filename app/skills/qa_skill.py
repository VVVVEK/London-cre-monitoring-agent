"""qa_skill - explainable business Q&A grounded in stored evidence.

Hard constraints (integrity policy):
  * Never invent numbers - answers are built only from retrieved signals/events.
  * Prefer `observed` evidence; any use of `synthetic`/`estimated` is stated and
    caps the confidence.
  * Always return: answer, key_points, evidence (source+date+metric), confidence,
    limitations.
"""
from __future__ import annotations

import pandas as pd

from app.data.models import Evidence, QAResult
from app.data import repository
from app.llm.client import LLMClient
from app.llm.prompts import QA_SYSTEM
from app.skills import analysis_skill
from app.utils.logging import get_logger

log = get_logger(__name__)

SUBMARKETS = ["City", "West End", "Canary Wharf", "Midtown"]
METRIC_KEYWORDS = {
    "Vacancy Rate": ["vacancy", "vacant", "empty"],
    "Availability Rate": ["availability", "available"],
    "Prime Rent": ["prime rent", "rent", "rental", "headline rent"],
    "Grade A Rent": ["grade a", "grade-a"],
    "Take-up Volume": ["take-up", "takeup", "take up", "demand", "leasing", "absorption"],
    "Pipeline Stock": ["pipeline", "supply", "development"],
    "Refurbishment Pipeline": ["refurb", "refurbishment", "retrofit"],
    "Pre-let Ratio": ["pre-let", "prelet", "pre let"],
    "Policy Rate": ["interest rate", "policy rate", "base rate", "rates"],
    "CPI": ["cpi", "inflation"],
    "Core CPI": ["core cpi", "core inflation"],
    "Office Employment": ["employment", "jobs", "labour", "labor", "hiring"],
    "Gilt Yield": ["gilt", "bond yield"],
    "Unemployment Rate": ["unemployment", "jobless"],
}
SCORE_WORDS = ["stress", "risk", "resilience", "opportunity", "attractive", "best", "worst"]
NEWS_WORDS = ["hybrid", "esg", "sustainab", "tenant", "news", "relocat", "flight to quality"]


def _detect(question: str):
    q = question.lower()
    sms = [s for s in SUBMARKETS if s.lower() in q]
    metrics = [m for m, kws in METRIC_KEYWORDS.items() if any(k in q for k in kws)]
    wants_score = any(w in q for w in SCORE_WORDS)
    wants_news = any(w in q for w in NEWS_WORDS)
    return sms or SUBMARKETS, metrics, wants_score, wants_news


def _evidence_for(df, submarkets, metrics) -> tuple[list[Evidence], list[str]]:
    evidence, points = [], []
    for sm in submarkets:
        for metric in metrics:
            s = analysis_skill._series(df, sm, metric)
            if s.empty:
                continue
            row = s.iloc[-1]
            evidence.append(Evidence(source=row["source"], timestamp=str(row["date"]),
                                     metric=f"{sm} {metric}", value=float(row["value"]),
                                     evidence_type=row.get("data_quality", "synthetic"),
                                     source_url=row.get("source_url")))
            chg, pct = analysis_skill._momentum(df, sm, metric)
            trend = f" ({'+' if (chg or 0) >= 0 else ''}{chg:.1f} over 3 periods)" if chg is not None else ""
            points.append(f"{sm} {metric}: {row['value']:g}{row['unit'] and ' ' + row['unit'] or ''}{trend}")
    return evidence, points


def _confidence(evidence: list[Evidence], base: float) -> float:
    if not evidence:
        return 0.0
    if any(e.evidence_type == "observed" for e in evidence):
        return min(0.9, base)
    return min(0.5, base)  # synthetic/estimated cap


def run(question: str) -> QAResult:
    df = repository.signals_dataframe()
    submarkets, metrics, wants_score, wants_news = _detect(question)
    if not metrics and not wants_score and not wants_news:
        metrics = ["Vacancy Rate", "Prime Rent", "Take-up Volume"]

    evidence, points = ([], [])
    if metrics:
        evidence, points = _evidence_for(df, submarkets, metrics)

    if wants_news or wants_score:
        analysis = analysis_skill.run()
        if wants_news:
            drivers = analysis.get("demand_drivers", {})
            for sm in submarkets:
                smd = drivers.get("by_submarket", {}).get(sm, {})
                for hl in smd.get("headlines", [])[:2]:
                    points.append(f"News ({sm}): {hl['headline'][:80]} [{hl['evidence_type']}]")
                    evidence.append(Evidence(
                        source=hl["source"], timestamp=hl["date"], metric=f"{sm} news",
                        note=hl["headline"][:120], evidence_type=hl["evidence_type"],
                        source_url=hl.get("source_url")))
        if wants_score:
            for sc in analysis["score_objects"]:
                if sc.submarket in submarkets:
                    points.append(f"{sc.submarket} {sc.name}: {sc.score} ({sc.level})")
                    evidence.extend(sc.evidence)

    if not evidence and not points:
        return QAResult(
            answer="I cannot answer this from the available data.",
            key_points=[], evidence=[], confidence=0.0,
            limitations="No matching signals were found for the question. "
                        "Try naming a submarket (City/West End/Canary Wharf/Midtown) and a metric.")

    has_observed = any(e.evidence_type == "observed" for e in evidence)
    has_synth = any(e.evidence_type != "observed" for e in evidence)
    limitations = ""
    if has_synth:
        limitations = ("Some/all cited CRE metrics are SYNTHETIC sample data "
                       "(reason: missing_public_source) used for PoC validation - not a market fact. "
                       "Macro/news are live (observed) only when API/RSS are reachable.")

    # LLM phrasing if available; otherwise deterministic summary.
    llm = LLMClient()
    answer, conf = None, 0.55
    if llm.available:
        ev_text = "\n".join(f"- [{e.evidence_type}] {e.metric}={e.value} ({e.source}, {e.timestamp})"
                            for e in evidence)
        data = llm.complete_json(QA_SYSTEM, f"QUESTION: {question}\nEVIDENCE:\n{ev_text}")
        if data:
            answer = data.get("answer")
            points = data.get("key_points", points) or points
            conf = float(data.get("confidence", 0.6))
            if data.get("limitations"):
                limitations = (limitations + " " + data["limitations"]).strip()

    if not answer:
        lead = "Based on the latest stored signals"
        tag = " (note: based on synthetic sample data)" if (has_synth and not has_observed) else ""
        answer = f"{lead}{tag}: " + "; ".join(points[:6]) + "."

    result = QAResult(answer=answer, key_points=points[:8], evidence=evidence[:10],
                      confidence=round(_confidence(evidence, conf), 2), limitations=limitations)
    log.info("qa answered (conf=%.2f, evidence=%d)", result.confidence, len(result.evidence))
    return result
