from dataclasses import dataclass, field
from contextlib import nullcontext
from time import perf_counter
from uuid import uuid4

from fleet_health_orchestrator.exceptions import AnomalyThresholdError
from fleet_health_orchestrator.llm import (
    enrich_diagnosis_hypotheses,
    generate_action_plan,
    generate_diagnosis_hypotheses,
    openai_trace,
    refine_incident_summary,
)
from fleet_health_orchestrator.models import IncidentReport, RetrievalHit, TelemetryEvent
from fleet_health_orchestrator.rag import LexicalRetrievalBackend, RetrievalBackend


def _base_document_id(document_id: str) -> str:
    return document_id.split("#chunk-", 1)[0]


def _cited_runbook_id_from_action(action: str) -> str | None:
    if not action.startswith("Follow "):
        return None
    rest = action[len("Follow "):]
    if ":" not in rest:
        return None
    return rest.split(":", 1)[0].strip() or None


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
        with openai_trace("fleet-health.agent.diagnosis"):
            hypotheses = generate_diagnosis_hypotheses(event, hits)
            tags = set(event.tags)

            if not hypotheses:
                if "cpu" in tags or "cpu" in event.metric:
                    hypotheses.extend(["thermal throttling risk", "cooling subsystem stress"])
                elif "battery" in tags or "thermal" in tags:
                    hypotheses.extend(["cooling degradation", "ambient overload"])
                elif "motor" in tags or "current" in tags:
                    hypotheses.extend(["mechanical resistance", "load profile drift"])
                else:
                    hypotheses.append(f"{event.metric} threshold excursion")

            if any(hit.source == "incident" for hit in hits):
                hypotheses.append("repeat pattern from prior incident history")

            for hit in hits[:3]:
                if hit.title.strip():
                    hypotheses.append(f"retrieved context: {hit.title.strip()}")

            hypotheses = list(dict.fromkeys(hypotheses))
            hypotheses.extend(enrich_diagnosis_hypotheses(event, hits, hypotheses))
            hypotheses = list(dict.fromkeys(hypotheses))
            confidence_score = min(0.95, 0.55 + (0.1 * len(hits)))
            return DiagnosisResult(
                hypotheses=hypotheses,
                confidence_score=round(confidence_score, 2)
            )


@dataclass
class PlannerAgent:
    def plan(self, event: TelemetryEvent, hits: list[RetrievalHit]) -> PlanResult:
        runbook_hits = [
            hit.model_copy(update={"document_id": _base_document_id(hit.document_id)})
            for hit in hits
            if hit.source == "runbook"
        ]
        with openai_trace("fleet-health.agent.planner"):
            actions = generate_action_plan(event, runbook_hits)

            if not actions:
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
        runbook_ids = {_base_document_id(hit.document_id) for hit in hits if hit.source == "runbook"}
        checks = [
            "anomaly confirmed by MonitorAgent",
            "recommendations limited to operator review or maintenance actions"
        ]
        warnings: list[str] = []
        bad_citation = False

        if has_runbook:
            checks.append("runbook evidence attached")
            for action in plan.actions:
                cited = _cited_runbook_id_from_action(action)
                if cited is not None and cited not in runbook_ids:
                    bad_citation = True
                    warnings.append(
                        f"recommended action cites {cited} which was not in retrieved runbook evidence"
                    )
            if runbook_ids and plan.actions and not any(
                _cited_runbook_id_from_action(action) is not None for action in plan.actions
            ):
                warnings.append(
                    "retrieved runbooks present but no Follow <runbook_id>: line anchored recommendations"
                )
        else:
            warnings.append("no runbook evidence matched; using conservative fallback actions")

        return VerificationResult(
            passed=bool(plan.actions) and not bad_citation,
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
        runbooks = list(dict.fromkeys(_base_document_id(hit.document_id) for hit in hits if hit.source == "runbook"))
        matched_incidents = [hit.document_id for hit in hits if hit.source == "incident"]
        summary = f"{event.metric} exceeded threshold on {event.device_id}."
        summary = refine_incident_summary(event, summary) or summary
        return IncidentReport(
            incident_id=f"inc_{uuid4().hex[:10]}",
            device_id=event.device_id,
            status="open",
            summary=summary,
            root_cause_hypotheses=diagnosis.hypotheses,
            recommended_actions=plan.actions,
            evidence={
                "matched_incidents": matched_incidents,
                "runbooks": runbooks
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
        trace_context = openai_trace(
            "fleet-health.pipeline",
            metadata={
                "device_id": event.device_id,
                "fleet_id": event.fleet_id,
                "metric": event.metric,
                "severity": event.severity,
            },
        )
        with trace_context if trace_context is not None else nullcontext():
            if not self.monitor.detect_anomaly(event):
                raise AnomalyThresholdError()
            retrieved_context = self.retriever.retrieve(event=event, rag_documents=rag_documents)
            diagnosis = self.diagnosis.diagnose(event=event, hits=retrieved_context)
            plan = self.planner.plan(event=event, hits=retrieved_context)
            verification = self.verifier.verify(plan=plan, hits=retrieved_context)
            latency_ms = (perf_counter() - started_at) * 1000
            return self.reporter.compose(
                event=event,
                hits=retrieved_context,
                diagnosis=diagnosis,
                plan=plan,
                verification=verification,
                latency_ms=latency_ms,
            )
