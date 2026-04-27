import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fleet_health_orchestrator.models import IncidentReport, TelemetryEvent


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
        return postgres_query if self._use_postgres else sqlite_query

    def _init_db(self) -> None:
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
