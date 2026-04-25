from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from fleet_health_orchestrator.models import IncidentReport, RetrievalHit, TelemetryEvent
from fleet_health_orchestrator.rag import LexicalRetrievalBackend, RetrievalBackend


@dataclass
class MonitorAgent:
    def detect_anomaly(self, event: TelemetryEvent) -> bool:
        return event.value > event.threshold


@dataclass
class RetrieverAgent:
    retrieval_backend: RetrievalBackend = field(default_factory=LexicalRetrievalBackend)

    def retrieve(self, event: TelemetryEvent, rag_documents: list[dict[str, object]]) -> list[RetrievalHit]:
        query = f"{event.metric} {' '.join(event.tags)} {event.severity}"
        return self.retrieval_backend.search(query=query, documents=rag_documents, limit=3)

@dataclass
class ReporterAgent:
    def _recommended_actions(self, hits: list[RetrievalHit]) -> list[str]:
        runbook_hits = [hit for hit in hits if hit.source == "runbook"]
        actions: list[str] = []

        for hit in runbook_hits[:2]:
            first_sentence = hit.excerpt.split(".")[0].strip()
            if first_sentence:
                actions.append(f"Follow {hit.document_id}: {first_sentence}.")

        return actions or [
            "Review recent telemetry for repeated threshold crossings",
            "Have an operator inspect the device before returning to normal duty cycle"
        ]

    def compose(self, event: TelemetryEvent, hits: list[RetrievalHit]) -> IncidentReport:
        runbooks = [hit.document_id for hit in hits if hit.source == "runbook"]
        matched_incidents = [hit.document_id for hit in hits if hit.source == "incident"]
        return IncidentReport(
            incident_id=f"inc_{uuid4().hex[:10]}",
            device_id=event.device_id,
            status="open",
            summary=f"{event.metric} exceeded threshold on {event.device_id}.",
            root_cause_hypotheses=["cooling degradation", "ambient overload"],
            recommended_actions=self._recommended_actions(hits),
            evidence={
                "matched_incidents": matched_incidents,
                "runbooks": runbooks,
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
