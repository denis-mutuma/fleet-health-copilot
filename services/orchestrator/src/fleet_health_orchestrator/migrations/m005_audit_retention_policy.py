"""005 — audit event retention policy helpers

Adds an indexed occurred_at column on audit_events (already present
in the CREATE TABLE from migration 003) and creates the
``audit_event_retention_days`` configuration table that the application
can use to enforce per-tenant or global retention policies.

The retention_days column defaults to NULL, meaning no automatic
expiry.  A background job or manual script can DELETE from audit_events
WHERE occurred_at < now() - retention_days using this table.
"""

MIGRATION: dict = {
    "id": "005",
    "description": "audit retention policy config table",
    "sqlite": """
CREATE TABLE IF NOT EXISTS audit_retention_policy (
    policy_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    entity_type TEXT,
    retention_days INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
;
CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_retention_policy_tenant_entity
    ON audit_retention_policy(tenant_id, entity_type)
""",
    "postgres": """
CREATE TABLE IF NOT EXISTS audit_retention_policy (
    policy_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    entity_type TEXT,
    retention_days INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
;
CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_retention_policy_tenant_entity
    ON audit_retention_policy(tenant_id, entity_type)
""",
}
