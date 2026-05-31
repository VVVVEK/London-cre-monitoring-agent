"""Thin data-access layer over sqlite (via SQLModel)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlmodel import Session, SQLModel, create_engine, delete, select

from app.data.models import (
    Alert,
    AlertResult,
    EventNews,
    MarketSignal,
    Run,
)
from app.utils.config import get_settings

_engine = None

# Lightweight migrations: columns added after initial PoC release.
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "events_news": [("tags", "TEXT DEFAULT '[]'")],
    "alerts": [
        ("alert_key", "TEXT DEFAULT ''"),
        ("lifecycle", "TEXT DEFAULT 'new'"),
        ("first_seen", "TEXT"),
        ("last_seen", "TEXT"),
    ],
}


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().db_uri, echo=False)
    return _engine


def _session() -> Session:
    return Session(get_engine(), expire_on_commit=False)


def _migrate_db() -> None:
    """Add missing columns on existing sqlite DBs (create_all won't alter tables)."""
    db_path = get_settings().db_uri.replace("sqlite:///", "")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for table, cols in _MIGRATIONS.items():
            cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not cur.fetchone():
                continue
            existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
            for col_name, col_def in cols:
                if col_name not in existing:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
        conn.commit()
        conn.close()
    except Exception:
        pass  # fresh DB will get full schema from create_all


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())
    _migrate_db()


def replace_signals(signals: list[MarketSignal]) -> int:
    with _session() as s:
        s.exec(delete(MarketSignal))
        for sig in signals:
            s.add(sig)
        s.commit()
    return len(signals)


def signals_dataframe() -> pd.DataFrame:
    with _session() as s:
        rows = s.exec(select(MarketSignal)).all()
    if not rows:
        return pd.DataFrame(
            columns=[
                "date", "submarket", "metric_name", "value",
                "unit", "source", "confidence", "data_quality",
                "source_url", "source_detail", "retrieved_at", "synthetic_reason",
            ]
        )
    df = pd.DataFrame([r.model_dump() for r in rows])
    # sqlite/pandas may surface missing optional strings as NaN; normalize to None
    for col in ("source_url", "source_detail", "synthetic_reason"):
        if col in df.columns:
            df[col] = df[col].where(df[col].notna(), None)
    return df


def replace_events(events: list[EventNews]) -> int:
    with _session() as s:
        s.exec(delete(EventNews))
        for e in events:
            s.add(e)
        s.commit()
    return len(events)


def list_events() -> list[EventNews]:
    with _session() as s:
        return list(s.exec(select(EventNews).order_by(EventNews.date.desc())).all())


def _alert_key(alert_type: str, submarket: str) -> str:
    return f"{alert_type}:{submarket}"


def save_alerts(results: list[AlertResult]) -> dict:
    """Merge triggered alerts with history (new / ongoing / resolved lifecycle)."""
    now = datetime.utcnow().isoformat()
    triggered_keys: set[str] = set()
    stats = {"new": 0, "ongoing": 0, "resolved": 0, "total_active": 0}

    with _session() as s:
        active = list(s.exec(select(Alert).where(Alert.status == "open")).all())
        active_by_key = {a.alert_key: a for a in active if a.alert_key}

        for r in results:
            key = _alert_key(r.alert_type, r.related_submarket)
            triggered_keys.add(key)
            payload = json.dumps([e.model_dump() for e in r.evidence])
            if key in active_by_key:
                a = active_by_key[key]
                a.severity = r.severity
                a.trigger_reason = r.trigger_reason
                a.evidence = payload
                a.suggested_action = r.suggested_action
                a.last_seen = now
                a.lifecycle = "ongoing"
                a.status = "open"
                stats["ongoing"] += 1
                s.add(a)
            else:
                s.add(Alert(
                    alert_key=key,
                    severity=r.severity,
                    alert_type=r.alert_type,
                    trigger_reason=r.trigger_reason,
                    evidence=payload,
                    suggested_action=r.suggested_action,
                    related_submarket=r.related_submarket,
                    status="open",
                    lifecycle="new",
                    first_seen=now,
                    last_seen=now,
                    alert_time=now,
                ))
                stats["new"] += 1

        for a in active:
            if a.alert_key and a.alert_key not in triggered_keys:
                a.status = "resolved"
                a.lifecycle = "resolved"
                a.last_seen = now
                s.add(a)
                stats["resolved"] += 1

        s.commit()
        stats["total_active"] = stats["new"] + stats["ongoing"]
    return stats


def list_alerts(active_only: bool = True) -> list[Alert]:
    with _session() as s:
        stmt = select(Alert).order_by(Alert.severity.desc(), Alert.last_seen.desc())
        if active_only:
            stmt = stmt.where(Alert.status == "open")
        return list(s.exec(stmt).all())


def list_alert_history(limit: int = 50) -> list[Alert]:
    with _session() as s:
        return list(s.exec(
            select(Alert).order_by(Alert.last_seen.desc()).limit(limit)
        ).all())


def start_run(run_type: str) -> int:
    with _session() as s:
        run = Run(run_type=run_type, status="running")
        s.add(run)
        s.commit()
        s.refresh(run)
        return run.run_id


def finish_run(run_id: int, status: str, error: Optional[str] = None) -> None:
    with _session() as s:
        run = s.get(Run, run_id)
        if run:
            run.status = status
            run.end_time = datetime.utcnow().isoformat()
            run.error_message = error
            s.add(run)
            s.commit()


def list_runs(limit: int = 20) -> list[Run]:
    with _session() as s:
        return list(s.exec(select(Run).order_by(Run.run_id.desc()).limit(limit)).all())


def last_run(run_type: Optional[str] = None) -> Optional[Run]:
    with _session() as s:
        stmt = select(Run).order_by(Run.run_id.desc())
        if run_type:
            stmt = stmt.where(Run.run_type == run_type)
        return s.exec(stmt).first()
