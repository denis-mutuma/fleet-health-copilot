# Fleet Health Orchestrator API Reference

Base URL (local): <http://localhost:8000>

Interactive docs:

- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`

## Error Model

The API returns structured errors with a compatibility `detail` field.

```json
{
  "detail": "Incident not found.",
  "error": {
    "code": "resource_not_found",
    "message": "Incident not found.",
    "details": {
      "incident_id": "inc_missing"
    }
  }
}
```

Common error codes:

- `validation_error`
- `invalid_request`
- `resource_not_found`
- `service_not_ready`
- `internal_error`

## Health

### GET /health

Returns liveness status.

Response:

```json
{"status": "ok"}
```

### GET /ready

Checks database and repository readiness.

Response:

```json
{"status": "ready"}
```

## Events

### POST /v1/events

Ingest a telemetry event.

Request example:

```json
{
  "event_id": "evt_01HABC123",
  "fleet_id": "fleet-alpha",
  "device_id": "robot-03",
  "timestamp": "2026-01-20T10:15:00Z",
  "metric": "battery_temp_c",
  "value": 74.2,
  "threshold": 65.0,
  "severity": "high",
  "tags": ["battery", "thermal"]
}
```

### GET /v1/events

List telemetry events in reverse-chronological order.

## Incidents

### POST /v1/incidents/from-event

Create an incident report from a telemetry event by running the full orchestration pipeline.

Returns `400` when the event does not exceed threshold.

### GET /v1/incidents

List incidents.

### GET /v1/incidents/{incident_id}

Fetch a single incident by ID.

Returns `404` when missing.

### POST /v1/incidents/{incident_id}

Acknowledge an incident (status set to acknowledged).

Returns `404` when missing.

### PATCH /v1/incidents/{incident_id}

Update incident status.

Request example:

```json
{"status": "acknowledged"}
```

Allowed statuses:

- `open`
- `acknowledged`
- `resolved`

Returns `404` when missing.

## RAG

### POST /v1/rag/documents

Ingest a raw document payload. The service chunks the content, stores chunks in `rag_documents`, and optionally indexes vectors when `RETRIEVAL_BACKEND=s3vectors`.

Request example:

```json
{
  "document_id": "rb_battery_thermal_v2",
  "source": "runbook",
  "title": "Battery Thermal Drift Response",
  "content": "Reduce duty cycle and inspect cooling system when battery thermal drift repeats.",
  "tags": ["battery", "thermal"]
}
```

Response includes chunk/index metadata:

```json
{
  "document_id": "rb_battery_thermal_v2",
  "source": "runbook",
  "title": "Battery Thermal Drift Response",
  "chunk_count": 3,
  "indexed_chunks": 3,
  "retrieval_backend": "s3vectors",
  "embedding_provider": "openai",
  "embedding_model": "text-embedding-3-large",
  "llm_model": "gpt-5.4-mini"
}
```

### GET /v1/rag/documents

List RAG document families grouped by base `document_id`.

### DELETE /v1/rag/documents/{document_id}

Delete a full document family, including all chunks and vector rows when S3 Vectors is enabled.

### POST /v1/rag/documents/upload

Upload a file for ingestion (`multipart/form-data`).

Supported file types: `.txt`, `.md`, `.markdown`, `.json`, `.jsonl`, `.csv`, `.log`, `.html`, `.htm`, `.pdf`, `.docx`.

Form fields:

- `file` (required)
- `source` (optional, default `manual`)
- `title` (optional)
- `tags` (optional, comma-separated)
- `document_id` (optional)
- `chunk_size_chars` (optional)
- `chunk_overlap_chars` (optional)

### POST /v1/rag/documents/upload/async

Queue a background ingestion job and return job state immediately.

Supports header `Idempotency-Key` to safely deduplicate retries.

### GET /v1/rag/ingestion-jobs

List recent ingestion jobs.

### GET /v1/rag/ingestion-jobs/{job_id}

Fetch one ingestion job status (`pending`, `running`, `succeeded`, `failed`).

### GET /v1/rag/search

Search indexed RAG documents.

Query parameters:

- `query`: search text (required)
- `limit`: max hits (default 5, min 1, max 50)

## Orchestration

### POST /v1/orchestrate/event

Ingest an event and immediately run orchestration to generate an incident.

Returns `400` when the event does not exceed threshold.

## Metrics

### GET /v1/metrics

Returns in-process counters and latency metrics.

Example response:

```json
{
  "events_ingested_total": 12.0,
  "incidents_generated_total": 7.0,
  "rag_queries_total": 4.0,
  "rag_query_latency_ms_last": 1.2,
  "orchestration_latency_ms_last": 11.4
}
```
