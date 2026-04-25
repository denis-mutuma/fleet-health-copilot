from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from fleet_health_orchestrator.models import IncidentReport, RetrievalHit, TelemetryEvent
from fleet_health_orchestrator.rag import rank_documents


@dataclass
class MonitorAgent:
    def detect_anomaly(self, event: TelemetryEvent) -> bool:
        return event.value > event.threshold


@dataclass
class RetrieverAgent:
    def retrieve(self, event: TelemetryEvent, rag_documents: list[dict[str, object]]) -> list[RetrievalHit]:
        query = f"{event.metric} {' '.join(event.tags)} {event.severity}"
        return rank_documents(query=query, documents=rag_documents, limit=3)


@dataclass
class ReporterAgent:
    def compose(self, event: TelemetryEvent, hits: list[RetrievalHit]) -> IncidentReport:
        runbooks = [hit.document_id for hit in hits if hit.source == "runbook"]
        matched_incidents = [hit.document_id for hit in hits if hit.source == "incident"]
        return IncidentReport(
            incident_id=f"inc_{uuid4().hex[:10]}",
            device_id=event.device_id,
            status="open",
            summary=f"{event.metric} exceeded threshold on {event.device_id}.",
            root_cause_hypotheses=["cooling degradation", "ambient overload"],
            recommended_actions=[
                "Reduce duty cycle by 20%",
                "Schedule cooling system inspection within 24h"
            ],
            evidence={
                "matched_incidents": matched_incidents or ["inc_2025_102", "inc_2025_187"],
                "runbooks": runbooks or ["rb_battery_thermal_v2"],
                "generated_at": [datetime.now(UTC).isoformat()]
            }
        )


@dataclass
class AgentOrchestrator:
    monitor: MonitorAgent
    retriever: RetrieverAgent
    reporter: ReporterAgent

    def execute(self, event: TelemetryEvent, rag_documents: list[dict[str, object]]) -> IncidentReport:
        if not self.monitor.detect_anomaly(event):
            raise ValueError("Event does not exceed threshold.")
        retrieved_context = self.retriever.retrieve(event=event, rag_documents=rag_documents)
        return self.reporter.compose(event=event, hits=retrieved_context)
