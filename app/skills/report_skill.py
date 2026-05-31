"""report_skill - assemble the weekly Markdown briefing.

Sections: Executive Summary, Submarket Deep Dive, Risk & Opportunity, Alerts,
Source Freshness, Next-week Watchlist, plus the integrity sections
Data Provenance & Quality and (conditionally) Synthetic Data Disclosure.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from app import __version__
from app.data import repository
from app.skills import analysis_skill
from app.utils.config import REPORTS_DIR
from app.utils.logging import get_logger

log = get_logger(__name__)


def _quality_breakdown(df) -> dict[str, int]:
    out: dict[str, int] = {}
    if df.empty:
        return out
    for q, n in df.groupby("data_quality").size().items():
        out[str(q)] = int(n)
    return out


def _fmt_evidence(ev_list) -> str:
    return "; ".join(e.render() for e in ev_list) if ev_list else "n/a"


def run(provenance: Optional[dict] = None, out_dir: Optional[Path] = None) -> dict:
    df = repository.signals_dataframe()
    analysis = analysis_skill.run()
    alerts = repository.list_alerts()
    events = repository.list_events()

    now = datetime.now()
    version = f"{__version__}+{now.strftime('%Y%m%d-%H%M')}"
    latest_period = analysis.get("latest_period", "n/a")
    qb = _quality_breakdown(df)
    has_synth = qb.get("synthetic", 0) > 0

    L: list[str] = []
    L.append(f"# London Office CRE - Weekly Market Briefing")
    L.append(f"_Generated: {now.strftime('%Y-%m-%d %H:%M')} | Version: {version} | "
             f"Latest data period: {latest_period}_\n")

    # ---- Executive Summary ----
    L.append("## 1. Executive Summary")
    by_sm = analysis.get("by_submarket", {})
    if by_sm:
        worst = max(by_sm, key=lambda s: by_sm[s]["stress"])
        best = max(by_sm, key=lambda s: by_sm[s]["opportunity"])
        high_alerts = sum(1 for a in alerts if a.severity == "High")
        L.append(f"- Highest market stress: **{worst}** "
                 f"(stress {by_sm[worst]['stress']:.0f}/100).")
        L.append(f"- Most attractive submarket: **{best}** "
                 f"(opportunity {by_sm[best]['opportunity']:.0f}/100).")
        L.append(f"- Active alerts: **{len(alerts)}** "
                 f"({high_alerts} High). See section 4.")
        mom = analysis.get("momentum_ranking", [])
        if mom:
            L.append(f"- Rent momentum leader (3q): **{mom[0]['submarket']}** "
                     f"({mom[0]['prime_rent_3q_pct']:+.1f}%).")
    else:
        L.append("- No analytical data available.")
    L.append("")

    # ---- Submarket Deep Dive ----
    L.append("## 2. Submarket Deep Dive")
    L.append("| Submarket | Prime Rent | Vacancy | Availability | Avail-Vac Spread | Take-up | Stress | Resilience | Supply Risk | Opportunity |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for sm in analysis.get("submarkets", []):
        pr = analysis_skill._latest(df, sm, "Prime Rent")
        vc = analysis_skill._latest(df, sm, "Vacancy Rate")
        av = analysis_skill._latest(df, sm, "Availability Rate")
        tk = analysis_skill._latest(df, sm, "Take-up Volume")
        sc = by_sm.get(sm, {})
        av_txt = f"{av['value']:.1f}%" if av is not None else "n/a"
        spread = sc.get("availability_vacancy_spread")
        spread_txt = f"{spread:+.1f}pp" if spread is not None else "n/a"
        L.append(f"| {sm} | {pr['value']:.0f} £/sqft | {vc['value']:.1f}% | {av_txt} | {spread_txt} | "
                 f"{tk['value']:.0f}k | {sc.get('stress',0):.0f} | {sc.get('resilience',0):.0f} | "
                 f"{sc.get('supply_risk',0):.0f} | {sc.get('opportunity',0):.0f} |")
    L.append("")
    sp = analysis.get("spreads", {})
    if sp:
        L.append(f"- Rent spread vs mean: {sp.get('rent_spread_vs_mean', {})}")
        L.append(f"- Vacancy spread vs mean: {sp.get('vacancy_spread_vs_mean', {})}")
        avs = sp.get("availability_vacancy_spread", {})
        if avs:
            L.append(f"- Availability-vacancy spread (shadow supply): {avs}")
        fq = analysis.get("flight_to_quality", [])
        if fq:
            L.append(f"- Flight-to-quality proxy (Grade A 3q growth leader): "
                     f"**{fq[0]['submarket']}** ({fq[0]['grade_a_3q_pct']:+.1f}%)")
    L.append("")

    # ---- Occupier Demand Drivers (news-fed) ----
    L.append("## 3. Occupier Demand Drivers (News)")
    drivers = analysis.get("demand_drivers", {})
    highlights = drivers.get("highlights", [])
    if highlights:
        L.append("**Global demand-driver tags (from classified news):**")
        for h in highlights:
            L.append(f"- `{h['tag']}`: {h['count']} mention(s)")
        L.append("")
        for sm in analysis.get("submarkets", []):
            smd = drivers.get("by_submarket", {}).get(sm, {})
            if not smd.get("tags") and not smd.get("headlines"):
                continue
            obs = "observed" if smd.get("has_observed") else "synthetic/estimated"
            L.append(f"**{sm}** (news quality: {obs}) — "
                     f"+{smd.get('positive',0)} / -{smd.get('negative',0)} / "
                     f"neutral {smd.get('neutral',0)}")
            for hl in smd.get("headlines", [])[:2]:
                tags = ", ".join(hl.get("tags", [])) or "general"
                L.append(f"  - [{hl['evidence_type']}] {hl['headline'][:90]} "
                         f"({tags}, {hl['date']})")
        L.append("")
    else:
        L.append("- No classified news events available this cycle.")
        L.append("")

    # ---- Risk & Opportunity ----
    L.append("## 4. Risk & Opportunity")
    for sc in analysis.get("score_objects", []):
        if sc.name in ("Market Stress Score", "Submarket Opportunity Score"):
            L.append(f"- **{sc.submarket} - {sc.name}: {sc.score} ({sc.level})** - {sc.explanation}")
    L.append("")

    # ---- Alerts ----
    L.append("## 5. Alerts")
    if alerts:
        for a in alerts:
            life = getattr(a, "lifecycle", "new") or "new"
            L.append(f"- **[{a.severity}] [{life.upper()}] {a.alert_type}** "
                     f"({a.related_submarket}): {a.trigger_reason}")
            L.append(f"  - Suggested action: {a.suggested_action}")
            if getattr(a, "first_seen", None):
                L.append(f"  - First seen: {a.first_seen[:19]} | Last seen: {a.last_seen[:19]}")
    else:
        L.append("- No active alerts this cycle.")
    L.append("")

    # ---- Source Freshness ----
    L.append("## 6. Source Freshness")
    if not df.empty:
        fresh = (df.groupby("source")
                   .agg(latest_period=("date", "max"), retrieved=("retrieved_at", "max"),
                        rows=("value", "size"), quality=("data_quality", "first"))
                   .reset_index().sort_values("source"))
        L.append("| Source | Quality | Latest period | Retrieved at | Rows |")
        L.append("|---|---|---|---|---|")
        for _, r in fresh.iterrows():
            L.append(f"| {r['source']} | {r['quality']} | {r['latest_period']} | "
                     f"{str(r['retrieved'])[:19]} | {r['rows']} |")
    news_sources = {e.source for e in events}
    L.append(f"\n- News/events ingested: {len(events)} items from {len(news_sources)} source(s).")
    stale = [a for a in alerts if a.alert_type == "data_staleness"]
    if stale:
        L.append("\n**Staleness warnings:**")
        for a in stale:
            L.append(f"- {a.trigger_reason}")
    L.append("")

    # ---- Next-week Watchlist ----
    L.append("## 7. Next-week Watchlist")
    watch = []
    for a in alerts[:4]:
        watch.append(f"Track {a.related_submarket} ({a.alert_type.replace('_',' ')}).")
    neg_events = [e for e in events if e.impact_direction == "negative"][:3]
    for e in neg_events:
        watch.append(f"Follow up on news: \"{e.headline[:70]}\" ({e.affected_submarket}).")
    if not watch:
        watch.append("No critical items; continue routine monitoring.")
    for w in watch:
        L.append(f"- {w}")
    L.append("")

    # ---- Data Provenance & Quality (integrity) ----
    L.append("## 8. Data Provenance & Quality")
    L.append(f"- Signal quality breakdown: {qb}")
    if provenance:
        L.append(f"- Source tracks: CRE core = `{provenance.get('cre_core')}`, "
                 f"macro = `{provenance.get('macro')}`, news = `{provenance.get('news')}`.")
    L.append("- Classification: **Observed** = live API/RSS with source_url + retrieved_at; "
             "**Synthetic** = local sample_data; **Estimated** = derived/incomplete provenance.")
    L.append("")

    # ---- Synthetic Data Disclosure (conditional) ----
    if has_synth:
        L.append("## 9. Synthetic Data Disclosure")
        L.append(f"- {qb.get('synthetic', 0)} signal rows are **synthetic** "
                 "(reason: `missing_public_source`) and are used only for PoC pipeline "
                 "validation and alert testing - **not real market facts**.")
        L.append("- Affected metric families: prime/Grade A rent, vacancy/availability, "
                 "take-up, pipeline/completions/pre-let (and macro/news when live sources are offline).")
        L.append("- Any alert triggered solely by synthetic data is downgraded one severity "
                 "level and tagged `[SYNTHETIC-TEST]`.")
        L.append("- Real-source onboarding backlog tracked in `DATA_INTEGRITY.md`.")
        L.append("")

    content = "\n".join(L)
    target = (out_dir or REPORTS_DIR)
    target.mkdir(parents=True, exist_ok=True)
    fname = f"weekly_briefing_{now.strftime('%Y%m%d_%H%M')}.md"
    path = target / fname
    path.write_text(content, encoding="utf-8")
    log.info("report written: %s (%d chars)", path, len(content))
    return {"path": str(path), "version": version, "sections": 9 if has_synth else 8,
            "has_synthetic": has_synth, "content": content}
