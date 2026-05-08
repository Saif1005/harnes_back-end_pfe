from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from harness_backend.services.persistence import append_reasoning_memory, fetch_reasoning_memory

router = APIRouter(prefix="/mcp/reasoning-memory", tags=["mcp-memory"])


class ReasoningMemoryAppend(BaseModel):
    session_id: str = Field(..., min_length=1)
    run_id: str = Field(default="")
    user_id: str = Field(default="")
    kind: str = Field(default="react_step", max_length=64)
    payload: dict = Field(default_factory=dict)


class ReasoningMemoryRead(BaseModel):
    session_id: str = Field(..., min_length=1)
    limit: int = Field(default=80, ge=1, le=500)


@router.post("/append")
def reasoning_memory_append(body: ReasoningMemoryAppend) -> dict:
    try:
        append_reasoning_memory(
            session_id=body.session_id,
            run_id=body.run_id or "",
            user_id=body.user_id or "",
            kind=body.kind,
            payload=body.payload,
        )
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"reasoning_memory_append_failed: {exc}") from exc


@router.post("/read")
def reasoning_memory_read(body: ReasoningMemoryRead) -> dict:
    try:
        items = fetch_reasoning_memory(session_id=body.session_id, limit=body.limit)
        return {"ok": True, "items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"reasoning_memory_read_failed: {exc}") from exc
