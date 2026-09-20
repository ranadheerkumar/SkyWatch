import os
import logging
from typing import Any

from app.schemas.canonical_execution import (
    BrowserType,
    PlatformType,
    ProviderCapabilities,
    ProviderHealthStatus,
    ProviderType,
)
from app.services.execution_providers.base import ExecutionProvider
from app.services.execution_providers.local_provider import LocalExecutionProvider
from app.services.execution_providers.sauce_labs_provider import SauceLabsExecutionProvider
from app.services.execution_providers.lambdatest_provider import LambdaTestExecutionProvider
from app.services.execution_providers.cloud_container_provider import CloudContainerExecutionProvider

logger = logging.getLogger(__name__)


class ExecutionProviderRegistry:
    """
    Central Registry for all Multi-Environment Execution Providers in SkyWatch.
    Enables dynamic capability discovery, health monitoring, and intelligent
    execution dispatch across Local, Cloud Grids, and Cloud Containers.
    """

    def __init__(self):
        self._providers: dict[str, ExecutionProvider] = {}
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        # 1. First-Class Local Provider (Always Available, Zero-Cloud Default)
        self.register(LocalExecutionProvider("local", "Local Playwright Runner"))

        # 2. Remote Cloud Grids
        self.register(SauceLabsExecutionProvider("sauce_labs", "Sauce Labs Cloud Grid"))
        self.register(LambdaTestExecutionProvider("lambdatest", "LambdaTest Smart Automation Grid"))

        # 3. Cloud Containers & Docker
        self.register(CloudContainerExecutionProvider("docker", "Docker Container Runner", cloud_target="docker"))
        self.register(CloudContainerExecutionProvider("azure", "Azure Container Apps Runner", cloud_target="azure"))
        self.register(CloudContainerExecutionProvider("gcp", "GCP Cloud Run Runner", cloud_target="gcp"))
        self.register(CloudContainerExecutionProvider("aws", "AWS ECS Fargate Runner", cloud_target="aws"))

    def register(self, provider: ExecutionProvider) -> None:
        self._providers[provider.provider_id] = provider
        logger.info("Registered execution provider: %s (%s)", provider.provider_id, provider.name)

    def get(self, provider_id: str | None) -> ExecutionProvider:
        if not provider_id or provider_id.strip() == "":
            return self.get_default_provider()
        clean_id = provider_id.strip().lower()
        if clean_id in self._providers:
            return self._providers[clean_id]
        logger.warning("Requested provider '%s' not found, falling back to default provider.", provider_id)
        return self.get_default_provider()

    def get_default_provider(self) -> ExecutionProvider:
        """
        Resolves default provider from environment variable `SKYWATCH_EXECUTION_PROVIDER`
        or `EXECUTION_PROVIDER`. Defaults securely to 'local' for zero-regression local execution.
        """
        preferred = (
            os.getenv("SKYWATCH_EXECUTION_PROVIDER")
            or os.getenv("EXECUTION_PROVIDER")
            or "local"
        ).strip().lower()

        if preferred in self._providers and self._providers[preferred].is_configured():
            return self._providers[preferred]
        return self._providers["local"]

    def list_all(self) -> list[ExecutionProvider]:
        return list(self._providers.values())

    def get_all_capabilities(self) -> list[ProviderCapabilities]:
        return [p.get_capabilities() for p in self._providers.values()]

    async def check_all_health(self) -> list[ProviderHealthStatus]:
        statuses = []
        for provider in self._providers.values():
            try:
                status = await provider.check_health()
                statuses.append(status)
            except Exception as exc:
                statuses.append(
                    ProviderHealthStatus(
                        provider_id=provider.provider_id,
                        is_available=False,
                        status="unreachable",
                        latency_ms=None,
                        error_message=str(exc),
                    )
                )
        return statuses

    def find_best_provider(
        self,
        target_platform: str = "web",
        browser: str = "chromium",
        requires_real_device: bool = False,
        requires_tunnel: bool = False,
    ) -> ExecutionProvider:
        """
        Dynamically selects the best execution provider based on execution requirements.
        If real devices are required: prefers Sauce Labs or LambdaTest (if configured).
        If offline or standard web: prefers Local.
        """
        clean_platform = target_platform.lower()
        clean_browser = browser.lower()

        # Check cloud grids for real devices or mobile
        if requires_real_device or clean_platform == "mobile":
            for pid in ("sauce_labs", "lambdatest"):
                p = self._providers.get(pid)
                if p and p.is_configured():
                    return p

        # Check tunnels
        if requires_tunnel:
            for pid in ("sauce_labs", "lambdatest"):
                p = self._providers.get(pid)
                if p and p.is_configured():
                    return p

        # Default fallback to Local Execution Provider
        return self._providers.get("local", self.get_default_provider())


# Global singleton instance
execution_registry = ExecutionProviderRegistry()
