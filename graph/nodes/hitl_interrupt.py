from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from harness_backend.core.state import HarnessState


def node_hitl_interrupt(state: HarnessState) -> HarnessState:
    plans = state.get("tool_plan", [])
    has_critical = any(bool(plan.get("critical")) for plan in plans)
    state["pending_critical_action"] = has_critical
    state["hitl_required"] = has_critical
    if has_critical:
        state["approval_id"] = str(uuid4())
        state["interrupt_reason"] = "critical_tool_requires_approval"
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state

