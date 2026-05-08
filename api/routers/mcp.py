from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harness_backend.tools.contracts import McpEnvelope, ToolResult
from harness_backend.tools.registry import dispatch_tool

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("/tool-call", response_model=ToolResult)
def mcp_tool_call(envelope: McpEnvelope) -> ToolResult:
    try:
        return dispatch_tool(envelope)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"mcp_tool_call_failed: {exc}") from exc

