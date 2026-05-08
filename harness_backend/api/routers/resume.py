from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harness_backend.api.schemas.requests import ResumeRequest
from harness_backend.api.schemas.responses import InvokeResponse
from harness_backend.graph.nodes.synthesizer import node_synthesizer
from harness_backend.graph.nodes.tool_executor import node_tool_executor
from harness_backend.graph.checkpoint.sqlite_store import SQLiteCheckpointStore
from harness_backend.tools.implementations.prediction_tools import run_prediction_regression
from harness_backend.tools.implementations.stock_tools import run_stock_check
from harness_backend.services.stock_runtime import apply_recipe_consumption

router = APIRouter(prefix="/resume", tags=["resume"])
CHECKPOINT_DB_PATH = "/tmp/harness/checkpoints.sqlite"


@router.post("", response_model=InvokeResponse)
def resume(payload: ResumeRequest) -> InvokeResponse:
    store = SQLiteCheckpointStore(db_path=CHECKPOINT_DB_PATH)
    state = store.load_latest(run_id=payload.run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run_not_found")

    if state.get("approval_id") != payload.approval_id:
        raise HTTPException(status_code=400, detail="approval_id_mismatch")

    if payload.approved:
        state["hitl_required"] = False
        state["pending_critical_action"] = False
        state = node_tool_executor(state)
        recipe_items: list[dict] = []
        for tr in state.get("tool_results", []):
            if tr.get("tool_name") == "recipe_compute" and bool(tr.get("ok")):
                recipe_items = list(dict(tr.get("data") or {}).get("recipe_items") or [])
                break
        if recipe_items:
            consumption = apply_recipe_consumption(
                recipe_items=recipe_items,
                run_id=str(state.get("run_id", "")),
                reason="approved_order",
            )
            state.setdefault("metadata", {})["stock_consumption"] = consumption
            # refresh stock + prediction after actual consumption
            tool_results = state.setdefault("tool_results", [])
            tool_results.append(
                {
                    "tool_name": "stock_check",
                    "ok": True,
                    "model": "dataset-aggregator",
                    "data": run_stock_check("post-approval-refresh"),
                }
            )
            tool_results.append(
                {
                    "tool_name": "prediction_regression",
                    "ok": True,
                    "model": "ridge-regression",
                    "data": run_prediction_regression("post-approval-refresh"),
                }
            )
        store.save(state, node_name="tool_executor")
        state = node_synthesizer(state)
        store.save(state, node_name="synthesizer")
        return InvokeResponse(
            run_id=payload.run_id,
            status="ok",
            route=state.get("route", "unknown"),
            message=state.get("output_message", "Execution resumed after approval"),
            approval_id="",
            details={
                "tool_results": state.get("tool_results", []),
                "errors": state.get("errors", []),
                "metadata": state.get("metadata", {}),
                "react_trace": state.get("react_trace", []),
            },
        )

    state["route"] = "error"
    state["output_message"] = "Execution rejected by reviewer"
    store.save(state, node_name="resume_rejected")
    return InvokeResponse(
        run_id=payload.run_id,
        status="rejected",
        route="error",
        message=state["output_message"],
        approval_id="",
        details={
            "tool_results": state.get("tool_results", []),
            "errors": state.get("errors", []),
            "metadata": state.get("metadata", {}),
            "react_trace": state.get("react_trace", []),
        },
    )

