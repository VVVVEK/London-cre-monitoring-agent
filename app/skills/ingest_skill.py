"""ingest_skill - dual-track data acquisition with multi-source news merge.

Track 1 (API, observed):
    * Macro: FRED API
    * News:  RSS + NewsAPI (deduped)
Track 2 (sample_data, synthetic fallback for CRE core + offline sources).
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from typing import Any

import requests

from app.utils.config import SAMPLE_DATA_DIR, get_settings
from app.utils.logging import get_logger
from app.utils.news_utils import merge_news_sources

log = get_logger(__name__)

CRE_SAMPLE_FILES = [
    "office_rent_by_submarket.csv",
    "vacancy_rate_by_submarket.csv",
    "takeup_supply_pipeline.csv",
]

FRED_SERIES = {
    "policy_rate": ("IRSTCI01GBM156N", "percent", "UK call-money/immediate rate (BoE policy proxy)"),
    "cpi": ("GBRCPIALLMINMEI", "index", "UK CPI all items index"),
    "core_cpi": ("GBRCPICORMINMEI", "index", "UK core CPI: all items ex food & energy (index)"),
    "unemployment_rate": ("LRHUTTTTGBM156S", "percent", "UK unemployment rate"),
    "gilt_yield": ("IRLTLT01GBM156N", "percent", "UK 10y government bond yield"),
    # No FRED series for UK *office* employment specifically; the national
    # employment rate (15-64, quarterly) is the best fresh observed labour-demand
    # proxy. Labelled transparently as a proxy, never as literal office headcount.
    "office_employment": ("LREM64TTGBQ156S", "percent",
                          "UK employment rate 15-64 (quarterly) - labour-demand proxy for office occupiers"),
}


def _now() -> str:
    return datetime.utcnow().isoformat()


def _load_cre_sample() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fname in CRE_SAMPLE_FILES:
        path = SAMPLE_DATA_DIR / fname
        if not path.exists():
            log.warning("missing sample file: %s", path)
            continue
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.append(
                    {
                        "date": r["date"],
                        "submarket": r["submarket"],
                        "metric": r["metric"],
                        "value": float(r["value"]),
                        "unit": r["unit"],
                        "source": f"sample_data/{fname}",
                        "source_url": None,
                        "source_detail": r.get("source", ""),
                        "data_quality": "synthetic",
                        "synthetic_reason": "missing_public_source",
                        "retrieved_at": _now(),
                    }
                )
    log.info("loaded %d synthetic CRE rows from sample_data", len(rows))
    return rows


def _fetch_fred(settings) -> list[dict[str, Any]]:
    if settings.prefer_sample_data or not settings.fred_enabled:
        return []
    start = (datetime.utcnow() - timedelta(days=900)).strftime("%Y-%m-%d")
    out: list[dict[str, Any]] = []
    for metric, (series_id, unit, note) in FRED_SERIES.items():
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "observation_start": start,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            obs = [o for o in resp.json().get("observations", []) if o["value"] != "."]
            for o in obs[-5:]:
                out.append(
                    {
                        "date": o["date"],
                        "submarket": "London",
                        "metric": metric,
                        "value": float(o["value"]),
                        "unit": unit,
                        "source": "FRED",
                        "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
                        "source_detail": f"{series_id} | {note}",
                        "data_quality": "observed",
                        "synthetic_reason": None,
                        "retrieved_at": _now(),
                    }
                )
        except Exception as exc:
            log.warning("FRED fetch failed for %s: %s", series_id, exc)
    if out:
        log.info("fetched %d observed macro rows from FRED", len(out))
    return out


def _load_macro_sample() -> list[dict[str, Any]]:
    path = SAMPLE_DATA_DIR / "macro_uk.csv"
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "date": r["date"],
                    "submarket": r["submarket"],
                    "metric": r["metric"],
                    "value": float(r["value"]),
                    "unit": r["unit"],
                    "source": "sample_data/macro_uk.csv",
                    "source_url": None,
                    "source_detail": r.get("source", ""),
                    "data_quality": "synthetic",
                    "synthetic_reason": "missing_public_source",
                    "retrieved_at": _now(),
                }
            )
    log.info("loaded %d synthetic macro rows (FRED unavailable)", len(rows))
    return rows


def _fetch_rss(settings) -> list[dict[str, Any]]:
    if settings.prefer_sample_data:
        return []
    try:
        import feedparser
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for feed_url in settings.rss_feed_list:
        try:
            parsed = feedparser.parse(feed_url)
            for e in parsed.entries[:15]:
                published = ""
                if getattr(e, "published_parsed", None):
                    published = datetime(*e.published_parsed[:6]).date().isoformat()
                link = getattr(e, "link", None)
                out.append(
                    {
                        "date": published or datetime.utcnow().date().isoformat(),
                        "headline": getattr(e, "title", "").strip(),
                        "summary": (getattr(e, "summary", "") or "")[:500],
                        "source": getattr(parsed.feed, "title", "RSS") or "RSS",
                        "source_url": link,
                        "source_name": getattr(parsed.feed, "title", "RSS"),
                        "data_quality": "observed",
                        "synthetic_reason": None,
                        "retrieved_at": _now(),
                        "ingest_channel": "rss",
                    }
                )
        except Exception as exc:
            log.warning("RSS fetch failed for %s: %s", feed_url, exc)
    if out:
        log.info("fetched %d observed news items from RSS", len(out))
    return out


def _fetch_newsapi(settings) -> list[dict[str, Any]]:
    if settings.prefer_sample_data or not settings.newsapi_enabled:
        return []
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": settings.newsapi_query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 25,
        "apiKey": settings.newsapi_key,
    }
    out: list[dict[str, Any]] = []
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        for art in resp.json().get("articles", []):
            headline = (art.get("title") or "").strip()
            if not headline or headline == "[Removed]":
                continue
            published = (art.get("publishedAt") or "")[:10]
            out.append(
                {
                    "date": published or datetime.utcnow().date().isoformat(),
                    "headline": headline,
                    "summary": (art.get("description") or art.get("content") or "")[:500],
                    "source": art.get("source", {}).get("name", "NewsAPI"),
                    "source_url": art.get("url"),
                    "source_name": art.get("source", {}).get("name", "NewsAPI"),
                    "data_quality": "observed",
                    "synthetic_reason": None,
                    "retrieved_at": _now(),
                    "ingest_channel": "newsapi",
                }
            )
        log.info("fetched %d observed news items from NewsAPI", len(out))
    except Exception as exc:
        log.warning("NewsAPI fetch failed: %s", exc)
    return out


def _load_news_sample() -> list[dict[str, Any]]:
    path = SAMPLE_DATA_DIR / "news_sample.csv"
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "date": r["date"],
                    "headline": r["headline"],
                    "summary": r["summary"],
                    "source": "sample_data/news_sample.csv",
                    "source_url": None,
                    "source_name": "sample_data",
                    "data_quality": "synthetic",
                    "synthetic_reason": "missing_public_source",
                    "retrieved_at": _now(),
                    "ingest_channel": "sample",
                }
            )
    log.info("loaded %d synthetic news rows (live news unavailable)", len(rows))
    return rows


def run() -> dict[str, Any]:
    settings = get_settings()

    signal_rows = _load_cre_sample()

    macro_rows = _fetch_fred(settings)
    macro_source = "FRED(observed)" if macro_rows else "sample_data(synthetic)"
    if not macro_rows:
        macro_rows = _load_macro_sample()
    signal_rows.extend(macro_rows)

    rss_rows = _fetch_rss(settings)
    newsapi_rows = _fetch_newsapi(settings)
    news_rows = merge_news_sources(rss_rows, newsapi_rows)
    news_channels = []
    if rss_rows:
        news_channels.append("RSS")
    if newsapi_rows:
        news_channels.append("NewsAPI")
    if news_rows:
        news_source = "+".join(news_channels) + "(observed)"
    else:
        news_rows = _load_news_sample()
        news_source = "sample_data(synthetic)"

    provenance = {
        "cre_core": "sample_data(synthetic)",
        "macro": macro_source,
        "news": news_source,
        "news_rss_count": len(rss_rows),
        "news_newsapi_count": len(newsapi_rows),
        "news_deduped_count": len(news_rows),
        "signal_rows": len(signal_rows),
        "news_rows": len(news_rows),
        "llm_enabled": settings.llm_enabled,
        "fred_enabled": settings.fred_enabled,
        "newsapi_enabled": settings.newsapi_enabled,
    }
    log.info("ingest provenance: %s", provenance)
    return {"signals": signal_rows, "news": news_rows, "provenance": provenance}
