"""Persistence layer for telemetry, incidents, RAG documents, and ingestion jobs."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fleet_health_orchestrator.models import IncidentReport, TelemetryEvent


def _utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class FleetRepository:
    def __init__(self, db_path: Path, database_url: str = "") -> None:
        self.db_path = db_path
        self.database_url = database_url
        self._use_postgres = database_url.startswith(("postgres://", "postgresql://"))

        if not self._use_postgres:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @contextmanager
    def _connect(self):
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
        """Create and evolve repository tables required by current API behavior."""
        with self._connect() as connection:
            connection.execute(
                """
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
                """
            )
            connection.execute(
                """
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
                """
            )

            optional_columns = {
                "confidence_score": "DOUBLE PRECISION NOT NULL DEFAULT 0.0",
                "agent_trace_json": "TEXT NOT NULL DEFAULT '[]'",
                "verification_json": "TEXT NOT NULL DEFAULT '{}'",
                "latency_ms": "DOUBLE PRECISION NOT NULL DEFAULT 0.0",
            }

            if self._use_postgres:
                for column, definition in optional_columns.items():
                    connection.execute(
                        f"ALTER TABLE incidents ADD COLUMN IF NOT EXISTS {column} {definition}"
                    )
            else:
                incident_columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(incidents)").fetchall()
                }
                for column, definition in optional_columns.items():
                    if column not in incident_columns:
                        connection.execute(
                            f"ALTER TABLE incidents ADD COLUMN {column} {definition}"
                        )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_documents (
                    document_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL
                )
                """
            )

            connection.execute(
                self._sql(
                    """
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
                    """,
                    """
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
                    """,
                )
            )

            if self._use_postgres:
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_ingestion_jobs_idempotency_key ON rag_ingestion_jobs(idempotency_key)"
                )
            else:
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_ingestion_jobs_idempotency_key ON rag_ingestion_jobs(idempotency_key)"
                )

            connection.execute(
                self._sql(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        session_id TEXT PRIMARY KEY,
                        incident_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        session_id TEXT PRIMARY KEY,
                        incident_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """,
                )
            )

            connection.execute(
                self._sql(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        message_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        citations_json TEXT NOT NULL DEFAULT '[]',
                        action TEXT,
                        action_status TEXT,
                        action_payload_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
                    )
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        message_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES chat_sessions(session_id),
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        citations_json TEXT NOT NULL DEFAULT '[]',
                        action TEXT,
                        action_status TEXT,
                        action_payload_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                    """,
                )
            )

            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created_at ON chat_messages(session_id, created_at)"
            )

    def _incident_from_row(self, row: sqlite3.Row) -> IncidentReport:
        return IncidentReport(
            incident_id=row["incident_id"],
            device_id=row["device_id"],
            status=row["status"],
            summary=row["summary"],
            root_cause_hypotheses=json.loads(row["root_cause_hypotheses_json"]),
            recommended_actions=json.loads(row["recommended_actions_json"]),
            evidence=json.loads(row["evidence_json"]),
            confidence_score=row["confidence_score"],
            agent_trace=json.loads(row["agent_trace_json"]),
            verification=json.loads(row["verification_json"]),
            latency_ms=row["latency_ms"]
        )

    def insert_event(self, event: TelemetryEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO events
                    (event_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO events
                    (event_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO UPDATE SET
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

    def list_events(self) -> list[TelemetryEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json
                FROM events
                ORDER BY timestamp DESC
                """
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

    def insert_incident(self, incident: IncidentReport) -> None:
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO incidents
                    (
                        incident_id,
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO incidents
                    (
                        incident_id,
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (incident_id) DO UPDATE SET
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

    def list_incidents(self) -> list[IncidentReport]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT incident_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                FROM incidents
                ORDER BY incident_id DESC
                """
            ).fetchall()

        return [self._incident_from_row(row) for row in rows]

    def get_incident(self, incident_id: str) -> IncidentReport | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    """
                SELECT incident_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                FROM incidents
                WHERE incident_id = ?
                """,
                    """
                SELECT incident_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                FROM incidents
                WHERE incident_id = %s
                """,
                ),
                (incident_id,)
            ).fetchone()

        if row is None:
            return None

        return self._incident_from_row(row)

    def update_incident_status(
        self,
        incident_id: str,
        status: str
    ) -> IncidentReport | None:
        with self._connect() as connection:
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

        if row_count == 0:
            return None

        return self.get_incident(incident_id)

    def insert_rag_document(
        self,
        document_id: str,
        source: str,
        title: str,
        content: str,
        tags: list[str]
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO rag_documents
                    (document_id, source, title, content, tags_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO rag_documents
                    (document_id, source, title, content, tags_json)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (document_id) DO UPDATE SET
                      source = EXCLUDED.source,
                      title = EXCLUDED.title,
                      content = EXCLUDED.content,
                      tags_json = EXCLUDED.tags_json
                    """,
                ),
                (
                    document_id,
                    source,
                    title,
                    content,
                    json.dumps(tags)
                )
            )

    def list_rag_documents(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, source, title, content, tags_json
                FROM rag_documents
                """
            ).fetchall()

        return [
            {
                "document_id": row["document_id"],
                "source": row["source"],
                "title": row["title"],
                "content": row["content"],
                "tags": json.loads(row["tags_json"])
            }
            for row in rows
        ]

    def delete_rag_document_family(self, document_id: str) -> int:
        with self._connect() as connection:
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

        return int(cursor.rowcount)

    def insert_rag_ingestion_job(
        self,
        *,
        job_id: str,
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
                    (job_id, status, source, title, tags_json, filename, idempotency_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO rag_ingestion_jobs
                    (job_id, status, source, title, tags_json, filename, idempotency_key, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                ),
                (
                    job_id,
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

    def get_rag_ingestion_job(self, job_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    """
                    SELECT job_id, status, source, title, tags_json, filename, idempotency_key,
                           document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                    FROM rag_ingestion_jobs
                    WHERE job_id = ?
                    """,
                    """
                    SELECT job_id, status, source, title, tags_json, filename, idempotency_key,
                           document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                    FROM rag_ingestion_jobs
                    WHERE job_id = %s
                    """,
                ),
                (job_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "job_id": row["job_id"],
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
    ) -> dict[str, object] | None:
        with self._connect() as connection:
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

        if row is None:
            return None
        return self.get_rag_ingestion_job(str(row["job_id"]))

    def list_rag_ingestion_jobs(self, limit: int = 20) -> list[dict[str, object]]:
        capped_limit = max(1, min(limit, 200))
        with self._connect() as connection:
            rows = connection.execute(
                self._sql(
                    """
                    SELECT job_id, status, source, title, tags_json, filename, idempotency_key,
                           document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                    FROM rag_ingestion_jobs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    """
                    SELECT job_id, status, source, title, tags_json, filename, idempotency_key,
                           document_id, chunk_count, indexed_chunks, error_message, created_at, updated_at
                    FROM rag_ingestion_jobs
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                ),
                (capped_limit,),
            ).fetchall()

        return [
            {
                "job_id": row["job_id"],
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

    def create_chat_session(self, *, session_id: str, incident_id: str | None) -> dict[str, object]:
        now = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO chat_sessions
                    (session_id, incident_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO chat_sessions
                    (session_id, incident_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                      incident_id = EXCLUDED.incident_id,
                      updated_at = EXCLUDED.updated_at
                    """,
                ),
                (session_id, incident_id, now, now),
            )

        return {
            "session_id": session_id,
            "incident_id": incident_id,
            "created_at": now,
            "updated_at": now,
        }

    def get_chat_session(self, session_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    """
                    SELECT session_id, incident_id, created_at, updated_at
                    FROM chat_sessions
                    WHERE session_id = ?
                    """,
                    """
                    SELECT session_id, incident_id, created_at, updated_at
                    FROM chat_sessions
                    WHERE session_id = %s
                    """,
                ),
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "session_id": row["session_id"],
            "incident_id": row["incident_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_chat_sessions(self, limit: int = 50) -> list[dict[str, object]]:
        capped_limit = max(1, min(limit, 200))
        with self._connect() as connection:
            rows = connection.execute(
                self._sql(
                    """
                    SELECT session_id, incident_id, created_at, updated_at
                    FROM chat_sessions
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    """
                    SELECT session_id, incident_id, created_at, updated_at
                    FROM chat_sessions
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                ),
                (capped_limit,),
            ).fetchall()

        return [
            {
                "session_id": row["session_id"],
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
    ) -> dict[str, object]:
        now = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    INSERT OR REPLACE INTO chat_messages
                    (message_id, session_id, role, content, citations_json, action, action_status, action_payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    """
                    INSERT INTO chat_messages
                    (message_id, session_id, role, content, citations_json, action, action_status, action_payload_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (message_id) DO UPDATE SET
                      role = EXCLUDED.role,
                      content = EXCLUDED.content,
                      citations_json = EXCLUDED.citations_json,
                      action = EXCLUDED.action,
                      action_status = EXCLUDED.action_status,
                      action_payload_json = EXCLUDED.action_payload_json
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
            "created_at": now,
        }

    def list_chat_messages(self, session_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                self._sql(
                    """
                    SELECT message_id, session_id, role, content, citations_json, action, action_status, action_payload_json, created_at
                    FROM chat_messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    """,
                    """
                    SELECT message_id, session_id, role, content, citations_json, action, action_status, action_payload_json, created_at
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
                "created_at": row["created_at"],
            }
            for row in rows
        ]
