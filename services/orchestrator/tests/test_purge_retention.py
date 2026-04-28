"""Tests for audit event retention — FleetRepository.purge_expired_audit_events()."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from fleet_health_orchestrator.repository import FleetRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_repo(tmp_path: Path) -> FleetRepository:
    return FleetRepository(db_path=tmp_path / "test.db")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_policy(repo: FleetRepository, *, retention_days: int, tenant_id: str | None = None, entity_type: str | None = None) -> str:
    policy_id = f"pol_{uuid4().hex[:8]}"
    now_iso = _now().isoformat()
    with repo._connect() as conn:
        conn.execute(
            "INSERT INTO audit_retention_policy "
            "(policy_id, tenant_id, entity_type, retention_days, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (policy_id, tenant_id, entity_type, retention_days, now_iso, now_iso),
        )
    return policy_id


def _seed_audit_event(repo: FleetRepository, *, occurred_at: datetime, tenant_id: str | None = None, entity_type: str = "incident") -> str:
    event_id = f"audit_{uuid4().hex}"
    with repo._connect() as conn:
        conn.execute(
            "INSERT INTO audit_events "
            "(event_id, tenant_id, entity_type, entity_id, action, actor, source, details_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                tenant_id,
                entity_type,
                f"ent_{uuid4().hex[:8]}",
                "test.action",
                "system:test",
                "test",
                "{}",
                _iso(occurred_at),
            ),
        )
    return event_id


def _count_audit_events(repo: FleetRepository) -> int:
    with repo._connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM audit_events").fetchone()
    return int(row["cnt"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPurgeExpiredAuditEvents:
    def test_no_policies_returns_zero(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        result = repo.purge_expired_audit_events()
        assert result == {"audit_events_deleted": 0}

    def test_no_events_older_than_cutoff_returns_zero(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        _seed_policy(repo, retention_days=30)
        # Seed a fresh event (5 days old — within retention)
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=5))
        result = repo.purge_expired_audit_events()
        assert result == {"audit_events_deleted": 0}
        assert _count_audit_events(repo) == 1

    def test_deletes_events_older_than_retention(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        _seed_policy(repo, retention_days=30)
        # One expired event (40 days old)
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=40))
        # One fresh event (10 days old)
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=10))

        result = repo.purge_expired_audit_events()
        assert result == {"audit_events_deleted": 1}
        assert _count_audit_events(repo) == 1

    def test_global_policy_deletes_across_tenants(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        # Global policy (tenant_id=None)
        _seed_policy(repo, retention_days=7)
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=10), tenant_id="acme")
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=10), tenant_id="beta")
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=3), tenant_id="acme")

        result = repo.purge_expired_audit_events()
        assert result == {"audit_events_deleted": 2}
        assert _count_audit_events(repo) == 1

    def test_tenant_scoped_policy_only_deletes_matching_tenant(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        _seed_policy(repo, retention_days=7, tenant_id="acme")
        # Expired, matching tenant — should be deleted
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=10), tenant_id="acme")
        # Expired, different tenant — should NOT be deleted
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=10), tenant_id="beta")

        result = repo.purge_expired_audit_events()
        assert result == {"audit_events_deleted": 1}
        assert _count_audit_events(repo) == 1

    def test_entity_type_scoped_policy_only_deletes_matching_entity_type(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        _seed_policy(repo, retention_days=7, entity_type="incident")
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=10), entity_type="incident")
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=10), entity_type="device")

        result = repo.purge_expired_audit_events()
        assert result == {"audit_events_deleted": 1}

    def test_multiple_policies_accumulate_deleted_count(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        _seed_policy(repo, retention_days=7, tenant_id="acme")
        _seed_policy(repo, retention_days=14, tenant_id="beta")

        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=10), tenant_id="acme")
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=20), tenant_id="beta")

        result = repo.purge_expired_audit_events()
        assert result["audit_events_deleted"] == 2

    def test_policy_with_zero_retention_days_skipped(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        _seed_policy(repo, retention_days=0)
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=9999))

        result = repo.purge_expired_audit_events()
        # retention_days=0 is ignored; nothing deleted
        assert result == {"audit_events_deleted": 0}

    def test_custom_now_parameter(self, tmp_path: Path) -> None:
        """Allowing injection of 'now' enables deterministic testing."""
        repo = _tmp_repo(tmp_path)
        _seed_policy(repo, retention_days=30)
        reference = datetime(2030, 6, 1, tzinfo=timezone.utc)
        # Event occurred 31 days before our reference point
        _seed_audit_event(repo, occurred_at=reference - timedelta(days=31))
        # Event occurred 5 days before reference — should be kept
        _seed_audit_event(repo, occurred_at=reference - timedelta(days=5))

        result = repo.purge_expired_audit_events(now=reference)
        assert result == {"audit_events_deleted": 1}
        assert _count_audit_events(repo) == 1

    def test_idempotent_second_sweep(self, tmp_path: Path) -> None:
        repo = _tmp_repo(tmp_path)
        _seed_policy(repo, retention_days=7)
        _seed_audit_event(repo, occurred_at=_now() - timedelta(days=30))

        result1 = repo.purge_expired_audit_events()
        result2 = repo.purge_expired_audit_events()

        assert result1 == {"audit_events_deleted": 1}
        assert result2 == {"audit_events_deleted": 0}
