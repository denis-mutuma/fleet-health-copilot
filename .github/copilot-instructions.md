# Copilot Instructions for `fleet-health-copilot`

## Build, test, and lint commands

Repository now has a monorepo scaffold with a Next.js app and Python orchestrator service.

- **Install web deps:** `npm install --workspace apps/web`
- **Run web app (dev):** `npm run web:dev`
- **Build web app:** `npm run web:build`
- **Lint web app:** `npm run web:lint`
- **Run orchestrator tests (full):** `PYTHONPATH=services/orchestrator/src .venv/bin/pytest -q services/orchestrator/tests`
- **Run a single orchestrator test:** `PYTHONPATH=services/orchestrator/src .venv/bin/pytest -q services/orchestrator/tests/test_health.py::test_rag_index_and_search`
- **Replay telemetry sample data:** `.venv/bin/python services/orchestrator/scripts/replay_events.py`
- **Index RAG sample runbooks (HTTP to orchestrator):** `.venv/bin/python services/orchestrator/scripts/index_documents.py`
- **Index SQLite RAG docs into Amazon S3 Vectors (AWS creds + index):** `.venv/bin/python services/orchestrator/scripts/index_s3_vectors.py --bucket BUCKET --index INDEX` (see `docs/s3-vectors-operations.md`; use `--dry-run` first)
- **Run pipeline evaluation:** `.venv/bin/python services/orchestrator/scripts/evaluate_pipeline.py` (outputs include precision/recall, retrieval hit rate, **mean reciprocal rank**, **verifier_pass_rate**, latency)
- **Run local stack with Docker:** `docker compose up --build`
- **Run orchestrator API locally:** `PYTHONPATH=services/orchestrator/src .venv/bin/uvicorn fleet_health_orchestrator.main:app --reload --port 8000`

## Current UI/API workflow

- Dashboard (`/`) reads live incidents from orchestrator `/v1/incidents`.
- Simulation calls web API `/api/incidents` which posts a telemetry payload to orchestrator `/v1/orchestrate/event`.
- Incident details at `/incidents/[incident_id]` show summary, hypotheses, actions, confidence, agent trace, verification, latency, and evidence.

### Web environment variables

- `ORCHESTRATOR_API_BASE_URL` (server-side preferred): orchestrator base URL used by Next.js server components and route handlers.
- `NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL` (fallback): public fallback if server-only variable is not set.

## High-level architecture

The target system (from `idea/context.md` and `idea/Capstone Project Direction.md`) is a **Fleet Health Copilot**: a software-only, multi-agent platform for robotics/IoT fleet operations.

End-to-end architecture:

1. **Data layer:** synthetic/replayed telemetry, maintenance history, incident records, and runbook/docs corpus (`services/orchestrator/data/*.jsonl`).
2. **Ingestion layer:** `services/orchestrator` receives events at `/v1/events` and `/v1/orchestrate/event`; replay scripts live under `services/orchestrator/scripts`.
3. **Retrieval layer (RAG):** index docs through `/v1/rag/documents` and query through `/v1/rag/search`. Default retrieval is **lexical** over SQLite. Optional **`FLEET_RETRIEVAL_BACKEND=s3vectors`** uses Amazon S3 Vectors `query_vectors` with pluggable **`FLEET_EMBEDDING_PROVIDER`** (`hash`, `openai`, `http`, optional `sentence_transformers` in `[embeddings]` extra). **`index_s3_vectors.py`** upserts embedded documents from SQLite into an S3 Vectors index (same embedder as queries). See `docs/s3-vectors-operations.md` and `README.md`.
4. **Agent layer:** `/v1/orchestrate/event` runs **Monitor → Retriever → Diagnosis → Planner → Verifier → Reporter** (deterministic pipeline in `services/orchestrator/src/fleet_health_orchestrator/agents.py`). Optional OpenAI-assisted summary refinement lives in `llm.py` behind env flags.
5. **MCP tool layer:** MCP servers expose operational tools (telemetry, retrieval search, incident CRUD and status, maintenance history) delegating to the orchestrator HTTP API.
6. **Cloud layer:** Terraform under `infra/terraform`, bootstrap module `infra/terraform/bootstrap-state`, `backend.tf.example` for S3 remote state, GitHub Actions `test.yml` on PRs, and **`deploy-dev.yml`** (`workflow_dispatch`: fmt/validate; optional **`terraform plan`** when repository secret **`AWS_ROLE_ARN`** is configured for OIDC).

Primary product flow: ingest operational signals → detect anomaly → retrieve context → diagnose → plan → verify grounding → generate operator-facing incident report.

## Key conventions for this codebase

These are explicit project constraints captured in `idea/context.md`:

- Keep the capstone **software-only**; avoid hardware-dependent implementation.
- Favor **production-style modular design** (clear service and agent boundaries) over a chatbot-style single-agent app.
- Maintain a **simple, short, clear, concise** code style.
- Planned stack preferences: **Next.js** (UI), **uv** (Python environment), **Docker**, **AWS** cloud services, **AWS S3 Vectors** for optional vector retrieval, **Clerk** for authentication.
- Planned delivery/deployment conventions: **Terraform** for infrastructure and **GitHub Actions** workflows for **dev**, **test**, and **production**.
- UI direction should follow an **OpenAI website-like theme**.
- Keep request/response contracts aligned with JSON schemas in `packages/contracts/`.
- Treat `services/orchestrator/data/*.jsonl` as seed datasets for local replay/index/evaluation loops.

## Primary demo scenario (implementation default)

When multiple options are possible, default to this vertical slice:

- **Scenario:** Battery thermal drift (and optionally motor or network) on simulated robots in `sample_events.jsonl`.
- **Agents (all implemented):** `MonitorAgent`, `RetrieverAgent`, `DiagnosisAgent`, `PlannerAgent`, `VerifierAgent`, `ReporterAgent`.
- **UI scope:** authenticated dashboard with incident list, detail/report view, simulation, acknowledge/resolve.
- **Out of scope:** autonomous remediation execution, real hardware integration.
- **Optional extensions:** LLM-backed copy or planning (see `llm.py` and README env vars), full `terraform apply` in AWS after remote state and OIDC setup (`docs/terraform-bootstrap.md`).

Canonical event shape for plumbing:

```json
{
  "event_id": "evt_01H...",
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

Canonical incident report shape (fields may vary; orchestration adds confidence, trace, verification, latency):

```json
{
  "incident_id": "inc_01H...",
  "device_id": "robot-03",
  "status": "open",
  "summary": "battery_temp_c exceeded threshold on robot-03.",
  "root_cause_hypotheses": ["cooling degradation", "ambient overload"],
  "recommended_actions": ["Follow rb_battery_thermal_v2: Reduce duty cycle..."],
  "evidence": {
    "matched_incidents": ["inc_2025_102"],
    "runbooks": ["rb_battery_thermal_v2"]
  },
  "confidence_score": 0.75,
  "agent_trace": ["MonitorAgent detected...", "RetrieverAgent returned 1 context hits"],
  "verification": { "passed": true, "checks": ["runbook evidence attached"], "warnings": [] },
  "latency_ms": 12.5
}
```
