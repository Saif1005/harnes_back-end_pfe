from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError

from harness_backend.core.state import HarnessState
from harness_backend.tools.contracts import ToolCall


class ToolCallPlan(BaseModel):
    tool_name: str = Field(..., min_length=1)
    critical: bool = False
    payload: dict = Field(default_factory=dict)


def node_guardrails(state: HarnessState) -> HarnessState:
    """
    Validate tool plans before execution.
    """
    try:
        plans = state.get("tool_plan", [])
        validated = []
        for plan in plans:
            coarse = ToolCallPlan(**plan).model_dump()
            strict = ToolCall(**coarse).model_dump()
            validated.append(strict)
        state["tool_plan"] = validated
    except ValidationError as exc:
        state.setdefault("errors", []).append(f"guardrails_validation_error: {exc}")
        state["route"] = "error"
    finally:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state

