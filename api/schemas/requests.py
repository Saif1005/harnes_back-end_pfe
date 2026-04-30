from __future__ import annotations

from pydantic import BaseModel, Field


class InvokeRequest(BaseModel):
    session_id: str = Field(default="", description="Conversation/session identifier")
    user_id: str = Field(default="", description="Operator identifier")
    query: str = Field(..., min_length=1, description="User query to process")
    source: str = Field(default="user", description="user | scheduler | webhook")


class ResumeRequest(BaseModel):
    run_id: str = Field(..., min_length=1, description="LangGraph run identifier")
    approval_id: str = Field(..., min_length=1, description="HITL approval event identifier")
    approved: bool = Field(..., description="True to continue, False to reject")
    reviewer: str = Field(default="", description="Reviewer identity")
    comment: str = Field(default="", description="Optional review comment")

