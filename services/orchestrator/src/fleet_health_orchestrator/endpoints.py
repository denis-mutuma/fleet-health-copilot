import sqlite3
from time import perf_counter

from fastapi import APIRouter, Body, Depends, Path, Query

from fleet_health_orchestrator.dependencies import AppDependencies, get_dependencies
from fleet_health_orchestrator.exceptions import ReadinessError, ResourceNotFoundError
from fleet_health_orchestrator.models import (
    IncidentReport,
    IncidentStatusUpdate,
    RagDocument,
    RetrievalHit,
    TelemetryEvent,
)

router = APIRouter()


EVENT_EXAMPLE = {
    "event_id": "evt_01HABC123",
    "fleet_id": "fleet-alpha",
    "device_id": "robot-03",
    "timestamp": "2026-01-20T10:15:00Z",
    "metric": "battery_temp_c",
    "value": 74.2,
    "threshold": 65.0,
    "severity": "high",
    "tags": ["battery", "thermal"],
}

RAG_DOCUMENT_EXAMPLE = {
    "document_id": "rb_battery_thermal_v2",
    "source": "runbook",
    "title": "Battery Thermal Drift Response",
    "content": "Reduce duty cycle and inspect cooling system when battery thermal drift repeats.",
    "tags": ["battery", "thermal"],
}

INCIDENT_STATUS_UPDATE_EXAMPLE = {
    "status": "acknowledged",
}


def _readiness(dependencies: AppDependencies) -> None:
    """Validate repository and database readiness before serving requests."""
    db_path = dependencies.repository.db_path
    parent = db_path.parent

    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".fleet_ready_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        dependencies.logger.error("Database path not writable: %s", exc)
        raise ReadinessError(
            "Database path not writable.",
            details={"reason": str(exc)},
        ) from exc

    try:
        with sqlite3.connect(str(db_path)) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        dependencies.logger.error("SQLite not ready: %s", exc)
        raise ReadinessError(
            "SQLite is not ready.",
            details={"reason": str(exc)},
        ) from exc

    try:
        dependencies.repository.list_rag_documents()
    except sqlite3.Error as exc:
        dependencies.logger.error("Repository check failed: %s", exc)
        raise ReadinessError(
            "Repository check failed.",
            details={"reason": str(exc)},
        ) from exc


def _create_incident_from_event(event: TelemetryEvent, dependencies: AppDependencies) -> IncidentReport:
    started_at = perf_counter()
    incident = dependencies.orchestrator.execute(
        event=event,
        rag_documents=dependencies.repository.list_rag_documents(),
    )

    dependencies.repository.insert_incident(incident)
    latency_ms = (perf_counter() - started_at) * 1000
    dependencies.metrics["incidents_generated_total"] += 1
    dependencies.metrics["orchestration_latency_ms_last"] = latency_ms

    dependencies.logger.info(
        "Incident generated: %s (device=%s, confidence=%.2f, latency=%.1f ms)",
        incident.incident_id,
        incident.device_id,
        incident.confidence_score,
        latency_ms,
    )
    return incident


@router.get(
    "/health",
    tags=["Health"],
    summary="Liveness health check",
    response_description="Service process is running.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    tags=["Health"],
    summary="Readiness health check",
    response_description="Service dependencies are ready.",
    responses={
        503: {
            "description": "Repository or database is not ready.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Repository check failed.",
                        "error": {
                            "code": "service_not_ready",
                            "message": "Repository check failed.",
                            "details": {"reason": "disk I/O error"},
                        },
                    }
                }
            },
        }
    },
)
def ready(dependencies: AppDependencies = Depends(get_dependencies)) -> dict[str, str]:
    _readiness(dependencies)
    return {"status": "ready"}


@router.post(
    "/v1/events",
    response_model=TelemetryEvent,
    tags=["Events"],
    summary="Ingest telemetry event",
    response_description="The persisted telemetry event.",
)
def ingest_event(
    event: TelemetryEvent = Body(
        ...,
        openapi_examples={
            "battery_thermal_event": {
                "summary": "Battery thermal threshold breach",
                "value": EVENT_EXAMPLE,
            }
        },
    ),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> TelemetryEvent:
    dependencies.repository.insert_event(event)
    dependencies.metrics["events_ingested_total"] += 1
    dependencies.logger.debug(
        "Event ingested: %s from %s (value=%.2f, threshold=%.2f)",
        event.metric,
        event.device_id,
        event.value,
        event.threshold,
    )
    return event


@router.get(
    "/v1/events",
    response_model=list[TelemetryEvent],
    tags=["Events"],
    summary="List telemetry events",
    response_description="Telemetry events ordered by timestamp descending.",
)
def list_events(dependencies: AppDependencies = Depends(get_dependencies)) -> list[TelemetryEvent]:
    return dependencies.repository.list_events()


@router.post(
    "/v1/incidents/from-event",
    response_model=IncidentReport,
    tags=["Incidents"],
    summary="Create incident from telemetry event",
    response_description="Generated incident report from orchestration pipeline.",
    responses={
        400: {
            "description": "Event did not exceed anomaly threshold.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Event does not exceed threshold.",
                        "error": {
                            "code": "invalid_request",
                            "message": "Event does not exceed threshold.",
                        },
                    }
                }
            },
        }
    },
)
def create_incident_from_event(
    event: TelemetryEvent = Body(
        ...,
        openapi_examples={
            "battery_thermal_event": {
                "summary": "Telemetry event to analyze",
                "value": EVENT_EXAMPLE,
            }
        },
    ),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> IncidentReport:
    return _create_incident_from_event(event, dependencies)


@router.get(
    "/v1/incidents",
    response_model=list[IncidentReport],
    tags=["Incidents"],
    summary="List incidents",
    response_description="Incident reports ordered by incident ID descending.",
)
def list_incidents(dependencies: AppDependencies = Depends(get_dependencies)) -> list[IncidentReport]:
    return dependencies.repository.list_incidents()


@router.get(
    "/v1/incidents/{incident_id}",
    response_model=IncidentReport,
    tags=["Incidents"],
    summary="Get incident by ID",
    response_description="Incident report for the provided ID.",
    responses={
        404: {
            "description": "Incident was not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Incident not found.",
                        "error": {
                            "code": "resource_not_found",
                            "message": "Incident not found.",
                            "details": {"incident_id": "inc_missing"},
                        },
                    }
                }
            },
        }
    },
)
def get_incident(
    incident_id: str = Path(..., description="Unique incident identifier."),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> IncidentReport:
    incident = dependencies.repository.get_incident(incident_id)
    if incident is None:
        dependencies.logger.warning("Incident not found: %s", incident_id)
        raise ResourceNotFoundError(
            "Incident not found.",
            details={"incident_id": incident_id},
        )
    return incident


@router.post(
    "/v1/incidents/{incident_id}",
    response_model=IncidentReport,
    tags=["Incidents"],
    summary="Acknowledge incident",
    response_description="Updated incident report with status acknowledged.",
    responses={
        404: {
            "description": "Incident was not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Incident not found.",
                        "error": {
                            "code": "resource_not_found",
                            "message": "Incident not found.",
                            "details": {"incident_id": "inc_missing"},
                        },
                    }
                }
            },
        }
    },
)
def acknowledge_incident(
    incident_id: str = Path(..., description="Unique incident identifier."),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> IncidentReport:
    incident = dependencies.repository.update_incident_status(incident_id, "acknowledged")
    if incident is None:
        dependencies.logger.warning("Incident not found for acknowledgement: %s", incident_id)
        raise ResourceNotFoundError(
            "Incident not found.",
            details={"incident_id": incident_id},
        )

    dependencies.logger.info("Incident acknowledged: %s", incident_id)
    return incident


@router.patch(
    "/v1/incidents/{incident_id}",
    response_model=IncidentReport,
    tags=["Incidents"],
    summary="Update incident status",
    response_description="Updated incident report.",
    responses={
        404: {
            "description": "Incident was not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Incident not found.",
                        "error": {
                            "code": "resource_not_found",
                            "message": "Incident not found.",
                            "details": {"incident_id": "inc_missing"},
                        },
                    }
                }
            },
        }
    },
)
def update_incident(
    incident_id: str = Path(..., description="Unique incident identifier."),
    update: IncidentStatusUpdate = Body(
        ...,
        openapi_examples={
            "acknowledge": {
                "summary": "Mark incident as acknowledged",
                "value": INCIDENT_STATUS_UPDATE_EXAMPLE,
            }
        },
    ),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> IncidentReport:
    incident = dependencies.repository.update_incident_status(incident_id, update.status)
    if incident is None:
        dependencies.logger.warning("Incident not found for update: %s", incident_id)
        raise ResourceNotFoundError(
            "Incident not found.",
            details={"incident_id": incident_id},
        )

    dependencies.logger.info("Incident status updated: %s -> %s", incident_id, update.status)
    return incident


@router.post(
    "/v1/rag/documents",
    response_model=RagDocument,
    tags=["RAG"],
    summary="Upsert RAG document",
    response_description="Stored RAG document.",
)
def upsert_rag_document(
    document: RagDocument = Body(
        ...,
        openapi_examples={
            "runbook_document": {
                "summary": "Runbook entry for thermal drift",
                "value": RAG_DOCUMENT_EXAMPLE,
            }
        },
    ),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> RagDocument:
    dependencies.repository.insert_rag_document(
        document_id=document.document_id,
        source=document.source,
        title=document.title,
        content=document.content,
        tags=document.tags,
    )
    dependencies.logger.debug("RAG document upserted: %s (%s)", document.document_id, document.source)
    return document


@router.get(
    "/v1/rag/search",
    response_model=list[RetrievalHit],
    tags=["RAG"],
    summary="Search RAG corpus",
    response_description="Matching retrieval hits ordered by relevance.",
)
def rag_search(
    query: str = Query(..., min_length=1, description="Search query text."),
    limit: int = Query(5, ge=1, le=50, description="Maximum number of hits to return."),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> list[RetrievalHit]:
    started_at = perf_counter()
    documents = dependencies.repository.list_rag_documents()
    hits = dependencies.retrieval_backend.search(query=query, documents=documents, limit=limit)
    latency_ms = (perf_counter() - started_at) * 1000

    dependencies.metrics["rag_queries_total"] += 1
    dependencies.metrics["rag_query_latency_ms_last"] = latency_ms

    dependencies.logger.debug("RAG search: query=%r, hits=%d, latency=%.1f ms", query, len(hits), latency_ms)
    return hits


@router.post(
    "/v1/orchestrate/event",
    response_model=IncidentReport,
    tags=["Orchestration"],
    summary="Orchestrate event end-to-end",
    response_description="Generated incident report after ingest + orchestration.",
    responses={
        400: {
            "description": "Event did not exceed anomaly threshold.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Event does not exceed threshold.",
                        "error": {
                            "code": "invalid_request",
                            "message": "Event does not exceed threshold.",
                        },
                    }
                }
            },
        }
    },
)
def orchestrate_event(
    event: TelemetryEvent = Body(
        ...,
        openapi_examples={
            "battery_thermal_event": {
                "summary": "Event that triggers full pipeline",
                "value": EVENT_EXAMPLE,
            }
        },
    ),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> IncidentReport:
    dependencies.repository.insert_event(event)
    dependencies.metrics["events_ingested_total"] += 1
    dependencies.logger.debug("Event ingested via orchestrate: %s from %s", event.metric, event.device_id)
    return _create_incident_from_event(event, dependencies)


@router.get(
    "/v1/metrics",
    tags=["Metrics"],
    summary="Get runtime metrics",
    response_description="Current in-process counters and latency metrics.",
)
def get_metrics(dependencies: AppDependencies = Depends(get_dependencies)) -> dict[str, float]:
    return dependencies.metrics.copy()
