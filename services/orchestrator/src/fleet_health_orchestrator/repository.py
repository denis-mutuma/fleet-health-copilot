"""Persistence layer for telemetry, incidents, RAG documents, and ingestion jobs."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta as _timedelta, timezone
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

from fleet_health_orchestrator.migrations import ALL_MIGRATIONS
from fleet_health_orchestrator.migrations.runner import apply_migrations
from fleet_health_orchestrator.models import AuditEvent, IncidentReport, IncidentStatusHistoryEntry, TelemetryEvent


def _utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class FleetRepository:
    def __init__(self, db_path: Path, database_url: str = "") -> None:
        self.db_path = db_path
        self.database_url = database_url
        self._use_postgres = database_url.startswith(("postgres://", "postgresql://"))

        if not self._use_postgres:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @contextmanager
    def _connect(self) -> Generator[Any, None, None]:
        """Yield a DB connection and handle commit/rollback consistently."""
        if self._use_postgres:
            import psycopg
            from psycopg.rows import dict_row

            connection = psycopg.connect(self.database_url, row_factory=dict_row)
        else:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row

        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _sql(self, sqlite_query: str, postgres_query: str) -> str:
        """Select backend-specific SQL text for SQLite or PostgreSQL."""
        return postgres_query if self._use_postgres else sqlite_query

    def _init_db(self) -> None:
        """Run all pending schema migrations."""
        with self._connect() as connection:
            apply_migrations(
                connection,
                ALL_MIGRATIONS,
                use_postgres=self._use_postgres,
                now_iso=_utc_now_iso(),
            )

    def _incident_from_row(
        self,
        row: sqlite3.Row,
        *,
        status_history: list[IncidentStatusHistoryEntry] | None = None,
        audit_events: list[AuditEvent] | None = None,
    ) -> IncidentReport:
        return IncidentReport(
            incident_id=row["incident_id"],
            tenant_id=row.get("tenant_id") if hasattr(row, "get") else row["tenant_id"],
            device_id=row["device_id"],
            status=row["status"],
            summary=row["summary"],
            root_cause_hypotheses=json.loads(row["root_cause_hypotheses_json"]),
            recommended_actions=json.loads(row["recommended_actions_json"]),
            evidence=json.loads(row["evidence_json"]),
            confidence_score=row["confidence_score"],
            agent_trace=json.loads(row["agent_trace_json"]),
            verification=json.loads(row["verification_json"]),
            latency_ms=row["latency_ms"],
            status_history=status_history or [],
            audit_events=audit_events or [],
        )

    def _status_history_from_rows(self, rows: list[sqlite3.Row]) -> list[IncidentStatusHistoryEntry]:
        return [
            IncidentStatusHistoryEntry(
                history_id=row["history_id"],
                incident_id=row["incident_id"],
                previous_status=row["previous_status"],
                status=row["status"],
                changed_at=_coerce_datetime(row["changed_at"]),
                actor=row["actor"],
                source=row["source"],
                reason=row["reason"],
            )
            for row in rows
        ]

    def _audit_events_from_rows(self, rows: list[sqlite3.Row]) -> list[AuditEvent]:
        return [
            AuditEvent(
                event_id=row["event_id"],
                tenant_id=row.get("tenant_id") if hasattr(row, "get") else row["tenant_id"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                action=row["action"],
                actor=row["actor"],
                source=row["source"],
                occurred_at=_coerce_datetime(row["occurred_at"]),
                details=json.loads(row["details_json"]),
            )
            for row in rows
        ]

    def _list_incident_status_history(self, connection: Any, incident_id: str) -> list[IncidentStatusHistoryEntry]:
        rows = connection.execute(
            self._sql(
                """
                SELECT history_id, incident_id, previous_status, status, changed_at, actor, source, reason
                FROM incident_status_history
                WHERE incident_id = ?
                ORDER BY changed_at DESC, history_id DESC
                """,
                """
                SELECT history_id, incident_id, previous_status, status, changed_at, actor, source, reason
                FROM incident_status_history
                WHERE incident_id = %s
                ORDER BY changed_at DESC, history_id DESC
                """,
            ),
            (incident_id,),
        ).fetchall()
        return self._status_history_from_rows(rows)

    def _list_incident_audit_events(self, connection: Any, incident_id: str) -> list[AuditEvent]:
        rows = connection.execute(
            self._sql(
                """
                SELECT event_id, tenant_id, entity_type, entity_id, action, actor, source, details_json, occurred_at
                FROM audit_events
                WHERE entity_type = ? AND entity_id = ?
                ORDER BY occurred_at DESC, event_id DESC
                """,
                """
                SELECT event_id, tenant_id, entity_type, entity_id, action, actor, source, details_json, occurred_at
                FROM audit_events
                WHERE entity_type = %s AND entity_id = %s
                ORDER BY occurred_at DESC, event_id DESC
                """,
            ),
            ("incident", incident_id),
        ).fetchall()
        return self._audit_events_from_rows(rows)

    def list_audit_events(
        self,
        *,
        limit: int = 100,
        tenant_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[AuditEvent]:
        capped_limit = max(1, min(limit, 500))
        conditions: list[str] = []
        params: list[object] = []

        placeholder = "%s" if self._use_postgres else "?"

        if tenant_id is not None:
            conditions.append(f"tenant_id = {placeholder}")
            params.append(tenant_id)
        if entity_type is not None:
            conditions.append(f"entity_type = {placeholder}")
            params.append(entity_type)
        if entity_id is not None:
            conditions.append(f"entity_id = {placeholder}")
            params.append(entity_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            "SELECT event_id, tenant_id, entity_type, entity_id, action, actor, source, details_json, occurred_at "
            "FROM audit_events "
            f"{where_clause} "
            "ORDER BY occurred_at DESC, event_id DESC "
            f"LIMIT {placeholder}"
        )
        params.append(capped_limit)

        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return self._audit_events_from_rows(rows)

    def _record_incident_status_history(
        self,
        connection: Any,
        *,
        incident_id: str,
        tenant_id: str | None,
        previous_status: str | None,
        status: str,
        actor: str,
        source: str,
        reason: str | None,
    ) -> None:
        connection.execute(
            self._sql(
                """
                INSERT INTO incident_status_history
                (history_id, incident_id, tenant_id, previous_status, status, changed_at, actor, source, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                """
                INSERT INTO incident_status_history
                (history_id, incident_id, tenant_id, previous_status, status, changed_at, actor, source, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
            ),
            (
                f"hist_{uuid4().hex}",
                incident_id,
                tenant_id,
                previous_status,
                status,
                _utc_now_iso(),
                actor,
                source,
                reason,
            ),
        )

    def _record_audit_event(
        self,
        connection: Any,
        *,
        tenant_id: str | None,
        entity_type: str,
        entity_id: str,
        action: str,
        actor: str,
        source: str,
        details: dict[str, object],
    ) -> None:
        connection.execute(
            self._sql(
                """
                INSERT INTO audit_events
                (event_id, tenant_id, entity_type, entity_id, action, actor, source, details_json, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                """
                INSERT INTO audit_events
                (event_id, tenant_id, entity_type, entity_id, action, actor, source, details_json, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
            ),
            (
                f"audit_{uuid4().hex}",
                tenant_id,
                entity_type,
                entity_id,
                action,
                actor,
                source,
                json.dumps(details),
                _utc_now_iso(),
            ),
        )

    def _ensure_incident_lifecycle_records(self, connection: Any, incident: IncidentReport) -> None:
        history_exists = connection.execute(
            self._sql(
                "SELECT 1 FROM incident_status_history WHERE incident_id = ? LIMIT 1",
                "SELECT 1 FROM incident_status_history WHERE incident_id = %s LIMIT 1",
            ),
            (incident.incident_id,),
        ).fetchone()
        if history_exists is None:
            self._record_incident_status_history(
                connection,
                incident_id=incident.incident_id,
                tenant_id=incident.tenant_id,
                previous_status=None,
                status=incident.status,
                actor="system:orchestrator",
                source="orchestrator.event",
                reason="Incident created from telemetry orchestration.",
            )

        audit_exists = connection.execute(
            self._sql(
                "SELECT 1 FROM audit_events WHERE entity_type = ? AND entity_id = ? AND action = ? LIMIT 1",
                "SELECT 1 FROM audit_events WHERE entity_type = %s AND entity_id = %s AND action = %s LIMIT 1",
            ),
            ("incident", incident.incident_id, "incident.created"),
        ).fetchone()
        if audit_exists is None:
            self._record_audit_event(
                connection,
                tenant_id=incident.tenant_id,
                entity_type="incident",
                entity_id=incident.incident_id,
                action="incident.created",
                actor="system:orchestrator",
                source="orchestrator.event",
                details={
                    "status": incident.status,
                    "device_id": incident.device_id,
                    "summary": incident.summary,
                },
            )

    def insert_event(self, event: TelemetryEvent, *, tenant_id: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO events
                                        (event_id, tenant_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO events
                                        (event_id, tenant_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO UPDATE SET
                                            tenant_id = EXCLUDED.tenant_id,
                      fleet_id = EXCLUDED.fleet_id,
                      device_id = EXCLUDED.device_id,
                      timestamp = EXCLUDED.timestamp,
                      metric = EXCLUDED.metric,
                      value = EXCLUDED.value,
                      threshold = EXCLUDED.threshold,
                      severity = EXCLUDED.severity,
                      tags_json = EXCLUDED.tags_json
                    """,
                ),
                (
                    event.event_id,
                    tenant_id,
                    event.fleet_id,
                    event.device_id,
                    event.timestamp.isoformat(),
                    event.metric,
                    event.value,
                    event.threshold,
                    event.severity,
                    json.dumps(event.tags)
                )
            )

    def list_events(self, *, tenant_id: str | None = None) -> list[TelemetryEvent]:
        with self._connect() as connection:
            if tenant_id is None:
                rows = connection.execute(
                    """
                    SELECT event_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json
                    FROM events
                    ORDER BY timestamp DESC
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql(
                        """
                        SELECT event_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json
                        FROM events
                        WHERE tenant_id = ?
                        ORDER BY timestamp DESC
                        """,
                        """
                        SELECT event_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json
                        FROM events
                        WHERE tenant_id = %s
                        ORDER BY timestamp DESC
                        """,
                    ),
                    (tenant_id,),
                ).fetchall()

        return [
            TelemetryEvent(
                event_id=row["event_id"],
                fleet_id=row["fleet_id"],
                device_id=row["device_id"],
                timestamp=row["timestamp"] if isinstance(row["timestamp"], datetime) else datetime.fromisoformat(row["timestamp"]),
                metric=row["metric"],
                value=row["value"],
                threshold=row["threshold"],
                severity=row["severity"],
                tags=json.loads(row["tags_json"])
            )
            for row in rows
        ]

    def insert_incident(self, incident: IncidentReport, *, tenant_id: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO incidents
                    (
                        incident_id,
                        tenant_id,
                        device_id,
                        status,
                        summary,
                        root_cause_hypotheses_json,
                        recommended_actions_json,
                        evidence_json,
                        confidence_score,
                        agent_trace_json,
                        verification_json,
                        latency_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO incidents
                    (
                        incident_id,
                        tenant_id,
                        device_id,
                        status,
                        summary,
                        root_cause_hypotheses_json,
                        recommended_actions_json,
                        evidence_json,
                        confidence_score,
                        agent_trace_json,
                        verification_json,
                        latency_ms
                    )
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (incident_id) DO UPDATE SET
                                            tenant_id = EXCLUDED.tenant_id,
                      device_id = EXCLUDED.device_id,
                      status = EXCLUDED.status,
                      summary = EXCLUDED.summary,
                      root_cause_hypotheses_json = EXCLUDED.root_cause_hypotheses_json,
                      recommended_actions_json = EXCLUDED.recommended_actions_json,
                      evidence_json = EXCLUDED.evidence_json,
                      confidence_score = EXCLUDED.confidence_score,
                      agent_trace_json = EXCLUDED.agent_trace_json,
                      verification_json = EXCLUDED.verification_json,
                      latency_ms = EXCLUDED.latency_ms
                    """,
                ),
                (
                    incident.incident_id,
                    tenant_id,
                    incident.device_id,
                    incident.status,
                    incident.summary,
                    json.dumps(incident.root_cause_hypotheses),
                    json.dumps(incident.recommended_actions),
                    json.dumps(incident.evidence),
                    incident.confidence_score,
                    json.dumps(incident.agent_trace),
                    json.dumps(incident.verification),
                    incident.latency_ms
                )
            )
            incident_for_lifecycle = incident.model_copy(update={"tenant_id": tenant_id})
            self._ensure_incident_lifecycle_records(connection, incident_for_lifecycle)

    def list_incidents(self, *, tenant_id: str | None = None) -> list[IncidentReport]:
        with self._connect() as connection:
            if tenant_id is None:
                rows = connection.execute(
                    """
                    SELECT incident_id, tenant_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                    FROM incidents
                    ORDER BY incident_id DESC
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql(
                        """
                        SELECT incident_id, tenant_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                        FROM incidents
                        WHERE tenant_id = ?
                        ORDER BY incident_id DESC
                        """,
                        """
                        SELECT incident_id, tenant_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                        FROM incidents
                        WHERE tenant_id = %s
                        ORDER BY incident_id DESC
                        """,
                    ),
                    (tenant_id,),
                ).fetchall()

        return [self._incident_from_row(row) for row in rows]

    def get_incident(self, incident_id: str, *, tenant_id: str | None = None) -> IncidentReport | None:
        with self._connect() as connection:
            if tenant_id is None:
                row = connection.execute(
                    self._sql(
                        """
                    SELECT incident_id, tenant_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                    FROM incidents
                    WHERE incident_id = ?
                    """,
                        """
                    SELECT incident_id, tenant_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                    FROM incidents
                    WHERE incident_id = %s
                    """,
                    ),
                    (incident_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    self._sql(
                        """
                    SELECT incident_id, tenant_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                    FROM incidents
                    WHERE incident_id = ? AND tenant_id = ?
                    """,
                        """
                    SELECT incident_id, tenant_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                    FROM incidents
                    WHERE incident_id = %s AND tenant_id = %s
                    """,
                    ),
                    (incident_id, tenant_id),
                ).fetchone()

            if row is None:
                return None

            status_history = self._list_incident_status_history(connection, incident_id)
            audit_events = self._list_incident_audit_events(connection, incident_id)

        return self._incident_from_row(
            row,
            status_history=status_history,
            audit_events=audit_events,
        )

    def update_incident_status(
        self,
        incident_id: str,
        status: str,
        *,
        actor: str = "system:api",
        reason: str | None = None,
        source: str = "api.incidents",
        tenant_id: str | None = None,
    ) -> IncidentReport | None:
        with self._connect() as connection:
            if tenant_id is None:
                existing = connection.execute(
                    self._sql(
                        "SELECT status FROM incidents WHERE incident_id = ?",
                        "SELECT status FROM incidents WHERE incident_id = %s",
                    ),
                    (incident_id,),
                ).fetchone()
            else:
                existing = connection.execute(
                    self._sql(
                        "SELECT status FROM incidents WHERE incident_id = ? AND tenant_id = ?",
                        "SELECT status FROM incidents WHERE incident_id = %s AND tenant_id = %s",
                    ),
                    (incident_id, tenant_id),
                ).fetchone()
            if existing is None:
                return None

            previous_status = str(existing["status"])
            if previous_status == status:
                return self.get_incident(incident_id)

            cursor = connection.execute(
                self._sql(
                    """
                    UPDATE incidents
                    SET status = ?
                    WHERE incident_id = ?
                    """,
                    """
                    UPDATE incidents
                    SET status = %s
                    WHERE incident_id = %s
                    """,
                ),
                (status, incident_id)
            )
            row_count = cursor.rowcount

            if row_count > 0:
                self._record_incident_status_history(
                    connection,
                    incident_id=incident_id,
                    tenant_id=tenant_id,
                    previous_status=previous_status,
                    status=status,
                    actor=actor,
                    source=source,
                    reason=reason,
                )
                self._record_audit_event(
                    connection,
                    tenant_id=tenant_id,
                    entity_type="incident",
                    entity_id=incident_id,
                    action="incident.status_updated",
                    actor=actor,
                    source=source,
                    details={
                        "from_status": previous_status,
                        "to_status": status,
                        **({"reason": reason} if reason else {}),
                    },
                )

        if row_count == 0:
            return None

        return self.get_incident(incident_id, tenant_id=tenant_id)

    def insert_rag_document(
        self,
        document_id: str,
        source: str,
        title: str,
        content: str,
        tags: list[str],
        *,
        tenant_id: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO rag_documents
                    (document_id, tenant_id, source, title, content, tags_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO rag_documents
                    (document_id, tenant_id, source, title, content, tags_json)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (document_id) DO UPDATE SET
                      tenant_id = EXCLUDED.tenant_id,
                      source = EXCLUDED.source,
                      title = EXCLUDED.title,
                      content = EXCLUDED.content,
                      tags_json = EXCLUDED.tags_json
                    """,
                ),
                (
                    document_id,
                    tenant_id,
                    source,
                    title,
                    content,
                    json.dumps(tags)
                )
            )

    def list_rag_documents(self, *, tenant_id: str | None = None) -> list[dict[str, object]]:
        with self._connect() as connection:
            if tenant_id is None:
                rows = connection.execute(
                    """
                    SELECT document_id, tenant_id, source, title, content, tags_json
                    FROM rag_documents
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql(
                        """
                        SELECT document_id, tenant_id, source, title, content, tags_json
                        FROM rag_documents
                        WHERE tenant_id = ?
                        """,
                        """
                        SELECT document_id, tenant_id, source, title, content, tags_json
                        FROM rag_documents
                        WHERE tenant_id = %s
                        """,
                    ),
                    (tenant_id,),
                ).fetchall()

        return [
            {
                "document_id": row["document_id"],
                "tenant_id": row["tenant_id"],
                "source": row["source"],
                "title": row["title"],
                "content": row["content"],
                "tags": json.loads(row["tags_json"])
            }
            for row in rows
        ]

    def delete_rag_document_family(self, document_id: str, *, tenant_id: str | None = None) -> int:
        with self._connect() as connection:
            if tenant_id is None:
                cursor = connection.execute(
                    self._sql(
                        """
                        DELETE FROM rag_documents
                        WHERE document_id = ? OR document_id LIKE ?
                        """,
                        """
                        DELETE FROM rag_documents
                        WHERE document_id = %s OR document_id LIKE %s
                        """,
                    ),
                    (document_id, f"{document_id}#chunk-%"),
                )
            else:
                cursor = connection.execute(
                    self._sql(
                        """
                        DELETE FROM rag_documents
                        WHERE tenant_id = ? AND (document_id = ? OR document_id LIKE ?)
                        """,
                        """
                        DELETE FROM rag_documents
                        WHERE tenant_id = %s AND (document_id = %s OR document_id LIKE %s)
                        """,
                    ),
                    (tenant_id, document_id, f"{document_id}#chunk-%"),
                )

        return int(cursor.rowcount)

    def insert_rag_ingestion_job(
        self,
        *,
        job_id: str,
        tenant_id: str | None,
        source: str,
        title: str,
        tags: list[str],
        filename: str,
        idempotency_key: str | None,
    ) -> None:
        now = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT INTO rag_ingestion_jobs
                    (job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO rag_ingestion_jobs
                    (job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                ),
                (
                    job_id,
                    tenant_id,
                    "pending",
                    source,
                    title,
                    json.dumps(tags),
                    filename,
                    idempotency_key,
                    now,
                    now,
                ),
            )

    def update_rag_ingestion_job(
        self,
        *,
        job_id: str,
        status: str,
        document_id: str | None = None,
        chunk_count: int | None = None,
        indexed_chunks: int | None = None,
        error_message: str | None = None,
    ) -> None:
        now = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    UPDATE rag_ingestion_jobs
                    SET status = ?,
                        document_id = COALESCE(?, document_id),
                        chunk_count = COALESCE(?, chunk_count),
                        indexed_chunks = COALESCE(?, indexed_chunks),
                        error_message = ?,
                        updated_at = ?
                    WHERE job_id = ?
                    """,
                    """
                    UPDATE rag_ingestion_jobs
                    SET status = %s,
                        document_id = COALESCE(%s, document_id),
                        chunk_count = COALESCE(%s, chunk_count),
                        indexed_chunks = COALESCE(%s, indexed_chunks),
                        error_message = %s,
                        updated_at = %s
                    WHERE job_id = %s
                    """,
                ),
                (
                    status,
                    document_id,
                    chunk_count,
                    indexed_chunks,
                    error_message,
                    now,
                    job_id,
                ),
            )

    def get_rag_ingestion_job(self, job_id: str, *, tenant_id: str | None = None) -> dict[str, object] | None:
        with self._connect() as connection:
            if tenant_id is None:
                row = connection.execute(
                    self._sql(
                        """
                        SELECT job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key,
                               document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                        FROM rag_ingestion_jobs
                        WHERE job_id = ?
                        """,
                        """
                        SELECT job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key,
                               document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                        FROM rag_ingestion_jobs
                        WHERE job_id = %s
                        """,
                    ),
                    (job_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    self._sql(
                        """
                        SELECT job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key,
                               document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                        FROM rag_ingestion_jobs
                        WHERE job_id = ? AND tenant_id = ?
                        """,
                        """
                        SELECT job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key,
                               document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                        FROM rag_ingestion_jobs
                        WHERE job_id = %s AND tenant_id = %s
                        """,
                    ),
                    (job_id, tenant_id),
                ).fetchone()

        if row is None:
            return None

        return {
            "job_id": row["job_id"],
            "tenant_id": row["tenant_id"],
            "status": row["status"],
            "source": row["source"],
            "title": row["title"],
            "tags": json.loads(row["tags_json"]),
            "filename": row["filename"],
            "idempotency_key": row["idempotency_key"],
            "document_id": row["document_id"],
            "chunk_count": int(row["chunk_count"]),
            "indexed_chunks": int(row["indexed_chunks"]),
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_rag_ingestion_job_by_idempotency_key(
        self,
        idempotency_key: str,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._connect() as connection:
            if tenant_id is None:
                row = connection.execute(
                    self._sql(
                        """
                        SELECT job_id
                        FROM rag_ingestion_jobs
                        WHERE idempotency_key = ?
                        """,
                        """
                        SELECT job_id
                        FROM rag_ingestion_jobs
                        WHERE idempotency_key = %s
                        """,
                    ),
                    (idempotency_key,),
                ).fetchone()
            else:
                row = connection.execute(
                    self._sql(
                        """
                        SELECT job_id
                        FROM rag_ingestion_jobs
                        WHERE idempotency_key = ? AND tenant_id = ?
                        """,
                        """
                        SELECT job_id
                        FROM rag_ingestion_jobs
                        WHERE idempotency_key = %s AND tenant_id = %s
                        """,
                    ),
                    (idempotency_key, tenant_id),
                ).fetchone()

        if row is None:
            return None
        return self.get_rag_ingestion_job(str(row["job_id"]), tenant_id=tenant_id)

    def list_rag_ingestion_jobs(self, limit: int = 20, *, tenant_id: str | None = None) -> list[dict[str, object]]:
        capped_limit = max(1, min(limit, 200))
        with self._connect() as connection:
            if tenant_id is None:
                rows = connection.execute(
                    self._sql(
                        """
                        SELECT job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key,
                               document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                        FROM rag_ingestion_jobs
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        """
                        SELECT job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key,
                               document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                        FROM rag_ingestion_jobs
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                    ),
                    (capped_limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql(
                        """
                        SELECT job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key,
                               document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                        FROM rag_ingestion_jobs
                        WHERE tenant_id = ?
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        """
                        SELECT job_id, tenant_id, status, source, title, tags_json, filename, idempotency_key,
                               document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                        FROM rag_ingestion_jobs
                        WHERE tenant_id = %s
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                    ),
                    (tenant_id, capped_limit),
                ).fetchall()

        return [
            {
                "job_id": row["job_id"],
                "tenant_id": row["tenant_id"],
                "status": row["status"],
                "source": row["source"],
                "title": row["title"],
                "tags": json.loads(row["tags_json"]),
                "filename": row["filename"],
                "idempotency_key": row["idempotency_key"],
                "document_id": row["document_id"],
                "chunk_count": int(row["chunk_count"]),
                "indexed_chunks": int(row["indexed_chunks"]),
                "error_message": row["error_message"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def create_chat_session(
        self,
        *,
        session_id: str,
        incident_id: str | None,
        tenant_id: str | None = None,
    ) -> dict[str, object]:
        now = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO chat_sessions
                    (session_id, tenant_id, incident_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO chat_sessions
                    (session_id, tenant_id, incident_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                      tenant_id = EXCLUDED.tenant_id,
                      incident_id = EXCLUDED.incident_id,
                      updated_at = EXCLUDED.updated_at
                    """,
                ),
                (session_id, tenant_id, incident_id, now, now),
            )

        return {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "incident_id": incident_id,
            "created_at": now,
            "updated_at": now,
        }

    def get_chat_session(self, session_id: str, *, tenant_id: str | None = None) -> dict[str, object] | None:
        with self._connect() as connection:
            if tenant_id is None:
                row = connection.execute(
                    self._sql(
                        """
                        SELECT session_id, tenant_id, incident_id, created_at, updated_at
                        FROM chat_sessions
                        WHERE session_id = ?
                        """,
                        """
                        SELECT session_id, tenant_id, incident_id, created_at, updated_at
                        FROM chat_sessions
                        WHERE session_id = %s
                        """,
                    ),
                    (session_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    self._sql(
                        """
                        SELECT session_id, tenant_id, incident_id, created_at, updated_at
                        FROM chat_sessions
                        WHERE session_id = ? AND tenant_id = ?
                        """,
                        """
                        SELECT session_id, tenant_id, incident_id, created_at, updated_at
                        FROM chat_sessions
                        WHERE session_id = %s AND tenant_id = %s
                        """,
                    ),
                    (session_id, tenant_id),
                ).fetchone()

        if row is None:
            return None

        return {
            "session_id": row["session_id"],
            "tenant_id": row["tenant_id"],
            "incident_id": row["incident_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_chat_sessions(self, limit: int = 50, *, tenant_id: str | None = None) -> list[dict[str, object]]:
        capped_limit = max(1, min(limit, 200))
        with self._connect() as connection:
            if tenant_id is None:
                rows = connection.execute(
                    self._sql(
                        """
                        SELECT session_id, tenant_id, incident_id, created_at, updated_at
                        FROM chat_sessions
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        """
                        SELECT session_id, tenant_id, incident_id, created_at, updated_at
                        FROM chat_sessions
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                    ),
                    (capped_limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql(
                        """
                        SELECT session_id, tenant_id, incident_id, created_at, updated_at
                        FROM chat_sessions
                        WHERE tenant_id = ?
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        """
                        SELECT session_id, tenant_id, incident_id, created_at, updated_at
                        FROM chat_sessions
                        WHERE tenant_id = %s
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                    ),
                    (tenant_id, capped_limit),
                ).fetchall()

        return [
            {
                "session_id": row["session_id"],
                "tenant_id": row["tenant_id"],
                "incident_id": row["incident_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def insert_chat_message(
        self,
        *,
        message_id: str,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict[str, object]] | None = None,
        action: str | None = None,
        action_status: str | None = None,
        action_payload: dict[str, object] | None = None,
        tool_calls: list[dict[str, object]] | None = None,
        trace_spans: list[dict[str, object]] | None = None,
        llm_cost_usd: float | None = None,
    ) -> dict[str, object]:
        now = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO chat_messages
                    (message_id, session_id, role, content, citations_json, action, action_status, action_payload_json, tool_calls_json, trace_spans_json, llm_cost_usd, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO chat_messages
                    (message_id, session_id, role, content, citations_json, action, action_status, action_payload_json, tool_calls_json, trace_spans_json, llm_cost_usd, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (message_id) DO UPDATE SET
                      role = EXCLUDED.role,
                      content = EXCLUDED.content,
                      citations_json = EXCLUDED.citations_json,
                      action = EXCLUDED.action,
                      action_status = EXCLUDED.action_status,
                      action_payload_json = EXCLUDED.action_payload_json,
                      tool_calls_json = EXCLUDED.tool_calls_json,
                      trace_spans_json = EXCLUDED.trace_spans_json,
                      llm_cost_usd = EXCLUDED.llm_cost_usd
                    """,
                ),
                (
                    message_id,
                    session_id,
                    role,
                    content,
                    json.dumps(citations or []),
                    action,
                    action_status,
                    json.dumps(action_payload or {}),
                    json.dumps(tool_calls or []),
                    json.dumps(trace_spans or []),
                    llm_cost_usd,
                    now,
                ),
            )
            connection.execute(
                self._sql(
                    """
                    UPDATE chat_sessions
                    SET updated_at = ?
                    WHERE session_id = ?
                    """,
                    """
                    UPDATE chat_sessions
                    SET updated_at = %s
                    WHERE session_id = %s
                    """,
                ),
                (now, session_id),
            )

        return {
            "message_id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "citations": citations or [],
            "action": action,
            "action_status": action_status,
            "action_payload": action_payload or {},
            "tool_calls": tool_calls or [],
            "trace_spans": trace_spans or [],
            "llm_cost_usd": llm_cost_usd,
            "created_at": now,
        }

    def list_chat_messages(self, session_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                self._sql(
                    """
                    SELECT message_id, session_id, role, content, citations_json, action, action_status, action_payload_json, tool_calls_json, trace_spans_json, llm_cost_usd, created_at
                    FROM chat_messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    """,
                    """
                    SELECT message_id, session_id, role, content, citations_json, action, action_status, action_payload_json, tool_calls_json, trace_spans_json, llm_cost_usd, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    """,
                ),
                (session_id,),
            ).fetchall()

        return [
            {
                "message_id": row["message_id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "content": row["content"],
                "citations": json.loads(row["citations_json"]),
                "action": row["action"],
                "action_status": row["action_status"],
                "action_payload": json.loads(row["action_payload_json"]),
                "tool_calls": json.loads(row["tool_calls_json"] or "[]"),
                "trace_spans": json.loads(row["trace_spans_json"] or "[]"),
                "llm_cost_usd": row["llm_cost_usd"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def purge_expired_audit_events(self, *, now: datetime | None = None) -> dict[str, int]:
        """Delete audit events that have exceeded their configured retention period.

        Reads all rows from ``audit_retention_policy`` where ``retention_days``
        is not NULL.  For each policy, computes a cutoff timestamp
        ``(now - retention_days days)`` and hard-deletes matching rows from
        ``audit_events``.

        A policy row with ``tenant_id IS NULL`` and ``entity_type IS NULL``
        applies globally.  When either column is set, it scopes the delete
        to that tenant or entity type respectively.

        Returns a dict ``{"audit_events_deleted": <total>}`` summarising
        what was removed.
        """
        reference = now or datetime.now(timezone.utc)
        total_deleted = 0

        with self._connect() as connection:
            placeholder = "%s" if self._use_postgres else "?"

            policy_rows = connection.execute(
                "SELECT policy_id, tenant_id, entity_type, retention_days "
                "FROM audit_retention_policy "
                "WHERE retention_days IS NOT NULL"
            ).fetchall()

            for policy in policy_rows:
                retention_days = int(policy["retention_days"])
                if retention_days <= 0:
                    continue

                cutoff = reference - _timedelta(days=retention_days)
                cutoff_iso = cutoff.isoformat()

                conditions = [f"occurred_at < {placeholder}"]
                params: list[object] = [cutoff_iso]

                policy_tenant = policy["tenant_id"]
                policy_entity_type = policy["entity_type"]

                if policy_tenant is not None:
                    conditions.append(f"tenant_id = {placeholder}")
                    params.append(policy_tenant)
                if policy_entity_type is not None:
                    conditions.append(f"entity_type = {placeholder}")
                    params.append(policy_entity_type)

                where_clause = " AND ".join(conditions)
                cursor = connection.execute(
                    f"DELETE FROM audit_events WHERE {where_clause}",
                    tuple(params),
                )
                deleted = cursor.rowcount if cursor.rowcount is not None else 0
                total_deleted += deleted

        return {"audit_events_deleted": total_deleted}
