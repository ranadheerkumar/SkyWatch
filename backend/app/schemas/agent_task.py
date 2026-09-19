from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class AgentTaskCreate(BaseModel):
    objective: str = Field(min_length=3, max_length=5000, description="High-level goal or instruction for the agent.")
    application_id: int | None = Field(default=None, description="Optional target application ID.")
    max_iterations: int = Field(default=20, ge=1, le=50, description="Maximum ReAct loop iterations.")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context (URLs, credentials, module focus).")


class AgentTaskApproveRequest(BaseModel):
    step_id: str | None = Field(default=None, description="Step ID being approved or rejected.")
    approved: bool = Field(default=True, description="Whether to approve or reject the action.")
    feedback: str | None = Field(default=None, description="Optional feedback or instruction for replanning.")


class AgentTaskResponse(BaseModel):
    id: str
    objective: str
    application_id: int | None = None
    created_by: int
    status: str
    plan: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    trace: list[dict[str, Any]] | None = None
    artifacts: dict[str, Any] | None = None
    error: str | None = None
    total_steps: int = 0
    completed_steps: int = 0
    total_llm_calls: int = 0
    duration_ms: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentTaskListItem(BaseModel):
    id: str
    objective: str
    application_id: int | None = None
    created_by: int
    status: str
    total_steps: int = 0
    completed_steps: int = 0
    total_llm_calls: int = 0
    duration_ms: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentTaskTraceResponse(BaseModel):
    task_id: str
    status: str
    trace_count: int
    trace: list[dict[str, Any]]
