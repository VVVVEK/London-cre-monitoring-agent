"""Unit + integration tests: Q&A evidence + report assembly + full pipeline."""
from pathlib import Path

from app.orchestrator import orchestrator
from app.skills import qa_skill, report_skill


def test_full_pipeline_runs():
    summary = orchestrator.run_pipeline()
    assert summary["status"] in ("success", "partial")
    assert "alert" in summary["stages"]


def test_ask_returns_evidence_and_limitations():
    orchestrator.run_pipeline()
    res = qa_skill.run("What is the vacancy rate in Canary Wharf?")
    assert res.answer
    assert len(res.evidence) >= 1
    # Synthetic CRE data must be disclosed and confidence capped.
    assert "SYNTHETIC" in res.limitations.upper()
    assert res.confidence <= 0.5
    assert res.evidence[0].evidence_type in ("observed", "estimated", "synthetic")


def test_ask_handles_no_match_gracefully():
    orchestrator.run_pipeline()
    res = qa_skill.run("Tell me about residential prices in Tokyo")
    # No matching metric/submarket signals -> honest low confidence, no fabrication.
    assert res.confidence <= 0.5


def test_report_has_required_sections(tmp_path: Path):
    orchestrator.run_pipeline()
    out = report_skill.run(provenance={"cre_core": "sample_data(synthetic)",
                                       "macro": "sample_data(synthetic)",
                                       "news": "sample_data(synthetic)"},
                           out_dir=tmp_path)
    content = out["content"]
    for heading in ["Executive Summary", "Submarket Deep Dive",
                    "Occupier Demand Drivers", "Risk & Opportunity",
                    "Alerts", "Source Freshness", "Next-week Watchlist",
                    "Data Provenance & Quality", "Synthetic Data Disclosure"]:
        assert heading in content
    assert Path(out["path"]).exists()
    assert out["has_synthetic"] is True


def test_pipeline_survives_news_source_failure(monkeypatch):
    # Force the news stage to blow up; the pipeline must still finish + alert.
    from app.skills import news_impact_skill

    def boom(_):
        raise RuntimeError("simulated news outage")

    monkeypatch.setattr(news_impact_skill, "run", boom)
    summary = orchestrator.run_pipeline()
    assert summary["status"] == "partial"
    assert summary["stages"]["alert"]["alerts"] >= 2
