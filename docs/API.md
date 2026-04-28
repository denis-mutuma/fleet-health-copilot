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
  "llm_model": "gpt-4o-mini"
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

## Chat

### POST /v1/chat/sessions

Create a persistent chat session.

Request example:

```json
{
  "incident_id": "inc_abc123"
}
```

`incident_id` is optional. When provided, chat answers are scoped with incident context.

### GET /v1/chat/sessions

List recent chat sessions, ordered by update time.

### GET /v1/chat/sessions/{session_id}

Fetch one full conversation with session metadata and all messages.

### POST /v1/chat/sessions/{session_id}/messages

Post a user message and receive an updated conversation (user + assistant messages persisted).

Request example:

```json
{
  "content": "What runbooks apply to battery thermal drift?"
}
```

Assistant messages can include:

- `citations`: RAG-grounding references (document ID, source, score, excerpt)
- `action`: command/action type
- `action_status`: `success` or `error`
- `action_payload`: structured action output for UI cards
- `tool_calls`: MCP tool execution records for the assistant turn (tool name, input, output/error, latency)
- `trace_spans`: OpenAI and MCP span telemetry (latency, token usage, per-call estimated cost)
- `llm_cost_usd`: cumulative estimated LLM cost for the assistant turn, derived from token usage and configured rates

Chat execution behavior is controlled by environment settings:

- `LLM_CHAT_ENABLED`, `LLM_CHAT_MODEL`, `LLM_CHAT_TEMPERATURE`, `LLM_CHAT_MAX_OUTPUT_TOKENS`
- `CHAT_TOOL_TIMEOUT_SECONDS` enforces a hard timeout per tool call
- `CHAT_TOOL_MAX_CALLS_PER_TURN` caps tool calls per assistant turn
- `CHAT_TOOL_TRANSPORT=local|http_json` selects local in-process tool execution or remote HTTP JSON API calls
- `CHAT_TOOL_HTTP_RETRIEVAL_BASE_URL`, `CHAT_TOOL_HTTP_INCIDENTS_BASE_URL`, `CHAT_TOOL_HTTP_TELEMETRY_BASE_URL` configure HTTP JSON transport endpoints
- `LLM_CHAT_INPUT_COST_PER_1K_TOKENS_USD`, `LLM_CHAT_OUTPUT_COST_PER_1K_TOKENS_USD` configure cost estimation rates

Supported command patterns in message content:

- `report incident metric=<metric> device=<device_id> value=<n> threshold=<n>`
- `/list incidents`
- `/open <incident_id>`
- `/status <incident_id> <open|acknowledged|resolved>`
- `/checklist [incident_id]`
- `/simulate`

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
