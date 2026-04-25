from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TelemetryEvent(BaseModel):
    event_id: str
    fleet_id: str
    device_id: str
    timestamp: datetime
    metric: str
    value: float
    threshold: float
    severity: Literal["low", "medium", "high", "critical"]
    tags: list[str] = Field(default_factory=list)


class IncidentReport(BaseModel):
    incident_id: str
    device_id: str
    status: Literal["open", "acknowledged", "resolved"]
    summary: str
    root_cause_hypotheses: list[str]
    recommended_actions: list[str]
    evidence: dict[str, list[str]]
    confidence_score: float = 0.0
    agent_trace: list[str] = Field(default_factory=list)
    verification: dict[str, object] = Field(default_factory=dict)
    latency_ms: float = 0.0


class IncidentStatusUpdate(BaseModel):
    status: Literal["open", "acknowledged", "resolved"]


class RagDocument(BaseModel):
    document_id: str
    source: Literal["runbook", "incident", "manual", "note"]
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    document_id: str
    source: str
    title: str
    score: float
    excerpt: str
