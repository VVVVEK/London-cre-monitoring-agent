"""CLI entrypoint (typer + rich).

Commands:
    ingest | normalize | analyze | alert | report | ask "<q>" | run_pipeline | weekly
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.data import repository
from app.orchestrator import orchestrator
from app.skills import (
    alert_skill,
    analysis_skill,
    ingest_skill,
    news_impact_skill,
    normalize_skill,
    report_skill,
)
from app.utils.config_check import check_all

app = typer.Typer(add_completion=False, help="London Office CRE Monitoring AI Agent")
console = Console()


@app.command()
def ingest():
    """Acquire data (FRED + RSS live; sample_data fallback)."""
    repository.init_db()
    data = ingest_skill.run()
    norm = normalize_skill.run(data["signals"])
    news_impact_skill.run(data["news"])
    console.print(Panel.fit(f"Provenance: {data['provenance']}\nNormalized: {norm}",
                            title="ingest"))


@app.command()
def normalize():
    """Re-run normalization on freshly ingested data."""
    repository.init_db()
    data = ingest_skill.run()
    console.print(normalize_skill.run(data["signals"]))


@app.command()
def analyze():
    """Compute composite scores and show them."""
    repository.init_db()
    if repository.signals_dataframe().empty:
        orchestrator.run_pipeline()
    res = analysis_skill.run()
    table = Table(title="Composite Scores")
    for col in ("Submarket", "Stress", "Resilience", "Supply Risk", "Opportunity"):
        table.add_column(col)
    for sm, v in res["by_submarket"].items():
        table.add_row(sm, f"{v['stress']:.0f}", f"{v['resilience']:.0f}",
                      f"{v['supply_risk']:.0f}", f"{v['opportunity']:.0f}")
    console.print(table)


@app.command()
def alert():
    """Run the alert rules and list triggered alerts."""
    repository.init_db()
    if repository.signals_dataframe().empty:
        orchestrator.run_pipeline()
    res = alert_skill.run()
    table = Table(title=f"Alerts ({res['by_severity']})")
    for col in ("Severity", "Type", "Submarket", "Trigger"):
        table.add_column(col, overflow="fold")
    for a in res["result_objects"]:
        table.add_row(a.severity, a.alert_type, a.related_submarket, a.trigger_reason)
    console.print(table)


@app.command()
def report():
    """Generate the weekly Markdown briefing."""
    res = orchestrator.run_weekly_briefing()
    if res.get("report"):
        console.print(Panel.fit(f"Report saved: {res['report']['path']}\n"
                                f"Version: {res['report']['version']} | "
                                f"Synthetic disclosed: {res['report']['has_synthetic']}",
                                title="report"))
    else:
        console.print(f"[red]report failed: {res.get('error')}")


@app.command()
def ask(question: str = typer.Argument(..., help="Business question")):
    """Answer a business question with structured evidence."""
    res = orchestrator.ask(question)
    console.print(Panel.fit(res["answer"], title="Answer"))
    if res["key_points"]:
        console.print("[bold]Key points:[/bold]")
        for p in res["key_points"]:
            console.print(f"  - {p}")
    console.print("[bold]Evidence:[/bold]")
    for e in res["evidence"]:
        tag = e["evidence_type"].upper()
        url = f" {e['source_url']}" if e.get("source_url") else ""
        console.print(f"  - [{tag}] {e['metric']}={e['value']} ({e['source']}, {e['timestamp']}){url}")
    console.print(f"[bold]Confidence:[/bold] {res['confidence']}")
    if res["limitations"]:
        console.print(f"[yellow]Limitations:[/yellow] {res['limitations']}")


@app.command(name="run_pipeline")
def run_pipeline():
    """Run the full ingest->...->alert pipeline."""
    res = orchestrator.run_pipeline()
    console.print(Panel.fit(f"status={res['status']} | run_id={res['run_id']}\n"
                            f"stages={list(res['stages'].keys())}\nerrors={res['errors']}",
                            title="run_pipeline"))


@app.command()
def weekly():
    """Alias: full pipeline + weekly briefing report."""
    report()


@app.command(name="check-config")
def check_config():
    """Verify API keys and connectivity (does not print secrets)."""
    report = check_all()
    table = Table(title="Configuration Check")
    table.add_column("Item")
    table.add_column("Status")
    for k, v in report["keys"].items():
        table.add_row(f"key:{k}", v)
    for k, v in report["connectivity"].items():
        table.add_row(f"connect:{k}", str(v))
    console.print(table)
    if report["recommendations"]:
        console.print("[yellow]Recommendations:[/yellow]")
        for r in report["recommendations"]:
            console.print(f"  - {r}")


@app.command()
def runs(limit: int = typer.Option(15, help="Number of recent runs to show")):
    """Show pipeline execution history from the runs audit table."""
    repository.init_db()
    rows = repository.list_runs(limit=limit)
    table = Table(title=f"Recent Runs (last {limit})")
    for col in ("ID", "Type", "Status", "Start", "End", "Error"):
        table.add_column(col, overflow="fold")
    for r in rows:
        table.add_row(str(r.run_id), r.run_type, r.status,
                      (r.start_time or "")[:19], (r.end_time or "")[:19] or "-",
                      (r.error_message or "-")[:40])
    console.print(table)


@app.command(name="alert-history")
def alert_history(limit: int = typer.Option(20, help="Max alerts to show")):
    """Show alert history including resolved items and lifecycle."""
    repository.init_db()
    rows = repository.list_alert_history(limit=limit)
    table = Table(title=f"Alert History (last {limit})")
    for col in ("Severity", "Lifecycle", "Status", "Type", "Submarket", "Last Seen"):
        table.add_column(col)
    for a in rows:
        table.add_row(a.severity, a.lifecycle or "-", a.status, a.alert_type,
                      a.related_submarket, (a.last_seen or "")[:19])
    console.print(table)


if __name__ == "__main__":
    app()
