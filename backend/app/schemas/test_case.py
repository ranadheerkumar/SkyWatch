import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.execution import Check, Step


from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.execution import Check, Step


class TestCaseCreate(BaseModel):
    application_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    preconditions: str | None = None
    steps: str = Field(default="")
    expected_result: str | None = None
    status: str = Field(default="draft", max_length=40)
    priority: str = Field(default="medium", max_length=20)
    category: str = Field(default="positive", max_length=40)
    tags: list[str] = Field(default_factory=list)
    version: int = Field(default=1)
    automation_status: str = Field(default="automated", max_length=40)
    test_data: dict[str, Any] | list[Any] | None = None


class TestCaseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    preconditions: str | None = None
    steps: str | None = None
    expected_result: str | None = None
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    version: int | None = None
    automation_status: str | None = None
    test_data: dict[str, Any] | list[Any] | None = None


class TestCaseReviewRequest(BaseModel):
    action: Literal["approve", "reject"]


class TestCaseCloneRequest(BaseModel):
    new_title: str | None = None
    target_application_id: int | None = None


class TestCaseBulkDeleteRequest(BaseModel):
    test_case_ids: list[int] = Field(min_length=1, max_length=500)

    @field_validator("test_case_ids")
    @classmethod
    def validate_test_case_ids(cls, value: list[int]) -> list[int]:
        if any(test_case_id < 1 for test_case_id in value):
            raise ValueError("Test case IDs must be positive")
        return value


class TestCaseBulkDeleteResponse(BaseModel):
    requested_count: int = Field(ge=1)
    deleted_count: int = Field(ge=0)


class TestCaseResponse(TestCaseCreate):
    id: int
    created_by: int

    @field_validator("test_data", mode="before")
    @classmethod
    def normalize_legacy_test_data(cls, value: Any) -> dict[str, Any] | list[Any] | None:
        if value is None or isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                return None
            return parsed if isinstance(parsed, (dict, list)) else None
        return None

    model_config = {"from_attributes": True}


class TestCaseAutomationDefinition(BaseModel):
    steps: list[Step] = Field(default_factory=list, max_length=100)
    checks: list[Check] = Field(default_factory=list, max_length=25)


class TestCaseAutomationResponse(TestCaseAutomationDefinition):
    test_case_id: int


class TestCaseAutomationReadiness(BaseModel):
    test_case_id: int
    title: str
    status: str
    has_automation: bool
    confidence_score: int = Field(ge=0, le=100)
    confidence_label: Literal["high", "medium", "low"]
    needs_manual_selector_review: bool
    reasons: list[str] = Field(default_factory=list, max_length=10)


class AITestCaseGenerateRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=10000)
    input_format: Literal["text", "user_story", "acceptance_criteria", "brd", "csv", "excel", "openapi", "db_schema", "performance_requirements"] = "text"
    max_cases: int | None = Field(default=None, ge=1, le=50)
    replace_existing_drafts: bool = Field(default=False)
    target_url: str | None = Field(default=None, max_length=2048)
    include_authenticated_snapshot: bool = Field(default=False)
    login_email: str | None = Field(default=None, max_length=500)
    login_password: str | None = Field(default=None, max_length=500)
    login_email_selector: str | None = Field(default=None, max_length=500)
    login_password_selector: str | None = Field(default=None, max_length=500)
    login_submit_selector: str | None = Field(default=None, max_length=500)
    min_steps_per_case: int = Field(default=2, ge=1, le=20)
    max_steps_per_case: int = Field(default=15, ge=2, le=30)
    include_positive_scenarios: bool = Field(default=True)
    include_negative_scenarios: bool = Field(default=True)
    include_boundary_scenarios: bool = Field(default=True)
    include_edge_cases: bool = Field(default=True)
    include_security_scenarios: bool = Field(default=True)
    include_validation_rules: bool = Field(default=True)
    include_accessibility_checks: bool = Field(default=True)
    include_api_validations: bool = Field(default=False)
    include_performance_scenarios: bool = Field(default=False)
    performance_budget: str | None = Field(default=None, max_length=500)
    module_focus: str | None = Field(default=None, max_length=500)
    document_context: str | None = Field(default=None, max_length=60000)
    document_names: list[str] = Field(default_factory=list, max_length=20)
    jira_key: str | None = Field(default=None, max_length=100)
    jira_link: str | None = Field(default=None, max_length=2048)
    jira_context: str | None = Field(default=None, max_length=60000)
    jira_summary: str | None = Field(default=None, max_length=500)
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)


class AIGenerationJobResponse(BaseModel):
    id: str
    application_id: int
    provider: str | None = None
    model: str | None = None
    status: Literal["queued", "running", "completed", "failed"]
    phase: str
    generated_count: int
    valid_count: int
    review_count: int
    result: dict | None = None
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class AIDocumentFileAnalysis(BaseModel):
    filename: str
    extension: str
    size_bytes: int
    pages_parsed: int
    requirements_found: int
    features_identified: int
    modules_identified: list[str] = Field(default_factory=list)
    business_rules_found: int
    workflows_discovered: int
    extracted_characters: int
    warnings: list[str] = Field(default_factory=list)


class AIDocumentAnalysisResponse(BaseModel):
    files: list[AIDocumentFileAnalysis] = Field(default_factory=list)
    total_files: int
    total_pages: int
    requirements_found: int
    features_identified: int
    modules_identified: list[str] = Field(default_factory=list)
    business_rules_found: int
    workflows_discovered: int
    extracted_characters: int
    context_text: str = Field(default="", max_length=60000)
    warnings: list[str] = Field(default_factory=list)


class MultiFormatIngestRequest(BaseModel):
    application_id: int
    format: Literal["text", "markdown_table", "csv", "json", "openapi", "db_schema"] = "text"
    content: str
    preconditions: str | None = None
    target_url: str | None = None


class AIGeneratedTestCase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    preconditions: str = Field(default="", max_length=4000)
    steps: str = Field(min_length=1, max_length=12000)
    expected_result: str = Field(default="", max_length=4000)
    priority: str = Field(default="medium", max_length=20)
    category: str = Field(default="positive", max_length=40)
    tags: list[str] = Field(default_factory=list)
    status: Literal["draft", "ready"] = "draft"
    test_data: dict[str, Any] | list[Any] | None = None


class AIProposalItem(BaseModel):
    temp_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    preconditions: str | None = None
    steps: str = Field(default="")
    expected_result: str | None = None
    priority: str = Field(default="medium", max_length=20)
    category: str = Field(default="positive", max_length=40)
    tags: list[str] = Field(default_factory=list)
    confidence_score: int = Field(default=85, ge=0, le=100)
    confidence_label: Literal["high", "medium", "low"] = "high"
    needs_manual_selector_review: bool = False
    reasons: list[str] = Field(default_factory=list)
    selected: bool = True


class AIProposalResponse(BaseModel):
    application_id: int
    source_filename: str | None = None
    summary: str
    total_proposed: int
    proposals: list[AIProposalItem]


class ApproveProposalsRequest(BaseModel):
    application_id: int
    approved_cases: list[TestCaseCreate] = Field(min_length=1)
    replace_existing: bool = False


class AIGeneratedTestCaseSet(BaseModel):
    summary: str = Field(default="", max_length=4000)
    test_cases: list[AIGeneratedTestCase] = Field(min_length=1, max_length=50)
    generation_mode: Literal["provider"] | None = None
    generation_note: str = Field(default="", max_length=2000)
    generation_provider: str = Field(default="", max_length=120)
    planner_used: bool = False
    planner_provider: str = Field(default="", max_length=120)
    planner_model: str = Field(default="", max_length=120)
    planner_case_target: int = Field(default=0, ge=0, le=50)
    generator_call_count: int = Field(default=1, ge=1, le=20)
