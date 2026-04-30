from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harness_backend.api.schemas.requests import InvokeRequest
from harness_backend.api.schemas.responses import InvokeResponse
from harness_backend.core.state import new_state
from harness_backend.graph.builder import build_harness_graph
from harness_backend.graph.checkpoint.sqlite_store import SQLiteCheckpointStore

router = APIRouter(prefix="/invoke", tags=["invoke"])

CHECKPOINT_DB_PATH = "/tmp/harness/checkpoints.sqlite"


@router.post("", response_model=InvokeResponse)
def invoke(payload: InvokeRequest) -> InvokeResponse:
    try:
        state = new_state(query=payload.query, session_id=payload.session_id, user_id=payload.user_id)
        runner = build_harness_graph(checkpointer=SQLiteCheckpointStore(db_path=CHECKPOINT_DB_PATH))
        state = runner.run(state)
        status = "interrupted" if state.get("hitl_required") else "ok"
        if state.get("route") == "error":
            status = "error"
        return InvokeResponse(
            run_id=state["run_id"],
            status=status,
            route=state.get("route", "unknown"),
            message=state.get("output_message", ""),
            approval_id=state.get("approval_id", ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"invoke_failed: {exc}") from exc

