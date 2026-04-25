# Demo Runbook

This runbook shows the fastest path to demo Fleet Health Copilot locally.

## Prerequisites

- Node.js 22 for the Next.js web app.
- Python 3.11+ with a local `.venv`.
- Clerk test keys for authenticated web routes.
- Docker, if using the containerized flow.

Install dependencies:

```bash
npm install --workspace apps/web
python -m venv .venv
.venv/bin/pip install -e "services/orchestrator[dev]"
```

Configure web env:

```bash
cp apps/web/.env.example apps/web/.env.local
```

Set real values for:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `CLERK_SECRET_KEY`

## Local Process Demo

Start the orchestrator:

```bash
PYTHONPATH=services/orchestrator/src .venv/bin/uvicorn fleet_health_orchestrator.main:app --reload --port 8000
```

Start the web app in another terminal:

```bash
npm run web:dev
```

Index sample runbooks and historical incidents:

```bash
.venv/bin/python services/orchestrator/scripts/index_documents.py
```

Open `http://localhost:3000`, sign in, and click the simulation button.

Expected result:

- Dashboard shows an open incident for `robot-03`.
- Incident detail shows summary, hypotheses, recommended actions, confidence, agent trace, verification checks, latency, and evidence.
- Evidence references retrieved runbooks or historical incidents, not synthetic fallback IDs.

## Evaluation Demo

Run the evaluation helper:

```bash
.venv/bin/python services/orchestrator/scripts/evaluate_pipeline.py
```

Expected output shape:

```json
{
  "events_total": 4.0,
  "expected_anomalies": 3.0,
  "incidents_generated": 3.0,
  "true_positives": 3.0,
  "false_positives": 0.0,
  "false_negatives": 0.0,
  "true_negatives": 1.0,
  "precision": 1.0,
  "recall": 1.0,
  "accuracy": 1.0,
  "retrieval_hit_rate": 1.0,
  "agent_task_success_rate": 1.0,
  "average_response_latency_ms": 12.3,
  "average_time_to_diagnosis_ms": 1.2
}
```

The exact values can change if seed events change, but the important presentation point is that the metric names map to real confusion-matrix, retrieval, agent-success, and latency checks.

## MCP Tool Demo

With the orchestrator running, each MCP package can be started as a tool server:

```bash
ORCHESTRATOR_API_BASE_URL=http://127.0.0.1:8000 mcp-telemetry
ORCHESTRATOR_API_BASE_URL=http://127.0.0.1:8000 mcp-retrieval
ORCHESTRATOR_API_BASE_URL=http://127.0.0.1:8000 mcp-incidents
```

Tools exposed:

- `query_device_events(device_id, limit)`
- `lookup_device_health(device_id)`
- `search_operational_context(query, limit)`
- `create_incident(event_payload)`
- `search_incidents()`
- `read_incident(incident_id)`
- `update_incident(incident_id, status)`
- `search_maintenance_history(device_id)`

Use this part of the demo to explain how an external agent host could call operational tools without coupling directly to the dashboard.

## Docker Demo

Export Clerk keys and start the stack:

```bash
export NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
export CLERK_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
docker compose up --build
```

Open `http://localhost:3000`.

Expected result:

- `orchestrator` starts Uvicorn on port `8000`.
- `web` builds the production Next.js app and serves it on port `3000`.

## Verification

Run the full local check set:

```bash
npm run web:lint
npm run web:build
PYTHONPATH=services/orchestrator/src .venv/bin/pytest -q services/orchestrator/tests
PYTHONPATH=services/mcp-telemetry/src .venv/bin/pytest -q services/mcp-telemetry/tests
PYTHONPATH=services/mcp-retrieval/src .venv/bin/pytest -q services/mcp-retrieval/tests
PYTHONPATH=services/mcp-incidents/src .venv/bin/pytest -q services/mcp-incidents/tests
```

## Talk Track

1. Fleet telemetry arrives as structured events.
2. The monitor agent gates the workflow by checking anomaly thresholds.
3. The retriever agent searches runbooks and incident history.
4. The diagnosis, planner, and verifier agents turn evidence into safe operator actions.
5. The reporter agent generates an evidence-grounded incident report with confidence and traceability.
6. The dashboard gives operators a simple incident operations view.
7. MCP tools expose the same operational capabilities to external agent hosts.
