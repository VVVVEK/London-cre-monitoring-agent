"""Verify API keys and connectivity without printing secrets."""
from __future__ import annotations

import requests

from app.llm.client import LLMClient
from app.utils.config import get_settings


def check_all() -> dict:
    settings = get_settings()
    report: dict = {"keys": {}, "connectivity": {}, "recommendations": []}

    report["keys"]["fred"] = "configured" if settings.fred_enabled else "missing"
    report["keys"]["newsapi"] = "configured" if settings.newsapi_enabled else "missing"
    report["keys"]["openai"] = "configured" if settings.llm_enabled else "missing"
    report["keys"]["llm_provider"] = settings.llm_provider
    report["keys"]["rss"] = f"{len(settings.rss_feed_list)} feed(s)"

    # FRED ping + per-series observed status (matches the series the pipeline pulls)
    if settings.fred_enabled:
        from app.skills.ingest_skill import FRED_SERIES
        for metric, (series_id, _unit, _note) in FRED_SERIES.items():
            try:
                r = requests.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": settings.fred_api_key,
                        "file_type": "json",
                        "limit": 1,
                        "sort_order": "desc",
                    },
                    timeout=10,
                )
                if r.status_code == 200:
                    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
                    if obs:
                        report["connectivity"][f"fred:{metric}"] = f"observed (latest {obs[0]['date']})"
                    else:
                        report["connectivity"][f"fred:{metric}"] = "no data"
                else:
                    report["connectivity"][f"fred:{metric}"] = f"error_{r.status_code}"
            except Exception as exc:
                report["connectivity"][f"fred:{metric}"] = f"failed: {exc}"
    else:
        report["connectivity"]["fred"] = "skipped (no key)"
        report["recommendations"].append("Add FRED_API_KEY for observed macro data.")

    # NewsAPI ping
    if settings.newsapi_enabled:
        try:
            r = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"country": "gb", "pageSize": 1, "apiKey": settings.newsapi_key},
                timeout=10,
            )
            report["connectivity"]["newsapi"] = "ok" if r.status_code == 200 else f"error_{r.status_code}"
        except Exception as exc:
            report["connectivity"]["newsapi"] = f"failed: {exc}"
    else:
        report["connectivity"]["newsapi"] = "skipped (no key)"
        report["recommendations"].append("Add NEWSAPI_KEY for richer observed news.")

    # LLM (OpenAI or Qwen)
    llm = LLMClient()
    label = settings.llm_provider.lower()
    report["connectivity"][label] = "ok" if llm.available else (
        "skipped (no key)" if not settings.llm_enabled else "init_failed"
    )
    if not settings.llm_enabled:
        report["recommendations"].append("Add OPENAI_API_KEY (or Qwen key) for LLM news classification and Q&A.")

    # RSS (always try first feed)
    if settings.rss_feed_list and not settings.prefer_sample_data:
        try:
            import feedparser
            parsed = feedparser.parse(settings.rss_feed_list[0])
            n = len(parsed.entries)
            report["connectivity"]["rss"] = f"ok ({n} entries from first feed)"
        except Exception as exc:
            report["connectivity"]["rss"] = f"failed: {exc}"
    else:
        report["connectivity"]["rss"] = "skipped"

    return report
