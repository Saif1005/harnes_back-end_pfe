from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ToolName = Literal["classification_run", "recipe_compute", "stock_check", "prediction_regression"]


class ToolPayload(BaseModel):
    query: str = Field(default="", description="Operator query")
    article: str = Field(default="", description="Product family/article")
    tonnage: float = Field(default=0.0, ge=0.0)
    context: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    tool_name: ToolName
    critical: bool = False
    payload: ToolPayload = Field(default_factory=ToolPayload)


class ToolResult(BaseModel):
    tool_name: str
    ok: bool
    model: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class McpContext(BaseModel):
    run_id: str = ""
    session_id: str = ""
    user_id: str = ""
    trace_id: str = ""
    route: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class McpEnvelope(BaseModel):
    source_agent: str
    target_tool: ToolName
    payload: ToolPayload
    context: McpContext = Field(default_factory=McpContext)

