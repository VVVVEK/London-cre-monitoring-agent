"""recommendation_skill - evidence-based submarket recommendations.

Business logic lives here, not in the UI. Recommendations are rule-based first;
LLM wording can be added later without changing the schema.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.data.models import Evidence
from app.data import repository
from app.skills import analysis_skill
from app.utils.integrity import clean_optional_str

InvestmentGoal = Literal["Risk-Averse", "Return-Seeking", "Balanced"]
RiskLevel = Literal["Low", "Medium", "High"]
DataQuality = Literal["observed", "estimated", "synthetic", "mixed", "unknown"]


class RecommendationRequest(BaseModel):
    """Input contract for recommendation generation."""

    goal: InvestmentGoal = "Balanced"
    risk_level: RiskLevel = "Medium"
    horizon_months: Literal[3, 6, 12] = 6
    preferred_submarkets: list[str] = Field(default_factory=list)
    budget_million_gbp: Optional[float] = None
    allow_synthetic: bool = True


class RecommendedSubmarket(BaseModel):
    """One ranked submarket recommendation."""

    submarket: str
    score: float
    rationale: str
    data_quality: DataQuality
    evidence: list[Evidence] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    """Actionable next step for the business team."""

    action: str
    priority: Literal["Low", "Medium", "High"]
    rationale: str
    data_quality: DataQuality
    evidence: list[Evidence] = Field(default_factory=list)


class RecommendationResult(BaseModel):
    """Output contract required by the Streamlit UI and orchestrator."""

    recommended_submarkets: list[RecommendedSubmarket] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = 0.0
    limitations: str = ""
    data_quality: DataQuality = "unknown"


def _overall_quality(evidence: list[Evidence]) -> DataQuality:
    qualities = {e.evidence_type for e in evidence}
    if not qualities:
        return "unknown"
    if len(qualities) == 1:
        q = next(iter(qualities))
        return q if q in ("observed", "estimated", "synthetic") else "unknown"
    return "mixed"


def _confidence(evidence: list[Evidence], selected_count: int) -> float:
    if not evidence or selected_count == 0:
        return 0.0
    qualities = {e.evidence_type for e in evidence}
    base = 0.72
    if "synthetic" in qualities:
        base = min(base, 0.5)
    if "estimated" in qualities:
        base = min(base, 0.6)
    if "observed" in qualities and len(qualities) == 1:
        base = 0.85
    return round(base, 2)


def _score_for_goal(goal: InvestmentGoal, risk_level: RiskLevel, metrics: dict) -> float:
    stress = metrics.get("stress", 50.0)
    resilience = metrics.get("resilience", 50.0)
    supply = metrics.get("supply_risk", 50.0)
    opportunity = metrics.get("opportunity", 50.0)

    if goal == "Risk-Averse":
        score = resilience * 0.45 + (100 - stress) * 0.35 + (100 - supply) * 0.20
    elif goal == "Return-Seeking":
        score = opportunity * 0.55 + resilience * 0.25 + (100 - supply) * 0.10 + (100 - stress) * 0.10
    else:
        score = opportunity * 0.35 + resilience * 0.30 + (100 - stress) * 0.20 + (100 - supply) * 0.15

    # Lower tolerance penalizes stress/supply more heavily.
    if risk_level == "Low":
        score -= max(stress - 35, 0) * 0.25
        score -= max(supply - 45, 0) * 0.20
    elif risk_level == "High":
        score += opportunity * 0.10
        score -= max(stress - 75, 0) * 0.10
    return max(0.0, min(100.0, score))


def _row_evidence(df, submarket: str, metric: str) -> Evidence | None:
    row = analysis_skill._latest(df, submarket, metric)
    if row is None:
        return None
    return Evidence(
        source=row["source"],
        timestamp=str(row["date"]),
        metric=f"{submarket} {metric}",
        value=float(row["value"]),
        evidence_type=row.get("data_quality", "synthetic"),
        source_url=clean_optional_str(row.get("source_url")),
    )


def _submarket_evidence(df, submarket: str) -> list[Evidence]:
    evidence = []
    for metric in ("Prime Rent", "Vacancy Rate", "Take-up Volume", "Pipeline Stock", "Pre-let Ratio"):
        ev = _row_evidence(df, submarket, metric)
        if ev:
            evidence.append(ev)
    return evidence


def _action_for(request: RecommendationRequest, rec: RecommendedSubmarket) -> RecommendedAction:
    if request.goal == "Risk-Averse":
        action = f"Prioritise defensive monitoring and prime-quality opportunities in {rec.submarket}."
        priority: Literal["Low", "Medium", "High"] = "High" if rec.score >= 70 else "Medium"
    elif request.goal == "Return-Seeking":
        action = f"Evaluate upside case and leasing catalysts in {rec.submarket}; stress-test downside first."
        priority = "High" if rec.score >= 65 else "Medium"
    else:
        action = f"Shortlist {rec.submarket} for balanced risk-return review in the next IC discussion."
        priority = "High" if rec.score >= 70 else "Medium"
    return RecommendedAction(
        action=action,
        priority=priority,
        rationale=rec.rationale,
        data_quality=rec.data_quality,
        evidence=rec.evidence[:3],
    )


def generate_recommendation(request: RecommendationRequest) -> RecommendationResult:
    """Generate a rule-based, evidence-backed submarket recommendation."""
    df = repository.signals_dataframe()
    if df.empty:
        return RecommendationResult(
            limitations="No market signals available. Run the pipeline before requesting recommendations.",
            data_quality="unknown",
        )

    analysis = analysis_skill.run()
    candidates = request.preferred_submarkets or analysis.get("submarkets", [])
    ranked: list[RecommendedSubmarket] = []
    excluded_for_quality: list[str] = []

    for submarket in candidates:
        metrics = analysis.get("by_submarket", {}).get(submarket)
        if not metrics:
            continue
        evidence = _submarket_evidence(df, submarket)
        quality = _overall_quality(evidence)
        if not request.allow_synthetic and quality in ("synthetic", "mixed"):
            excluded_for_quality.append(submarket)
            continue
        score = _score_for_goal(request.goal, request.risk_level, metrics)
        rationale = (
            f"{request.goal} / {request.risk_level} risk profile: "
            f"stress={metrics.get('stress', 0):.0f}, resilience={metrics.get('resilience', 0):.0f}, "
            f"supply_risk={metrics.get('supply_risk', 0):.0f}, opportunity={metrics.get('opportunity', 0):.0f}."
        )
        ranked.append(
            RecommendedSubmarket(
                submarket=submarket,
                score=round(score, 1),
                rationale=rationale,
                data_quality=quality,
                evidence=evidence,
            )
        )

    ranked.sort(key=lambda r: r.score, reverse=True)
    selected = ranked[:3]
    all_evidence = [ev for rec in selected for ev in rec.evidence]
    quality = _overall_quality(all_evidence)
    actions = [_action_for(request, rec) for rec in selected]

    limitations = []
    if any(ev.evidence_type == "synthetic" for ev in all_evidence):
        limitations.append(
            "Synthetic data is used only for PoC validation and is not a real market fact."
        )
    if excluded_for_quality:
        limitations.append(
            "Excluded submarkets because allow_synthetic=False: "
            + ", ".join(excluded_for_quality)
        )
    if request.budget_million_gbp is not None:
        limitations.append(
            "Budget is captured for workflow context only; this PoC does not size transactions."
        )

    return RecommendationResult(
        recommended_submarkets=selected,
        recommended_actions=actions,
        evidence=all_evidence[:12],
        confidence=_confidence(all_evidence, len(selected)),
        limitations=" ".join(limitations),
        data_quality=quality,
    )
