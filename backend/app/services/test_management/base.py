"""SkyWatch Unified Test Management Provider Base Contract.

Defines the platform-neutral interface for all enterprise Test Management platforms
(Xray, Jira, Tricentis qTest, and future integrations) per Section 16 of the Master Charter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

try:
    from app.models.integration_connection import IntegrationConnection
except ImportError:
    IntegrationConnection = Any  # type: ignore[assignment,misc]
from app.schemas.universal_quality_model import (
    CanonicalDefect,
    CanonicalExecutionResult,
    CanonicalRequirement,
    CanonicalTestCase,
    CanonicalTestExecution,
    CanonicalTestPlan,
    CanonicalTestRun,
    CanonicalTestSet,
)
from app.services.integrations import IntegrationTestResult


class TestManagementError(RuntimeError):
    """Raised when a Test Management provider operation fails."""
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TestManagementProvider(ABC):
    """Abstract base interface for all enterprise test management systems."""

    def __init__(self, connection: IntegrationConnection, credential: str) -> None:
        self.connection = connection
        self.credential = credential

    @abstractmethod
    def get_capabilities(self) -> dict[str, bool]:
        """Return boolean feature matrix of supported capabilities."""
        pass

    @abstractmethod
    async def test_connection(self) -> IntegrationTestResult:
        """Validate credentials, permissions, and network connectivity."""
        pass

    # =========================================================================
    # Test Cases (CRUD & Search)
    # =========================================================================

    @abstractmethod
    async def create_test_case(self, case: CanonicalTestCase) -> CanonicalTestCase:
        """Create a new test case in the external system."""
        pass

    @abstractmethod
    async def get_test_case(self, external_id: str) -> CanonicalTestCase:
        """Retrieve a test case by external key or ID."""
        pass

    @abstractmethod
    async def update_test_case(self, external_id: str, case: CanonicalTestCase) -> CanonicalTestCase:
        """Update an existing test case."""
        pass

    @abstractmethod
    async def search_test_cases(
        self, query: str = "", *, page: int = 1, page_size: int = 50
    ) -> tuple[list[CanonicalTestCase], int]:
        """Search test cases matching criteria with pagination."""
        pass

    @abstractmethod
    async def archive_test_case(self, external_id: str) -> bool:
        """Archive, deactivate, or delete a test case per provider capability."""
        pass

    # =========================================================================
    # Test Plans & Test Sets
    # =========================================================================

    @abstractmethod
    async def create_test_plan(self, plan: CanonicalTestPlan) -> CanonicalTestPlan:
        """Create a high-level test plan."""
        pass

    @abstractmethod
    async def get_test_plan(self, external_id: str) -> CanonicalTestPlan:
        """Retrieve test plan details and associated tests."""
        pass

    @abstractmethod
    async def associate_tests_to_plan(self, plan_external_id: str, test_keys: list[str]) -> bool:
        """Link test cases to an existing test plan."""
        pass

    @abstractmethod
    async def create_test_set(self, test_set: CanonicalTestSet) -> CanonicalTestSet:
        """Create a test set grouping."""
        pass

    @abstractmethod
    async def associate_tests_to_set(self, set_external_id: str, test_keys: list[str]) -> bool:
        """Link test cases to a test set."""
        pass

    # =========================================================================
    # Executions & Result Ingestion
    # =========================================================================

    @abstractmethod
    async def create_test_execution(self, run: CanonicalTestRun) -> str:
        """Create a test execution run container in the external system."""
        pass

    @abstractmethod
    async def import_execution_results(
        self, execution_key: str, results: list[CanonicalExecutionResult], metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Publish test execution results into the external platform."""
        pass

    # =========================================================================
    # Defects & Requirements
    # =========================================================================

    @abstractmethod
    async def create_defect(self, defect: CanonicalDefect) -> CanonicalDefect:
        """Create a defect or bug record."""
        pass

    @abstractmethod
    async def link_defect(self, defect_external_id: str, test_key_or_run_id: str) -> bool:
        """Link a defect to a test case or execution."""
        pass

    @abstractmethod
    async def list_requirements(
        self, *, page: int = 1, page_size: int = 50
    ) -> tuple[list[CanonicalRequirement], int | None]:
        """Retrieve user stories or requirements."""
        pass

    # =========================================================================
    # Evidence & Attachments
    # =========================================================================

    @abstractmethod
    async def upload_evidence(
        self, external_id: str, file_name: str, content: bytes, content_type: str
    ) -> dict[str, Any]:
        """Attach binary evidence (screenshots, videos, logs) to an entity."""
        pass
