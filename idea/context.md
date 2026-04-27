# Context for an LLM

You are helping a senior software engineer and experienced practitioner in embedded systems, edge AI, and robotics design a capstone project.

## User profile
- Seniority: 10+ years of experience.
- Background: embedded systems, edge AI, robotics.
- Strengths/interests: AI agents, RAG, MCP, cloud AI, IoT, robotics, production-grade systems.
- Preference: software-only project preferred; no hardware simulation required for the main capstone.
- Goal: build a capstone that demonstrates mastery of the concepts learned from courses on:
  - deploying LLMs and agents at scale,
  - agentic workflows with MCP,
  - LLM engineering with RAG and QLoRA,
  - generative AI leadership and system design.

## High-level project direction
The best capstone direction is a **Multi-Agent Edge Robotics Intelligence Platform (Fleet Health Copilot)**.

### Core idea
Build a system that ingests telemetry, logs, and operational data from simulated or software-represented robots, IoT devices, or edge nodes. The system should use multiple specialized AI agents to:
- detect anomalies,
- retrieve relevant context,
- diagnose issues,
- propose actions,
- validate the plan,
- generate a final incident or maintenance report.

## Why this is a strong capstone
This project is strong because it combines:
- multi-agent orchestration,
- retrieval-augmented generation,
- MCP-based tool access,
- cloud-based model hosting/orchestration,
- edge-style streaming data,
- robotics and embedded-systems realism,
- production-style software architecture.

It is better than a simple chatbot because it shows system design, not just prompt usage.

Recommend **Fleet Health Copilot** as the strongest capstone because it:
- has a clear real-world story,
- naturally supports RAG and multi-agent orchestration,
- fits the user’s embedded/robotics background,
- can be built without physical hardware,
- allows for strong demo and evaluation metrics.

## Suggested architecture
The system can be described as follows:

### Data layer
Use software-generated or replayed data instead of hardware.
Possible inputs:
- telemetry streams,
- event logs,
- sensor CSV/JSON,
- fault injection records,
- maintenance records,
- documentation and runbooks.

### Ingestion layer
A service that accepts streaming events from:
- device simulators,
- mock robot services,
- log replay scripts,
- batch uploads.

### Retrieval layer
Use RAG over:
- manuals,
- runbooks,
- incident history,
- maintenance notes,
- model docs,
- sensor summaries.

### Agent layer
Use specialized agents, for example:
- Monitor Agent,
- Retriever Agent,
- Diagnosis Agent,
- Planner Agent,
- Verifier Agent,
- Reporter Agent.

### MCP layer
Expose tools through MCP servers for:
- telemetry queries,
- log search,
- vector search,
- device status lookup,
- maintenance history,
- incident creation,
- report generation.

### Cloud layer
Use the cloud for:
- model hosting,
- orchestration,
- storage,
- evaluation,
- batch processing,
- fine-tuning or experimentation.

## Strong project story
The project should be presented as:

> “A multi-agent AI system for monitoring robotic and IoT fleets, retrieving operational context, reasoning over incidents, and producing safe maintenance recommendations using RAG, MCP, and cloud-hosted AI services.”

## Capstone-level deliverables
A strong final project should include:
- a working demo,
- backend API or orchestration service,
- MCP servers,
- a RAG knowledge base,
- at least 3 agents with distinct roles,
- cloud deployment,
- evaluation metrics,
- architecture documentation,
- diagrams,
- a short technical report or presentation deck.

## Suggested evaluation metrics
Useful metrics to include:
- anomaly detection precision/recall,
- retrieval relevance,
- agent task success rate,
- response latency,
- time-to-diagnosis,
- human readability of final reports.

## Tone and design goals
The capstone should feel:
- realistic,
- production-oriented,
- modular,
- explainable,
- technically deep,
- impressive to employers or reviewers.

## What not to make
Avoid making it:
- a simple chatbot,
- a toy demo,
- a hardware-dependent project,
- a project without evaluation,
- a system with only one agent and no retrieval.

## Final recommendation
If the user wants the best possible capstone, recommend:
**Fleet Health Copilot with multi-agent orchestration, RAG, MCP tools, and cloud deployment.**

## other things
- i want to use aws as the cloud provider, clerk for authentication, terraform, github actions and other cloud services
- i want to keep the project professional. the code should be simple, clear and consice
- use uv environment, nextjs, docker and other technologies
- use aws s3vectors
- i want the ui to have the theme of openai website