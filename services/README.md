# Services Overview

This folder contains all backend services used by Fleet Health Copilot.

## Structure

- `orchestrator/`: FastAPI orchestration API for events, incidents, retrieval, RAG ingestion, and agent pipeline execution.
- `mcp-telemetry/`: MCP tool server for telemetry reads and quick device health checks.
- `mcp-retrieval/`: MCP tool server for RAG context search.
- `mcp-incidents/`: MCP tool server for incident create/read/update workflows.

## Current RAG Baseline

- Canonical runbook seed corpus: `orchestrator/data/runbooks_detailed.jsonl`
- Sample telemetry events: `orchestrator/data/sample_events.jsonl`
- Upload ingestion endpoints are implemented in the orchestrator and support chunking plus optional S3 Vectors indexing.

## Design Notes

- Keep service boundaries thin and explicit.
- Keep MCP services as small API adapters over orchestrator routes.
- Keep environment-driven configuration in `orchestrator/src/fleet_health_orchestrator/config.py`.
