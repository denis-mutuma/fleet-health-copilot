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
- **Index RAG sample runbooks:** `.venv/bin/python services/orchestrator/scripts/index_documents.py`
- **Run pipeline evaluation:** `.venv/bin/python services/orchestrator/scripts/evaluate_pipeline.py`
- **Run local stack with Docker:** `docker compose up --build`
- **Run orchestrator API locally:** `PYTHONPATH=services/orchestrator/src .venv/bin/uvicorn fleet_health_orchestrator.main:app --reload --port 8000`

## Current MVP UI/API workflow

- Dashboard (`/`) now reads live incidents from orchestrator `/v1/incidents`.
- “Simulate thermal incident” in the dashboard calls web API `/api/incidents` which posts a canonical telemetry event to orchestrator `/v1/orchestrate/event`.
- Incident details are shown at `/incidents/[incident_id]` with summary, hypotheses, actions, and evidence.

### Web environment variables

- `ORCHESTRATOR_API_BASE_URL` (server-side preferred): orchestrator base URL used by Next.js server components and route handlers.
- `NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL` (fallback): public fallback if server-only variable is not set.

## High-level architecture

The target system (from `idea/context.md` and `idea/Capstone Project Direction.md`) is a **Fleet Health Copilot**: a software-only, multi-agent platform for robotics/IoT fleet operations.

End-to-end architecture:

1. **Data layer:** synthetic/replayed telemetry, logs, maintenance history, incident records, and runbook/docs corpus.
2. **Ingestion layer:** `services/orchestrator` receives events at `/v1/events`; replay scripts live under `services/orchestrator/scripts`.
3. **Retrieval layer (RAG):** index docs through `/v1/rag/documents` and query through `/v1/rag/search`; current baseline is lexical retrieval over persisted runbook/incident docs.
4. **Agent layer:** monitor/retriever/reporter orchestration is exposed by `/v1/orchestrate/event` and persisted as incident reports.
5. **MCP tool layer:** MCP servers expose operational tools (telemetry query, log search, vector search, status/history lookup, incident/report actions).
6. **Cloud layer:** AWS-oriented hosting/orchestration/storage/evaluation and experimentation workflows.

Primary product flow: ingest operational signals -> detect anomaly -> retrieve context -> diagnose -> plan + verify action -> generate operator-facing incident/maintenance report.

## Key conventions for this codebase

These are explicit project constraints captured in `idea/context.md`:

- Keep the capstone **software-only**; avoid hardware-dependent implementation.
- Favor **production-style modular design** (clear service and agent boundaries) over a chatbot-style single-agent app.
- Maintain a **simple, short, clear, concise** code style.
- Planned stack preferences: **Next.js** (UI), **uv** (Python environment), **Docker**, **AWS** cloud services, **AWS S3 Vectors** for retrieval storage, **Clerk** for authentication.
- Planned delivery/deployment conventions: **Terraform** for infrastructure and **GitHub Actions** workflows for **dev**, **test**, and **production**.
- UI direction should follow an **OpenAI website-like theme**.
- Keep request/response contracts aligned with JSON schemas in `packages/contracts/`.
- Treat `services/orchestrator/data/*.jsonl` as seed datasets for local replay/index/evaluation loops.

## MVP use-case baseline (implementation default)

When multiple options are possible, default to this first vertical slice:

- **Scenario:** Battery thermal drift incident on one simulated robot in a fleet.
- **Agents in MVP:** `Monitor` (anomaly trigger), `Retriever` (past incident + runbook lookup), `Reporter` (operator-facing summary).
- **Minimal UI scope:** authenticated dashboard with fleet incident list and single incident detail/report view.
- **Out-of-scope for MVP:** planner/verifier agents, autonomous remediation execution, real hardware integration.

Canonical event shape for MVP plumbing:

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

Canonical incident report shape from orchestration:

```json
{
  "incident_id": "inc_01H...",
  "device_id": "robot-03",
  "status": "open",
  "summary": "Battery thermal drift detected with similar historical incidents.",
  "root_cause_hypotheses": ["cooling degradation", "ambient overload"],
  "recommended_actions": [
    "Reduce duty cycle by 20%",
    "Schedule cooling system inspection within 24h"
  ],
  "evidence": {
    "matched_incidents": ["inc_2025_102", "inc_2025_187"],
    "runbooks": ["rb_battery_thermal_v2"]
  }
}
```
