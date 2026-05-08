from __future__ import annotations

"""Static tool sequences used by deterministic workers and ReAct heuristic fallback."""

from typing import Any


def static_tool_plan_for_route(route: str, query: str) -> list[dict[str, Any]]:
    q = query or ""
    if route == "recipe_worker":
        return [
            {"tool_name": "recipe_compute", "critical": False, "payload": {"query": q}},
            {"tool_name": "stock_check", "critical": False, "payload": {"query": q}},
            {"tool_name": "prediction_regression", "critical": False, "payload": {"query": q}},
        ]
    if route == "classification_worker":
        return [
            {"tool_name": "classification_run", "critical": False, "payload": {"query": q}},
            {"tool_name": "prediction_regression", "critical": False, "payload": {"query": q}},
        ]
    if route == "stock_worker":
        return [
            {"tool_name": "stock_check", "critical": False, "payload": {"query": q}},
            {"tool_name": "prediction_regression", "critical": False, "payload": {"query": q}},
        ]
    return []
