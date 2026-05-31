"""Unit tests: trend/momentum + composite scoring direction."""
import pandas as pd

from app.skills import analysis_skill, ingest_skill, normalize_skill


def _seed():
    data = ingest_skill.run()
    normalize_skill.run(data["signals"])


def test_momentum_direction():
    df = pd.DataFrame([
        {"date": "2025-09-30", "submarket": "X", "metric_name": "Prime Rent",
         "value": 100.0, "unit": "x", "source": "s", "data_quality": "synthetic"},
        {"date": "2025-12-31", "submarket": "X", "metric_name": "Prime Rent",
         "value": 105.0, "unit": "x", "source": "s", "data_quality": "synthetic"},
        {"date": "2026-03-31", "submarket": "X", "metric_name": "Prime Rent",
         "value": 110.0, "unit": "x", "source": "s", "data_quality": "synthetic"},
    ])
    abs_chg, pct = analysis_skill._momentum(df, "X", "Prime Rent", periods=2)
    assert abs_chg == 10.0
    assert round(pct, 1) == 10.0


def test_scores_reflect_stress_vs_resilience():
    _seed()
    res = analysis_skill.run()
    by = res["by_submarket"]
    assert by["Canary Wharf"]["stress"] > by["West End"]["stress"]
    assert by["West End"]["resilience"] > by["Canary Wharf"]["resilience"]
    assert by["West End"]["opportunity"] > by["Canary Wharf"]["opportunity"]


def test_analysis_includes_demand_drivers():
    from app.skills import ingest_skill, normalize_skill, news_impact_skill, analysis_skill
    from app.data import repository
    repository.init_db()
    d = ingest_skill.run()
    normalize_skill.run(d["signals"])
    news_impact_skill.run(d["news"])
    res = analysis_skill.run()
    assert "demand_drivers" in res
    assert "highlights" in res["demand_drivers"]

