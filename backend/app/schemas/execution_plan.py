from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class ExecutionPlanCreate(BaseModel):
    application_id: int
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    target_type: Literal["web", "api", "database", "mobile"] = "web"
    case_ids: list[int] = Field(default_factory=list)
    suite_ids: list[int] = Field(default_factory=list)
    execution_mode: Literal["watch_live", "background"] = "watch_live"
    schedule_cron: str | None = None
    status: str = Field(default="active", max_length=40)


class ExecutionPlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    target_type: Literal["web", "api", "database", "mobile"] | None = None
    case_ids: list[int] | None = None
    suite_ids: list[int] | None = None
    execution_mode: Literal["watch_live", "background"] | None = None
    schedule_cron: str | None = None
    status: str | None = None


class ExecutionPlanResponse(ExecutionPlanCreate):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
