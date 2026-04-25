import json
import sqlite3
from pathlib import Path

from fleet_health_orchestrator.models import IncidentReport, TelemetryEvent


class FleetRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

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
                    value REAL NOT NULL,
                    threshold REAL NOT NULL,
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
                    evidence_json TEXT NOT NULL
                )
                """
            )
            incident_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(incidents)").fetchall()
            }
            optional_columns = {
                "confidence_score": "REAL NOT NULL DEFAULT 0.0",
                "agent_trace_json": "TEXT NOT NULL DEFAULT '[]'",
                "verification_json": "TEXT NOT NULL DEFAULT '{}'",
                "latency_ms": "REAL NOT NULL DEFAULT 0.0"
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
                """
                INSERT OR REPLACE INTO events
                (event_id, fleet_id, device_id, timestamp, metric, value, threshold, severity, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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
                timestamp=row["timestamp"],
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
                """
                SELECT incident_id, device_id, status, summary, root_cause_hypotheses_json, recommended_actions_json, evidence_json, confidence_score, agent_trace_json, verification_json, latency_ms
                FROM incidents
                WHERE incident_id = ?
                """,
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
                """
                UPDATE incidents
                SET status = ?
                WHERE incident_id = ?
                """,
                (status, incident_id)
            )

        if cursor.rowcount == 0:
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
                """
                INSERT OR REPLACE INTO rag_documents
                (document_id, source, title, content, tags_json)
                VALUES (?, ?, ?, ?, ?)
                """,
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
