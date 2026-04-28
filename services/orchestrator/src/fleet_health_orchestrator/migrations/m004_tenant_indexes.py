"""004 — tenant indexes

Adds composite indexes on tenant_id + primary lookup key for the
tables most frequently filtered by tenant scope.  These are advisory
on SQLite (where the query planner may use them) and important for
PostgreSQL query performance at scale.
"""

MIGRATION: dict = {
    "id": "004",
    "description": "add tenant lookup indexes",
    "sqlite": """
CREATE INDEX IF NOT EXISTS idx_incidents_tenant_id
    ON incidents(tenant_id)
;
CREATE INDEX IF NOT EXISTS idx_events_tenant_id
    ON events(tenant_id)
;
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_occurred_at
    ON audit_events(tenant_id, occurred_at)
;
CREATE INDEX IF NOT EXISTS idx_rag_ingestion_jobs_tenant_id
    ON rag_ingestion_jobs(tenant_id)
;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant_id
    ON chat_sessions(tenant_id)
""",
    "postgres": """
CREATE INDEX IF NOT EXISTS idx_incidents_tenant_id
    ON incidents(tenant_id)
;
CREATE INDEX IF NOT EXISTS idx_events_tenant_id
    ON events(tenant_id)
;
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_occurred_at
    ON audit_events(tenant_id, occurred_at)
;
CREATE INDEX IF NOT EXISTS idx_rag_ingestion_jobs_tenant_id
    ON rag_ingestion_jobs(tenant_id)
;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant_id
    ON chat_sessions(tenant_id)
""",
}
