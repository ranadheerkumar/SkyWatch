from abc import ABC, abstractmethod
from typing import Any
import logging

from app.schemas.canonical_execution import (
    CanonicalExecutionRequest,
    CanonicalExecutionResult,
    ProviderCapabilities,
    ProviderHealthStatus,
    ProviderType,
)

logger = logging.getLogger(__name__)


class ExecutionProvider(ABC):
    """
    Abstract Base Class for all SkyWatch Execution Providers.
    Every provider (Local, Sauce Labs, LambdaTest, Azure, GCP, AWS, Docker, CI)
    must implement this interface, guaranteeing zero code duplication
    and application-agnostic cloud portability.
    """

    def __init__(self, provider_id: str, name: str, provider_type: ProviderType):
        self.provider_id = provider_id
        self.name = name
        self.provider_type = provider_type

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """
        Returns the matrix of capabilities supported by this provider:
        supported browsers, platforms, real devices, tunnels, max concurrency, etc.
        """
        pass

    @abstractmethod
    async def check_health(self) -> ProviderHealthStatus:
        """
        Runs a lightweight health and connectivity probe.
        Verifies credentials, network connectivity, and service availability.
        """
        pass

    @abstractmethod
    async def execute(self, request: CanonicalExecutionRequest) -> CanonicalExecutionResult:
        """
        Executes the canonical test execution request and returns a normalized
        CanonicalExecutionResult.
        """
        pass

    async def cancel(self, run_id: str) -> bool:
        """
        Optional cancellation hook. Default implementation logs and returns False.
        """
        logger.info("Cancellation requested for run %s on provider %s (default no-op)", run_id, self.provider_id)
        return False

    async def cleanup(self, run_id: str) -> None:
        """
        Optional cleanup hook called after execution completes (e.g. closing remote sessions,
        releasing container instances, removing temporary artifacts).
        """
        pass

    def is_configured(self) -> bool:
        """
        Checks whether the provider has the necessary configuration / credentials.
        For Local execution, this is always True.
        """
        return True
