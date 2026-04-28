"""002 — add tenant_id columns

Adds tenant_id to every table that participates in multi-tenant
isolation: events, incidents, rag_documents, rag_ingestion_jobs,
chat_sessions, and incident_status_history.

SQLite does not support ADD COLUMN IF NOT EXISTS, so each statement
is guarded by checking PRAGMA table_info at runtime — here we use
the conventional approach of issuing the ALTER and letting the runner
skip if the migration is already recorded.  For idempotency on SQLite
we rely on the schema_migrations guard; the statements will only run
once per database.
"""

MIGRATION: dict = {
    "id": "002",
    "description": "add tenant_id to all domain tables",
    "sqlite": """
ALTER TABLE events ADD COLUMN tenant_id TEXT
;
ALTER TABLE incidents ADD COLUMN tenant_id TEXT
;
ALTER TABLE rag_documents ADD COLUMN tenant_id TEXT
;
ALTER TABLE rag_ingestion_jobs ADD COLUMN tenant_id TEXT
;
ALTER TABLE chat_sessions ADD COLUMN tenant_id TEXT
;
ALTER TABLE incident_status_history ADD COLUMN tenant_id TEXT
""",
    "postgres": """
ALTER TABLE events ADD COLUMN IF NOT EXISTS tenant_id TEXT
;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS tenant_id TEXT
;
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS tenant_id TEXT
;
ALTER TABLE rag_ingestion_jobs ADD COLUMN IF NOT EXISTS tenant_id TEXT
;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS tenant_id TEXT
;
ALTER TABLE incident_status_history ADD COLUMN IF NOT EXISTS tenant_id TEXT
""",
}
