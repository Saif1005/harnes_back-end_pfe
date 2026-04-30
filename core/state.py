from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict
from uuid import uuid4

RouteName = Literal["stock_worker", "recipe_worker", "classification_worker", "synthesizer", "error"]


class HarnessState(TypedDict, total=False):
    run_id: str
    session_id: str
    user_id: str
    input_query: str
    normalized_query: str
    route: RouteName
    pending_critical_action: bool
    hitl_required: bool
    approval_id: str
    interrupt_reason: str
    tool_plan: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    errors: list[str]
    output_message: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_state(query: str, session_id: str = "", user_id: str = "") -> HarnessState:
    now = now_utc_iso()
    return HarnessState(
        run_id=str(uuid4()),
        session_id=session_id,
        user_id=user_id,
        input_query=query,
        normalized_query=query.strip().lower(),
        route="synthesizer",
        pending_critical_action=False,
        hitl_required=False,
        approval_id="",
        interrupt_reason="",
        tool_plan=[],
        tool_results=[],
        errors=[],
        output_message="",
        metadata={},
        created_at=now,
        updated_at=now,
    )

