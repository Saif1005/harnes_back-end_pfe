from __future__ import annotations

from harness_backend.tools.contracts import McpEnvelope, ToolResult
from harness_backend.tools.implementations.classification_tools import run_material_classification
from harness_backend.tools.implementations.prediction_tools import run_prediction_regression
from harness_backend.tools.implementations.recipe_tools import run_recipe_compute
from harness_backend.tools.implementations.stock_tools import run_stock_check
from harness_backend.services.persistence import persist_tool_run


def dispatch_tool(envelope: McpEnvelope) -> ToolResult:
    tool_name = envelope.target_tool
    query = envelope.payload.query
    context = envelope.context.model_dump()
    if tool_name == "classification_run":
        data = run_material_classification(query)
        result = ToolResult(tool_name=tool_name, ok=True, model=data.get("model_used", ""), data=data, context=context)
        _persist_tool(envelope, result)
        return result
    if tool_name == "recipe_compute":
        data = run_recipe_compute(query)
        result = ToolResult(tool_name=tool_name, ok=True, model=data.get("model_used", ""), data=data, context=context)
        _persist_tool(envelope, result)
        return result
    if tool_name == "stock_check":
        data = run_stock_check(query)
        result = ToolResult(tool_name=tool_name, ok=True, model="dataset-aggregator", data=data, context=context)
        _persist_tool(envelope, result)
        return result
    if tool_name == "prediction_regression":
        data = run_prediction_regression(query)
        result = ToolResult(tool_name=tool_name, ok=True, model=data.get("model_used", ""), data=data, context=context)
        _persist_tool(envelope, result)
        return result
    result = ToolResult(tool_name=tool_name, ok=False, error=f"unknown_tool: {tool_name}", context=context)
    _persist_tool(envelope, result)
    return result


def _persist_tool(envelope: McpEnvelope, result: ToolResult) -> None:
    ctx = envelope.context
    persist_tool_run(
        run_id=str(ctx.run_id),
        session_id=str(ctx.session_id),
        user_id=str(ctx.user_id),
        route=str(ctx.route),
        tool_name=str(result.tool_name),
        ok=bool(result.ok),
        model=str(result.model),
        payload=envelope.payload.model_dump(),
        result=result.model_dump(),
    )

