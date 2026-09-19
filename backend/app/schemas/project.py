from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    lifecycle: Literal["active", "paused", "archived"] = "active"
    owner: str = Field(default="Admin QA", min_length=1, max_length=120)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    lifecycle: Literal["active", "paused", "archived"] | None = None
    owner: str | None = Field(default=None, min_length=1, max_length=120)


class ProjectResponse(ProjectCreate):
    id: str
    created_by: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
