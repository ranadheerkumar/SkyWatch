import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv
from app.core.version import get_application_version

_backend_dir = Path(__file__).resolve().parents[2]
_root_dir = _backend_dir.parent
load_dotenv(_root_dir / ".env")
load_dotenv(_backend_dir / ".env")


def _resolve_database_url() -> str:
    raw_url = (
        os.getenv("DATABASE_URL")
        or (f"sqlite:///{(_backend_dir / 'sheppard.db').as_posix()}" if (_backend_dir / "sheppard.db").exists() else "sqlite:///./skywatch.db")
    ).strip()
    if raw_url.startswith("postgres://"):
        raw_url = "postgresql://" + raw_url[len("postgres://"):]
    if raw_url.startswith("sqlite:///") and not raw_url.startswith("sqlite:///:memory:"):
        path_part = raw_url[len("sqlite:///"):]
        if not Path(path_part).is_absolute():
            cand_backend = (_backend_dir / path_part).resolve()
            cand_root = (_root_dir / path_part).resolve()
            if cand_backend.exists() or not cand_root.exists():
                return f"sqlite:///{cand_backend.as_posix()}"
            return f"sqlite:///{cand_root.as_posix()}"
    return raw_url


@dataclass(frozen=True)
class Settings:
    # Application & Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    APP_NAME: str = "SkyWatch API"
    APP_VERSION: str = get_application_version()
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")

    # Database
    DATABASE_URL: str = _resolve_database_url()
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    ALLOW_PRIVATE_TARGETS: bool = os.getenv("ALLOW_PRIVATE_TARGETS", "false").lower() in ("true", "1")

    # Security & Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "skywatch-local-secret-key-development-2026")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    # External integrations are environment-configured and read-only.
    INTEGRATIONS_READ_ONLY: bool = (
        os.getenv("SKYWATCH_INTEGRATIONS_READ_ONLY")
        or os.getenv("AI_QA_ENGINE_INTEGRATIONS_READ_ONLY", "true")
    ).lower() in ("true", "1", "yes", "on")
    INTEGRATION_TIMEOUT_SECONDS: float = float(
        os.getenv("SKYWATCH_INTEGRATION_TIMEOUT_SECONDS")
        or os.getenv("AI_QA_ENGINE_INTEGRATION_TIMEOUT_SECONDS", "15")
    )
    INTEGRATION_MAX_RESPONSE_BYTES: int = int(
        os.getenv("SKYWATCH_INTEGRATION_MAX_RESPONSE_BYTES")
        or os.getenv("AI_QA_ENGINE_INTEGRATION_MAX_RESPONSE_BYTES", "2000000")
    )
    INTEGRATION_MAX_ASSET_ITEMS: int = int(
        os.getenv("SKYWATCH_INTEGRATION_MAX_ASSET_ITEMS")
        or os.getenv("AI_QA_ENGINE_INTEGRATION_MAX_ASSET_ITEMS", "100")
    )
    INTEGRATION_USER_AGENT: str = (
        os.getenv("SKYWATCH_INTEGRATION_USER_AGENT")
        or os.getenv("AI_QA_ENGINE_INTEGRATION_USER_AGENT", "SkyWatch/2.0")
    )

    JIRA_BASE_URL: str = os.getenv("JIRA_BASE_URL", "").strip()
    JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "").strip()
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "").strip()
    JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "").strip()
    JIRA_FILTER_ID: str = os.getenv("JIRA_FILTER_ID", "").strip()
    JIRA_PROFILE_NAME: str = os.getenv("JIRA_PROFILE_NAME", "").strip()
    JIRA_CREDENTIAL_ENV_NAME: str = os.getenv("JIRA_CREDENTIAL_ENV_NAME", "JIRA_API_TOKEN").strip()

    QTEST_BASE_URL: str = os.getenv("QTEST_BASE_URL", "").strip()
    QTEST_TOKEN: str = os.getenv("QTEST_TOKEN", "").strip()
    QTEST_PROJECT_ID: str = os.getenv("QTEST_PROJECT_ID", "").strip()
    QTEST_PROJECT_NAME: str = os.getenv("QTEST_PROJECT_NAME", "").strip()
    QTEST_PROFILE_NAME: str = os.getenv("QTEST_PROFILE_NAME", "").strip()
    QTEST_CREDENTIAL_ENV_NAME: str = os.getenv("QTEST_CREDENTIAL_ENV_NAME", "QTEST_TOKEN").strip()

    # Initial Admin Seed
    INITIAL_ADMIN_EMAIL: str = os.getenv(
        "INITIAL_ADMIN_EMAIL",
        os.getenv("SKYWATCH_ADMIN_EMAIL", os.getenv("AI_QA_ENGINE_ADMIN_EMAIL", "demo@example.com")),
    )
    INITIAL_ADMIN_PASSWORD: str = os.getenv(
        "INITIAL_ADMIN_PASSWORD",
        os.getenv("SKYWATCH_ADMIN_PASSWORD", os.getenv("AI_QA_ENGINE_ADMIN_PASSWORD", "DemoPassword123!")),
    )

    # AI Multi-Provider Configuration
    AI_PROVIDER: str = (
        os.getenv("AI_PROVIDER")
        or os.getenv("SKYWATCH_PROVIDER")
        or os.getenv("AI_QA_ENGINE_PROVIDER")
        or os.getenv("AI_QA_ENGINE_OPENAI_PROVIDER", "github_copilot")
    ).strip().lower()
    AI_MODEL: str = (
        os.getenv("AI_MODEL")
        or os.getenv("SKYWATCH_MODEL")
        or os.getenv("AI_QA_ENGINE_MODEL")
        or os.getenv("AI_QA_ENGINE_OPENAI_MODEL", "gpt-4o")
    )
    AI_API_KEY: str = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("AI_API_KEY")
        or os.getenv("SKYWATCH_API_KEY")
        or os.getenv("AI_OPENAI_API_KEY")
        or os.getenv("AI_QA_ENGINE_OPENAI_API_KEY")
        or os.getenv("AI_QA_ENGINE_API_KEY")
        or ""
    )
    AI_ENDPOINT: str = (
        os.getenv("AI_ENDPOINT")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("SKYWATCH_BASE_URL")
        or os.getenv("AI_BASE_URL")
        or os.getenv("AI_QA_ENGINE_OPENAI_BASE_URL")
        or os.getenv("AI_QA_ENGINE_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    AI_TEMPERATURE: float = float(os.getenv("AI_TEMPERATURE", "0.2"))
    AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "4096"))
    AI_TIMEOUT_SECONDS: int = int(
        os.getenv("AI_TIMEOUT_SECONDS")
        or os.getenv("SKYWATCH_TIMEOUT_SECONDS")
        or os.getenv("AI_QA_ENGINE_TIMEOUT_SECONDS", "45")
    )

    # Playwright Execution Settings
    EXECUTION_MODE: str = os.getenv("SKYWATCH_EXECUTION_MODE", os.getenv("AI_QA_ENGINE_EXECUTION_MODE", "watch_live"))
    STEP_SETTLE_MS: int = int(os.getenv("SKYWATCH_STEP_SETTLE_MS", os.getenv("AI_QA_ENGINE_STEP_SETTLE_MS", "1200")))
    VISIBLE_SLOW_MO_MS: int = int(os.getenv("SKYWATCH_PLAYWRIGHT_SLOW_MO_MS", os.getenv("AI_QA_ENGINE_PLAYWRIGHT_SLOW_MO_MS", "450")))
    DEMO_SLOW_MO_MS: int = int(os.getenv("SKYWATCH_PLAYWRIGHT_DEMO_SLOW_MO_MS", os.getenv("AI_QA_ENGINE_PLAYWRIGHT_DEMO_SLOW_MO_MS", "900")))
    SHOWCASE_SLOW_MO_MS: int = int(os.getenv("SKYWATCH_PLAYWRIGHT_SHOWCASE_SLOW_MO_MS", os.getenv("AI_QA_ENGINE_PLAYWRIGHT_SHOWCASE_SLOW_MO_MS", "650")))
    KEEP_BROWSER_OPEN_SECONDS: int = int(os.getenv("SKYWATCH_KEEP_BROWSER_OPEN_SECONDS", os.getenv("AI_QA_ENGINE_KEEP_BROWSER_OPEN_SECONDS", "6")))
    CAPTURE_SCREENSHOTS: bool = (os.getenv("SKYWATCH_CAPTURE_SCREENSHOTS") or os.getenv("AI_QA_ENGINE_CAPTURE_SCREENSHOTS", "true")).lower() in ("true", "1")

    # Queue & Worker Settings
    QUEUE_BACKEND: str = (os.getenv("SKYWATCH_QUEUE_BACKEND") or os.getenv("AI_QA_ENGINE_QUEUE_BACKEND", "local")).strip().lower()
    QUEUE_NAME: str = os.getenv("SKYWATCH_QUEUE_NAME", os.getenv("AI_QA_ENGINE_QUEUE_NAME", "skywatch-runs"))
    REDIS_URL: str = os.getenv("SKYWATCH_REDIS_URL", os.getenv("AI_QA_ENGINE_REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")))

    def __post_init__(self) -> None:
        if not self.INTEGRATIONS_READ_ONLY:
            raise RuntimeError("SKYWATCH_INTEGRATIONS_READ_ONLY must remain true while external writes are disabled")
        if self.ENVIRONMENT.strip().lower() != "production":
            return
        if self.SECRET_KEY in {"skywatch-local-secret-key-development-2026", "ai-qa-engine-local-secret-key-development-2026", "change-me-before-production"}:
            raise RuntimeError("SECRET_KEY must be configured with a production value")
        if self.INITIAL_ADMIN_PASSWORD in {"DemoPassword123!", ""}:
            raise RuntimeError("INITIAL_ADMIN_PASSWORD must be configured with a production value")


settings = Settings()
