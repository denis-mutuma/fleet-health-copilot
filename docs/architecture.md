# Architecture

Fleet Health Copilot is a software-only incident operations platform for simulated robotics and IoT fleets. It demonstrates telemetry ingestion, deterministic multi-agent orchestration, retrieval-augmented context, MCP tool access, and operator-facing incident reports.

## System View

```mermaid
flowchart LR
  operator["Operator"] --> webApp["Next.js Dashboard"]
  webApp --> webApi["Next.js API Routes"]
  webApi --> orchestrator["FastAPI Orchestrator"]
  orchestrator --> sqlite["SQLite Store"]
  orchestrator --> ragBackend["Retrieval Backend"]
  mcpTools["MCP Tool Servers"] --> orchestrator
  seedData["Seed Events And Runbooks"] --> orchestrator
```

Primary components:

- `apps/web`: Clerk-protected Next.js dashboard for incident list/detail views and simulation.
- `services/orchestrator`: FastAPI service for telemetry ingestion, RAG search, incident orchestration, persistence, and metrics.
- `services/mcp-*`: MCP tool servers for telemetry, retrieval, and incident actions.
- `services/orchestrator/data`: JSONL seed data for demo events, runbooks, and historical incidents.
- `packages/contracts`: JSON Schemas for event and incident report shapes.

## Runtime Flow

```mermaid
sequenceDiagram
  participant Operator
  participant Web as Next.js Web
  participant API as Next.js API
  participant Orchestrator as FastAPI Orchestrator
  participant Agents as Agent Orchestrator
  participant Retrieval as Retrieval Backend
  participant Store as SQLite

  Operator->>Web: Trigger incident simulation
  Web->>API: POST /api/incidents
  API->>Orchestrator: POST /v1/orchestrate/event
  Orchestrator->>Store: Persist telemetry event
  Orchestrator->>Agents: Execute agent pipeline
  Note right of Agents: Monitor, Retriever, Diagnosis, Planner, Verifier, Reporter
  Agents->>Retrieval: Search runbooks and incident history
  Retrieval-->>Agents: Return ranked evidence
  Agents-->>Orchestrator: Incident report
  Orchestrator->>Store: Persist incident
  Orchestrator-->>API: Incident report
  API-->>Web: Incident report
  Web-->>Operator: Dashboard and detail view
```

## Agent Flow

```mermaid
flowchart LR
  event["Telemetry Event"] --> monitor["Monitor Agent"]
  monitor -->|"value > threshold"| retriever["Retriever Agent"]
  monitor -->|"value <= threshold"| reject["Reject Non-Anomaly"]
  retriever --> context["Runbooks And Incident History"]
  context --> diagnosis["Diagnosis Agent"]
  diagnosis --> planner["Planner Agent"]
  planner --> verifier["Verifier Agent"]
  verifier --> reporter["Reporter Agent"]
  reporter --> report["Evidence-Grounded Incident Report"]
```

Current agents are intentionally simple and deterministic:

- `MonitorAgent` flags events whose metric value exceeds the threshold.
- `RetrieverAgent` builds a query from metric, tags, and severity.
- `DiagnosisAgent` derives root-cause hypotheses from telemetry and retrieved history.
- `PlannerAgent` converts runbook evidence into operator actions.
- `VerifierAgent` checks that recommendations are grounded and conservative.
- `ReporterAgent` produces a structured incident report with confidence, trace, verification, latency, and evidence.

## Retrieval

Retrieval is behind a small backend interface:

- `LexicalRetrievalBackend` is the local default and ranks documents by token overlap.
- `S3VectorsRetrievalBackend` is opt-in and calls AWS S3 Vectors `query_vectors` (boto3 `s3vectors` client), mapping vector metadata plus the SQLite-backed document list into `RetrievalHit` rows. Query embeddings are pluggable (`FLEET_EMBEDDING_PROVIDER`: hash, OpenAI, HTTP, or optional sentence-transformers); `scripts/index_s3_vectors.py` upserts SQLite RAG rows into an index with the same embedder. See [s3-vectors-operations.md](s3-vectors-operations.md) for IAM and rollout order.
- `FLEET_RETRIEVAL_BACKEND=lexical` keeps local development dependency-light; set `FLEET_RETRIEVAL_BACKEND=s3vectors` with bucket/index or index ARN when running against AWS.

## MCP Tool Layer

The MCP layer exposes orchestrator capabilities as tool servers:

- `mcp-telemetry`: `query_device_events(device_id, limit)`, `lookup_device_health(device_id)`
- `mcp-retrieval`: `search_operational_context(query, limit)`
- `mcp-incidents`: `create_incident(event_payload)`, `search_incidents()`, `read_incident(incident_id)`, `update_incident(incident_id, status)`, `search_maintenance_history(device_id)`

These tools keep the capstone modular and make the orchestrator accessible to agent hosts without coupling them to the web UI.

## Deployment Shape

Local deployment uses Docker Compose:

- `web`: production-built Next.js app served with `next start`.
- `orchestrator`: FastAPI API served by Uvicorn.

AWS deploy automation runs through **[`.github/workflows/deploy-aws.yml`](../.github/workflows/deploy-aws.yml)** with Terraform in `infra/terraform` for the `prod` environment.
