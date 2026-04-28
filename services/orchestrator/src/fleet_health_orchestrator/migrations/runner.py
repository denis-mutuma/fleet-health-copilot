"""Versioned schema migration runner.

Each migration is a module-level dict::

    MIGRATION = {
        "id": "001",
        "description": "short human-readable label",
        "sqlite": "SQL to run on SQLite",
        "postgres": "SQL to run on PostgreSQL",
    }

Multiple statements are separated with a semicolon that is the sole
non-whitespace content on its line (``\\n;\\n``), which lets the runner
split them safely regardless of statement content.

The runner keeps a ``schema_migrations`` table that records every
applied migration id so re-entrant calls are no-ops.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_STATEMENT_SEPARATOR = "\n;\n"


def _split_statements(sql: str) -> list[str]:
    """Split a migration SQL block on the statement separator."""
    return [s.strip() for s in sql.split(_STATEMENT_SEPARATOR) if s.strip()]


def _ensure_tracking_table(connection: Any, *, use_postgres: bool) -> None:
    """Create the schema_migrations tracking table if it does not exist."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _applied_ids(connection: Any) -> set[str]:
    rows = connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
    return {row["migration_id"] if hasattr(row, "__getitem__") else row[0] for row in rows}


def _record_migration(connection: Any, migration_id: str, now_iso: str) -> None:
    connection.execute(
        "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)"
        if not _is_postgres_connection(connection)
        else "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (%s, %s)",
        (migration_id, now_iso),
    )


def _is_postgres_connection(connection: Any) -> bool:
    """Detect psycopg connection by module name."""
    return type(connection).__module__.startswith("psycopg")


def apply_migrations(
    connection: Any,
    migrations: list[dict],
    *,
    use_postgres: bool,
    now_iso: str,
) -> None:
    """Apply any not-yet-applied migrations within the given connection.

    The caller is responsible for committing / rolling back the connection.
    All migrations in a single call share the same transaction.
    """
    _ensure_tracking_table(connection, use_postgres=use_postgres)
    done = _applied_ids(connection)

    for migration in sorted(migrations, key=lambda m: m["id"]):
        mid = migration["id"]
        if mid in done:
            continue

        sql_key = "postgres" if use_postgres else "sqlite"
        sql_block = migration.get(sql_key, "")
        if not sql_block.strip():
            logger.warning("Migration %s has no SQL for dialect %s — skipping", mid, sql_key)
            _record_migration(connection, mid, now_iso)
            continue

        logger.info("Applying migration %s: %s", mid, migration.get("description", ""))
        for statement in _split_statements(sql_block):
            connection.execute(statement)

        _record_migration(connection, mid, now_iso)
        logger.info("Migration %s applied successfully", mid)
