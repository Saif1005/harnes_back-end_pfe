# Harness Backend (Modular Scaffold)

This package introduces a production-oriented orchestration harness without breaking
the current runtime services.

## Goals

- Clear separation of concerns (API, graph, agents, tools, schemas).
- Deterministic supervisor node (routing only).
- Typed shared state for LangGraph execution.
- Persistent-checkpoint-ready architecture.
- HITL-ready APIs (`invoke`, `resume`, `approvals`).

## Current Scope

This is a scaffold and core bootstrap for:

- Input Gate (`/invoke` + request validation),
- Supervisor routing node,
- LangGraph builder skeleton,
- Standardized typed state model.

Next implementation steps:

1. plug PostgreSQL checkpointer for production,
2. replace lexical classification with CamemBERT/XLM-R inference endpoints,
3. replace recipe parser with Qwen-7B tool-calling pipeline,
4. connect Mistral-7B orchestration prompts in supervisor/agents.

## Implemented in this revision

- SQLite persistent checkpoints for each node transition.
- Worker nodes for classification/recipe/stock and prediction.
- Guardrails with strict Pydantic tool contracts.
- HITL interrupt before critical actions.
- MCP-like envelope bridge between agents and tool executor.
- Regression prediction tool (`Ridge`, with safe fallback if unavailable).
- Data integration from:
  - `dataset_classification_compatible.csv`
  - `correlation_qualite_ingredients_recette.csv`
  - `formuleexacte.csv`
  - `formule_recette.md` (configured path)

## Training Endpoints

- `POST /admin/training/classification`
  - Trains classification artifacts from `dataset_classification_compatible.csv`.
  - Uses `TFIDF + LogisticRegression` when `scikit-learn` is available.
  - Falls back to dataset statistics artifact when sklearn is unavailable.

## Communication Protocols

- REST API for external clients/operator frontend.
- MCP-style internal envelopes for agent-to-tool communication.
- Legacy bridge adapters for existing microservices (PDR/MP, MP/CHIMIE, recette).

## Docker

- Build image:
  - `docker build -f harness_backend/Dockerfile -t harness-backend .`
- Run compose:
  - `docker compose -f docker-compose.harness.yml up -d --build`

## Real MCP Server

- MCP endpoint is available in backend API:
  - `POST /mcp/tool-call`
- Standalone MCP app entrypoint:
  - `harness_backend/mcp_server_main.py`
- To enable external MCP usage from tool executor:
  - set `mcp_enabled=true`
  - set `mcp_server_url=http://<host>:<port>/mcp/tool-call`
- MCP SDK import visibility:
  - `harness_backend/services/mcp_sdk.py` attempts `import mcp`
  - runtime import status is exposed by `GET /system/protocols`

## LangGraph Nodes

Defined graph nodes are listed in:

- `harness_backend/graph/nodes/catalog.py`

Runtime graph import/load status is exposed by:

- `GET /system/protocols`

## Training Docker (classification + prediction)

- Classification training image:
  - `harness_backend/docker/training/Dockerfile.classification-train`
- Prediction training image:
  - `harness_backend/docker/training/Dockerfile.prediction-train`
- Compose:
  - `harness_backend/docker/training/docker-compose.training.yml`
