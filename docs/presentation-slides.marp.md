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

- Confusion matrix: true/false positives and negatives; precision, recall, accuracy
- Retrieval: hit rate and mean reciprocal rank for expected runbook IDs
- Workflow: verifier pass rate, runbook action grounding rate, latency

`evaluate_pipeline.py` replays [sample_events.jsonl](../services/orchestrator/data/sample_events.jsonl) (battery, motor, network, vibration, CPU thermal, and true negatives).

---

# CI and quality

- PR workflow: web lint/build, Python tests, MCP packages, `scripts/validate_terraform.sh`
- **deploy-aws**: push **`develop` / `staging` / `main`** → OIDC + S3 state + **`terraform apply`** + ECR + second apply (commit SHA)
- Remote state: [terraform-bootstrap.md](terraform-bootstrap.md) and [backend.tf.example](../infra/terraform/backend.tf.example)

---

# Limitations

- Local default is lexical RAG; S3 Vectors needs matching embeddings and IAM for meaningful ANN
- Agents are mostly deterministic; optional OpenAI summary refine only
- Terraform **`apply`** and remote state are operator-driven until your account is wired

---

# Next steps

- Same **`FLEET_EMBEDDING_PROVIDER`** and dimension for **`index_s3_vectors.py`** and orchestrator query
- OIDC role + **`AWS_ROLE_ARN`** for CI plan; bootstrap bucket for shared state
- Optional LLM-backed diagnosis/planning; larger eval seed set

---

# Closing

Fleet Health Copilot: multi-agent workflow, RAG, MCP tools, authenticated web UI, Docker, CI, and a clear path to AWS—all explainable without hardware.
