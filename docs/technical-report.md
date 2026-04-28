# Technical Report

## Project Summary

Fleet Health Copilot is a software-only multi-agent operations platform for robotics and IoT fleets. It ingests telemetry events, detects anomalous device behavior, retrieves runbook and incident-history context, and generates evidence-grounded incident reports for authenticated operators.

The project demonstrates system design across a web UI, orchestration API, persistence layer, retrieval backend, MCP tool layer, Docker runtime, CI quality gates, and repeatable evaluation.

## Problem Statement

Operators of robotic or edge-device fleets need fast, explainable incident triage. Raw telemetry alone does not tell an operator what happened, whether it resembles prior failures, or what action to take next.

Fleet Health Copilot addresses this by turning telemetry threshold crossings into structured incident reports that include:

- affected device and incident state,
- likely root-cause hypotheses,
- recommended operator actions,
- retrieved evidence from runbooks and historical incidents.

## Goals

Primary goals:

- Build a working end-to-end incident workflow from telemetry event to evidence-grounded report.
- Use multiple specialized agents with distinct responsibilities.
- Add retrieval-augmented context over runbooks and incident history.
- Expose operational capabilities through MCP tool servers.
- Keep the codebase simple, modular, and production-oriented.
- Support local development, Docker, and CI verification.

Non-goals for the current MVP:

- Physical hardware integration.
- Autonomous remediation.
- Operating a hosted multi-tenant cloud product (the repo ships **IaC and GitHub Actions** for **your** AWS account; applying it remains an operator responsibility).
- LLM-generated actions without evidence grounding.

## Implementation Overview

The current system includes:

- `apps/web`: Next.js dashboard protected by Clerk.
- `services/orchestrator`: FastAPI service for events, incidents, RAG search, orchestration, metrics, and SQLite/PostgreSQL persistence.
- `services/mcp-telemetry`: MCP tool server for querying telemetry events.
- `services/mcp-retrieval`: MCP tool server for searching operational context.
- `services/mcp-incidents`: MCP tool server for creating and reading incident reports.
- `services/orchestrator/data`: JSONL seed data for detailed runbooks and telemetry events.
- `.github/workflows/deploy-aws.yml`: Production deployment workflow.
- `infra/terraform`: AWS environment scaffold for production deployment, including CloudFront, WAF, API Gateway, ECS, and PostgreSQL.

## Agent Design

The agent workflow is deterministic by design so the capstone demo remains explainable and repeatable.

| Agent | Responsibility | Current implementation |
| --- | --- | --- |
| Monitor Agent | Decide whether a telemetry event is anomalous | Checks whether `value > threshold` |
| Retriever Agent | Find relevant context | Builds a query from metric, tags, and severity |
| Diagnosis Agent | Explain likely causes | Derives hypotheses from telemetry, tags, and incident-history matches |
| Planner Agent | Propose operator actions | Converts runbook excerpts into ordered maintenance actions |
| Verifier Agent | Validate report safety and grounding | Confirms actions exist and flags missing runbook evidence |
| Reporter Agent | Produce the incident report | Adds confidence, trace, verification, latency, actions, and evidence |

This keeps responsibilities separated while allowing OpenAI-backed diagnosis, planning, and summary refinement where configured.

## Retrieval Design

Retrieval and ingestion use a backend interface:

- `LexicalRetrievalBackend` is the local default.
- `S3VectorsRetrievalBackend` is opt-in and implements `query_vectors` against Amazon S3 Vectors.
- Upload ingestion supports chunking and indexing via `POST /v1/rag/documents/upload` and `POST /v1/rag/documents/upload/async`.

This split keeps local development runnable without cloud dependencies while making the storage/retrieval boundary explicit.

## MCP Design

The MCP layer exposes operational tools to external agent hosts:

- `query_device_events(device_id, limit)`
- `lookup_device_health(device_id)`
- `search_operational_context(query, limit)`
- `create_incident(event_payload)`
- `search_incidents()`
- `read_incident(incident_id)`
- `update_incident(incident_id, status)`
- `search_maintenance_history(device_id)`

Each MCP package also keeps a plain Python helper API. This makes the services testable without requiring an MCP host during local CI.

## Evaluation

The evaluation helper replays sample telemetry events through `/v1/orchestrate/event` and reports confusion-matrix and workflow metrics:

- true positives,
- false positives,
- false negatives,
- true negatives,
- precision,
- recall,
- accuracy,
- retrieval hit rate,
- mean reciprocal rank of the expected runbook in the evidence list,
- verifier pass rate on generated incidents,
- runbook action grounding rate (actions that cite retrieved runbook IDs when runbooks are present),
- agent task success rate,
- response latency,
- time-to-diagnosis.

The current seed set includes:

- battery thermal drift anomalies on `robot-03` (and a below-threshold control on `robot-05`),
- motor current spike anomalies on `robot-07`,
- normal motor current event on `robot-11`,
- network latency high and normal events on `robot-09` and `robot-14`,
- vibration RMS anomaly and normal on `robot-12`,
- CPU thermal anomaly and normal on `robot-15`.

This is intentionally small but honest: metric names map directly to the anomaly detection behavior being demonstrated.

## Failure cases (operator)

Short triage reference for demos and deployments:

- **RAG miss:** no or weak evidence in the incident report—run [`index_documents.py`](../services/orchestrator/scripts/index_documents.py) (or S3 Vectors indexing) and confirm query terms align with corpus titles.
- **Verifier fail:** recommended actions cite runbook IDs that were not in the retrieval set—fix corpus or adjust the event so the expected runbook ranks; see verifier rules in [`agents.py`](../services/orchestrator/src/fleet_health_orchestrator/agents.py).
- **S3 Vectors IAM errors:** task role missing `s3vectors:QueryVectors` / `GetVectors`, or wrong index ARN—see [s3-vectors-operations.md](s3-vectors-operations.md).
- **ECS image pull failure:** ECR repository or digest missing for the task definition tag—re-run **`deploy-aws`** or verify `container_image_tags` in Terraform.

## Performance

End-to-end latency and per-request timings are reported by [`evaluate_pipeline.py`](../services/orchestrator/scripts/evaluate_pipeline.py) (orchestration and time-to-diagnosis fields in its JSON output). For cloud runs, use CloudWatch logs and metrics (ECS task, ALB target response time) when running the optional Terraform deployment.

## Production Readiness Work

Completed hardening:

- Web container builds the Next.js app and runs `next start`.
- Local quality gate runs web lint/build, docs link checks, orchestrator tests, and MCP tests (`npm run quality:check`).
- Next.js was patched within the current major version.
- Clerk and ESLint advisories were patched where safe.
- Deprecated `next lint` was replaced with ESLint CLI.
- README, architecture docs, and demo runbook document setup and operation.

Known remaining gaps:

- S3 Vectors **ANN quality** still depends on using the same **`FLEET_EMBEDDING_PROVIDER`** (e.g. `openai`, `http`, `sentence_transformers`) and dimension for both [`index_s3_vectors.py`](../services/orchestrator/scripts/index_s3_vectors.py) and live queries; the default `hash` provider is deterministic only (the API logs a warning when `s3vectors` + hash). See [s3-vectors-operations.md](s3-vectors-operations.md).
- Deploys are automated through `.github/workflows/deploy-aws.yml` for `main` (prod), including Terraform apply and ECR image publishing. Environment secrets and networking inputs (VPC/subnets) still need to be provided in the `prod` GitHub Environment; Terraform now provisions PostgreSQL, API Gateway, CloudFront, and WAF as part of the production path.
- Agent outputs support OpenAI Responses API calls for summary refinement, diagnosis generation, and action planning (`gpt-4o-mini` by default), while verifier constraints still enforce conservative and grounded actions.
- PostCSS remains flagged through Next with no safe npm fix available on the current line.

## Capstone Requirement Mapping

| Requirement | Status |
| --- | --- |
| Working demo | Implemented with local and Docker paths |
| Backend orchestration API | Implemented with FastAPI |
| RAG knowledge base | Implemented with seed docs and lexical retrieval |
| At least 3 agents | Implemented: monitor, retriever, diagnosis, planner, verifier, and reporter (deterministic pipeline) |
| MCP tool access | Implemented: telemetry, retrieval, incidents |
| Evaluation metrics | Implemented with confusion-matrix output |
| Architecture documentation | Implemented |
| Cloud deployment story | Implemented in repo: Docker + Terraform with GitHub Actions deploy automation for production |

## Next Steps

Recommended next implementation steps:

1. Configure **`FLEET_EMBEDDING_PROVIDER`** and dimension consistently for S3 Vectors **query** and **`index_s3_vectors.py`** ingestion so ANN matches production vectors (see [s3-vectors-operations.md](s3-vectors-operations.md)).
2. Deepen diagnosis or verifier grounding against retrieved evidence, or introduce optional LLM-backed variants.
3. Validate the full production path in AWS, including API Gateway routing, PostgreSQL connectivity, and CloudFront behavior.
4. Expand the evaluation dataset beyond the current small seed set.
5. Add custom domain, ACM, and Route 53 wiring for a polished public entrypoint.
