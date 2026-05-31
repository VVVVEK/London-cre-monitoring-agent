"""Orchestrator - wires the 7 skills into runnable flows.

Flows:
  * run_pipeline       : ingest -> normalize -> analysis -> news_impact -> alert
  * run_weekly_briefing: full pipeline + report
  * ask                : answer a single business question

Resilience: each stage is wrapped so a single data-source failure still lets the
run finish (status="partial") and a report can still be produced.
"""
from __future__ import annotations

from typing import Optional

from app.data import repository
from app.skills import (
    alert_skill,
    analysis_skill,
    ingest_skill,
    news_impact_skill,
    normalize_skill,
    qa_skill,
    recommendation_skill,
    report_skill,
)
from app.utils.logging import get_logger

log = get_logger(__name__)


def run_pipeline() -> dict:
    repository.init_db()
    run_id = repository.start_run("pipeline")
    summary: dict = {"run_id": run_id, "stages": {}, "errors": []}
    provenance = {}
    try:
        ingested = ingest_skill.run()
        provenance = ingested["provenance"]
        summary["stages"]["ingest"] = provenance

        summary["stages"]["normalize"] = normalize_skill.run(ingested["signals"])
        summary["stages"]["analysis"] = {"submarkets": analysis_skill.run()["submarkets"]}

        try:
            summary["stages"]["news_impact"] = news_impact_skill.run(ingested["news"])
        except Exception as exc:  # news must not break the pipeline
            log.warning("news_impact failed (continuing): %s", exc)
            summary["errors"].append(f"news_impact: {exc}")

        summary["stages"]["alert"] = alert_skill.run()
        status = "partial" if summary["errors"] else "success"
        repository.finish_run(run_id, status)
        summary["status"] = status
    except Exception as exc:
        log.error("pipeline failed: %s", exc)
        repository.finish_run(run_id, "failed", str(exc))
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
    summary["provenance"] = provenance
    return summary


def run_weekly_briefing() -> dict:
    pipeline = run_pipeline()
    run_id = repository.start_run("weekly_briefing")
    try:
        report = report_skill.run(provenance=pipeline.get("provenance"))
        repository.finish_run(run_id, "success")
        return {"pipeline": pipeline, "report": report}
    except Exception as exc:
        log.error("report failed: %s", exc)
        repository.finish_run(run_id, "failed", str(exc))
        return {"pipeline": pipeline, "report": None, "error": str(exc)}


def ask(question: str, ensure_data: bool = True) -> dict:
    repository.init_db()
    if ensure_data and repository.signals_dataframe().empty:
        run_pipeline()
    run_id = repository.start_run("ask")
    try:
        result = qa_skill.run(question)
        repository.finish_run(run_id, "success")
        return result.model_dump()
    except Exception as exc:
        repository.finish_run(run_id, "failed", str(exc))
        raise


def recommend(
    goal: recommendation_skill.InvestmentGoal = "Balanced",
    risk_level: recommendation_skill.RiskLevel = "Medium",
    horizon_months: int = 6,
    preferred_submarkets: Optional[list[str]] = None,
    budget_million_gbp: Optional[float] = None,
    allow_synthetic: bool = True,
    ensure_data: bool = True,
) -> dict:
    """Orchestrator-level recommendation entrypoint for CLI/UI callers."""
    repository.init_db()
    if ensure_data and repository.signals_dataframe().empty:
        run_pipeline()
    request = recommendation_skill.RecommendationRequest(
        goal=goal,
        risk_level=risk_level,
        horizon_months=horizon_months,
        preferred_submarkets=preferred_submarkets or [],
        budget_million_gbp=budget_million_gbp,
        allow_synthetic=allow_synthetic,
    )
    run_id = repository.start_run("recommendation")
    try:
        result = recommendation_skill.generate_recommendation(request)
        repository.finish_run(run_id, "success")
        return result.model_dump()
    except Exception as exc:
        repository.finish_run(run_id, "failed", str(exc))
        raise
