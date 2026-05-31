"""Tests for news deduplication helpers."""
from app.utils.news_utils import dedupe_news, normalize_headline


def test_normalize_headline_strips_punctuation():
    assert normalize_headline("London Office: Market Rises!") == "london office market rises"


def test_dedupe_news_keeps_first():
    items = [
        {"headline": "London office rents rise", "source": "A"},
        {"headline": "London office rents rise.", "source": "B"},
        {"headline": "Different headline", "source": "C"},
    ]
    out = dedupe_news(items)
    assert len(out) == 2
    assert out[0]["source"] == "A"
