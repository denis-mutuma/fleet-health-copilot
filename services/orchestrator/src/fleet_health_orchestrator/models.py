from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TelemetryEvent(BaseModel):
    event_id: str
    fleet_id: str
    device_id: str
    timestamp: datetime
    metric: str = Field(min_length=1)
    value: float
    threshold: float = Field(gt=0)
    severity: Literal["low", "medium", "high", "critical"]
    tags: list[str] = Field(default_factory=list)

    @field_validator("metric", "event_id", "fleet_id", "device_id")
    @classmethod
    def _non_empty_string(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, tags: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in tags:
            cleaned = tag.strip().lower()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized


class IncidentReport(BaseModel):
    incident_id: str
    device_id: str
    status: Literal["open", "acknowledged", "resolved"]
    summary: str = Field(min_length=1)
    root_cause_hypotheses: list[str]
    recommended_actions: list[str]
    evidence: dict[str, list[str]]
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    agent_trace: list[str] = Field(default_factory=list)
    verification: dict[str, object] = Field(default_factory=dict)
    latency_ms: float = Field(default=0.0, ge=0.0)

    @field_validator("incident_id", "device_id", "summary")
    @classmethod
    def _required_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class IncidentStatusUpdate(BaseModel):
    status: Literal["open", "acknowledged", "resolved"]


class RagDocument(BaseModel):
    document_id: str
    source: Literal["runbook", "incident", "manual", "note"]
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)

    @field_validator("document_id", "title", "content")
    @classmethod
    def _doc_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class RetrievalHit(BaseModel):
    document_id: str
    source: str
    title: str
    score: float = Field(ge=0.0)
    excerpt: str
