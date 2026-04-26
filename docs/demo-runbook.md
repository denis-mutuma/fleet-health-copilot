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

## Rehearsal checklist

- Confirm orchestrator `/health`, `/ready`, and web load after `npm run web:dev`.
- Run `index_documents.py` so RAG retrieval is non-empty before simulation.
- Walk one **battery**, one **motor**, and one **network** incident; open detail and read verification + evidence.
- Run `evaluate_pipeline.py` once and skim `verifier_pass_rate` and retrieval metrics.

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

A checked-in snapshot of the JSON metrics (same seed files, no live port) lives in [capstone-demo-artifacts.md](capstone-demo-artifacts.md). Regenerate it after changing runbooks or sample events:

```bash
PYTHONPATH=services/orchestrator/src .venv/bin/python scripts/capture_capstone_eval_snapshot.py
```

The exact numeric values can drift with hardware and seed edits, but the metric names map to real confusion-matrix, retrieval (including mean reciprocal rank of the expected runbook), agent-success, and latency checks.

For **latency** in AWS, use the JSON fields from `evaluate_pipeline.py` locally first; in ECS, pair that narrative with **CloudWatch** log-derived duration or ALB target response metrics once you enable observability.

## Failure cases (demo QA)

If something looks wrong during rehearsal, use this short triage list:

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Empty evidence / generic actions | RAG miss (no indexed runbooks or lexical mismatch) | Run `index_documents.py`; confirm query terms overlap seed titles. |
| Verification warnings or blocked actions | Verifier rejected citations not present in retrieval | Re-run after indexing; avoid citing runbook IDs that were not retrieved. |
| `s3vectors` errors in logs | IAM or wrong bucket/index/embedding dimension | Check `s3vectors:QueryVectors` (and `GetVectors` if needed), env vars, and [s3-vectors-operations.md](s3-vectors-operations.md). |
| ECS task stuck / unhealthy | Image pull, secrets, or DB volume | Inspect task stopped reason, ECR tag exists, Secrets Manager values populated, EFS mount for SQLite. |

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
