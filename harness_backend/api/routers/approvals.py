from __future__ import annotations

from fastapi import APIRouter

from harness_backend.graph.checkpoint.sqlite_store import SQLiteCheckpointStore

router = APIRouter(prefix="/approvals", tags=["approvals"])
CHECKPOINT_DB_PATH = "/tmp/harness/checkpoints.sqlite"


@router.get("/pending")
def list_pending_approvals() -> dict[str, list[dict[str, str]]]:
    store = SQLiteCheckpointStore(db_path=CHECKPOINT_DB_PATH)
    items: list[dict[str, str]] = []
    for state in store.list_latest_states(limit=200):
        if state.get("hitl_required"):
            items.append(
                {
                    "run_id": state.get("run_id", ""),
                    "approval_id": state.get("approval_id", ""),
                    "reason": state.get("interrupt_reason", ""),
                }
            )
    return {"items": items}

