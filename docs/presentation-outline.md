# Presentation Outline

## Slide 1: Title

**Fleet Health Copilot: Multi-Agent Incident Intelligence for Robotics and IoT Fleets**

Talk track:

- Introduce the project as a software-only fleet operations copilot.
- Emphasize robotics/IoT realism without hardware dependency.
- State the core demo: telemetry event to evidence-grounded incident report.

## Slide 2: Problem

Operators receive telemetry, logs, and alerts, but still need context.

Talk track:

- A threshold breach is not enough by itself.
- Operators need to know whether the event resembles prior incidents.
- Recommendations should be grounded in runbooks and history.

## Slide 3: Project Goals

- End-to-end working demo.
- Multi-agent orchestration.
- Retrieval-augmented incident context.
- MCP tool access.
- Production-style CI, Docker, and documentation.

Talk track:

- This is a systems capstone, not a standalone chatbot.
- Each layer has a clear engineering responsibility.

## Slide 4: System Architecture

Use the diagram from `docs/architecture.md`.

Talk track:

- Next.js provides the authenticated operator dashboard.
- FastAPI orchestrates ingestion, retrieval, reporting, and persistence.
- MCP servers expose the same operational actions as tools.
- SQLite and JSONL seed data keep the demo simple and repeatable.

## Slide 5: Agent Workflow

Monitor -> Retriever -> Reporter

Talk track:

- Monitor agent gates the workflow by anomaly threshold.
- Retriever agent searches runbooks and incident history.
- Reporter agent composes structured output with evidence.
- Deterministic agents make the MVP repeatable and explainable.

## Slide 6: Retrieval and Evidence

Talk track:

- Retrieval uses a backend interface.
- Local default is lexical ranking over seed runbooks and incident history.
- AWS S3 Vectors is supported as an opt-in retrieval backend behind the same interface as lexical search.
- Reports avoid synthetic fallback evidence and only show retrieved IDs.

## Slide 7: MCP Tool Layer

Available tools:

- `query_device_events(device_id, limit)`
- `search_operational_context(query, limit)`
- `create_incident(event_payload)`
- `search_incidents()`
- `read_incident(incident_id)`

Talk track:

- MCP decouples operational capabilities from the web UI.
- External agent hosts could call these tools directly.
- Each tool delegates to the orchestrator API.

## Slide 8: Demo Walkthrough

Demo sequence:

1. Start orchestrator and web app.
2. Index runbooks and historical incidents.
3. Trigger a simulated battery thermal incident.
4. Open the incident detail page.
5. Show summary, actions, and evidence.
6. Run evaluation metrics.

Talk track:

- The demo path is documented in `docs/demo-runbook.md`.
- Emphasize repeatability and clear expected outputs.

## Slide 9: Evaluation

Metrics:

- true positives,
- false positives,
- false negatives,
- true negatives,
- precision,
- recall,
- accuracy.

Talk track:

- The evaluation helper uses real confusion-matrix terms.
- The seed set is intentionally small but honest.
- This creates a basis for expanding the dataset later.

## Slide 10: Engineering Quality

- Web lint and production build.
- Orchestrator pytest suite.
- MCP package tests.
- Pull request CI.
- Docker Compose production-style web container.
- Documentation and demo runbook.

Talk track:

- The project has quality gates around the main behavioral surfaces.
- Docker runs `next start`, not dev mode.
- The project is ready for incremental cloud deployment work.

## Slide 11: Current Limitations

- Lexical retrieval is the current local baseline.
- S3 Vectors backend calls `query_vectors`; wire real embeddings for meaningful ANN in production.
- Reporter is deterministic, not LLM-generated.
- Dataset is small.
- Terraform is not yet wired to a full deployed environment.

Talk track:

- These are deliberate MVP boundaries.
- The architecture leaves clear extension points.

## Slide 12: Next Steps

1. Wire a production embedding model for S3 Vectors query vectors (and optional vector indexing).
2. Deepen diagnosis and verifier evidence grounding, or add LLM-backed variants.
3. Expand evaluation data and retrieval relevance metrics.
4. Deploy through Terraform and GitHub Actions.
5. Add a final polished UI pass.

Talk track:

- The next work deepens the capstone without changing the core architecture.
- AWS and richer agents are now incremental extensions rather than rewrites.

## Slide 13: Closing

Fleet Health Copilot demonstrates a realistic, modular, production-oriented AI system for robotic fleet operations.

Talk track:

- It combines multi-agent workflow, RAG, MCP tools, web UI, backend orchestration, Docker, and CI.
- The implementation is simple enough to explain and deep enough to extend.
