# Migration Map: Legacy Multi-Agent -> Harness Backend

This file maps old architecture components to the new `harness_backend` modules.

## 1) Entry/API Layer

- Legacy: `cerveau_orchestrateur/main.py`, `src/api/routes.py`
- New: `harness_backend/main.py`, `harness_backend/api/routers/*`

## 2) LangGraph Orchestration Core

- Legacy: `cerveau_orchestrateur/src/agent/graph.py`
- New:
  - `harness_backend/graph/builder.py`
  - `harness_backend/graph/nodes/supervisor.py`
  - `harness_backend/core/state.py`

## 3) Workers

- Legacy Classification logic: `src/tools/classification_api.py`
- New worker + tool:
  - `harness_backend/graph/nodes/workers.py`
  - `harness_backend/tools/implementations/classification_tools.py`

- Legacy Recipe logic: `src/tools/recette_api.py` + recipe microservice
- New worker + tool:
  - `harness_backend/graph/nodes/workers.py`
  - `harness_backend/tools/implementations/recipe_tools.py`

- Legacy Stock/Warehouse checks inside graph/services
- New worker + tool:
  - `harness_backend/graph/nodes/workers.py`
  - `harness_backend/tools/implementations/stock_tools.py`

## 4) Guardrails + Contracts

- Legacy: implicit checks across graph/tool code
- New:
  - `harness_backend/graph/nodes/guardrails.py`
  - `harness_backend/tools/contracts.py`

## 5) HITL (Interrupt / Resume)

- Legacy: confirmation token flow in graph
- New:
  - `harness_backend/graph/nodes/hitl_interrupt.py`
  - `harness_backend/api/routers/resume.py`
  - `harness_backend/api/routers/approvals.py`

## 6) Tool Execution + MCP-style Bridge

- Legacy: direct calls from graph/tool modules
- New:
  - `harness_backend/graph/nodes/tool_executor.py`
  - `harness_backend/tools/adapters/mcp_adapter.py`
  - `harness_backend/tools/registry.py`

## 7) Persistent Checkpointing

- Legacy: LangGraph memory/checkpoint tied to old runtime
- New:
  - `harness_backend/graph/checkpoint/store.py`
  - `harness_backend/graph/checkpoint/sqlite_store.py`

## Legacy Compatibility Adapters

- `harness_backend/tools/adapters/legacy_tools_api.py` keeps runtime compatibility with:
  - `url_instance_a` (PDR/MP),
  - `url_classification_mp_chimie`,
  - `url_recette_agent`.

If remote services are unavailable, local fallback logic is used to keep the system operational.

## Integrated Legacy Logic (ported)

- `harness_backend/services/legacy_compat.py` ports high-value logic from legacy graph:
  - robust route fallback heuristic,
  - recipe item parsing from free text,
  - ingredient canonical naming,
  - stock matching with aliases/fuzzy logic,
  - stock alerts and production capacity estimation.

- Wired in:
  - `harness_backend/graph/routes.py` (routing),
  - `harness_backend/tools/implementations/recipe_tools.py` (recipe parsing),
  - `harness_backend/tools/implementations/stock_tools.py` (inventory map),
  - `harness_backend/graph/nodes/synthesizer.py` (table + alerts + capacity text).

