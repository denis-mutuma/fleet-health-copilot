"""003 — audit_events table

Creates the audit_events table and its covering index.
This table was introduced alongside the audit trail API.
"""

MIGRATION: dict = {
    "id": "003",
    "description": "create audit_events table",
    "sqlite": """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    source TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
)
;
CREATE INDEX IF NOT EXISTS idx_audit_events_entity_occurred_at
    ON audit_events(entity_type, entity_id, occurred_at)
""",
    "postgres": """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    source TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
)
;
CREATE INDEX IF NOT EXISTS idx_audit_events_entity_occurred_at
    ON audit_events(entity_type, entity_id, occurred_at)
""",
}
