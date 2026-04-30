from __future__ import annotations

from datetime import datetime, timezone

from harness_backend.core.state import HarnessState


def node_recipe_worker(state: HarnessState) -> HarnessState:
    query = state.get("input_query", "")
    state["tool_plan"] = [
        {"tool_name": "recipe_compute", "critical": False, "payload": {"query": query}},
        {"tool_name": "stock_check", "critical": False, "payload": {"query": query}},
        {"tool_name": "prediction_regression", "critical": False, "payload": {"query": query}},
    ]
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state


def node_classification_worker(state: HarnessState) -> HarnessState:
    query = state.get("input_query", "")
    state["tool_plan"] = [
        {"tool_name": "classification_run", "critical": False, "payload": {"query": query}},
        {"tool_name": "prediction_regression", "critical": False, "payload": {"query": query}},
    ]
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state


def node_stock_worker(state: HarnessState) -> HarnessState:
    query = state.get("input_query", "")
    state["tool_plan"] = [
        {"tool_name": "stock_check", "critical": False, "payload": {"query": query}},
        {"tool_name": "prediction_regression", "critical": False, "payload": {"query": query}},
    ]
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state

