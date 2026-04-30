from __future__ import annotations

from harness_backend.tools.contracts import McpEnvelope, ToolResult
from harness_backend.tools.implementations.classification_tools import run_material_classification
from harness_backend.tools.implementations.prediction_tools import run_prediction_regression
from harness_backend.tools.implementations.recipe_tools import run_recipe_compute
from harness_backend.tools.implementations.stock_tools import run_stock_check


def dispatch_tool(envelope: McpEnvelope) -> ToolResult:
    tool_name = envelope.target_tool
    query = envelope.payload.query
    context = envelope.context.model_dump()
    if tool_name == "classification_run":
        data = run_material_classification(query)
        return ToolResult(tool_name=tool_name, ok=True, model=data.get("model_used", ""), data=data, context=context)
    if tool_name == "recipe_compute":
        data = run_recipe_compute(query)
        return ToolResult(tool_name=tool_name, ok=True, model=data.get("model_used", ""), data=data, context=context)
    if tool_name == "stock_check":
        data = run_stock_check(query)
        return ToolResult(tool_name=tool_name, ok=True, model="dataset-aggregator", data=data, context=context)
    if tool_name == "prediction_regression":
        data = run_prediction_regression(query)
        return ToolResult(tool_name=tool_name, ok=True, model=data.get("model_used", ""), data=data, context=context)
    return ToolResult(tool_name=tool_name, ok=False, error=f"unknown_tool: {tool_name}", context=context)

