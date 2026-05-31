"""Persistence schema (SQLModel) + lightweight pydantic value objects.

Tables required by the spec: market_signals, events_news, alerts, runs.
A shared ``Evidence`` object is used by qa/alert/report so every conclusion
carries the same traceable (source + timestamp + metric) shape.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Literal, Optional

from pydantic import BaseModel
from sqlmodel import Field, SQLModel

# Data-quality vocabulary enforced across the whole agent (see DATA_INTEGRITY.md).
DataQuality = Literal["observed", "estimated", "synthetic"]


# --------------------------------------------------------------------------- #
# Persisted tables
# --------------------------------------------------------------------------- #
class MarketSignal(SQLModel, table=True):
    __tablename__ = "market_signals"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True)            # ISO date string (period end)
    submarket: str = Field(index=True)       # City / West End / Canary Wharf / Midtown / London
    metric_name: str = Field(index=True)
    value: float
    unit: str
    source: str
    confidence: float = 1.0
    # --- data-integrity fields (binding policy) ---
    data_quality: str = Field(default="synthetic", index=True)
    source_url: Optional[str] = None
    source_detail: Optional[str] = None      # series_id / report page / mock label
    retrieved_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    synthetic_reason: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class EventNews(SQLModel, table=True):
    __tablename__ = "events_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True)            # published_at
    headline: str
    summary: str = ""                        # raw snippet
    affected_submarket: str = "London"
    impact_direction: str = "neutral"        # positive / negative / neutral
    time_horizon: str = "medium"             # short / medium / long
    source: str = ""                         # source_name
    confidence: float = 0.5
    # --- data-integrity fields ---
    data_quality: str = Field(default="synthetic", index=True)
    source_url: Optional[str] = None
    retrieved_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    synthetic_reason: Optional[str] = None
    tags: str = "[]"                         # JSON array: hybrid_working, esg, etc.


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    alert_key: str = Field(default="", index=True)   # alert_type:submarket
    alert_time: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    severity: str = "Low"                    # Low / Medium / High
    alert_type: str = ""
    trigger_reason: str = ""
    evidence: str = ""                       # JSON-encoded list[Evidence]
    suggested_action: str = ""
    related_submarket: str = "London"
    status: str = "open"                     # open / resolved
    lifecycle: str = "new"                   # new / ongoing / resolved
    first_seen: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_seen: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    run_id: Optional[int] = Field(default=None, primary_key=True)
    run_type: str = ""                       # pipeline / weekly_briefing / ask / ingest ...
    start_time: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    end_time: Optional[str] = None
    status: str = "running"                  # running / success / partial / failed
    error_message: Optional[str] = None


# --------------------------------------------------------------------------- #
# Value objects (not persisted directly)
# --------------------------------------------------------------------------- #
class Evidence(BaseModel):
    """A single traceable piece of evidence backing any conclusion.

    ``evidence_type`` mirrors ``data_quality`` so every output row can be marked
    Observed / Estimated / Synthetic per the integrity policy.
    """

    source: str
    timestamp: str
    metric: str = ""
    value: Optional[float] = None
    note: str = ""
    evidence_type: str = "synthetic"          # observed | estimated | synthetic
    source_url: Optional[str] = None

    def render(self) -> str:
        bits = [self.metric] if self.metric else []
        if self.value is not None:
            bits.append(f"{self.value:g}")
        head = " ".join(bits) if bits else self.note or "signal"
        tag = self.evidence_type.upper()
        url = f", url={self.source_url}" if self.source_url else ""
        return f"[{tag}] {head} (source={self.source}{url}, ts={self.timestamp})"


class CompositeScore(BaseModel):
    name: str
    submarket: str
    score: float                              # 0-100
    level: str                                # Low / Medium / High
    factors: dict[str, float]
    explanation: str
    evidence: list[Evidence] = []


class AlertResult(BaseModel):
    severity: str
    alert_type: str
    trigger_reason: str
    suggested_action: str
    related_submarket: str
    evidence: list[Evidence] = []


class QAResult(BaseModel):
    answer: str
    key_points: list[str] = []
    evidence: list[Evidence] = []
    confidence: float = 0.0
    limitations: str = ""
