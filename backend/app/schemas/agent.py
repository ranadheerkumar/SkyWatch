from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class AgentRecommendationCreate(BaseModel):
    application_id: int
    test_case_id: int | None = None
    recommendation_type: Literal[
        "missing_steps",
        "missing_validation",
        "ui_change_detected",
        "outdated_test",
        "new_test_case",
        "healing",
    ]
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    proposed_steps: list[dict[str, Any]] | None = None
    proposed_checks: list[dict[str, Any]] | None = None


class AgentRecommendationAction(BaseModel):
    action: Literal["approve", "reject"]
    review_notes: str | None = None


class AgentRecommendationResponse(BaseModel):
    id: int
    application_id: int
    test_case_id: int | None = None
    recommendation_type: str
    title: str
    description: str | None = None
    proposed_steps: list[dict[str, Any]] | None = None
    proposed_checks: list[dict[str, Any]] | None = None
    status: str
    created_by: int
    reviewed_by: int | None = None
    created_at: datetime
    reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}


class PreExecutionAnalysisRequest(BaseModel):
    application_id: int
    case_ids: list[int] = Field(default_factory=list)


class PreExecutionAnalysisResponse(BaseModel):
    application_id: int
    total_analyzed: int
    ready_count: int
    at_risk_count: int
    outdated_count: int
    insights: list[str]
    recommendations: list[AgentRecommendationResponse]
