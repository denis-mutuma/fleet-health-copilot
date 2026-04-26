---
marp: true
theme: default
paginate: true
header: "Fleet Health Copilot"
---

# Fleet Health Copilot

**Multi-Agent Incident Intelligence for Robotics and IoT Fleets**

- Software-only fleet operations copilot
- Demo: telemetry to evidence-grounded incident report

---

# Problem

- A threshold breach alone is weak signal for triage
- Operators need similarity to past incidents
- Actions must be grounded in runbooks and history

---

# Goals

- End-to-end working demo
- Multi-agent orchestration
- Retrieval-augmented context
- MCP tool access
- CI, Docker, and documentation

---

# Architecture

- Next.js + Clerk dashboard
- FastAPI orchestrator (events, RAG, orchestration, SQLite)
- MCP servers mirror REST API contracts

---

# Agent workflow

**Monitor → Retriever → Diagnosis → Planner → Verifier → Reporter**

- Deterministic, explainable pipeline
- Verifier checks grounding before the final report

---

# Retrieval

- Lexical default; optional S3 Vectors
- Embeddings: `hash`, OpenAI, HTTP, optional `sentence_transformers`
- Evidence lists real document IDs

---

# MCP tools

- Telemetry, retrieval, incidents servers
- Same shapes as orchestrator endpoints for external agent hosts

---

# Demo walkthrough

1. Start orchestrator and web
2. `index_documents.py` then optional `index_s3_vectors.py`
3. Simulate battery / motor / network incidents
4. Dashboard and incident detail (trace, verification, actions)

---

# Evaluation

- `evaluate_pipeline.py`: precision, recall, retrieval MRR, verifier pass rate, latency
- Expanded `sample_events.jsonl` for richer metric stress

---

# CI and quality

- PR workflow: web lint/build, Python tests
- Manual `deploy-dev`: Terraform fmt/validate; optional AWS plan when `AWS_ROLE_ARN` is set
- Remote state: `terraform-bootstrap.md` + `backend.tf.example`

---

# Limitations

- Production embeddings and IAM work for meaningful S3 ANN
- Optional LLM copy refine behind env flags
- Full `terraform apply` still operator-driven until account wiring

---

# Next steps

- Same embedding provider for index and query in AWS
- Remote state + OIDC + dev apply
- Deck polish and optional UI refinements

---

# Closing

Modular, production-oriented AI ops for robotic fleets: multi-agent workflow, RAG, MCP, and clear extension points.
