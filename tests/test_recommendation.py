"""Tests for recommendation_skill and orchestrator recommendation chain."""
from app.orchestrator import orchestrator
from app.skills import recommendation_skill


def _seed():
    orchestrator.run_pipeline()


def test_goal_type_switch_changes_recommendation_scores():
    _seed()
    risk_averse = orchestrator.recommend(goal="Risk-Averse", risk_level="Medium", horizon_months=6, ensure_data=False)
    return_seeking = orchestrator.recommend(goal="Return-Seeking", risk_level="Medium", horizon_months=6, ensure_data=False)

    assert risk_averse["recommended_submarkets"]
    assert return_seeking["recommended_submarkets"]
    assert (
        risk_averse["recommended_submarkets"][0]["score"]
        != return_seeking["recommended_submarkets"][0]["score"]
    )


def test_risk_level_switch_changes_recommendation_scores():
    _seed()
    low = orchestrator.recommend(goal="Balanced", risk_level="Low", horizon_months=6, ensure_data=False)
    high = orchestrator.recommend(goal="Balanced", risk_level="High", horizon_months=6, ensure_data=False)

    assert low["recommended_submarkets"]
    assert high["recommended_submarkets"]
    assert low["recommended_submarkets"][0]["score"] != high["recommended_submarkets"][0]["score"]


def test_recommendation_evidence_and_data_quality_present():
    _seed()
    result = orchestrator.recommend(goal="Balanced", risk_level="Medium", horizon_months=6, ensure_data=False)
    assert result["evidence"]
    assert result["data_quality"] in ("observed", "estimated", "synthetic", "mixed", "unknown")
    assert all(e["evidence_type"] for e in result["evidence"])
    assert all(e["source"] for e in result["evidence"])
    assert "Synthetic data" in result["limitations"]


def test_recommendation_chain_reachable_without_ui():
    _seed()
    request = recommendation_skill.RecommendationRequest(
        goal="Risk-Averse",
        risk_level="Low",
        horizon_months=3,
        preferred_submarkets=["City", "West End"],
    )
    direct = recommendation_skill.generate_recommendation(request)
    via_orchestrator = orchestrator.recommend(
        goal="Risk-Averse",
        risk_level="Low",
        horizon_months=3,
        preferred_submarkets=["City", "West End"],
        ensure_data=False,
    )
    assert direct.recommended_submarkets
    assert via_orchestrator["recommended_submarkets"]
