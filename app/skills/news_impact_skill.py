"""news_impact_skill - classify news into structured CRE event signals."""
from __future__ import annotations

import json
from typing import Any

from app.data.models import EventNews
from app.data import repository
from app.llm.client import LLMClient
from app.llm.prompts import NEWS_EXTRACT_SYSTEM
from app.utils.logging import get_logger

log = get_logger(__name__)

SUBMARKETS = ["City", "West End", "Canary Wharf", "Midtown"]

TAG_KEYWORDS = {
    "hybrid_working": ["hybrid", "remote work", "work from home", "flexible working"],
    "esg": ["esg", "sustainab", "net zero", "green", "epc", "carbon"],
    "flight_to_quality": ["flight-to-quality", "flight to quality", "prime", "grade a",
                          "best-in-class", "premium space"],
    "tenant_move": ["relocat", "expand", "downsiz", "sublet", "pre-let", "lease",
                    "headquarter", "hq", "consolidat"],
    "financing": ["interest rate", "base rate", "bank of england", "boe", "yield",
                  "refinanc", "financing", "debt", "valuation"],
}
NEG_WORDS = ["sublet", "downsiz", "consolidat", "weigh", "risk", "fall", "decline",
             "vacant", "higher for longer", "cut", "reduce"]
POS_WORDS = ["expand", "resilient", "demand", "pre-let", "growth", "record", "strong"]


def _rule_classify(headline: str, summary: str) -> dict[str, Any]:
    text = f"{headline} {summary}".lower()
    sm = next((s for s in SUBMARKETS if s.lower() in text), "London")
    tags = [t for t, kws in TAG_KEYWORDS.items() if any(k in text for k in kws)]
    neg = sum(w in text for w in NEG_WORDS)
    pos = sum(w in text for w in POS_WORDS)
    direction = "negative" if neg > pos else "positive" if pos > neg else "neutral"
    horizon = "short" if ("financing" in tags or direction == "negative") else "medium"
    return {"affected_submarket": sm, "impact_direction": direction,
            "time_horizon": horizon, "tags": tags, "confidence": 0.5}


def _llm_classify(llm: LLMClient, headline: str, summary: str) -> dict[str, Any] | None:
    data = llm.complete_json(NEWS_EXTRACT_SYSTEM, f"HEADLINE: {headline}\nSUMMARY: {summary}")
    if not data:
        return None
    data.setdefault("tags", [])
    return data


def run(raw_news: list[dict[str, Any]]) -> dict[str, Any]:
    llm = LLMClient()
    events: list[EventNews] = []
    tag_counts: dict[str, int] = {}

    for item in raw_news:
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        if not headline:
            continue
        cls = (_llm_classify(llm, headline, summary) if llm.available else None) \
            or _rule_classify(headline, summary)
        for t in cls.get("tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
        events.append(EventNews(
            date=str(item.get("date", "")),
            headline=headline,
            summary=summary,
            affected_submarket=cls.get("affected_submarket", "London"),
            impact_direction=cls.get("impact_direction", "neutral"),
            time_horizon=cls.get("time_horizon", "medium"),
            source=item.get("source_name") or item.get("source", ""),
            confidence=float(cls.get("confidence", 0.5)),
            data_quality=item.get("data_quality", "synthetic"),
            source_url=item.get("source_url"),
            synthetic_reason=item.get("synthetic_reason"),
            tags=json.dumps(cls.get("tags", [])),
        ))

    repository.replace_events(events)
    summary_out = {
        "events": len(events),
        "method": "llm" if llm.available else "rule_based",
        "demand_driver_tags": tag_counts,
        "negative_events": sum(1 for e in events if e.impact_direction == "negative"),
    }
    log.info("news_impact: %s", summary_out)
    return summary_out
