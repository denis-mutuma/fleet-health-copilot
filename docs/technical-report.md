# Technical Report

## Project Summary

Fleet Health Copilot is a software-only multi-agent operations platform for robotics and IoT fleets. It ingests telemetry events, detects anomalous device behavior, retrieves runbook and incident-history context, and generates evidence-grounded incident reports for authenticated operators.

The project is designed as a capstone artifact rather than a chatbot. It demonstrates system design across a web UI, orchestration API, persistence layer, retrieval backend, MCP tool layer, Docker runtime, CI quality gates, and repeatable evaluation.

## Problem Statement

Operators of robotic or edge-device fleets need fast, explainable incident triage. Raw telemetry alone does not tell an operator what happened, whether it resembles prior failures, or what action to take next.

Fleet Health Copilot addresses this by turning telemetry threshold crossings into structured incident reports that include:

- affected device and incident state,
- likely root-cause hypotheses,
- recommended operator actions,
- retrieved evidence from runbooks and historical incidents.

## Goals

Primary goals:

- Build a working end-to-end demo from telemetry event to incident report.
- Use multiple specialized agents with distinct responsibilities.
- Add retrieval-augmented context over runbooks and incident history.
- Expose operational capabilities through MCP tool servers.
- Keep the codebase simple, modular, and production-oriented.
- Support local development, Docker, and CI verification.

Non-goals for the current MVP:

- Physical hardware integration.
- Autonomous remediation.
- Full AWS deployment.
- LLM-generated actions without evidence grounding.

## Implementation Overview

The current system includes:

- `apps/web`: Next.js dashboard protected by Clerk.
- `services/orchestrator`: FastAPI service for events, incidents, RAG search, orchestration, metrics, and SQLite persistence.
- `services/mcp-telemetry`: MCP tool server for querying telemetry events.
- `services/mcp-retrieval`: MCP tool server for searching operational context.
- `services/mcp-incidents`: MCP tool server for creating and reading incident reports.
- `services/orchestrator/data`: JSONL seed data for demo runbooks, incident history, and telemetry events.
- `.github/workflows/test.yml`: Pull request quality gate for web, orchestrator, and MCP tests.
- `infra/terraform`: AWS environment scaffold for dev/test/prod planning.

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

This keeps responsibilities separated while leaving room for future LLM-backed diagnosis, planning, and verification agents.

## Retrieval Design

Retrieval uses a backend interface:

- `LexicalRetrievalBackend` is the local default.
- `S3VectorsRetrievalBackend` is opt-in and implements `query_vectors` against Amazon S3 Vectors, with lexical fallback as the default for laptop demos.

This split keeps the MVP runnable without cloud dependencies while making the storage/retrieval boundary explicit.

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
- agent task success rate,
- response latency,
- time-to-diagnosis.

The current seed set includes:

- battery thermal drift anomaly on `robot-03`,
- motor current spike anomaly on `robot-07`,
- normal motor current event on `robot-11`.

This is intentionally small but honest: metric names map directly to the anomaly detection behavior being demonstrated.

## Production Readiness Work

Completed hardening:

- Web container builds the Next.js app and runs `next start`.
- CI runs web lint/build, orchestrator tests, and MCP tests.
- Next.js was patched within the current major version.
- Clerk and ESLint advisories were patched where safe.
- Deprecated `next lint` was replaced with ESLint CLI.
- README, architecture docs, and demo runbook document setup and operation.

Known remaining gaps:

- S3 Vectors queries use a deterministic pseudo-embedding unless you set `FLEET_S3_VECTORS_QUERY_VECTOR_JSON` or extend the service with your embedding model, so ANN quality depends on matching production embeddings at index time.
- Terraform is present but not yet connected to an end-to-end deployment.
- The agents are deterministic and not yet LLM-generated.
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
| Cloud deployment story | Partially prepared through Docker, Terraform, and optional S3 Vectors retrieval |

## Next Steps

Recommended next implementation steps:

1. Wire a production embedding model for S3 Vectors queries so ANN results align with ingested vectors, and optionally add a vector upsert path from RAG documents.
2. Deepen diagnosis or verifier grounding against retrieved evidence, or introduce optional LLM-backed variants.
3. Add a deployed environment using Terraform and GitHub Actions.
4. Expand the evaluation dataset beyond the current small seed set.
5. Add a presentation deck using `docs/presentation-outline.md`.

See `docs/aws-deployment-plan.md` for the staged AWS rollout plan.
