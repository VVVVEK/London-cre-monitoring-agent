"""normalize_skill - map raw rows to the canonical schema + integrity checks.

Responsibilities:
  * Map raw metric labels -> canonical metric_name.
  * Validate value/unit, drop malformed rows, de-duplicate.
  * Enforce the integrity policy: a row tagged ``observed`` MUST carry
    source + source_url + retrieved_at, otherwise it is downgraded to
    ``estimated`` (we keep the value but stop calling it a hard fact).
"""
from __future__ import annotations

from typing import Any

from app.data.models import MarketSignal
from app.data import repository
from app.utils.logging import get_logger

log = get_logger(__name__)

METRIC_MAP = {
    "prime_rent": "Prime Rent",
    "grade_a_rent": "Grade A Rent",
    "vacancy": "Vacancy Rate",
    "availability": "Availability Rate",
    "takeup": "Take-up Volume",
    "take_up": "Take-up Volume",
    "net_absorption": "Net Absorption",
    "pipeline_stock": "Pipeline Stock",
    "completions": "Completions",
    "refurb_pipeline": "Refurbishment Pipeline",
    "prelet_ratio": "Pre-let Ratio",
    "policy_rate": "Policy Rate",
    "cpi": "CPI",
    "core_cpi": "Core CPI",
    "unemployment_rate": "Unemployment Rate",
    "office_employment": "Office Employment",
    "gilt_yield": "Gilt Yield",
}


def canonical_metric(raw: str) -> str | None:
    """Public helper (also used in unit tests)."""
    return METRIC_MAP.get(raw.strip().lower())


def _enforce_quality(row: dict[str, Any]) -> tuple[str, str | None]:
    dq = row.get("data_quality", "synthetic")
    reason = row.get("synthetic_reason")
    if dq == "observed":
        if not (row.get("source") and row.get("source_url") and row.get("retrieved_at")):
            # Cannot be called observed without full provenance.
            return "estimated", "incomplete_provenance"
    return dq, reason


def run(raw_signals: list[dict[str, Any]]) -> dict[str, Any]:
    seen: dict[tuple, MarketSignal] = {}
    dropped = 0
    for row in raw_signals:
        metric_name = canonical_metric(str(row.get("metric", "")))
        if metric_name is None:
            dropped += 1
            continue
        try:
            value = float(row["value"])
        except (TypeError, ValueError, KeyError):
            dropped += 1
            continue
        unit = str(row.get("unit", "")).strip() or "n/a"
        dq, reason = _enforce_quality(row)

        key = (row["date"], row["submarket"], metric_name)
        seen[key] = MarketSignal(
            date=str(row["date"]),
            submarket=str(row["submarket"]),
            metric_name=metric_name,
            value=value,
            unit=unit,
            source=str(row.get("source", "unknown")),
            confidence=float(row.get("confidence", 1.0)),
            data_quality=dq,
            source_url=row.get("source_url"),
            source_detail=row.get("source_detail"),
            retrieved_at=str(row.get("retrieved_at", "")),
            synthetic_reason=reason,
        )

    signals = list(seen.values())

    # Build the report from in-memory objects BEFORE persisting: committing the
    # session expires these instances and detaches them.
    quality_breakdown: dict[str, int] = {}
    for s in signals:
        quality_breakdown[s.data_quality] = quality_breakdown.get(s.data_quality, 0) + 1
    metrics = sorted({s.metric_name for s in signals})
    submarkets = sorted({s.submarket for s in signals})

    repository.replace_signals(signals)

    report = {
        "normalized": len(signals),
        "dropped": dropped,
        "quality_breakdown": quality_breakdown,
        "metrics": metrics,
        "submarkets": submarkets,
    }
    log.info("normalize report: %s", report)
    return report
