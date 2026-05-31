"""analysis_skill - fundamentals, momentum, spreads, and 4 composite scores.

All scores are rule-based and explainable. Factor weights live in
``SCORE_WEIGHTS`` (configurable). Every score carries its factor contributions,
a human explanation, and quality-tagged evidence so the integrity policy holds
end to end.
"""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd

from app.data.models import CompositeScore, Evidence
from app.data import repository
from app.utils.integrity import clean_optional_str
from app.utils.logging import get_logger

log = get_logger(__name__)

PROPERTY_SUBMARKETS = ["City", "West End", "Canary Wharf", "Midtown"]

# Configurable factor weights (override here or load from config if desired).
SCORE_WEIGHTS = {
    "market_stress": {"vacancy_level": 0.35, "vacancy_momentum": 0.30,
                      "rent_momentum": 0.20, "absorption": 0.15},
    "rental_resilience": {"rent_growth": 0.40, "low_vacancy": 0.35, "takeup": 0.25},
    "supply_risk": {"pipeline_intensity": 0.35, "refurb_intensity": 0.15,
                    "low_prelet": 0.25, "completions": 0.25},
    "opportunity": {"resilience": 0.40, "low_supply_risk": 0.30, "low_stress": 0.30},
}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _level(score: float) -> str:
    return "High" if score >= 66 else "Medium" if score >= 33 else "Low"


def _series(df: pd.DataFrame, submarket: str, metric: str) -> pd.DataFrame:
    s = df[(df.submarket == submarket) & (df.metric_name == metric)]
    return s.sort_values("date")


def _latest(df: pd.DataFrame, submarket: str, metric: str) -> Optional[pd.Series]:
    s = _series(df, submarket, metric)
    return None if s.empty else s.iloc[-1]


def _momentum(df: pd.DataFrame, submarket: str, metric: str, periods: int = 3):
    """Return (absolute_change, pct_change) over the last `periods` steps."""
    s = _series(df, submarket, metric)
    if len(s) < 2:
        return None, None
    recent = s.iloc[-1]["value"]
    base_idx = max(0, len(s) - 1 - periods)
    base = s.iloc[base_idx]["value"]
    abs_chg = recent - base
    pct = (abs_chg / base * 100) if base else 0.0
    return abs_chg, pct


def _ev(row: Optional[pd.Series], metric_label: str) -> Optional[Evidence]:
    if row is None:
        return None
    return Evidence(
        source=row["source"],
        timestamp=str(row["date"]),
        metric=metric_label,
        value=float(row["value"]),
        evidence_type=row.get("data_quality", "synthetic"),
        source_url=clean_optional_str(row.get("source_url")),
    )


# --------------------------------------------------------------------------- #
# Composite scores
# --------------------------------------------------------------------------- #
def _market_stress(df, sm) -> CompositeScore:
    w = SCORE_WEIGHTS["market_stress"]
    vac = _latest(df, sm, "Vacancy Rate")
    vac_abs, _ = _momentum(df, sm, "Vacancy Rate")
    _, rent_pct = _momentum(df, sm, "Prime Rent")
    absn = _latest(df, sm, "Net Absorption")

    f_vac = _clamp((vac["value"] - 4) / (16 - 4) * 100) if vac is not None else 0
    f_mom = _clamp((vac_abs or 0) / 6 * 100)
    f_rent = _clamp(-(rent_pct or 0) / 10 * 100)
    f_abs = _clamp(-(absn["value"] if absn is not None else 0) / 300 * 100)

    factors = {"vacancy_level": f_vac, "vacancy_momentum": f_mom,
               "rent_momentum": f_rent, "absorption": f_abs}
    score = sum(factors[k] * w[k] for k in w)
    ev = [e for e in (_ev(vac, "Vacancy Rate"), _ev(absn, "Net Absorption")) if e]
    if vac is not None:
        abs_txt = f", net absorption={absn['value']:.0f}k sqft" if absn is not None else ""
        expl = (f"Stress {score:.0f}/100: vacancy={vac['value']:.1f}% "
                f"({(vac_abs or 0):+.1f}pp/3q), prime-rent momentum={(rent_pct or 0):+.1f}%{abs_txt}.")
    else:
        expl = f"Stress {score:.0f}/100 (partial data)."
    return CompositeScore(name="Market Stress Score", submarket=sm, score=round(score, 1),
                          level=_level(score), factors=factors, explanation=expl, evidence=ev)


def _rental_resilience(df, sm) -> CompositeScore:
    w = SCORE_WEIGHTS["rental_resilience"]
    _, rent_pct = _momentum(df, sm, "Prime Rent")
    vac = _latest(df, sm, "Vacancy Rate")
    _, takeup_pct = _momentum(df, sm, "Take-up Volume")

    f_growth = _clamp(((rent_pct or 0) + 10) / 20 * 100)
    f_vac = _clamp((16 - (vac["value"] if vac is not None else 16)) / (16 - 3) * 100)
    f_takeup = _clamp(((takeup_pct or 0) + 30) / 60 * 100)

    factors = {"rent_growth": f_growth, "low_vacancy": f_vac, "takeup": f_takeup}
    score = sum(factors[k] * w[k] for k in w)
    ev = [e for e in (_ev(_latest(df, sm, "Prime Rent"), "Prime Rent"),
                      _ev(vac, "Vacancy Rate")) if e]
    expl = (f"Resilience {score:.0f}/100: prime-rent {(rent_pct or 0):+.1f}%/3q, "
            f"vacancy={vac['value']:.1f}%, take-up {(takeup_pct or 0):+.1f}%/3q."
            if vac is not None else f"Resilience {score:.0f}/100 (partial data).")
    return CompositeScore(name="Rental Resilience Score", submarket=sm, score=round(score, 1),
                          level=_level(score), factors=factors, explanation=expl, evidence=ev)


def _supply_risk(df, sm) -> CompositeScore:
    w = SCORE_WEIGHTS["supply_risk"]
    pipe = _latest(df, sm, "Pipeline Stock")
    comp = _latest(df, sm, "Completions")
    prelet = _latest(df, sm, "Pre-let Ratio")
    refurb = _latest(df, sm, "Refurbishment Pipeline")
    takeup = _latest(df, sm, "Take-up Volume")
    annual_takeup = (takeup["value"] * 4) if takeup is not None and takeup["value"] else 1

    ratio = (pipe["value"] / annual_takeup) if pipe is not None else 0
    refurb_ratio = (refurb["value"] / annual_takeup) if refurb is not None else 0
    f_pipe = _clamp(ratio / 3 * 100)
    # Refurbished stock re-enters the market and competes for the same occupiers;
    # scaled so ~1.5x annual take-up of refurb = full-scale (100) on this factor.
    f_refurb = _clamp(refurb_ratio / 1.5 * 100)
    f_prelet = _clamp(100 - (prelet["value"] if prelet is not None else 50))
    f_comp = _clamp((comp["value"] / annual_takeup) / 1.0 * 100) if comp is not None else 0

    factors = {"pipeline_intensity": f_pipe, "refurb_intensity": f_refurb,
               "low_prelet": f_prelet, "completions": f_comp}
    score = sum(factors[k] * w[k] for k in w)
    ev = [e for e in (_ev(pipe, "Pipeline Stock"), _ev(refurb, "Refurbishment Pipeline"),
                      _ev(prelet, "Pre-let Ratio")) if e]
    expl = (f"Supply risk {score:.0f}/100: pipeline/annual take-up={ratio:.1f}x, "
            f"refurb/annual take-up={refurb_ratio:.1f}x, pre-let={prelet['value']:.0f}%."
            if pipe is not None and prelet is not None else f"Supply risk {score:.0f}/100 (partial data).")
    return CompositeScore(name="Supply Risk Score", submarket=sm, score=round(score, 1),
                          level=_level(score), factors=factors, explanation=expl, evidence=ev)


def _opportunity(df, sm, resilience: float, supply_risk: float, stress: float,
                 news_nudge: float = 0.0) -> CompositeScore:
    w = SCORE_WEIGHTS["opportunity"]
    factors = {"resilience": resilience, "low_supply_risk": 100 - supply_risk,
               "low_stress": 100 - stress}
    base = sum(factors[k] * w[k] for k in w)
    score = _clamp(base + news_nudge)
    nudge_txt = f", news sentiment nudge {news_nudge:+.0f}" if news_nudge else ""
    expl = (f"Opportunity {score:.0f}/100 = blend of resilience ({resilience:.0f}), "
            f"low supply risk ({100 - supply_risk:.0f}), low stress ({100 - stress:.0f}){nudge_txt}.")
    return CompositeScore(name="Submarket Opportunity Score", submarket=sm, score=round(score, 1),
                          level=_level(score), factors=factors, explanation=expl, evidence=[])


def _parse_tags(raw: str) -> list[str]:
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []


def _demand_drivers_from_events(events) -> dict:
    """Aggregate news tags & sentiment by submarket (observed news weighted higher)."""
    global_tags: dict[str, int] = {}
    by_sm: dict[str, dict] = {sm: {"positive": 0, "negative": 0, "neutral": 0,
                                    "tags": {}, "headlines": [], "has_observed": False}
                              for sm in PROPERTY_SUBMARKETS}
    by_sm["London"] = {"positive": 0, "negative": 0, "neutral": 0,
                       "tags": {}, "headlines": [], "has_observed": False}

    for e in events:
        sm = e.affected_submarket if e.affected_submarket in by_sm else "London"
        bucket = by_sm.setdefault(sm, {"positive": 0, "negative": 0, "neutral": 0,
                                     "tags": {}, "headlines": [], "has_observed": False})
        weight = 2 if e.data_quality == "observed" else 1
        if e.data_quality == "observed":
            bucket["has_observed"] = True
        bucket[e.impact_direction] = bucket.get(e.impact_direction, 0) + weight
        for tag in _parse_tags(e.tags):
            bucket["tags"][tag] = bucket["tags"].get(tag, 0) + 1
            global_tags[tag] = global_tags.get(tag, 0) + 1
        if len(bucket["headlines"]) < 3:
            bucket["headlines"].append({
                "headline": e.headline,
                "direction": e.impact_direction,
                "tags": _parse_tags(e.tags),
                "source": e.source,
                "date": e.date,
                "evidence_type": e.data_quality,
                "source_url": e.source_url,
            })

    highlights = []
    for tag, count in sorted(global_tags.items(), key=lambda x: -x[1])[:5]:
        highlights.append({"tag": tag, "count": count})

    return {"by_submarket": by_sm, "global_tags": global_tags, "highlights": highlights}


def _news_sentiment_nudge(sm: str, drivers: dict) -> float:
    """Small score adjustment from observed news only (+/- up to 8 pts)."""
    bucket = drivers.get("by_submarket", {}).get(sm, {})
    if not bucket.get("has_observed"):
        return 0.0
    pos = bucket.get("positive", 0)
    neg = bucket.get("negative", 0)
    return _clamp((pos - neg) * 4, -8, 8)


def _news_stress_nudge(sm: str, drivers: dict) -> float:
    bucket = drivers.get("by_submarket", {}).get(sm, {})
    if not bucket.get("has_observed"):
        return 0.0
    neg = bucket.get("negative", 0)
    return _clamp(neg * 3, 0, 10)


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def run() -> dict:
    df = repository.signals_dataframe()
    if df.empty:
        log.warning("no signals available for analysis")
        return {"scores": [], "spreads": {}, "momentum_ranking": [], "submarkets": []}

    submarkets = [s for s in PROPERTY_SUBMARKETS if s in set(df.submarket)]
    events = repository.list_events()
    demand_drivers = _demand_drivers_from_events(events)
    scores: list[CompositeScore] = []
    by_sm: dict[str, dict] = {}

    for sm in submarkets:
        stress = _market_stress(df, sm)
        # Feed observed news sentiment back into stress/opportunity scores.
        stress_nudge = _news_stress_nudge(sm, demand_drivers)
        if stress_nudge:
            stress.score = round(_clamp(stress.score + stress_nudge), 1)
            stress.level = _level(stress.score)
            stress.explanation += f" (+{stress_nudge:.0f} from observed negative news)."
        resil = _rental_resilience(df, sm)
        supply = _supply_risk(df, sm)
        opp_nudge = _news_sentiment_nudge(sm, demand_drivers)
        opp = _opportunity(df, sm, resil.score, supply.score, stress.score, news_nudge=opp_nudge)
        scores.extend([stress, resil, supply, opp])
        by_sm[sm] = {"stress": stress.score, "resilience": resil.score,
                     "supply_risk": supply.score, "opportunity": opp.score,
                     "news_opportunity_nudge": opp_nudge}

    # Submarket spreads (rent & vacancy) vs cross-submarket mean.
    rent_latest = {sm: _latest(df, sm, "Prime Rent") for sm in submarkets}
    vac_latest = {sm: _latest(df, sm, "Vacancy Rate") for sm in submarkets}
    avail_latest = {sm: _latest(df, sm, "Availability Rate") for sm in submarkets}
    rent_vals = {sm: r["value"] for sm, r in rent_latest.items() if r is not None}
    vac_vals = {sm: v["value"] for sm, v in vac_latest.items() if v is not None}
    rent_mean = sum(rent_vals.values()) / len(rent_vals) if rent_vals else 0
    vac_mean = sum(vac_vals.values()) / len(vac_vals) if vac_vals else 0

    # Derived: availability-vacancy spread = latent/shadow supply not yet vacated.
    avail_vac_spread = {}
    for sm in submarkets:
        av, vc = avail_latest.get(sm), vac_latest.get(sm)
        if av is not None and vc is not None:
            avail_vac_spread[sm] = round(av["value"] - vc["value"], 1)
            by_sm.setdefault(sm, {})["availability_vacancy_spread"] = avail_vac_spread[sm]

    spreads = {
        "rent_spread_vs_mean": {sm: round(v - rent_mean, 1) for sm, v in rent_vals.items()},
        "vacancy_spread_vs_mean": {sm: round(v - vac_mean, 1) for sm, v in vac_vals.items()},
        "availability_vacancy_spread": avail_vac_spread,
    }

    # Momentum ranking (3-period prime-rent % change).
    momentum = []
    for sm in submarkets:
        _, pct = _momentum(df, sm, "Prime Rent")
        momentum.append({"submarket": sm, "prime_rent_3q_pct": round(pct or 0, 1)})
    momentum.sort(key=lambda d: d["prime_rent_3q_pct"], reverse=True)

    # Flight-to-quality proxy: Grade A rent growth leadership.
    fq = []
    for sm in submarkets:
        _, pct = _momentum(df, sm, "Grade A Rent")
        fq.append({"submarket": sm, "grade_a_3q_pct": round(pct or 0, 1)})
    fq.sort(key=lambda d: d["grade_a_3q_pct"], reverse=True)

    result = {
        "scores": [s.model_dump() for s in scores],
        "score_objects": scores,
        "by_submarket": by_sm,
        "spreads": spreads,
        "momentum_ranking": momentum,
        "flight_to_quality": fq,
        "demand_drivers": demand_drivers,
        "submarkets": submarkets,
        "latest_period": str(df["date"].max()),
    }
    log.info("analysis done for %d submarkets, %d scores", len(submarkets), len(scores))
    return result
