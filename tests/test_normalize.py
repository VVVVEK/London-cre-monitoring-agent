"""Unit tests: metric mapping + integrity downgrade + value validation."""
from app.skills import normalize_skill


def test_canonical_metric_mapping():
    assert normalize_skill.canonical_metric("prime_rent") == "Prime Rent"
    assert normalize_skill.canonical_metric("VACANCY") == "Vacancy Rate"
    assert normalize_skill.canonical_metric("policy_rate") == "Policy Rate"
    assert normalize_skill.canonical_metric("unknown_metric") is None


def test_normalize_drops_unmappable_and_bad_values():
    raw = [
        {"date": "2026-03-31", "submarket": "City", "metric": "prime_rent",
         "value": 84.0, "unit": "GBP/sqft/yr", "source": "sample_data/x.csv",
         "data_quality": "synthetic", "retrieved_at": "2026-03-31T00:00:00"},
        {"date": "2026-03-31", "submarket": "City", "metric": "junk_metric",
         "value": 1.0, "unit": "x", "source": "s"},
        {"date": "2026-03-31", "submarket": "City", "metric": "vacancy",
         "value": "not_a_number", "unit": "percent", "source": "s"},
    ]
    report = normalize_skill.run(raw)
    assert report["normalized"] == 1
    assert report["dropped"] == 2


def test_observed_without_provenance_is_downgraded():
    raw = [{
        "date": "2026-03-31", "submarket": "London", "metric": "policy_rate",
        "value": 5.25, "unit": "percent", "source": "FRED",
        "data_quality": "observed",            # claims observed...
        "source_url": None,                    # ...but missing url
        "retrieved_at": "2026-03-31T00:00:00",
    }]
    report = normalize_skill.run(raw)
    # estimated (downgraded), not observed
    assert report["quality_breakdown"].get("estimated") == 1
    assert "observed" not in report["quality_breakdown"]
