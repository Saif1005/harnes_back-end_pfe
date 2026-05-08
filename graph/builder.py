from __future__ import annotations

from typing import Any

from harness_backend.core.state import HarnessState
from harness_backend.graph.checkpoint.store import CheckpointStore
from harness_backend.graph.nodes.guardrails import node_guardrails
from harness_backend.graph.nodes.hitl_interrupt import node_hitl_interrupt
from harness_backend.graph.nodes.react_orchestrator import node_react_orchestrator
from harness_backend.graph.nodes.supervisor import node_supervisor
from harness_backend.graph.nodes.synthesizer import node_synthesizer
from harness_backend.graph.nodes.tool_executor import node_tool_executor
from harness_backend.graph.nodes.workers import (
    node_classification_worker,
    node_recipe_worker,
    node_stock_worker,
)

try:
    from langgraph.graph import END, START, StateGraph  # type: ignore
except Exception:  # noqa: BLE001
    END = "__end__"
    START = "__start__"
    StateGraph = None


class HarnessGraphRunner:
    """
    Lightweight deterministic runner that mirrors LangGraph node flow.
    """

    def __init__(self, checkpointer: CheckpointStore | None = None) -> None:
        self.checkpointer = checkpointer

    def _save(self, state: HarnessState, node_name: str) -> None:
        if self.checkpointer is not None:
            self.checkpointer.save(state, node_name=node_name)

    def run(self, state: HarnessState) -> HarnessState:
        state = node_supervisor(state)
        self._save(state, "supervisor")

        route = state.get("route")
        if route == "react_orchestrator":
            state = node_react_orchestrator(state)
            self._save(state, "react_orchestrator")
        elif route == "recipe_worker":
            state = node_recipe_worker(state)
            self._save(state, "recipe_worker")
        elif route == "classification_worker":
            state = node_classification_worker(state)
            self._save(state, "classification_worker")
        elif route == "stock_worker":
            state = node_stock_worker(state)
            self._save(state, "stock_worker")

        state = node_guardrails(state)
        self._save(state, "guardrails")

        state = node_hitl_interrupt(state)
        self._save(state, "hitl_interrupt")

        if not state.get("hitl_required", False):
            state = node_tool_executor(state)
            self._save(state, "tool_executor")

        state = node_synthesizer(state)
        self._save(state, "synthesizer")
        return state


def build_harness_graph(checkpointer: CheckpointStore | None = None) -> HarnessGraphRunner:
    if StateGraph is not None:
        return LangGraphRunner(checkpointer=checkpointer)
    return HarnessGraphRunner(checkpointer=checkpointer)


class LangGraphRunner(HarnessGraphRunner):
    """
    Native LangGraph compiled runtime with fallback-compatible API.
    """

    def __init__(self, checkpointer: CheckpointStore | None = None) -> None:
        super().__init__(checkpointer=checkpointer)
        graph = StateGraph(HarnessState)
        graph.add_node("supervisor", node_supervisor)
        graph.add_node("react_orchestrator", node_react_orchestrator)
        graph.add_node("classification_worker", node_classification_worker)
        graph.add_node("recipe_worker", node_recipe_worker)
        graph.add_node("stock_worker", node_stock_worker)
        graph.add_node("guardrails", node_guardrails)
        graph.add_node("hitl_interrupt", node_hitl_interrupt)
        graph.add_node("tool_executor", node_tool_executor)
        graph.add_node("synthesizer", node_synthesizer)

        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            self._route_selector,
            {
                "react_orchestrator": "react_orchestrator",
                "classification_worker": "classification_worker",
                "recipe_worker": "recipe_worker",
                "stock_worker": "stock_worker",
                "synthesizer": "synthesizer",
            },
        )
        graph.add_edge("react_orchestrator", "guardrails")
        graph.add_edge("classification_worker", "guardrails")
        graph.add_edge("recipe_worker", "guardrails")
        graph.add_edge("stock_worker", "guardrails")
        graph.add_edge("guardrails", "hitl_interrupt")
        graph.add_conditional_edges(
            "hitl_interrupt",
            self._hitl_selector,
            {"tool_executor": "tool_executor", "synthesizer": "synthesizer"},
        )
        graph.add_edge("tool_executor", "synthesizer")
        graph.add_edge("synthesizer", END)

        self.app = graph.compile()

    @staticmethod
    def _route_selector(state: HarnessState) -> str:
        route = str(state.get("route", "synthesizer"))
        if route not in {
            "react_orchestrator",
            "classification_worker",
            "recipe_worker",
            "stock_worker",
            "synthesizer",
        }:
            return "synthesizer"
        return route

    @staticmethod
    def _hitl_selector(state: HarnessState) -> str:
        return "synthesizer" if state.get("hitl_required", False) else "tool_executor"

    def run(self, state: HarnessState) -> HarnessState:
        out = self.app.invoke(state)
        if self.checkpointer is not None:
            self.checkpointer.save(out, node_name="langgraph_final")
        return out

