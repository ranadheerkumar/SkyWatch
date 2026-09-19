from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class TestDatasetCreate(BaseModel):
    application_id: int
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    data_rows: list[dict[str, Any]] = Field(default_factory=list)


class TestDatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    data_rows: list[dict[str, Any]] | None = None


class TestDatasetResponse(TestDatasetCreate):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SmartTestDataGenerateRequest(BaseModel):
    name: str = Field(default="Synthetic QA Dataset", max_length=200)
    description: str | None = None
    field_names: list[str] = Field(default_factory=lambda: ["first_name", "last_name", "email", "phone", "status"])
    scenario_types: list[str] = Field(default_factory=lambda: ["valid", "invalid", "boundary", "edge"])
    row_count: int = Field(default=10, ge=1, le=100)
    save_to_database: bool = True
    provider: str | None = None
    model: str | None = None


class SmartTestDataGenerateResponse(BaseModel):
    application_id: int
    dataset_id: int | None = None
    name: str
    row_count: int
    data_rows: list[dict[str, Any]]
    learned_entities_used: int = 0
