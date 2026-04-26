import logging
import os
import sqlite3
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException
from starlette.middleware.cors import CORSMiddleware

from fleet_health_orchestrator.agents import (
    AgentOrchestrator,
    DiagnosisAgent,
    MonitorAgent,
    PlannerAgent,
    ReporterAgent,
    RetrieverAgent,
    VerifierAgent
)
from fleet_health_orchestrator.models import (
    IncidentReport,
    IncidentStatusUpdate,
    RagDocument,
    RetrievalHit,
    TelemetryEvent
)
from fleet_health_orchestrator.rag import build_retrieval_backend
from fleet_health_orchestrator.repository import FleetRepository

app = FastAPI(title="Fleet Health Orchestrator", version="0.1.0")

_cors_origins_raw = (os.getenv("FLEET_CORS_ORIGINS") or "").strip()
if _cors_origins_raw:
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    if _cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "fleet_health.db"
)
repository = FleetRepository(Path(os.getenv("FLEET_DB_PATH", str(DEFAULT_DB_PATH))))
_embedding_dim_raw = os.getenv("FLEET_S3_VECTORS_EMBEDDING_DIM")
_embedding_dim = (
    int(_embedding_dim_raw.strip())
    if _embedding_dim_raw and _embedding_dim_raw.strip()
    else None
)
retrieval_backend = build_retrieval_backend(
    backend_name=os.getenv("FLEET_RETRIEVAL_BACKEND"),
    s3_vectors_bucket=os.getenv("FLEET_S3_VECTORS_BUCKET"),
    s3_vectors_index=os.getenv("FLEET_S3_VECTORS_INDEX"),
    s3_vectors_index_arn=os.getenv("FLEET_S3_VECTORS_INDEX_ARN"),
    s3_vectors_embedding_dimension=_embedding_dim,
    s3_vectors_query_vector_json=os.getenv("FLEET_S3_VECTORS_QUERY_VECTOR_JSON"),
    embedding_provider=os.getenv("FLEET_EMBEDDING_PROVIDER")
)

_log = logging.getLogger("fleet_health_orchestrator")
if (os.getenv("FLEET_RETRIEVAL_BACKEND") or "").strip().lower() == "s3vectors":
    _prov = (os.getenv("FLEET_EMBEDDING_PROVIDER") or "hash").strip().lower()
    if _prov in ("hash", "deterministic", "pseudo", ""):
        _log.warning(
            "FLEET_RETRIEVAL_BACKEND=s3vectors with hash-style embeddings; ANN quality is not "
            "production-like. Use openai, http, or sentence_transformers and match "
            "FLEET_S3_VECTORS_EMBEDDING_DIM for index_s3_vectors.py and query."
        )
orchestrator = AgentOrchestrator(
    monitor=MonitorAgent(),
    retriever=RetrieverAgent(retrieval_backend=retrieval_backend),
    diagnosis=DiagnosisAgent(),
    planner=PlannerAgent(),
    verifier=VerifierAgent(),
    reporter=ReporterAgent()
)
METRICS: dict[str, float] = {
    "events_ingested_total": 0,
    "incidents_generated_total": 0,
    "rag_queries_total": 0,
    "rag_query_latency_ms_last": 0,
    "orchestration_latency_ms_last": 0
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _readiness() -> None:
    """Raise HTTPException(503) if SQLite or repository is not usable."""
    db_path = repository.db_path
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".fleet_ready_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database path not writable: {exc}"
        ) from exc
    try:
        with sqlite3.connect(str(db_path)) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail=f"SQLite not ready: {exc}"
        ) from exc
    try:
        repository.list_rag_documents()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Repository check failed: {exc}"
        ) from exc


@app.get("/ready")
def ready() -> dict[str, str]:
    _readiness()
    return {"status": "ready"}


@app.post("/v1/events", response_model=TelemetryEvent)
def ingest_event(event: TelemetryEvent) -> TelemetryEvent:
    repository.insert_event(event)
    METRICS["events_ingested_total"] += 1
    return event


@app.get("/v1/events", response_model=list[TelemetryEvent])
def list_events() -> list[TelemetryEvent]:
    return repository.list_events()


@app.post("/v1/incidents/from-event", response_model=IncidentReport)
def create_incident_from_event(event: TelemetryEvent) -> IncidentReport:
    started_at = perf_counter()
    try:
        incident = orchestrator.execute(
            event=event,
            rag_documents=repository.list_rag_documents()
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    repository.insert_incident(incident)
    METRICS["incidents_generated_total"] += 1
    METRICS["orchestration_latency_ms_last"] = (perf_counter() - started_at) * 1000
    return incident


@app.get("/v1/incidents", response_model=list[IncidentReport])
def list_incidents() -> list[IncidentReport]:
    return repository.list_incidents()


@app.get("/v1/incidents/{incident_id}", response_model=IncidentReport)
def get_incident(incident_id: str) -> IncidentReport:
    incident = repository.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident


@app.patch("/v1/incidents/{incident_id}", response_model=IncidentReport)
def update_incident(
    incident_id: str,
    update: IncidentStatusUpdate
) -> IncidentReport:
    incident = repository.update_incident_status(incident_id, update.status)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident


@app.post("/v1/rag/documents", response_model=RagDocument)
def upsert_rag_document(document: RagDocument) -> RagDocument:
    repository.insert_rag_document(
        document_id=document.document_id,
        source=document.source,
        title=document.title,
        content=document.content,
        tags=document.tags
    )
    return document


@app.get("/v1/rag/search", response_model=list[RetrievalHit])
def rag_search(query: str, limit: int = 5) -> list[RetrievalHit]:
    started_at = perf_counter()
    documents = repository.list_rag_documents()
    hits = retrieval_backend.search(query=query, documents=documents, limit=limit)
    METRICS["rag_queries_total"] += 1
    METRICS["rag_query_latency_ms_last"] = (perf_counter() - started_at) * 1000
    return hits


@app.post("/v1/orchestrate/event", response_model=IncidentReport)
def orchestrate_event(event: TelemetryEvent) -> IncidentReport:
    repository.insert_event(event)
    METRICS["events_ingested_total"] += 1
    return create_incident_from_event(event)


@app.get("/v1/metrics")
def get_metrics() -> dict[str, float]:
    return METRICS
