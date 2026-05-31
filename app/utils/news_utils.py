"""Shared helpers for multi-source news ingest (dedup + merge)."""
from __future__ import annotations

import re
from typing import Any


def normalize_headline(headline: str) -> str:
    """Normalize a headline for cross-source deduplication."""
    text = headline.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120]


def dedupe_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate headlines (RSS + NewsAPI often overlap). Keeps first seen."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        headline = (item.get("headline") or "").strip()
        if not headline:
            continue
        key = normalize_headline(headline)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def merge_news_sources(*sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge multiple news lists then dedupe. Earlier lists win on conflict."""
    merged: list[dict[str, Any]] = []
    for src in sources:
        merged.extend(src)
    return dedupe_news(merged)
