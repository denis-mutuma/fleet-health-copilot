# Fleet Health Copilot — presentation slides

Export-friendly deck aligned with [presentation-outline.md](presentation-outline.md). Use one heading per slide when importing into Google Slides or PowerPoint.

**Marp:** [presentation-slides.marp.md](presentation-slides.marp.md) — run `npx @marp-team/marp-cli docs/presentation-slides.marp.md -o deck.pdf` (or `.pptx` with a converter) to export slides.

---

## Slide 1 — Title

**Fleet Health Copilot: Multi-Agent Incident Intelligence for Robotics and IoT Fleets**

- Software-only fleet operations copilot
- Demo: telemetry → evidence-grounded incident report

---

## Slide 2 — Problem

- Threshold breach is not enough for triage
- Operators need similarity to past incidents
- Recommendations must be grounded in runbooks and history

---

## Slide 3 — Goals

- End-to-end working demo
- Multi-agent orchestration
- Retrieval-augmented context
- MCP tool access
- CI, Docker, and documentation

---

## Slide 4 — Architecture

- Next.js + Clerk dashboard
- FastAPI orchestrator (events, RAG, orchestration, SQLite)
- MCP servers mirror API capabilities
- Reference diagram: [architecture.md](architecture.md)

---

## Slide 5 — Agent workflow

**Monitor → Retriever → Diagnosis → Planner → Verifier → Reporter**

- Deterministic, explainable pipeline
- Verifier checks grounding before the final report

---

## Slide 6 — Retrieval

- Pluggable backends: lexical (default), optional S3 Vectors
- Embeddings: `hash`, OpenAI, HTTP, or optional `sentence_transformers`
- Evidence lists real document IDs only

---

## Slide 7 — MCP tools

- Telemetry, retrieval, incidents servers
- Same contracts as the REST API for external agent hosts

---

## Slide 8 — Demo walkthrough

1. Start orchestrator and web
2. `index_documents.py` then optional `index_s3_vectors.py`
3. Simulate battery / motor / network incidents
4. Show dashboard and incident detail (trace, verification, actions)

---

## Slide 9 — Evaluation

- `evaluate_pipeline.py`: precision, recall, retrieval hit rate, **mean reciprocal rank**, latency
- Larger `sample_events.jsonl` for stress on metrics, not only happy path

---

## Slide 10 — CI and quality

- PR workflow: web lint/build, orchestrator + MCP tests
- Terraform `fmt` / `validate` locally; **`deploy-aws`** on push for OIDC + S3 state + apply + ECR
- Remote state bootstrap documented in [terraform-bootstrap.md](terraform-bootstrap.md)

---

## Slide 11 — Limitations

- Lexical baseline vs production embeddings for S3 Vectors
- Optional LLM summary refinement behind env flags
- Terraform apply still operator-driven until AWS wiring is complete

---

## Slide 12 — Next steps

- Production embeddings + optional vector upsert automation
- Deeper grounding or LLM variants for diagnosis/verifier
- Full dev deploy after remote state + OIDC
- Deck polish and UI pass

---

## Slide 13 — Closing

Fleet Health Copilot: modular, production-oriented AI ops for robotic fleets — multi-agent workflow, RAG, MCP, and clear extension points.
