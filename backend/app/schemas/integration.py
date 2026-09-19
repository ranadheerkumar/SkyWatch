from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.core.config import settings


IntegrationSystem = Literal["jira", "qtest"]
ConnectionStatus = Literal["untested", "active", "inactive", "error"]
AuthType = Literal["api_token", "basic_api_token", "bearer_token"]


class IntegrationConnectionCreate(BaseModel):
    system: IntegrationSystem
    name: str = Field(min_length=1, max_length=120)
    base_url: HttpUrl
    project_key: str | None = Field(default=None, max_length=120)
    project_name: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, max_length=320)
    auth_type: AuthType = "api_token"
    environment: str | None = Field(default=None, max_length=120)
    secret_ref: str | None = Field(default=None, max_length=160, pattern=r"^[A-Z][A-Z0-9_]{1,159}$")
    credential: str | None = Field(default=None, min_length=1, max_length=4096, exclude=True)

    @field_validator("name", "project_key", "project_name", "project_id", "username", "environment", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlparse(str(value))
        if parsed.username or parsed.password:
            raise ValueError("Base URL must not contain embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Base URL must not contain a query string or fragment")
        return value

    @model_validator(mode="after")
    def validate_project_requirements(self) -> "IntegrationConnectionCreate":
        if self.system == "jira" and not self.project_key and not settings.JIRA_FILTER_ID.isdigit():
            raise ValueError("Jira project key or numeric JIRA_FILTER_ID is required")
        if self.system == "qtest" and not (self.project_id or self.project_name):
            raise ValueError("qTest project ID or project name is required")
        if self.auth_type == "basic_api_token" and not self.username:
            raise ValueError("Username is required for basic API-token authentication")
        if not self.credential and not self.secret_ref:
            raise ValueError("Provide a credential or a secret reference")
        return self


class IntegrationConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: HttpUrl | None = None
    project_key: str | None = Field(default=None, max_length=120)
    project_name: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, max_length=320)
    auth_type: AuthType | None = None
    environment: str | None = Field(default=None, max_length=120)
    secret_ref: str | None = Field(default=None, max_length=160, pattern=r"^[A-Z][A-Z0-9_]{1,159}$")
    credential: str | None = Field(default=None, min_length=1, max_length=4096, exclude=True)

    @field_validator("name", "project_key", "project_name", "project_id", "username", "environment", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlparse(str(value))
        if parsed.username or parsed.password:
            raise ValueError("Base URL must not contain embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Base URL must not contain a query string or fragment")
        return value


class IntegrationConnectionResponse(BaseModel):
    id: int
    system: IntegrationSystem
    name: str
    base_url: str
    project_key: str | None = None
    project_name: str | None = None
    project_id: str | None = None
    username: str | None = None
    auth_type: AuthType
    environment: str | None = None
    status: ConnectionStatus
    credential_configured: bool
    environment_backed: bool = False
    secret_ref: str | None = None
    last_test_status: str | None = None
    last_test_message: str | None = None
    last_test_latency_ms: float | None = None
    last_tested_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IntegrationConnectionTestResponse(BaseModel):
    connection_id: int
    system: IntegrationSystem
    status: Literal["success", "error"]
    message: str
    latency_ms: int = Field(ge=0)
    read_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationEnvironmentProfile(BaseModel):
    configured: bool = False
    profile_name: str | None = None
    base_url: str | None = None
    username: str | None = None
    project_key: str | None = None
    filter_id: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    credential_env_name: str | None = None
    credential_configured: bool = False


class JiraEnvironmentUpdate(BaseModel):
    base_url: HttpUrl | None = None
    email: str | None = Field(default=None, max_length=320)
    api_token: str | None = Field(default=None, min_length=1, max_length=4096, exclude=True)
    project_key: str | None = Field(default=None, max_length=120)
    filter_id: str | None = Field(default=None, max_length=120)
    profile_name: str | None = Field(default=None, max_length=120)
    credential_env_name: str | None = Field(default=None, max_length=160, pattern=r"^[A-Z][A-Z0-9_]{1,159}$")

    @field_validator("email", "project_key", "filter_id", "profile_name", "credential_env_name", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is None:
            return value
        parsed = urlparse(str(value))
        if parsed.username or parsed.password:
            raise ValueError("Base URL must not contain embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Base URL must not contain a query string or fragment")
        return value

    @field_validator("filter_id")
    @classmethod
    def validate_filter_id(cls, value: str | None) -> str | None:
        if value and not value.isdigit():
            raise ValueError("Jira filter ID must contain only digits")
        return value


class QTestEnvironmentUpdate(BaseModel):
    base_url: HttpUrl | None = None
    token: str | None = Field(default=None, min_length=1, max_length=4096, exclude=True)
    project_id: str | None = Field(default=None, max_length=120)
    project_name: str | None = Field(default=None, max_length=200)
    profile_name: str | None = Field(default=None, max_length=120)
    credential_env_name: str | None = Field(default=None, max_length=160, pattern=r"^[A-Z][A-Z0-9_]{1,159}$")

    @field_validator("project_id", "project_name", "profile_name", "credential_env_name", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is None:
            return value
        parsed = urlparse(str(value))
        if parsed.username or parsed.password:
            raise ValueError("Base URL must not contain embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Base URL must not contain a query string or fragment")
        return value


class IntegrationEnvironmentUpdate(BaseModel):
    jira: JiraEnvironmentUpdate | None = None
    qtest: QTestEnvironmentUpdate | None = None

    @model_validator(mode="after")
    def require_system_update(self) -> "IntegrationEnvironmentUpdate":
        if self.jira is None and self.qtest is None:
            raise ValueError("Provide Jira or qTest environment settings")
        return self


class IntegrationEnvironmentResponse(BaseModel):
    read_only: bool = True
    jira: IntegrationEnvironmentProfile
    qtest: IntegrationEnvironmentProfile


IntegrationAssetType = Literal[
    "requirements",
    "modules",
    "releases",
    "cycles",
    "test_suites",
    "test_cases",
    "test_runs",
    "test_logs",
    "metadata",
]


class IntegrationAssetResponse(BaseModel):
    connection_id: int
    system: IntegrationSystem
    asset_type: IntegrationAssetType
    items: list[dict[str, Any]] = Field(default_factory=list)
    read_only: bool = True
    next_page: int | None = None


class JiraIssueResponse(BaseModel):
    key: str
    id: str | None = None
    summary: str
    description: str | None = None
    issue_type: str | None = None
    status: str | None = None
    priority: str | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    fix_versions: list[str] = Field(default_factory=list)
    assignee: str | None = None
    reporter: str | None = None
    url: str | None = None
    acceptance_criteria: str | None = None
    comments: list[str] = Field(default_factory=list)
    context_text: str = ""
    connection_id: int | None = None
    read_only: bool = True


class JiraFetchIssueRequest(BaseModel):
    issue_key_or_url: str = Field(min_length=1, max_length=2048)
    connection_id: int | None = None


class IntegrationActionError(BaseModel):
    system: IntegrationSystem
    action: str
    message: str
    status_code: int | None = None
    read_only: bool = True


class JiraLinkRequest(BaseModel):
    outward_key: str = Field(min_length=1, max_length=120)
    link_type: str = Field(default="Relates", max_length=120)
    comment: str | None = Field(default=None, max_length=5000)


class JiraTransitionRequest(BaseModel):
    transition_id: str = Field(min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=5000)


class JiraCommentRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=30000)


class QTestBuildCreateRequest(BaseModel):
    release_id: int | str
    build_name: str = Field(min_length=1, max_length=250)
    build_note: str = Field(default="", max_length=5000)


class QTestSubmitTestLogRequest(BaseModel):
    status: Literal["PASSED", "FAILED", "BLOCKED", "INCOMPLETE"] = "PASSED"
    start_time: str | None = None
    end_time: str | None = None
    name: str = Field(default="SkyWatch Test Run", max_length=250)
    note: str = Field(default="", max_length=5000)
    steps: list[dict[str, Any]] | None = None
    defect_ids: list[str | int] | None = None


class QTestExportTestCaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    description: str = Field(default="", max_length=10000)
    steps: list[dict[str, str]] | None = None
    parent_id: int | str | None = None


class IntegrationWebhookPayload(BaseModel):
    event: str
    timestamp: str | None = None
    issue_key: str | None = None
    project_key: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
