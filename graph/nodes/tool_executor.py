from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from harness_backend.core.state import HarnessState
from harness_backend.tools.adapters.mcp_adapter import MCPBridge
from harness_backend.tools.contracts import McpContext, McpEnvelope, ToolCall, ToolPayload
from harness_backend.tools.registry import dispatch_tool


def node_tool_executor(state: HarnessState) -> HarnessState:
    """Exécute le ``tool_plan`` et concatène après les résultats déjà collectés (ex. ReAct inline)."""
    prior = list(state.get("tool_results") or [])
    results: list[dict] = []
    bridge = MCPBridge(tool_dispatcher=dispatch_tool)
    for plan in state.get("tool_plan", []):
        call = ToolCall(**plan)
        context = McpContext(
            run_id=str(state.get("run_id", "")),
            session_id=str(state.get("session_id", "")),
            user_id=str(state.get("user_id", "")),
            trace_id=f"trace-{uuid4()}",
            route=str(state.get("route", "")),
            metadata=dict(state.get("metadata") or {}),
        )
        envelope = McpEnvelope(
            source_agent=state.get("route", "unknown"),
            target_tool=call.tool_name,
            payload=ToolPayload(**call.payload.model_dump()),
            context=context,
        )
        result = bridge.send(envelope)
        results.append(result.model_dump())
    state["tool_results"] = prior + results
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state

