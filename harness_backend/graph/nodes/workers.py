from __future__ import annotations

from datetime import datetime, timezone

from harness_backend.core.state import HarnessState
from harness_backend.graph.nodes.worker_plans import static_tool_plan_for_route


def node_recipe_worker(state: HarnessState) -> HarnessState:
    query = str(state.get("input_query", "") or "")
    state["tool_plan"] = static_tool_plan_for_route("recipe_worker", query)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state


def node_classification_worker(state: HarnessState) -> HarnessState:
    query = str(state.get("input_query", "") or "")
    state["tool_plan"] = static_tool_plan_for_route("classification_worker", query)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state


def node_stock_worker(state: HarnessState) -> HarnessState:
    query = str(state.get("input_query", "") or "")
    state["tool_plan"] = static_tool_plan_for_route("stock_worker", query)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state

