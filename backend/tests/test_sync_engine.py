"""Unit tests for the Unified Bidirectional Sync Engine."""

import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Mock httpx if not present in the environment
if "httpx" not in sys.modules:
    h = types.ModuleType("httpx")
    h.HTTPError = type("HTTPError", (Exception,), {})
    h.RequestError = type("RequestError", (Exception,), {})
    h.AsyncClient = object
    h.Client = object
    sys.modules["httpx"] = h

if "app.models" not in sys.modules:
    dummy_models = types.ModuleType("app.models")
    dummy_models.__path__ = [os.path.join(BACKEND_DIR, "app", "models")]
    sys.modules["app.models"] = dummy_models

if "app.models.integration_connection" not in sys.modules:
    dummy_ic = types.ModuleType("app.models.integration_connection")
    class IntegrationConnection:
        pass
    dummy_ic.IntegrationConnection = IntegrationConnection
    sys.modules["app.models.integration_connection"] = dummy_ic

if "app.schemas" not in sys.modules:
    dummy_schemas = types.ModuleType("app.schemas")
    dummy_schemas.__path__ = [os.path.join(BACKEND_DIR, "app", "schemas")]
    sys.modules["app.schemas"] = dummy_schemas

if "app.services" not in sys.modules:
    dummy_services = types.ModuleType("app.services")
    dummy_services.__path__ = [os.path.join(BACKEND_DIR, "app", "services")]
    sys.modules["app.services"] = dummy_services

from app.schemas.integration import SyncExecutionRequest
from app.schemas.universal_quality_model import (
    CanonicalDefect,
    CanonicalRequirement,
    CanonicalTestCase,
    CanonicalTestStep,
    DefectSeverity,
    DefectStatus,
    RequirementPriority,
    SyncJobStatus,
)
from app.services.test_management.base import TestManagementProvider
from app.services.test_management.registry import test_management_registry
from app.services.test_management.sync_engine import SyncEngine, sync_engine


class FakeConnection:
    def __init__(
        self,
        id: int = 10,
        system: str = "xray",
        name: str = "Sync Test Connection",
        base_url: str = "https://xray.cloud.getxray.app",
        project_key: str = "QA",
        project_id: str = "100",
        auth_type: str = "oauth2_client_credentials",
        username: str = "client_id_123",
        created_by: int = 1,
    ):
        self.id = id
        self.system = system
        self.name = name
        self.base_url = base_url
        self.project_key = project_key
        self.project_name = "QA Project"
        self.project_id = project_id
        self.auth_type = auth_type
        self.username = username
        self.created_by = created_by


class TestSyncEngine(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = SyncEngine(batch_size=10, concurrency_limit=3)
        self.conn = FakeConnection()

    async def test_execute_sync_dry_run(self) -> None:
        mock_provider = AsyncMock(spec=TestManagementProvider)
        mock_provider.list_requirements.return_value = (
            [
                CanonicalRequirement(
                    id="req-1",
                    project_id="QA",
                    title="Req 1",
                    description="",
                    priority=RequirementPriority.HIGH,
                )
            ],
            None,
        )
        mock_provider.search_test_cases.return_value = (
            [
                CanonicalTestCase(
                    id="case-ext-1",
                    application_id="QA",
                    title="External Case 1",
                    steps=[],
                )
            ],
            None,
        )

        with patch.object(test_management_registry, "get_provider", return_value=mock_provider):
            req = SyncExecutionRequest(
                sync_type="dry_run",
                entities=["requirements", "test_cases"],
                dry_run=True,
            )
            response = await self.engine.execute_sync(self.conn, "secret", req)

            self.assertEqual(response.connection_id, self.conn.id)
            self.assertEqual(response.system, self.conn.system)
            self.assertEqual(response.total_items, 2)
            self.assertEqual(response.skipped_items, 2)
            self.assertEqual(response.synced_items, 0)
            self.assertEqual(response.failed_items, 0)
            self.assertEqual(response.status, SyncJobStatus.COMPLETED.value)
            self.assertIsNotNone(response.checkpoint)

    async def test_execute_sync_bidirectional_success(self) -> None:
        mock_provider = AsyncMock(spec=TestManagementProvider)
        mock_provider.list_requirements.return_value = ([], None)
        mock_provider.search_test_cases.return_value = (
            [
                CanonicalTestCase(
                    id="case-ext-1",
                    application_id="QA",
                    title="External Test Case 1",
                    steps=[],
                )
            ],
            None,
        )
        mock_provider.create_test_case.return_value = CanonicalTestCase(
            id="case-synced-2",
            application_id="QA",
            title="Local Test Case 2",
            steps=[],
        )
        mock_provider.create_defect.return_value = CanonicalDefect(
            id="def-synced-1",
            project_id="QA",
            title="Local Defect 1",
            description="",
            severity=DefectSeverity.MAJOR,
            status=DefectStatus.OPEN,
        )

        local_cases = [
            CanonicalTestCase(
                id="case-local-2",
                application_id="QA",
                title="Local Test Case 2",
                steps=[],
            )
        ]
        local_defects = [
            CanonicalDefect(
                id="def-local-1",
                project_id="QA",
                title="Local Defect 1",
                description="",
                severity=DefectSeverity.MAJOR,
                status=DefectStatus.OPEN,
            )
        ]

        with patch.object(test_management_registry, "get_provider", return_value=mock_provider):
            req = SyncExecutionRequest(
                sync_type="full",
                entities=["test_cases", "defects"],
                dry_run=False,
            )
            response = await self.engine.execute_sync(
                self.conn,
                "secret",
                req,
                local_test_cases=local_cases,
                local_defects=local_defects,
            )

            self.assertEqual(response.total_items, 3)  # 1 imported case + 1 exported case + 1 exported defect
            self.assertEqual(response.synced_items, 3)
            self.assertEqual(response.failed_items, 0)
            self.assertEqual(response.status, SyncJobStatus.COMPLETED.value)
            self.assertGreater(response.duration_ms, 0)

    async def test_execute_sync_partial_failure(self) -> None:
        mock_provider = AsyncMock(spec=TestManagementProvider)
        mock_provider.search_test_cases.return_value = (
            [
                CanonicalTestCase(id="ext-1", application_id="QA", title="Case 1", steps=[]),
            ],
            None,
        )
        # Exporting local case raises an error
        mock_provider.create_test_case.side_effect = RuntimeError("External ALM timeout")

        local_cases = [
            CanonicalTestCase(id="loc-1", application_id="QA", title="Failing Case", steps=[]),
        ]

        with patch.object(test_management_registry, "get_provider", return_value=mock_provider):
            req = SyncExecutionRequest(
                sync_type="incremental",
                entities=["test_cases"],
                dry_run=False,
            )
            response = await self.engine.execute_sync(
                self.conn,
                "secret",
                req,
                local_test_cases=local_cases,
            )

            self.assertEqual(response.total_items, 2)
            self.assertEqual(response.synced_items, 1)  # external imported
            self.assertEqual(response.failed_items, 1)  # local failed to export
            self.assertEqual(response.status, SyncJobStatus.PARTIALLY_COMPLETED.value)
            self.assertEqual(len(response.errors), 1)
            self.assertIn("External ALM timeout", response.errors[0]["error"])

    def test_global_singleton_sync_engine(self) -> None:
        self.assertIsNotNone(sync_engine)
        self.assertIsInstance(sync_engine, SyncEngine)


if __name__ == "__main__":
    unittest.main()
