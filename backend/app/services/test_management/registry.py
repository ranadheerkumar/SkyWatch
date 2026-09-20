"""SkyWatch Central Test Management Provider Registry.

Resolves, instantiates, and manages test management provider adapters
(Xray, Jira, Tricentis qTest) across multiple active connections.
"""

from __future__ import annotations

import logging
from typing import Type

from app.models.integration_connection import IntegrationConnection
from app.services.test_management.base import TestManagementError, TestManagementProvider
from app.services.test_management.jira_provider import JiraProvider
from app.services.test_management.qtest_provider import QTestProvider
from app.services.test_management.xray_provider import XrayProvider

logger = logging.getLogger("skywatch.test_management.registry")


class TestManagementRegistry:
    """Registry mapping system identifiers to TestManagementProvider implementations."""

    def __init__(self) -> None:
        self._provider_classes: dict[str, Type[TestManagementProvider]] = {
            "xray": XrayProvider,
            "jira": JiraProvider,
            "qtest": QTestProvider,
        }

    def register(self, system: str, provider_cls: Type[TestManagementProvider]) -> None:
        """Register a new or custom test management provider."""
        self._provider_classes[system.lower()] = provider_cls
        logger.info(f"Registered test management provider for system '{system}'")

    def get_provider(
        self, connection: IntegrationConnection, credential: str
    ) -> TestManagementProvider:
        """Instantiate and return the appropriate provider adapter for a connection."""
        system = connection.system.lower()
        provider_cls = self._provider_classes.get(system)
        if not provider_cls:
            raise TestManagementError(
                f"Unsupported test management system '{system}'. Registered systems: {list(self._provider_classes.keys())}"
            )
        return provider_cls(connection, credential)

    def supported_systems(self) -> list[str]:
        return list(self._provider_classes.keys())


# Global singleton registry
test_management_registry = TestManagementRegistry()
