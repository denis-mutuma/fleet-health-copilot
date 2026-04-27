"""FastAPI route handlers for health, incident, and RAG operations."""

import sqlite3
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, Header, Path, Query, UploadFile

from fleet_health_orchestrator.dependencies import AppDependencies, get_dependencies
from fleet_health_orchestrator.exceptions import InvalidRequestError, ReadinessError, ResourceNotFoundError
from fleet_health_orchestrator.ingestion import (
    build_chunk_documents,
    chunk_text,
    delete_documents_from_s3_vectors,
    extract_text_from_bytes,
    generate_document_id,
    index_documents_to_s3_vectors,
    is_supported_upload,
)
from fleet_health_orchestrator.models import (
    IncidentReport,
    IncidentStatusUpdate,
    RagDeletionResponse,
    RagDocument,
    RagDocumentFamily,
    RagIngestionJob,
    RagIngestionRequest,
    RagIngestionResponse,
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
    """Execute orchestration for one event, persist incident, and record latency metrics."""
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


def _persist_and_optionally_index_documents(
    *,
    dependencies: AppDependencies,
    documents: list[dict[str, object]],
) -> int:
    """Persist chunk documents and index vectors when the S3 Vectors backend is enabled."""
    for document in documents:
        dependencies.repository.insert_rag_document(
            document_id=str(document["document_id"]),
            source=str(document["source"]),
            title=str(document["title"]),
            content=str(document["content"]),
            tags=list(document.get("tags", [])),
        )

    settings = dependencies.settings
    if settings.retrieval_backend.strip().lower() != "s3vectors":
        return 0

    bucket = settings.s3_vectors_bucket.strip()
    index = settings.s3_vectors_index.strip()
    index_arn = settings.s3_vectors_index_arn.strip()
    has_pair = bool(bucket and index)
    if not index_arn and not has_pair:
        raise InvalidRequestError(
            "S3 Vectors backend is enabled but index configuration is missing.",
            details={"expected": "S3_VECTORS_INDEX_ARN or S3_VECTORS_BUCKET+S3_VECTORS_INDEX"},
        )

    try:
        return index_documents_to_s3_vectors(
            documents=documents,
            bucket=bucket,
            index=index,
            index_arn=index_arn,
            embedding_dimension=settings.s3_vectors_embedding_dimension,
            embedding_provider=settings.effective_embedding_provider,
            embedding_model=settings.openai_embedding_model,
            openai_api_key=settings.openai_api_key,
            batch_size=settings.rag_index_batch_size,
        )
    except Exception as exc:
        dependencies.logger.exception("S3 Vectors indexing failed")
        raise ReadinessError(
            "Failed to index uploaded documents in vector backend.",
            details={"reason": str(exc)},
        ) from exc


def _ingest_document(
    *,
    dependencies: AppDependencies,
    request: RagIngestionRequest,
) -> RagIngestionResponse:
    """Build chunks from a request, persist/index them, and return ingestion metadata."""
    settings = dependencies.settings
    document_id = request.document_id or generate_document_id(
        filename=request.title,
        title=request.title,
        content=request.content,
    )
    chunks = chunk_text(
        request.content,
        chunk_size_chars=request.chunk_size_chars,
        chunk_overlap_chars=request.chunk_overlap_chars,
    )
    if not chunks:
        raise InvalidRequestError("Document content is empty after normalization.")

    documents = build_chunk_documents(
        document_id=document_id,
        source=request.source,
        title=request.title,
        tags=request.tags,
        chunks=chunks,
    )
    indexed_chunks = _persist_and_optionally_index_documents(dependencies=dependencies, documents=documents)
    dependencies.logger.info(
        "RAG document ingested: id=%s chunks=%d indexed=%d backend=%s",
        document_id,
        len(documents),
        indexed_chunks,
        settings.retrieval_backend,
    )

    return RagIngestionResponse(
        document_id=document_id,
        source=request.source,
        title=request.title,
        chunk_count=len(documents),
        indexed_chunks=indexed_chunks,
        retrieval_backend=settings.retrieval_backend,
        embedding_provider=settings.effective_embedding_provider,
        embedding_model=settings.openai_embedding_model,
        llm_model=settings.llm_report_model,
    )


def _base_document_id(document_id: str) -> str:
    """Return the stable document family ID from a chunk identifier."""
    return document_id.split("#chunk-", 1)[0]


def _normalize_chunk_title(title: str) -> str:
    """Remove chunk suffix from stored titles for grouped list responses."""
    marker = " (chunk "
    idx = title.rfind(marker)
    if idx > 0 and title.endswith(")"):
        return title[:idx]
    return title


def _to_ingestion_job(payload: dict[str, object]) -> RagIngestionJob:
    """Validate and normalize repository payload into API job model."""
    return RagIngestionJob.model_validate(payload)


def _run_async_ingestion_job(
    *,
    job_id: str,
    dependencies: AppDependencies,
    request: RagIngestionRequest,
) -> None:
    """Execute queued ingestion and transition job status through running/succeeded/failed."""
    dependencies.repository.update_rag_ingestion_job(job_id=job_id, status="running")
    try:
        result = _ingest_document(dependencies=dependencies, request=request)
        dependencies.repository.update_rag_ingestion_job(
            job_id=job_id,
            status="succeeded",
            document_id=result.document_id,
            chunk_count=result.chunk_count,
            indexed_chunks=result.indexed_chunks,
            error_message=None,
        )
    except Exception as exc:
        dependencies.repository.update_rag_ingestion_job(
            job_id=job_id,
            status="failed",
            error_message=str(exc)[:2000],
        )
        dependencies.logger.exception("Async RAG ingestion failed for job %s", job_id)


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
    response_model=RagIngestionResponse,
    tags=["RAG"],
    summary="Ingest RAG document",
    response_description="Stored and chunked RAG document.",
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
) -> RagIngestionResponse:
    request = RagIngestionRequest(
        document_id=document.document_id,
        source=document.source,
        title=document.title,
        content=document.content,
        tags=document.tags,
        chunk_size_chars=dependencies.settings.rag_chunk_size_chars,
        chunk_overlap_chars=dependencies.settings.rag_chunk_overlap_chars,
    )
    return _ingest_document(dependencies=dependencies, request=request)


@router.get(
    "/v1/rag/documents",
    response_model=list[RagDocumentFamily],
    tags=["RAG"],
    summary="List RAG document families",
    response_description="Chunk-aware RAG corpus grouped by base document ID.",
)
def list_rag_documents(
    dependencies: AppDependencies = Depends(get_dependencies),
) -> list[RagDocumentFamily]:
    # API returns document families, even though storage is chunk-level.
    grouped: dict[str, RagDocumentFamily] = {}
    for row in dependencies.repository.list_rag_documents():
        row_id = str(row.get("document_id", "")).strip()
        if not row_id:
            continue
        base_id = _base_document_id(row_id)
        if base_id not in grouped:
            grouped[base_id] = RagDocumentFamily(
                document_id=base_id,
                source=str(row.get("source", "manual")),
                title=_normalize_chunk_title(str(row.get("title", base_id))),
                tags=list(row.get("tags", [])),
                chunk_count=1,
            )
            continue
        grouped[base_id].chunk_count += 1

    return sorted(grouped.values(), key=lambda item: item.document_id, reverse=True)


@router.delete(
    "/v1/rag/documents/{document_id}",
    response_model=RagDeletionResponse,
    tags=["RAG"],
    summary="Delete RAG document family",
    response_description="Deleted all chunks for the base RAG document ID.",
    responses={
        404: {
            "description": "Document was not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "RAG document not found.",
                        "error": {
                            "code": "resource_not_found",
                            "message": "RAG document not found.",
                            "details": {"document_id": "doc_missing"},
                        },
                    }
                }
            },
        }
    },
)
def delete_rag_document(
    document_id: str = Path(..., description="Base RAG document identifier."),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> RagDeletionResponse:
    cleaned = document_id.strip()

    all_documents = dependencies.repository.list_rag_documents()
    keys = [
        str(row.get("document_id", "")).strip()
        for row in all_documents
        if str(row.get("document_id", "")).strip() == cleaned
        or str(row.get("document_id", "")).strip().startswith(f"{cleaned}#chunk-")
    ]
    if not keys:
        raise ResourceNotFoundError(
            "RAG document not found.",
            details={"document_id": cleaned},
        )

    settings = dependencies.settings
    if settings.retrieval_backend.strip().lower() == "s3vectors":
        bucket = settings.s3_vectors_bucket.strip()
        index = settings.s3_vectors_index.strip()
        index_arn = settings.s3_vectors_index_arn.strip()
        has_pair = bool(bucket and index)
        if not index_arn and not has_pair:
            raise InvalidRequestError(
                "S3 Vectors backend is enabled but index configuration is missing.",
                details={"expected": "S3_VECTORS_INDEX_ARN or S3_VECTORS_BUCKET+S3_VECTORS_INDEX"},
            )

        try:
            delete_documents_from_s3_vectors(
                document_keys=keys,
                bucket=bucket,
                index=index,
                index_arn=index_arn,
                batch_size=settings.rag_index_batch_size,
            )
        except Exception as exc:
            dependencies.logger.exception("S3 Vectors delete failed")
            raise ReadinessError(
                "Failed to delete vectors for RAG document family.",
                details={"reason": str(exc), "document_id": cleaned},
            ) from exc

    deleted = dependencies.repository.delete_rag_document_family(cleaned)
    if deleted == 0:
        raise ResourceNotFoundError(
            "RAG document not found.",
            details={"document_id": cleaned},
        )

    dependencies.logger.info("Deleted RAG document family: %s (chunks=%d)", cleaned, deleted)
    return RagDeletionResponse(document_id=cleaned, deleted_chunks=deleted)


@router.post(
    "/v1/rag/documents/upload",
    response_model=RagIngestionResponse,
    tags=["RAG"],
    summary="Upload and ingest RAG document",
    response_description="Stored, chunked, and indexed document from uploaded file.",
)
async def upload_rag_document(
    file: UploadFile = File(..., description="Document file (.txt, .md, .json, .jsonl, .csv, .log)."),
    source: str = Form("manual", description="Document source type: runbook, incident, manual, note."),
    title: str = Form("", description="Optional title override; defaults to filename."),
    tags: str = Form("", description="Comma-separated tags."),
    document_id: str = Form("", description="Optional stable document ID."),
    chunk_size_chars: int | None = Form(None, description="Optional chunk size override."),
    chunk_overlap_chars: int | None = Form(None, description="Optional chunk overlap override."),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> RagIngestionResponse:
    filename = (file.filename or "uploaded-document").strip()
    if not is_supported_upload(filename):
        raise InvalidRequestError(
            "Unsupported file type for document ingestion.",
            details={"filename": filename},
        )

    raw = await file.read()
    if len(raw) > dependencies.settings.rag_upload_max_bytes:
        raise InvalidRequestError(
            "Uploaded file exceeds maximum allowed size.",
            details={
                "max_bytes": dependencies.settings.rag_upload_max_bytes,
                "received_bytes": len(raw),
            },
        )

    text = extract_text_from_bytes(filename, raw)
    cleaned_title = title.strip() or filename
    tag_values = [value.strip().lower() for value in tags.split(",") if value.strip()]

    request = RagIngestionRequest(
        source=source.strip().lower() or "manual",
        title=cleaned_title,
        content=text,
        tags=tag_values,
        document_id=document_id.strip() or None,
        chunk_size_chars=chunk_size_chars or dependencies.settings.rag_chunk_size_chars,
        chunk_overlap_chars=chunk_overlap_chars
        if chunk_overlap_chars is not None
        else dependencies.settings.rag_chunk_overlap_chars,
    )
    if request.document_id is None:
        request.document_id = generate_document_id(
            filename=filename,
            title=request.title,
            content=request.content,
        )

    return _ingest_document(dependencies=dependencies, request=request)


@router.post(
    "/v1/rag/documents/upload/async",
    response_model=RagIngestionJob,
    tags=["RAG"],
    summary="Upload and ingest RAG document asynchronously",
    response_description="Queued RAG ingestion job state.",
)
async def upload_rag_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Document file (.txt, .md, .markdown, .json, .jsonl, .csv, .log, .html, .htm, .pdf, .docx)."),
    source: str = Form("manual", description="Document source type: runbook, incident, manual, note."),
    title: str = Form("", description="Optional title override; defaults to filename."),
    tags: str = Form("", description="Comma-separated tags."),
    document_id: str = Form("", description="Optional stable document ID."),
    chunk_size_chars: int | None = Form(None, description="Optional chunk size override."),
    chunk_overlap_chars: int | None = Form(None, description="Optional chunk overlap override."),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> RagIngestionJob:
    normalized_key = (idempotency_key or "").strip() or None
    if normalized_key is not None:
        # Idempotency key lets clients safely retry upload requests.
        existing = dependencies.repository.get_rag_ingestion_job_by_idempotency_key(normalized_key)
        if existing is not None:
            return _to_ingestion_job(existing)

    filename = (file.filename or "uploaded-document").strip()
    if not is_supported_upload(filename):
        raise InvalidRequestError(
            "Unsupported file type for document ingestion.",
            details={"filename": filename},
        )

    raw = await file.read()
    if len(raw) > dependencies.settings.rag_upload_max_bytes:
        raise InvalidRequestError(
            "Uploaded file exceeds maximum allowed size.",
            details={
                "max_bytes": dependencies.settings.rag_upload_max_bytes,
                "received_bytes": len(raw),
            },
        )

    text = extract_text_from_bytes(filename, raw)
    cleaned_title = title.strip() or filename
    tag_values = [value.strip().lower() for value in tags.split(",") if value.strip()]

    request = RagIngestionRequest(
        source=source.strip().lower() or "manual",
        title=cleaned_title,
        content=text,
        tags=tag_values,
        document_id=document_id.strip() or None,
        chunk_size_chars=chunk_size_chars or dependencies.settings.rag_chunk_size_chars,
        chunk_overlap_chars=chunk_overlap_chars
        if chunk_overlap_chars is not None
        else dependencies.settings.rag_chunk_overlap_chars,
    )
    if request.document_id is None:
        request.document_id = generate_document_id(
            filename=filename,
            title=request.title,
            content=request.content,
        )

    job_id = f"job_{uuid4().hex[:16]}"
    dependencies.repository.insert_rag_ingestion_job(
        job_id=job_id,
        source=request.source,
        title=request.title,
        tags=request.tags,
        filename=filename,
        idempotency_key=normalized_key,
    )

    background_tasks.add_task(
        _run_async_ingestion_job,
        job_id=job_id,
        dependencies=dependencies,
        request=request,
    )
    created = dependencies.repository.get_rag_ingestion_job(job_id)
    if created is None:
        raise ReadinessError("Failed to persist ingestion job.")
    return _to_ingestion_job(created)


@router.get(
    "/v1/rag/ingestion-jobs",
    response_model=list[RagIngestionJob],
    tags=["RAG"],
    summary="List recent RAG ingestion jobs",
)
def list_rag_ingestion_jobs(
    limit: int = Query(20, ge=1, le=200, description="Maximum jobs to return."),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> list[RagIngestionJob]:
    rows = dependencies.repository.list_rag_ingestion_jobs(limit=limit)
    return [_to_ingestion_job(row) for row in rows]


@router.get(
    "/v1/rag/ingestion-jobs/{job_id}",
    response_model=RagIngestionJob,
    tags=["RAG"],
    summary="Get ingestion job status",
    responses={
        404: {
            "description": "Ingestion job was not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "RAG ingestion job not found.",
                        "error": {
                            "code": "resource_not_found",
                            "message": "RAG ingestion job not found.",
                            "details": {"job_id": "job_missing"},
                        },
                    }
                }
            },
        }
    },
)
def get_rag_ingestion_job(
    job_id: str = Path(..., description="Ingestion job identifier."),
    dependencies: AppDependencies = Depends(get_dependencies),
) -> RagIngestionJob:
    row = dependencies.repository.get_rag_ingestion_job(job_id.strip())
    if row is None:
        raise ResourceNotFoundError(
            "RAG ingestion job not found.",
            details={"job_id": job_id.strip()},
        )
    return _to_ingestion_job(row)


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
