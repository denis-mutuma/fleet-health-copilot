"""Tests for the versioned schema migration runner and migrations 001-005."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fleet_health_orchestrator.migrations import ALL_MIGRATIONS
from fleet_health_orchestrator.migrations.runner import (
    _applied_ids,
    _ensure_tracking_table,
    apply_migrations,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _in_memory_connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Runner unit tests
# ---------------------------------------------------------------------------


class TestEnsureTrackingTable:
    def test_creates_schema_migrations_table(self):
        conn = _in_memory_connection()
        _ensure_tracking_table(conn, use_postgres=False)
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "schema_migrations" in tables

    def test_idempotent_on_second_call(self):
        conn = _in_memory_connection()
        _ensure_tracking_table(conn, use_postgres=False)
        _ensure_tracking_table(conn, use_postgres=False)  # must not raise


class TestAppliedIds:
    def test_empty_on_fresh_db(self):
        conn = _in_memory_connection()
        _ensure_tracking_table(conn, use_postgres=False)
        assert _applied_ids(conn) == set()

    def test_returns_recorded_ids(self):
        conn = _in_memory_connection()
        _ensure_tracking_table(conn, use_postgres=False)
        conn.execute(
            "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("001", _utc_now()),
        )
        assert "001" in _applied_ids(conn)


class TestApplyMigrations:
    def test_applies_all_migrations_on_fresh_db(self):
        conn = _in_memory_connection()
        apply_migrations(conn, ALL_MIGRATIONS, use_postgres=False, now_iso=_utc_now())
        conn.commit()

        applied = _applied_ids(conn)
        assert {m["id"] for m in ALL_MIGRATIONS} == applied

    def test_skips_already_applied_migrations(self):
        conn = _in_memory_connection()
        apply_migrations(conn, ALL_MIGRATIONS, use_postgres=False, now_iso=_utc_now())
        conn.commit()

        # Second call must not raise (idempotent)
        apply_migrations(conn, ALL_MIGRATIONS, use_postgres=False, now_iso=_utc_now())
        conn.commit()

        applied = _applied_ids(conn)
        assert {m["id"] for m in ALL_MIGRATIONS} == applied

    def test_partial_apply_completes_remaining(self):
        conn = _in_memory_connection()
        # Apply only migration 001 manually
        _ensure_tracking_table(conn, use_postgres=False)
        m001_sql = ALL_MIGRATIONS[0]["sqlite"]
        for stmt in m001_sql.split("\n;\n"):
            if stmt.strip():
                conn.execute(stmt.strip())
        conn.execute(
            "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("001", _utc_now()),
        )
        conn.commit()

        # Now run full suite — only 002..005 should execute
        apply_migrations(conn, ALL_MIGRATIONS, use_postgres=False, now_iso=_utc_now())
        conn.commit()

        applied = _applied_ids(conn)
        assert {m["id"] for m in ALL_MIGRATIONS} == applied

    def test_applies_custom_single_migration(self):
        conn = _in_memory_connection()
        single = [
            {
                "id": "001",
                "description": "test table",
                "sqlite": "CREATE TABLE test_table (id TEXT PRIMARY KEY)",
                "postgres": "",
            }
        ]
        apply_migrations(conn, single, use_postgres=False, now_iso=_utc_now())
        conn.commit()

        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "test_table" in tables

    def test_empty_sql_migration_is_recorded_without_error(self):
        conn = _in_memory_connection()
        no_sql = [
            {
                "id": "999",
                "description": "no-op",
                "sqlite": "",
                "postgres": "",
            }
        ]
        apply_migrations(conn, no_sql, use_postgres=False, now_iso=_utc_now())
        conn.commit()
        assert "999" in _applied_ids(conn)


# ---------------------------------------------------------------------------
# Integration: FleetRepository uses migration runner on init
# ---------------------------------------------------------------------------


class TestRepositoryMigrationIntegration:
    def test_fresh_db_has_all_expected_tables(self, tmp_path: Path):
        from fleet_health_orchestrator.repository import FleetRepository

        repo = FleetRepository(db_path=tmp_path / "test.db")
        conn = sqlite3.connect(tmp_path / "test.db")
        conn.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "schema_migrations",
            "events",
            "incidents",
            "rag_documents",
            "rag_ingestion_jobs",
            "chat_sessions",
            "chat_messages",
            "incident_status_history",
            "audit_events",
            "audit_retention_policy",
        }
        assert expected.issubset(tables)
        conn.close()

    def test_all_migrations_recorded_after_init(self, tmp_path: Path):
        from fleet_health_orchestrator.repository import FleetRepository

        FleetRepository(db_path=tmp_path / "test.db")
        conn = sqlite3.connect(tmp_path / "test.db")
        conn.row_factory = sqlite3.Row
        applied = {
            row["migration_id"]
            for row in conn.execute("SELECT migration_id FROM schema_migrations").fetchall()
        }
        conn.close()
        assert {m["id"] for m in ALL_MIGRATIONS} == applied

    def test_reinitializing_repository_is_idempotent(self, tmp_path: Path):
        from fleet_health_orchestrator.repository import FleetRepository

        db = tmp_path / "test.db"
        FleetRepository(db_path=db)
        # Second construction must not raise or duplicate migrations
        FleetRepository(db_path=db)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        conn.close()
        assert count == len(ALL_MIGRATIONS)
