from __future__ import annotations

from pydantic import BaseModel, Field


class InvokeResponse(BaseModel):
    run_id: str = Field(..., description="Execution id")
    status: str = Field(..., description="ok | interrupted | error")
    route: str = Field(default="unknown", description="supervisor route selected")
    message: str = Field(default="", description="User-facing output")
    approval_id: str = Field(default="", description="Set when HITL approval is required")
    details: dict = Field(default_factory=dict, description="Structured execution payload")


class HealthResponse(BaseModel):
    service: str
    version: str
    status: str

