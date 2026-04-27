# Fleet Health Copilot

A software-only **multi-agent platform** for detecting and diagnosing incidents in simulated robotics/IoT fleets. 

Ingests telemetry events → detects anomalies → retrieves operational context (runbooks, incident history) → generates evidence-grounded incident reports through specialized agents (Monitor → Retriever → Diagnosis → Planner → Verifier → Reporter).

## What This Is

- **Capstone project** demonstrating multi-agent orchestration, RAG, MCP, production architecture, and cloud deployment patterns.
- **Software-only**: No hardware simulation or integration required.
- **Fast local demo**: Fully runnable on your machine with SQLite persistence and seed data.
- **Production-ready foundations**: CI/CD, Docker containerization, IaC, JSON schemas, structured evaluation metrics, and AWS edge/runtime infrastructure.

## Quick Start

### Prerequisites
- **Node.js 22+** (web app)
- **Python 3.11+** (orchestrator)
- **Clerk test keys** (authentication)

### 1. Install Dependencies

```bash
# Node.js web app
npm install --workspace apps/web

# Python environment
python -m venv .venv
.venv/bin/pip install -e "services/orchestrator[dev]"
```

### 2. Configure Environment

Copy and fill out Clerk keys in the web app:

```bash
cp apps/web/.env.example apps/web/.env.local
# Edit with your Clerk publishable and secret keys
```

### 3. Run Locally

Start the orchestrator (terminal 1):

```bash
PYTHONPATH=services/orchestrator/src .venv/bin/uvicorn fleet_health_orchestrator.main:app --reload --port 8000
```

Start the web app (terminal 2):

```bash
npm run web:dev
```

Visit `http://localhost:3000` and sign in with Clerk.

### 4. Populate RAG Context

Index the seed runbooks into the orchestrator's retrieval backend:

```bash
.venv/bin/python services/orchestrator/scripts/index_documents.py
```

### 5. Simulate an Incident

Sign in and click **"Simulate thermal incident"** on the Operations dashboard. The system will:
1. Detect the threshold breach (Monitor Agent).
2. Retrieve relevant runbooks and incident history (Retriever Agent).
3. Diagnose root causes (Diagnosis Agent).
4. Plan corrective actions (Planner Agent).
5. Verify the plan (Verifier Agent).
6. Generate a final incident report (Reporter Agent).

### 6. Investigate in the Operator Console

The app shell exposes three sections in the left sidebar:

| Section | Path | Purpose |
|---------|------|---------|
| **Operations** | `/` | Dashboard with incident queue, status stats, and simulation control |
| **Chat** | `/chat` | Persistent operator chat with RAG citations and action tools |
| **Knowledge** | `/rag` | Retrieval corpus management — upload, list, and delete documents |

From an open incident, click **"Open chat for this incident"** to jump into a context-scoped conversation. From chat you can ask grounded questions, update status, generate checklists, and create or simulate incidents.

## Architecture

```
┌─ Next.js Web App (Clerk auth)
│  └─ /v1/* FastAPI Orchestrator
│     ├─ Monitor Agent (anomaly detection)
│     ├─ Retriever Agent (RAG over runbooks, history)
│     ├─ Diagnosis Agent (hypothesize root causes)
│     ├─ Planner Agent (recommend actions)
│     ├─ Verifier Agent (validate recommendations)
│     ├─ Reporter Agent (compose incident report)
│     └─ SQLite or PostgreSQL + JSONL (persistence + seed data)
```

- **apps/web** — Authenticated operator console with sidebar shell: Operations dashboard, Chat workspace, and Knowledge corpus manager (Next.js, Clerk).
- **services/orchestrator** — Event ingestion, agent orchestration, RAG, incident persistence.
- **services/mcp-*** — MCP tool servers exposing telemetry, retrieval, and incident operations.
- **packages/contracts** — Shared JSON schemas for API contracts.
- **services/orchestrator/data** — Seed runbooks and telemetry events (JSONL).

Production AWS shape:

- CloudFront + WAF in front of the public web entrypoint.
- Public ALB for the Next.js web service.
- HTTP API Gateway + VPC Link in front of an internal orchestrator ALB.
- ECS Fargate for both web and orchestrator services.
- PostgreSQL (RDS) for orchestrator persistence in production, while local development stays on SQLite.

## Documentation

- [Architecture deep-dive](docs/architecture.md)
- [Demo walkthrough](docs/demo-runbook.md)
- [API reference](docs/API.md)
- [Release notes](docs/release-notes.md)
- [Technical report](docs/technical-report.md)
- [RAG with S3 Vectors (optional)](docs/s3-vectors-operations.md)

## Key Commands

| Command | Purpose |
|---------|---------|
| `npm run web:dev` | Start web app (port 3000) |
| `npm run web:lint` | Lint web code |
| `npm run web:build` | Build web for production |
| `npm run docs:links` | Validate local links in markdown docs |
| `npm run quality:check` | Run lint + web build + docs link check + orchestrator tests + MCP tests |
| `npm run orchestrator:latency:check` | Check average time-to-diagnosis against a local latency budget |
| `.venv/bin/uvicorn fleet_health_orchestrator.main:app --reload --port 8000` | Start orchestrator |
| `PYTHONPATH=services/orchestrator/src .venv/bin/pytest -q services/orchestrator/tests` | Run all orchestrator tests |
| `.venv/bin/python services/orchestrator/scripts/evaluate_pipeline.py` | Run full evaluation (precision, recall, latency, etc.) |
| `.venv/bin/python services/orchestrator/scripts/index_documents.py` | Index seed runbooks into SQLite RAG |
| `.venv/bin/python services/orchestrator/scripts/replay_events.py` | Replay seed events to test end-to-end |

## Testing & Evaluation

### Unit and Integration Tests
```bash
# Run orchestrator tests
PYTHONPATH=services/orchestrator/src .venv/bin/pytest -q services/orchestrator/tests

# Run web tests
npm run web:test
```

### End-to-End Evaluation
```bash
# Full pipeline evaluation: precision, recall, retrieval hit rate, mean reciprocal rank, verifier pass rate, latency
.venv/bin/python services/orchestrator/scripts/evaluate_pipeline.py
```

## Docker (Optional)

```bash
docker compose up --build
```

Starts the orchestrator and all MCP servers in containers. Web app still runs locally.
```

Configure Clerk and the orchestrator URL:

```bash
cp apps/web/.env.example apps/web/.env.local
```

Set real `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` values in `apps/web/.env.local`. The default orchestrator URL is `http://127.0.0.1:8000`.

Optional orchestrator HTTP settings:

- `FLEET_DATABASE_URL` points the API at PostgreSQL and takes precedence over SQLite when set.
- `FLEET_DB_PATH` points the SQLite file used by the API (default under `services/orchestrator/data/`).
- `FLEET_CORS_ORIGINS` is a comma-separated list of allowed browser origins (for example `https://your-web-alb.example.com`). When unset, **no** CORS middleware is registered (fine for server-to-server or local Next.js API routes). When set, the orchestrator sends a tight `Access-Control-Allow-Origin` for those origins—use this when `NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL` exposes the orchestrator directly to the browser (common with ECS + ALB).
- `GET /health` returns process up. `GET /ready` returns **200** only when the SQLite parent directory is writable, SQLite answers `SELECT 1`, and the repository can list RAG metadata—useful for load-balancer readiness checks.

Optional orchestrator retrieval settings:

- `FLEET_RETRIEVAL_BACKEND=lexical` keeps the local default lexical token search.
- `FLEET_RETRIEVAL_BACKEND=s3vectors` calls Amazon S3 Vectors `query_vectors` through boto3 (`s3vectors` client).
- Either `FLEET_S3_VECTORS_BUCKET` and `FLEET_S3_VECTORS_INDEX`, or `FLEET_S3_VECTORS_INDEX_ARN`, is required when `s3vectors` is selected.
- `FLEET_S3_VECTORS_EMBEDDING_DIM` defaults to `3072` and must match the vector index dimension.
- `FLEET_S3_VECTORS_QUERY_VECTOR_JSON` is optional: a JSON array of floats used as the query vector for every search (same length as the embedding dim). Use it for integration checks against a known index; otherwise the service derives a deterministic pseudo-vector from the query string for API shape only—**production** queries should use the same embedding model as ingestion.

IAM: grant `s3vectors:QueryVectors`, and `s3vectors:GetVectors` when metadata or filters are returned (the backend sets `returnMetadata=true`). For indexing scripts, also grant `s3vectors:PutVectors`.

**Query embeddings** (`FLEET_EMBEDDING_PROVIDER`, default `hash`): `hash` (deterministic, no extra deps), `openai` (`FLEET_OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`), `http` (`FLEET_EMBEDDING_HTTP_URL` returning JSON `{"embedding":[...]}`), or `sentence_transformers` (install `pip install -e "services/orchestrator[embeddings]"` and set `FLEET_SENTENCE_TRANSFORMER_MODEL`). For production, use `openai` with `OPENAI_EMBEDDING_MODEL=text-embedding-3-large`. The embedding dimension must match the S3 Vectors index.

**OpenAI LLM calls** (requires `FLEET_OPENAI_API_KEY`): incident summary refinement, diagnosis generation/enrichment, and action planning use OpenAI Responses API calls with traces, defaulting to `gpt-5.4-mini` (`LLM_REPORT_MODEL`, `LLM_DIAGNOSIS_MODEL`).

**RAG ingestion API**:

- `POST /v1/rag/documents` ingests raw text payloads and chunks them for retrieval.
- `POST /v1/rag/documents/upload` accepts `.txt`, `.md`, `.markdown`, `.json`, `.jsonl`, `.csv`, `.log`, `.html`, `.htm`, `.pdf`, and `.docx`, chunks automatically, persists chunks, and indexes to S3 Vectors when `FLEET_RETRIEVAL_BACKEND=s3vectors`.
- `POST /v1/rag/documents/upload/async` queues ingestion and returns a job record immediately.
- `GET /v1/rag/ingestion-jobs/{job_id}` retrieves status (`pending`, `running`, `succeeded`, `failed`).
- `GET /v1/rag/ingestion-jobs` lists recent jobs.
- Chunking controls: `RAG_CHUNK_SIZE_CHARS`, `RAG_CHUNK_OVERLAP_CHARS`, `RAG_UPLOAD_MAX_BYTES`, `RAG_INDEX_BATCH_SIZE`.

**Index vectors from SQLite** (after runbooks are in the DB):

```bash
.venv/bin/python services/orchestrator/scripts/index_s3_vectors.py --bucket YOUR_BUCKET --index YOUR_INDEX
# or: --index-arn arn:aws:s3vectors:...
```

## Run Locally

Start the orchestrator:

```bash
PYTHONPATH=services/orchestrator/src .venv/bin/uvicorn fleet_health_orchestrator.main:app --reload --port 8000
```

Start the web app:

```bash
npm run web:dev
```

Open `http://localhost:3000`, sign in, and use the simulation button to create a thermal incident. The incident detail view shows confidence, agent trace, verification checks, evidence, and acknowledge/resolve actions.

## Demo Script

The local seed data covers multiple scenarios in `services/orchestrator/data/sample_events.jsonl` (battery thermal, motor current, network latency, vibration RMS, and true-negative controls). A reproducible evaluation snapshot is in [docs/capstone-demo-artifacts.md](docs/capstone-demo-artifacts.md).

With the orchestrator running, index sample runbooks and historical incidents:

```bash
.venv/bin/python services/orchestrator/scripts/index_documents.py
# optional explicit file
.venv/bin/python services/orchestrator/scripts/index_documents.py --documents-file services/orchestrator/data/runbooks_detailed.jsonl
```

The default seed file now uses a richer production-style runbook corpus at [services/orchestrator/data/runbooks_detailed.jsonl](services/orchestrator/data/runbooks_detailed.jsonl).

Replay sample telemetry events:

```bash
.venv/bin/python services/orchestrator/scripts/replay_events.py
```

Run the end-to-end evaluation helper:

```bash
.venv/bin/python services/orchestrator/scripts/evaluate_pipeline.py
```

The evaluation helper posts each event to `/v1/orchestrate/event` and reports anomaly precision/recall, retrieval hit rate, agent task success rate, response latency, and time-to-diagnosis. To refresh the checked-in metric snapshot without Uvicorn, run `PYTHONPATH=services/orchestrator/src .venv/bin/python scripts/capture_capstone_eval_snapshot.py`.

Then refresh the dashboard and open an incident detail page to inspect summary, hypotheses, actions, and retrieved runbook or incident evidence.

## MCP Tools

The `services/mcp-*` packages keep plain Python helper functions and expose minimal MCP server commands:

```bash
ORCHESTRATOR_API_BASE_URL=http://127.0.0.1:8000 mcp-telemetry
ORCHESTRATOR_API_BASE_URL=http://127.0.0.1:8000 mcp-retrieval
ORCHESTRATOR_API_BASE_URL=http://127.0.0.1:8000 mcp-incidents
```

Available tools:

- `mcp-telemetry`: `query_device_events(device_id, limit)` and `lookup_device_health(device_id)` delegate to `/v1/events`.
- `mcp-retrieval`: `search_operational_context(query, limit)` delegates to `/v1/rag/search`.
- `mcp-incidents`: `create_incident(event_payload)`, `search_incidents()`, `read_incident(incident_id)`, `update_incident(incident_id, status)`, and `search_maintenance_history(device_id)` delegate to incident endpoints.

## Verification

Run the main checks:

```bash
npm run web:lint
npm run web:build
npm run docs:links
PYTHONPATH=services/orchestrator/src .venv/bin/pytest -q services/orchestrator/tests
PYTHONPATH=services/mcp-telemetry/src .venv/bin/pytest -q services/mcp-telemetry/tests
PYTHONPATH=services/mcp-retrieval/src .venv/bin/pytest -q services/mcp-retrieval/tests
PYTHONPATH=services/mcp-incidents/src .venv/bin/pytest -q services/mcp-incidents/tests

# one-command quality gate from repo root
npm run quality:check
```

AWS deployment is automated in **`.github/workflows/deploy-aws.yml`**:

- Push to `main` deploys to the `prod` GitHub Environment.
- `workflow_dispatch` runs a manual production deploy.

The deploy workflow performs OIDC auth, Terraform init/validate/apply, ECR image build+push for web/orchestrator, a second Terraform apply pinned to the commit SHA image tags, ECS stabilization, a post-deploy ALB health check, and an API Gateway `/health` check when API Gateway is enabled. Terraform now provisions the production edge/runtime path: CloudFront, WAF, API Gateway, ECS, and PostgreSQL.

Required GitHub Environment secrets for `prod` deploys:

- `AWS_ROLE_ARN`
- `TF_STATE_BUCKET`
- `TF_LOCK_TABLE`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `CLERK_SECRET_KEY`
- `VPC_ID`
- `PUBLIC_SUBNET_IDS_JSON`

Optional Terraform setting (recommended for production network isolation):

- `private_subnet_ids` in `infra/terraform/env/prod.tfvars` (list of private subnets for PostgreSQL, internal ALB, and API Gateway VPC Link). When omitted, Terraform falls back to `public_subnet_ids`.

You can also run the full local stack with Docker:

```bash
export NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
export CLERK_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
docker compose up --build
```

The web container builds the Next.js app and serves it with `next start`. Supply real Clerk keys through the exported environment variables before using protected routes.

## Current Scope

The current implementation is a concise capstone core: deterministic six-agent orchestration (monitor through reporter), lexical RAG (default), optional AWS S3 Vectors RAG with pluggable embeddings, MCP tools, SQLite persistence, Clerk-protected OpenAI-style UI, evaluation metrics (including retrieval mean reciprocal rank and verifier pass rate), and AWS deployment scaffolding. Retrieval lives in `services/orchestrator/src/fleet_health_orchestrator/rag.py` with helpers in `embeddings.py`.

AWS infrastructure remains scaffolded under `infra/terraform` for optional environment provisioning. For S3 Vectors and embeddings, keep **`FLEET_EMBEDDING_PROVIDER`** aligned with indexing and query-time configuration; optional OpenAI flags are documented under **Optional OpenAI assist** above.

The canonical deployment path is now GitHub Actions + Terraform for production under `infra/terraform/env/prod.tfvars`.

## Git and history

If you rewrite `main` (for example to strip automated commit trailers), publish with:

```bash
git push --force-with-lease origin main
```

Operational checklist for S3 Vectors in AWS: [docs/s3-vectors-operations.md](docs/s3-vectors-operations.md).
