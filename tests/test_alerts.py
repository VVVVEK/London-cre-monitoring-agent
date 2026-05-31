"""Unit tests: alert rules trigger + synthetic downgrade integrity rule."""
from app.skills import alert_skill, ingest_skill, normalize_skill


def _seed():
    data = ingest_skill.run()
    normalize_skill.run(data["signals"])


def test_at_least_two_alerts_trigger():
    _seed()
    res = alert_skill.run()
    assert res["alerts"] >= 2
    types = {a.alert_type for a in res["result_objects"]}
    # Canary Wharf sample is built to fire these.
    assert "vacancy_deterioration" in types
    assert "supply_squeeze" in types


def test_synthetic_alerts_are_downgraded_and_tagged():
    _seed()
    res = alert_skill.run()
    # In offline/sample mode every market alert is synthetic-backed -> tagged + no High.
    market_alerts = [a for a in res["result_objects"] if a.alert_type != "data_staleness"]
    assert all("[SYNTHETIC-TEST]" in a.trigger_reason for a in market_alerts)
    assert all(a.severity != "High" for a in market_alerts)


def test_alert_lifecycle_new_then_ongoing():
    _seed()
    first = alert_skill.run()
    assert first["lifecycle"]["new"] >= 1
    second = alert_skill.run()
    assert second["lifecycle"]["ongoing"] >= 1
    assert second["lifecycle"]["new"] == 0


def test_downgrade_helper():
    assert alert_skill._downgrade("High") == "Medium"
    assert alert_skill._downgrade("Medium") == "Low"
    assert alert_skill._downgrade("Low") == "Low"
