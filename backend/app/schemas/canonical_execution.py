from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl


class ExecutionMode(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"
    CLOUD = "cloud"
    CI = "ci"
    HYBRID = "hybrid"


class ProviderType(str, Enum):
    LOCAL = "local"
    SAUCE_LABS = "sauce_labs"
    LAMBDATEST = "lambdatest"
    AZURE = "azure"
    GCP = "gcp"
    AWS = "aws"
    DOCKER = "docker"
    CI = "ci"


class BrowserType(str, Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"
    CHROME = "chrome"
    EDGE = "edge"


class PlatformType(str, Enum):
    WEB = "web"
    MOBILE = "mobile"
    API = "api"
    DESKTOP = "desktop"


class DeviceProfile(BaseModel):
    name: str
    platform: PlatformType = PlatformType.WEB
    os_version: str | None = None
    screen_width: int = 1280
    screen_height: int = 800
    pixel_ratio: float = 1.0
    is_mobile: bool = False
    has_touch: bool = False
    user_agent: str | None = None


class ProviderCapabilities(BaseModel):
    provider_id: str
    name: str
    provider_type: ProviderType
    description: str = ""
    supported_browsers: list[BrowserType] = Field(default_factory=lambda: [BrowserType.CHROMIUM])
    supported_platforms: list[PlatformType] = Field(default_factory=lambda: [PlatformType.WEB])
    supported_devices: list[str] = Field(default_factory=list)
    supports_real_devices: bool = False
    supports_emulators: bool = False
    supports_live_video: bool = True
    supports_tracing: bool = True
    supports_network_capture: bool = True
    supports_tunnels: bool = False
    supports_parallel_execution: bool = False
    max_concurrency: int = 1
    regions: list[str] = Field(default_factory=lambda: ["local"])
    requires_credentials: bool = False
    has_valid_credentials: bool = True


class ProviderHealthStatus(BaseModel):
    provider_id: str
    is_available: bool = True
    status: Literal["healthy", "degraded", "unreachable", "unconfigured"] = "healthy"
    latency_ms: float | None = None
    error_message: str | None = None
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CanonicalExecutionRequest(BaseModel):
    """
    Universal, platform-neutral execution request representing test execution
    across Local, Remote Grid, Cloud Containers, or CI environments.
    """
    run_id: str
    application_id: int | None = None
    target_url: str
    target_platform: PlatformType = PlatformType.WEB
    browser: BrowserType = BrowserType.CHROMIUM
    device: DeviceProfile | None = None
    execution_mode: ExecutionMode = ExecutionMode.LOCAL
    provider_id: str = "local"
    provider_config: dict[str, Any] = Field(default_factory=dict)
    
    steps: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    parameters: dict[str, str] = Field(default_factory=dict)
    timeout_ms: int = 30_000
    
    headless: bool = True
    slow_mode: str = "normal"
    trace_mode: str = "on_failure"
    capture_screenshot: bool = True
    capture_video: bool = True
    capture_audio: bool = True
    voice_gender: str = "male"
    
    healing_enabled: bool = True
    healing_attempts: int = 1
    ai_provider: str | None = None
    ai_model: str | None = None
    
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalExecutionResult(BaseModel):
    """
    Universal, platform-neutral execution response normalizing outputs from
    Local Playwright, Sauce Labs, LambdaTest, Azure, GCP, or AWS.
    """
    run_id: str
    provider_id: str
    provider_type: ProviderType
    status: Literal["passed", "failed", "error", "cancelled"]
    duration_ms: int = 0
    browser: str = "chromium"
    platform: str = "web"
    
    # Remote grid / cloud execution metadata
    remote_session_id: str | None = None
    remote_dashboard_url: str | None = None
    remote_video_url: str | None = None
    remote_logs_url: str | None = None
    
    # Step-by-step and assertion results
    checks: list[dict[str, Any]] = Field(default_factory=list)
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    
    # Error and diagnostic details
    console_errors: list[str] = Field(default_factory=list)
    network_errors: list[str] = Field(default_factory=list)
    failure_type: str | None = None
    failure_summary: str | None = None
    error: str | None = None
    
    # AI Self-Healing outcome
    healing_applied: bool = False
    healed_steps: list[dict[str, Any]] = Field(default_factory=list)
    healer_agent: str | None = None
    
    raw_provider_metadata: dict[str, Any] = Field(default_factory=dict)
