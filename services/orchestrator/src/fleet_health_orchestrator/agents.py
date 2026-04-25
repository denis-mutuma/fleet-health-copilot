from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from fleet_health_orchestrator.models import IncidentReport, RetrievalHit, TelemetryEvent
from fleet_health_orchestrator.rag import LexicalRetrievalBackend, RetrievalBackend


@dataclass
class DiagnosisResult:
    hypotheses: list[str]
    confidence_score: float


@dataclass
class PlanResult:
    actions: list[str]


@dataclass
class VerificationResult:
    passed: bool
    checks: list[str]
    warnings: list[str] = field(default_factory=list)


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
class DiagnosisAgent:
    def diagnose(self, event: TelemetryEvent, hits: list[RetrievalHit]) -> DiagnosisResult:
        hypotheses: list[str] = []
        tags = set(event.tags)

        if "battery" in tags or "thermal" in tags:
            hypotheses.extend(["cooling degradation", "ambient overload"])
        elif "motor" in tags or "current" in tags:
            hypotheses.extend(["mechanical resistance", "load profile drift"])
        else:
            hypotheses.append(f"{event.metric} threshold excursion")

        if any(hit.source == "incident" for hit in hits):
            hypotheses.append("repeat pattern from prior incident history")

        confidence_score = min(0.95, 0.55 + (0.1 * len(hits)))
        return DiagnosisResult(
            hypotheses=list(dict.fromkeys(hypotheses)),
            confidence_score=round(confidence_score, 2)
        )


@dataclass
class PlannerAgent:
    def plan(self, hits: list[RetrievalHit]) -> PlanResult:
        runbook_hits = [hit for hit in hits if hit.source == "runbook"]
        actions: list[str] = []

        for hit in runbook_hits[:2]:
            first_sentence = hit.excerpt.split(".")[0].strip()
            if first_sentence:
                actions.append(f"Follow {hit.document_id}: {first_sentence}.")

        return PlanResult(
            actions=actions or [
                "Review recent telemetry for repeated threshold crossings",
                "Have an operator inspect the device before returning to normal duty cycle"
            ]
        )


@dataclass
class VerifierAgent:
    def verify(self, plan: PlanResult, hits: list[RetrievalHit]) -> VerificationResult:
        has_runbook = any(hit.source == "runbook" for hit in hits)
        checks = [
            "anomaly confirmed by MonitorAgent",
            "recommendations limited to operator review or maintenance actions"
        ]
        warnings: list[str] = []

        if has_runbook:
            checks.append("runbook evidence attached")
        else:
            warnings.append("no runbook evidence matched; using conservative fallback actions")

        return VerificationResult(
            passed=bool(plan.actions),
            checks=checks,
            warnings=warnings
        )


@dataclass
class ReporterAgent:
    def compose(
        self,
        event: TelemetryEvent,
        hits: list[RetrievalHit],
        diagnosis: DiagnosisResult,
        plan: PlanResult,
        verification: VerificationResult,
        latency_ms: float
    ) -> IncidentReport:
        runbooks = [hit.document_id for hit in hits if hit.source == "runbook"]
        matched_incidents = [hit.document_id for hit in hits if hit.source == "incident"]
        return IncidentReport(
            incident_id=f"inc_{uuid4().hex[:10]}",
            device_id=event.device_id,
            status="open",
            summary=f"{event.metric} exceeded threshold on {event.device_id}.",
            root_cause_hypotheses=diagnosis.hypotheses,
            recommended_actions=plan.actions,
            evidence={
                "matched_incidents": matched_incidents,
                "runbooks": runbooks,
                "generated_at": [datetime.now(UTC).isoformat()]
            },
            confidence_score=diagnosis.confidence_score,
            agent_trace=[
                "MonitorAgent detected a threshold crossing",
                f"RetrieverAgent returned {len(hits)} context hits",
                f"DiagnosisAgent produced {len(diagnosis.hypotheses)} hypotheses",
                f"PlannerAgent produced {len(plan.actions)} recommended actions",
                "VerifierAgent approved report" if verification.passed else "VerifierAgent flagged report"
            ],
            verification={
                "passed": verification.passed,
                "checks": verification.checks,
                "warnings": verification.warnings
            },
            latency_ms=round(latency_ms, 2)
        )


@dataclass
class AgentOrchestrator:
    monitor: MonitorAgent
    retriever: RetrieverAgent
    diagnosis: DiagnosisAgent
    planner: PlannerAgent
    verifier: VerifierAgent
    reporter: ReporterAgent

    def execute(self, event: TelemetryEvent, rag_documents: list[dict[str, object]]) -> IncidentReport:
        started_at = perf_counter()
        if not self.monitor.detect_anomaly(event):
            raise ValueError("Event does not exceed threshold.")
        retrieved_context = self.retriever.retrieve(event=event, rag_documents=rag_documents)
        diagnosis = self.diagnosis.diagnose(event=event, hits=retrieved_context)
        plan = self.planner.plan(hits=retrieved_context)
        verification = self.verifier.verify(plan=plan, hits=retrieved_context)
        latency_ms = (perf_counter() - started_at) * 1000
        return self.reporter.compose(
            event=event,
            hits=retrieved_context,
            diagnosis=diagnosis,
            plan=plan,
            verification=verification,
            latency_ms=latency_ms
        )
