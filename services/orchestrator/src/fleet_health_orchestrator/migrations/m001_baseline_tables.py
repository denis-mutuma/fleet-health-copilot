"""001 — baseline tables

Creates the initial set of tables that existed before the migration
framework was introduced. Safe to run on a fresh database; for an
existing database the CREATE TABLE IF NOT EXISTS guards are no-ops.
"""

MIGRATION: dict = {
    "id": "001",
    "description": "baseline tables",
    "sqlite": """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    fleet_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metric TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    severity TEXT NOT NULL,
    tags_json TEXT NOT NULL
)
;
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    root_cause_hypotheses_json TEXT NOT NULL,
    recommended_actions_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    agent_trace_json TEXT NOT NULL DEFAULT '[]',
    verification_json TEXT NOT NULL DEFAULT '{}',
    latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0.0
)
;
CREATE TABLE IF NOT EXISTS rag_documents (
    document_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags_json TEXT NOT NULL
)
;
CREATE TABLE IF NOT EXISTS rag_ingestion_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    filename TEXT NOT NULL,
    idempotency_key TEXT,
    document_id TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    indexed_chunks INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
;
CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_ingestion_jobs_idempotency_key
    ON rag_ingestion_jobs(idempotency_key)
;
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    incident_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
;
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    action TEXT,
    action_status TEXT,
    action_payload_json TEXT NOT NULL DEFAULT '{}',
    tool_calls_json TEXT NOT NULL DEFAULT '[]',
    trace_spans_json TEXT NOT NULL DEFAULT '[]',
    llm_cost_usd DOUBLE PRECISION,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
)
;
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created_at
    ON chat_messages(session_id, created_at)
;
CREATE TABLE IF NOT EXISTS incident_status_history (
    history_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    previous_status TEXT,
    status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT,
    FOREIGN KEY(incident_id) REFERENCES incidents(incident_id)
)
;
CREATE INDEX IF NOT EXISTS idx_incident_status_history_incident_changed_at
    ON incident_status_history(incident_id, changed_at)
""",
    "postgres": """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    fleet_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metric TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    severity TEXT NOT NULL,
    tags_json TEXT NOT NULL
)
;
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    root_cause_hypotheses_json TEXT NOT NULL,
    recommended_actions_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    agent_trace_json TEXT NOT NULL DEFAULT '[]',
    verification_json TEXT NOT NULL DEFAULT '{}',
    latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0.0
)
;
CREATE TABLE IF NOT EXISTS rag_documents (
    document_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags_json TEXT NOT NULL
)
;
CREATE TABLE IF NOT EXISTS rag_ingestion_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    filename TEXT NOT NULL,
    idempotency_key TEXT,
    document_id TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    indexed_chunks INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
;
CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_ingestion_jobs_idempotency_key
    ON rag_ingestion_jobs(idempotency_key)
;
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    incident_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
;
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(session_id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    action TEXT,
    action_status TEXT,
    action_payload_json TEXT NOT NULL DEFAULT '{}',
    tool_calls_json TEXT NOT NULL DEFAULT '[]',
    trace_spans_json TEXT NOT NULL DEFAULT '[]',
    llm_cost_usd DOUBLE PRECISION,
    created_at TEXT NOT NULL
)
;
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created_at
    ON chat_messages(session_id, created_at)
;
CREATE TABLE IF NOT EXISTS incident_status_history (
    history_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
    previous_status TEXT,
    status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT
)
;
CREATE INDEX IF NOT EXISTS idx_incident_status_history_incident_changed_at
    ON incident_status_history(incident_id, changed_at)
""",
}
