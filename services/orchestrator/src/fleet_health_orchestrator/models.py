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
    status_history: list["IncidentStatusHistoryEntry"] = Field(default_factory=list)
    audit_events: list["AuditEvent"] = Field(default_factory=list)

    @field_validator("incident_id", "device_id", "summary")
    @classmethod
    def _required_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class IncidentStatusUpdate(BaseModel):
    status: Literal["open", "acknowledged", "resolved"]
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class IncidentStatusHistoryEntry(BaseModel):
    history_id: str
    incident_id: str
    previous_status: Literal["open", "acknowledged", "resolved"] | None = None
    status: Literal["open", "acknowledged", "resolved"]
    changed_at: datetime
    actor: str = Field(min_length=1)
    source: str = Field(min_length=1)
    reason: str | None = None

    @field_validator("history_id", "incident_id", "actor", "source", "reason")
    @classmethod
    def _history_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class AuditEvent(BaseModel):
    event_id: str
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    source: str = Field(min_length=1)
    occurred_at: datetime
    details: dict[str, object] = Field(default_factory=dict)

    @field_validator("event_id", "entity_type", "entity_id", "action", "actor", "source")
    @classmethod
    def _audit_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


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


class RagIngestionRequest(BaseModel):
    source: Literal["runbook", "incident", "manual", "note"] = "manual"
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    document_id: str | None = None
    chunk_size_chars: int = Field(default=1200, ge=200, le=20000)
    chunk_overlap_chars: int = Field(default=200, ge=0, le=5000)

    @field_validator("title", "content")
    @classmethod
    def _ingestion_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class RagIngestionResponse(BaseModel):
    document_id: str
    source: str
    title: str
    chunk_count: int = Field(ge=1)
    indexed_chunks: int = Field(ge=0)
    retrieval_backend: str
    embedding_provider: str
    embedding_model: str
    llm_model: str


class RagDocumentFamily(BaseModel):
    document_id: str
    source: str
    title: str
    tags: list[str] = Field(default_factory=list)
    chunk_count: int = Field(ge=1)


class RagDeletionResponse(BaseModel):
    document_id: str
    deleted_chunks: int = Field(ge=0)


class RagIngestionJob(BaseModel):
    job_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    source: str
    title: str
    tags: list[str] = Field(default_factory=list)
    filename: str
    idempotency_key: str | None = None
    document_id: str | None = None
    chunk_count: int = Field(default=0, ge=0)
    indexed_chunks: int = Field(default=0, ge=0)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class RetrievalHit(BaseModel):
    document_id: str
    source: str
    title: str
    score: float = Field(ge=0.0)
    excerpt: str


class ChatSessionCreateRequest(BaseModel):
    incident_id: str | None = None


class ChatSession(BaseModel):
    session_id: str
    incident_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatCitation(BaseModel):
    document_id: str
    source: str
    title: str
    score: float = Field(ge=0.0)
    excerpt: str


class ChatToolCall(BaseModel):
    tool_name: str = Field(min_length=1)
    input: dict[str, object] = Field(default_factory=dict)
    output: dict[str, object] = Field(default_factory=dict)
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: str | None = None


class ChatTraceSpan(BaseModel):
    span_name: str = Field(min_length=1)
    status: Literal["success", "error", "skipped"] = "success"
    latency_ms: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, object] = Field(default_factory=dict)
    error: str | None = None


class ChatMessage(BaseModel):
    message_id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    citations: list[ChatCitation] = Field(default_factory=list)
    action: str | None = None
    action_status: Literal["success", "error"] | None = None
    action_payload: dict[str, object] = Field(default_factory=dict)
    tool_calls: list[ChatToolCall] = Field(default_factory=list)
    trace_spans: list[ChatTraceSpan] = Field(default_factory=list)
    llm_cost_usd: float | None = Field(default=None, ge=0.0)
    created_at: datetime

    @field_validator("message_id", "session_id", "content")
    @classmethod
    def _chat_required_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class ChatMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def _chat_message_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class ChatConversation(BaseModel):
    session: ChatSession
    messages: list[ChatMessage]
