from __future__ import annotations

from fastapi import APIRouter

from harness_backend.config.settings import SETTINGS
from harness_backend.graph.nodes.catalog import LANGGRAPH_NODE_CATALOG
from harness_backend.services.mcp_sdk import load_mcp_sdk

try:
    import langchain  # type: ignore
except Exception:  # noqa: BLE001
    langchain = None

try:
    import langgraph  # type: ignore
except Exception:  # noqa: BLE001
    langgraph = None

router = APIRouter(prefix="/system/protocols", tags=["system"])


@router.get("")
def protocols() -> dict:
    mcp_module, mcp_version = load_mcp_sdk()
    return {
        "api_style": "REST",
        "runtime_imports": {
            "mcp_sdk_loaded": bool(mcp_module is not None),
            "mcp_sdk_version": mcp_version,
            "langchain_loaded": bool(langchain is not None),
            "langgraph_loaded": bool(langgraph is not None),
            "mcp_transport": SETTINGS.mcp_transport,
            "mcp_server_name": SETTINGS.mcp_server_name,
        },
        "langgraph_nodes": LANGGRAPH_NODE_CATALOG,
        "reasoning": {
            "chain_of_thought": "react_trace + prompt compressé (fenêtre de contexte)",
            "markov_chain": "phases industrielles classification → stock → recette → prédiction (markov_chain.py)",
            "mcmc": "Metropolis-Hastings discret sur candidats (mcmc_policy.py)",
            "reward_model": "score_action_intent + score_incumbent_state (reward_model.py)",
            "backtracking": "rollback si chute de récompense (backtrack.py + snapshots)",
            "memory_mcp": "/mcp/reasoning-memory/append|read (SQLite reasoning_memory)",
            "context_max_chars": SETTINGS.reasoning_context_max_chars,
            "mcmc_enabled": SETTINGS.reasoning_mcmc_enabled,
            "backtrack_enabled": SETTINGS.reasoning_backtrack_enabled,
        },
        "protocols": [
            {
                "name": "REST API",
                "transport": "HTTP/JSON",
                "entrypoints": [
                    "/invoke",
                    "/resume",
                    "/approvals/pending",
                    "/admin/training/classification",
                    "/admin/training/prediction",
                    "/tools/classification",
                    "/tools/recipe",
                    "/tools/stock",
                    "/tools/prediction",
                    "/admin/monitoring/metrics",
                    "/admin/monitoring/tool-runs",
                    "/mcp/reasoning-memory/append",
                    "/mcp/reasoning-memory/read",
                ],
            },
            {
                "name": "MCP Bridge/Server",
                "transport": "HTTP JSON envelope + in-process fallback",
                "entrypoints": ["/mcp/tool-call"],
                "components": [
                    "services/mcp_sdk.py",
                    "tools/contracts.py",
                    "tools/adapters/mcp_adapter.py",
                    "tools/registry.py",
                    "api/routers/mcp.py",
                ],
            },
        ],
        "models": {
            "orchestrator_react_supervisor": SETTINGS.orchestrator_model,
            "recipe_llm_qwen_instruct": SETTINGS.recipe_llm_model,
            "recipe_model_tag": SETTINGS.recipe_model,
            "recipe_use_llm": SETTINGS.recipe_use_llm,
            "classification_xlm_roberta_large": SETTINGS.classification_model_name,
            "classification_primary": SETTINGS.classifier_primary_model,
            "classification_secondary": SETTINGS.classifier_secondary_model,
            "prediction_stock": SETTINGS.prediction_model_name,
        },
        "orchestration": {
            "react_enabled": SETTINGS.orchestrator_react_enabled,
            "react_max_steps": SETTINGS.react_max_steps,
            "central_agent_node": "react_orchestrator",
        },
    }

