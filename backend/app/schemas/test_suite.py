from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _normalize_case_ids(case_ids: list[int]) -> list[int]:
    seen: set[int] = set()
    normalized: list[int] = []
    for case_id in case_ids:
        if case_id <= 0 or case_id in seen:
            continue
        seen.add(case_id)
        normalized.append(case_id)
    return normalized


class TestSuiteCreate(BaseModel):
    application_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    case_ids: list[int] = Field(default_factory=list, max_length=500)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Suite name is required")
        return normalized

    @field_validator("case_ids")
    @classmethod
    def validate_case_ids(cls, value: list[int]) -> list[int]:
        return _normalize_case_ids(value)


class TestSuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    case_ids: list[int] | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Suite name is required")
        return normalized

    @field_validator("case_ids")
    @classmethod
    def validate_case_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        return _normalize_case_ids(value)


class TestSuiteResponse(BaseModel):
    id: int
    application_id: int
    name: str
    description: str | None = None
    case_ids: list[int] = Field(default_factory=list)
    case_count: int = 0
    created_by: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}