import re
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Check(BaseModel):
	type: Literal["title_contains", "visible", "text_contains"]
	value: str = Field(min_length=1, max_length=500)


class Step(BaseModel):
	action: Literal[
		"click",
		"type",
		"select",
		"check",
		"uncheck",
		"navigate",
		"go_back",
		"reload",
		"assert_visible",
		"assert_text",
		"assert_title",
		"assert_url_contains",
	]
	selector: str | None = Field(default=None, max_length=500)
	value: str | None = Field(default=None, max_length=2_000)
	secret_name: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
	description: str | None = Field(default=None, max_length=500)


class ExecutionRequest(BaseModel):
	application_id: int | None = Field(default=None, ge=1)
	url: HttpUrl
	checks: list[Check] = Field(default_factory=list, max_length=25)
	steps: list[Step] = Field(default_factory=list, max_length=100)
	parameters: dict[str, str] = Field(default_factory=dict, max_length=50)
	timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
	capture_screenshot: bool = True
	highlight_actions: bool = True
	capture_video: bool = True
	capture_audio: bool = True
	voice_gender: Literal["male", "female"] = "male"
	execution_mode: Literal["watch_live", "background"] = "watch_live"
	execution_provider: str = Field(default="local", max_length=100)
	browser: Literal["chromium", "firefox", "webkit", "chrome", "edge"] = "chromium"
	target_platform: Literal["web", "mobile", "api", "desktop"] = "web"
	device_name: str | None = Field(default=None, max_length=200)
	provider_config: dict[str, Any] = Field(default_factory=dict)
	headless: bool | None = Field(default=None)
	slow_mode: Literal["normal", "demo", "showcase"] = "normal"
	trace_mode: Literal["off", "on_failure", "always"] = "on_failure"
	keep_browser_open_seconds: int = Field(default=0, ge=0, le=120)
	keep_browser_open_on_failure: bool = True
	healing_enabled: bool = True
	healing_attempts: int = Field(default=1, ge=0, le=2)
	ai_provider: str | None = Field(default=None, max_length=100)
	ai_model: str | None = Field(default=None, max_length=100)

	@field_validator("parameters")
	@classmethod
	def validate_parameters(cls, parameters: dict[str, str]) -> dict[str, str]:
		normalized: dict[str, str] = {}
		for raw_key, value in parameters.items():
			key = raw_key.strip()
			if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", key):
				raise ValueError(f"Invalid runtime parameter key '{raw_key}'. Use letters, numbers, dots, hyphens, or underscores.")
			if len(value) > 2_000:
				raise ValueError(f"Runtime parameter '{key}' exceeds the 2,000-character limit.")
			if key in normalized:
				raise ValueError(f"Runtime parameter '{key}' is defined more than once.")
			normalized[key] = value
		return normalized


class MobileExecutionRequest(BaseModel):
	platform: Literal["android", "ios"]
	artifact_path: str = Field(min_length=1, max_length=2048)
	device_name: str = Field(min_length=1, max_length=200)
	appium_url: HttpUrl | None = None
	steps: list[Step] = Field(default_factory=list, max_length=100)


class CheckResult(BaseModel):
	type: str
	value: str
	passed: bool
	message: str


class StepResult(BaseModel):
	index: int = Field(ge=1)
	action: str
	selector: str | None = None
	passed: bool
	message: str
	duration_ms: int = Field(ge=0)


class ExecutionArtifact(BaseModel):
	type: Literal["screenshot", "video", "trace"]
	path: str
	label: str
	step_index: int | None = Field(default=None, ge=1)


class ExecutionResponse(BaseModel):
	run_id: str
	url: str
	status: Literal["passed", "failed", "error", "cancelled"]
	failure_type: Literal[
		"LOCATOR",
		"TIMING",
		"NAVIGATION",
		"AUTHENTICATION",
		"TEST_DATA",
		"ENVIRONMENT",
		"NETWORK",
		"ASSERTION",
		"APPLICATION_DEFECT",
		"AUTOMATION_DEFECT",
		"UNKNOWN",
	] | None = None
	failure_summary: str | None = None
	title: str | None = None
	duration_ms: int
	audio_status: Literal["embedded", "unavailable", "disabled"] = "disabled"
	screenshot_path: str | None = None
	checks: list[CheckResult]
	step_results: list[StepResult] = Field(default_factory=list)
	step_artifacts: list[ExecutionArtifact] = Field(default_factory=list)
	artifacts: list[ExecutionArtifact] = Field(default_factory=list)
	console_errors: list[str] = Field(default_factory=list)
	network_errors: list[str] = Field(default_factory=list)
	error: str | None = None
	healer_agent: str | None = None
	healed_steps: list[dict[str, Any]] = Field(default_factory=list)
	execution_provider: str = "local"
	browser: str = "chromium"
	remote_session_id: str | None = None
	remote_dashboard_url: str | None = None


class RunCreated(BaseModel):
	run_id: str
	status: Literal["queued", "running", "passed", "failed", "error", "cancelled"]


class RunStatus(RunCreated):
	url: str
	application_id: int | None
	steps: list[dict] = Field(default_factory=list)
	result: ExecutionResponse | None = None
	log: str
	live_state: str | None = None
	current_action: str | None = None


class RunSummary(RunCreated):
	application_id: int
	batch_id: str | None = None
	build_name: str | None = None
	trigger_source: str | None = None
	created_at: str | None = None
	finished_at: str | None = None


class BuildExecutionSummary(BaseModel):
	build_id: str
	application_id: int
	name: str
	status: Literal["queued", "running", "passed", "failed", "error", "cancelled"]
	trigger_source: str = "manual"
	total_cases: int = 0
	passed_count: int = 0
	failed_count: int = 0
	error_count: int = 0
	pass_rate: float = 0.0
	duration_ms: float = 0.0
	created_at: str | None = None
	finished_at: str | None = None


class BuildCaseExecutionItem(BaseModel):
	run_id: str
	test_case_id: int | None = None
	title: str
	status: str
	duration_ms: int | None = None
	check_summary: str | None = None
	failure_type: str | None = None
	failure_summary: str | None = None
	error: str | None = None
	created_at: str | None = None
	finished_at: str | None = None
	result: dict[str, Any] | None = None


class BuildExecutionDetail(BaseModel):
	build_id: str
	application_id: int
	application_name: str
	target_url: str
	name: str
	status: Literal["queued", "running", "passed", "failed", "error", "cancelled"]
	trigger_source: str = "manual"
	total_cases: int = 0
	passed_count: int = 0
	failed_count: int = 0
	error_count: int = 0
	pass_rate: float = 0.0
	duration_ms: float = 0.0
	created_at: str | None = None
	finished_at: str | None = None
	cases: list[BuildCaseExecutionItem] = Field(default_factory=list)


class BatchExecutionRequest(BaseModel):
	application_id: int = Field(ge=1)
	case_ids: list[int] = Field(min_length=1, max_length=50)
	build_name: str | None = Field(default=None, max_length=200)
	trigger_source: str = Field(default="manual", max_length=50)
	execution_mode: Literal["watch_live", "background"] = "watch_live"
	execution_provider: str = Field(default="local", max_length=100)
	browser: Literal["chromium", "firefox", "webkit", "chrome", "edge"] = "chromium"
	capture_screenshot: bool = True
	capture_video: bool = True
	capture_audio: bool = True
	voice_gender: Literal["male", "female"] = "male"
	slow_mode: Literal["normal", "demo", "showcase"] = "normal"
	trace_mode: Literal["off", "on_failure", "always"] = "on_failure"
	keep_browser_open_on_failure: bool = True
	keep_browser_open_seconds: int | None = None
	healing_enabled: bool = True
	healing_attempts: int = Field(default=1, ge=0, le=2)
	ai_provider: str | None = Field(default=None, max_length=100)
	ai_model: str | None = Field(default=None, max_length=100)
	highlight_actions: bool = True
	parameters: dict[str, str] = Field(default_factory=dict)


class BatchExecutionCreated(BaseModel):
	build_id: str
	application_id: int
	name: str
	status: str
	total_cases: int
	runs: list[RunCreated] = Field(default_factory=list)
