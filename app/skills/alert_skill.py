"""alert_skill - rule-based early-warning rules with severity + evidence.

Rules: vacancy_deterioration, demand_weakening, supply_squeeze,
availability_overhang, macro_shock, data_staleness.

Integrity rule (binding): a `High` severity alert must be backed by `observed`
evidence. If an alert is triggered purely by `synthetic` data it is downgraded
one level and tagged `[SYNTHETIC-TEST]`.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.data.models import AlertResult, Evidence
from app.data import repository
from app.skills.analysis_skill import _latest, _momentum, _series
from app.utils.config import get_settings
from app.utils.integrity import clean_optional_str
from app.utils.logging import get_logger

log = get_logger(__name__)

PROPERTY_SUBMARKETS = ["City", "West End", "Canary Wharf", "Midtown"]

ALERT_THRESHOLDS = {
    "vacancy_cum_pp": 2.0,        # cumulative vacancy rise over 3q to trigger
    "demand_drop_ratio": 0.70,    # recent take-up < 70% of history => weak
    "supply_ratio": 2.0,          # pipeline / annual take-up multiple
    "rate_rise_pp": 0.5,          # policy-rate cumulative rise to flag macro
    "availability_overhang_pp": 2.0,  # availability-vacancy spread => shadow supply
}

_SEV_ORDER = ["Low", "Medium", "High"]


def _downgrade(sev: str) -> str:
    i = _SEV_ORDER.index(sev)
    return _SEV_ORDER[max(0, i - 1)]


def _ev(row, label: str) -> Evidence:
    return Evidence(source=row["source"], timestamp=str(row["date"]), metric=label,
                    value=float(row["value"]),                     evidence_type=row.get("data_quality", "synthetic"),
                    source_url=clean_optional_str(row.get("source_url")))


def _finalize(severity: str, reason: str, evidence: list[Evidence]) -> tuple[str, str]:
    """Apply the observed-vs-synthetic integrity rule."""
    has_observed = any(e.evidence_type == "observed" for e in evidence)
    if not has_observed:
        severity = _downgrade(severity)
        reason = f"[SYNTHETIC-TEST] {reason}"
    return severity, reason


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
def _rule_vacancy(df) -> list[AlertResult]:
    out = []
    for sm in PROPERTY_SUBMARKETS:
        s = _series(df, sm, "Vacancy Rate")
        if len(s) < 3:
            continue
        v = s["value"].tolist()
        rising = v[-1] > v[-2] > v[-3]
        cum = v[-1] - v[-3]
        if rising and cum >= ALERT_THRESHOLDS["vacancy_cum_pp"]:
            sev = "High" if cum >= 5 else "Medium" if cum >= 3 else "Low"
            reason = (f"{sm} vacancy rose for 2 consecutive periods, "
                      f"+{cum:.1f}pp over 3 quarters (to {v[-1]:.1f}%).")
            ev = [_ev(s.iloc[-3], "Vacancy Rate"), _ev(s.iloc[-1], "Vacancy Rate")]
            sev, reason = _finalize(sev, reason, ev)
            out.append(AlertResult(severity=sev, alert_type="vacancy_deterioration",
                                   trigger_reason=reason, related_submarket=sm, evidence=ev,
                                   suggested_action=(f"Review {sm} exposure; stress-test rent "
                                                     "assumptions and re-leasing timelines.")))
    return out


def _rule_demand(df) -> list[AlertResult]:
    out = []
    for sm in PROPERTY_SUBMARKETS:
        s = _series(df, sm, "Take-up Volume")
        if len(s) < 4:
            continue
        vals = s["value"].tolist()
        recent = sum(vals[-3:]) / 3
        hist = sum(vals[:-3]) / max(1, len(vals) - 3)
        if hist and recent < hist * ALERT_THRESHOLDS["demand_drop_ratio"]:
            ratio = recent / hist
            sev = "High" if ratio < 0.5 else "Medium" if ratio < 0.7 else "Low"
            reason = (f"{sm} recent take-up ({recent:.0f}k) is {ratio*100:.0f}% of its "
                      f"historical average ({hist:.0f}k) - demand weakening.")
            ev = [_ev(s.iloc[-1], "Take-up Volume"), _ev(s.iloc[0], "Take-up Volume")]
            sev, reason = _finalize(sev, reason, ev)
            out.append(AlertResult(severity=sev, alert_type="demand_weakening",
                                   trigger_reason=reason, related_submarket=sm, evidence=ev,
                                   suggested_action=(f"Reassess {sm} leasing pipeline and "
                                                     "incentive packages; watch occupier sentiment.")))
    return out


def _rule_supply(df) -> list[AlertResult]:
    out = []
    for sm in PROPERTY_SUBMARKETS:
        pipe = _latest(df, sm, "Pipeline Stock")
        takeup = _latest(df, sm, "Take-up Volume")
        prelet = _latest(df, sm, "Pre-let Ratio")
        if pipe is None or takeup is None or not takeup["value"]:
            continue
        ratio = pipe["value"] / (takeup["value"] * 4)
        if ratio >= ALERT_THRESHOLDS["supply_ratio"]:
            sev = "High" if ratio >= 4 else "Medium" if ratio >= 3 else "Low"
            pl = f" with only {prelet['value']:.0f}% pre-let" if prelet is not None else ""
            reason = (f"{sm} forward pipeline is {ratio:.1f}x annualised take-up{pl} - "
                      "potential supply squeeze on absorption.")
            ev = [_ev(pipe, "Pipeline Stock"), _ev(takeup, "Take-up Volume")]
            if prelet is not None:
                ev.append(_ev(prelet, "Pre-let Ratio"))
            sev, reason = _finalize(sev, reason, ev)
            out.append(AlertResult(severity=sev, alert_type="supply_squeeze",
                                   trigger_reason=reason, related_submarket=sm, evidence=ev,
                                   suggested_action=(f"Monitor {sm} completions vs pre-lets; "
                                                     "avoid speculative exposure until absorption improves.")))
    return out


def _rule_availability_overhang(df) -> list[AlertResult]:
    """Secondary supply risk: availability materially above vacancy signals
    shadow / latent space (sublets, lease breaks, marketed-but-occupied) that
    will compete for occupiers before it shows up in headline vacancy."""
    out = []
    for sm in PROPERTY_SUBMARKETS:
        avail = _latest(df, sm, "Availability Rate")
        vac = _latest(df, sm, "Vacancy Rate")
        if avail is None or vac is None:
            continue
        spread = avail["value"] - vac["value"]
        if spread < ALERT_THRESHOLDS["availability_overhang_pp"]:
            continue
        sev = "High" if spread >= 4 else "Medium" if spread >= 3 else "Low"
        reason = (f"{sm} availability ({avail['value']:.1f}%) exceeds vacancy "
                  f"({vac['value']:.1f}%) by {spread:.1f}pp - shadow/latent supply "
                  "overhang likely to pressure rents before headline vacancy reacts.")
        ev = [_ev(avail, "Availability Rate"), _ev(vac, "Vacancy Rate")]
        sev, reason = _finalize(sev, reason, ev)
        out.append(AlertResult(severity=sev, alert_type="availability_overhang",
                               trigger_reason=reason, related_submarket=sm, evidence=ev,
                               suggested_action=(f"Investigate {sm} sublet/grey space and lease-event "
                                                 "exposure; treat as forward vacancy in underwriting.")))
    return out


def _rule_macro(df) -> list[AlertResult]:
    rate = _series(df, "London", "Policy Rate")
    if len(rate) < 3:
        return []
    rates = rate["value"].tolist()
    rate_rise = rates[-1] - rates[-3]
    if rate_rise < ALERT_THRESHOLDS["rate_rise_pp"]:
        return []
    # Find the weakest leasing submarket (most negative 3q take-up momentum).
    weakest, worst_pct = None, 0.0
    for sm in PROPERTY_SUBMARKETS:
        _, pct = _momentum(df, sm, "Take-up Volume")
        if pct is not None and pct < worst_pct:
            weakest, worst_pct = sm, pct
    if weakest is None or worst_pct > -15:
        return []
    sev = "High" if (rate_rise >= 0.75 and worst_pct <= -30) else "Medium"
    reason = (f"Macro shock: UK policy rate +{rate_rise:.2f}pp over 3 periods "
              f"(to {rates[-1]:.2f}%) coinciding with {weakest} take-up {worst_pct:.0f}%/3q.")
    ev = [_ev(rate.iloc[-1], "Policy Rate"), _ev(rate.iloc[-3], "Policy Rate")]
    tk = _series(df, weakest, "Take-up Volume")
    if not tk.empty:
        ev.append(_ev(tk.iloc[-1], "Take-up Volume"))
    sev, reason = _finalize(sev, reason, ev)
    return [AlertResult(severity=sev, alert_type="macro_shock", trigger_reason=reason,
                        related_submarket=weakest, evidence=ev,
                        suggested_action=("Reassess financing costs and cap-rate assumptions; "
                                          "prioritise resilient prime assets over secondary stock."))]


def _rule_staleness(df) -> list[AlertResult]:
    """Warn when a data source's latest period is older than the configured threshold."""
    settings = get_settings()
    today = datetime.utcnow().date()
    out: list[AlertResult] = []

    for source, group in df.groupby("source"):
        quality = group["data_quality"].iloc[0]
        latest_date_str = group["date"].max()
        try:
            latest_date = datetime.strptime(str(latest_date_str)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        age_days = (today - latest_date).days
        is_macro = source == "FRED" or "macro" in str(source).lower()
        threshold = settings.staleness_days_macro if is_macro else settings.staleness_days_cre
        if age_days <= threshold:
            continue
        sev = "Medium" if age_days > threshold * 1.5 else "Low"
        reason = (f"Data staleness: `{source}` latest period {latest_date_str} "
                  f"is {age_days} days old (threshold {threshold}d).")
        ev = [Evidence(source=str(source), timestamp=str(latest_date_str),
                       metric="data_freshness", value=float(age_days),
                       evidence_type=str(quality),
                       note=f"threshold={threshold}d")]
        sev, reason = _finalize(sev, reason, ev)
        out.append(AlertResult(
            severity=sev, alert_type="data_staleness", trigger_reason=reason,
            related_submarket="London", evidence=ev,
            suggested_action=("Refresh this source or switch to a live feed; "
                              "stale inputs reduce confidence in conclusions.")))
    return out


def run() -> dict:
    df = repository.signals_dataframe()
    if df.empty:
        repository.save_alerts([])
        return {"alerts": 0, "by_severity": {}, "results": [], "lifecycle": {}}

    results: list[AlertResult] = []
    results += _rule_vacancy(df)
    results += _rule_demand(df)
    results += _rule_supply(df)
    results += _rule_availability_overhang(df)
    results += _rule_macro(df)
    results += _rule_staleness(df)

    # Rank High > Medium > Low.
    results.sort(key=lambda r: _SEV_ORDER.index(r.severity), reverse=True)
    lifecycle = repository.save_alerts(results)

    by_sev: dict[str, int] = {}
    for r in results:
        by_sev[r.severity] = by_sev.get(r.severity, 0) + 1
    log.info("alerts: %d triggered %s lifecycle=%s", len(results), by_sev, lifecycle)
    return {"alerts": len(results), "by_severity": by_sev,
            "results": [r.model_dump() for r in results], "result_objects": results,
            "lifecycle": lifecycle}
