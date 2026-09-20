"""Unit tests for Unified Test Management Providers and Registry."""

import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Mock httpx if not present in the environment
if "httpx" not in sys.modules:
    h = types.ModuleType("httpx")
    h.HTTPError = type("HTTPError", (Exception,), {})
    h.RequestError = type("RequestError", (Exception,), {})
    h.AsyncClient = MagicMock()
    h.Client = MagicMock()
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

from app.schemas.universal_quality_model import (
    CanonicalDefect,
    CanonicalExecutionResult,
    CanonicalTestCase,
    CanonicalTestExecution,
    CanonicalTestPlan,
    CanonicalTestRun,
    CanonicalTestSet,
    CanonicalTestStep,
    ExecutionStatus,
)
from app.services.test_management.base import TestManagementError, TestManagementProvider
from app.services.test_management.jira_provider import JiraProvider
from app.services.test_management.qtest_provider import QTestProvider
from app.services.test_management.registry import TestManagementRegistry, test_management_registry
from app.services.test_management.xray_provider import XrayClient, XrayProvider


class FakeConnection:
    def __init__(
        self,
        id: int = 1,
        system: str = "xray",
        name: str = "Test ALM Connection",
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


class TestTestManagementRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = TestManagementRegistry()

    def test_registered_providers(self) -> None:
        systems = self.registry.supported_systems()
        self.assertIn("jira", systems)
        self.assertIn("xray", systems)
        self.assertIn("qtest", systems)

    def test_get_provider_success(self) -> None:
        xray_conn = FakeConnection(system="xray")
        jira_conn = FakeConnection(system="jira", base_url="https://company.atlassian.net")
        qtest_conn = FakeConnection(system="qtest", base_url="https://company.qtestnet.com")

        xray = self.registry.get_provider(xray_conn, "token-1")
        self.assertIsInstance(xray, XrayProvider)
        jira = self.registry.get_provider(jira_conn, "token-2")
        self.assertIsInstance(jira, JiraProvider)
        qtest = self.registry.get_provider(qtest_conn, "token-3")
        self.assertIsInstance(qtest, QTestProvider)

    def test_get_unsupported_provider_raises(self) -> None:
        unsupported = FakeConnection(system="unsupported_alm")
        with self.assertRaises(TestManagementError):
            self.registry.get_provider(unsupported, "token")

    def test_global_singleton_registry(self) -> None:
        self.assertIn("xray", test_management_registry.supported_systems())


class TestXrayProvider(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.conn = FakeConnection(system="xray", project_key="QA")
        self.provider = XrayProvider(self.conn, "test-secret")

    def test_capabilities(self) -> None:
        caps = self.provider.get_capabilities()
        self.assertTrue(caps["TEST_CRUD"])
        self.assertTrue(caps["TEST_PLANS"])
        self.assertTrue(caps["TEST_SETS"])
        self.assertTrue(caps["TEST_EXECUTIONS"])
        self.assertTrue(caps["RESULT_IMPORT"])
        self.assertTrue(caps["DEFECT_LINKAGE"])
        self.assertTrue(caps["REQUIREMENTS"])

    async def test_create_and_get_test_case(self) -> None:
        with patch.object(self.provider.client, "xray_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "key": "QA-101",
                "id": "12345",
                "fields": {
                    "summary": "MFA prompt validation",
                    "description": "Ensure OTP modal appears",
                    "status": {"name": "Approved"},
                },
                "xrayFields": {
                    "steps": [{"action": "Enter password", "result": "Prompt rendered"}],
                },
            }
            case = CanonicalTestCase(
                id="case-1",
                application_id="app-1",
                title="MFA prompt validation",
                description="Ensure OTP modal appears",
                steps=[CanonicalTestStep(step_number=1, action="Enter password", expected_result="Prompt rendered")],
            )
            created = await self.provider.create_test_case(case)
            self.assertEqual(created.id, "case-xray-QA-101")
            self.assertEqual(created.title, "MFA prompt validation")

            fetched = await self.provider.get_test_case("QA-101")
            self.assertEqual(fetched.id, "case-xray-QA-101")
            self.assertEqual(fetched.title, "MFA prompt validation")

    async def test_create_test_plan(self) -> None:
        with patch.object(self.provider.client, "xray_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "QA-PLAN-1", "id": "2001"}
            plan = CanonicalTestPlan(
                id="plan-local",
                project_id="QA",
                name="Regression Plan v2.7",
                objective="Release quality gate",
            )
            created = await self.provider.create_test_plan(plan)
            self.assertEqual(created.id, "plan-xray-QA-PLAN-1")
            self.assertEqual(created.name, "Regression Plan v2.7")

    async def test_create_test_set(self) -> None:
        with patch.object(self.provider.client, "xray_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "QA-SET-1", "id": "3001"}
            test_set = CanonicalTestSet(
                id="set-local",
                project_id="QA",
                name="Smoke Test Set",
                description="High priority smoke suite",
                case_ids=["case-1", "case-2"],
            )
            created = await self.provider.create_test_set(test_set)
            self.assertEqual(created.id, "set-xray-QA-SET-1")
            self.assertEqual(created.name, "Smoke Test Set")

    async def test_import_execution_results(self) -> None:
        with patch.object(self.provider.client, "xray_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"testExecKey": "QA-EXEC-50", "id": "4001"}
            results = [
                CanonicalExecutionResult(
                    step_number=1,
                    status=ExecutionStatus.PASSED,
                    duration_ms=45.0,
                )
            ]
            exec_res = await self.provider.import_execution_results("QA-EXEC-50", results)
            self.assertIn("testExecKey", exec_res)


class TestJiraProvider(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.conn = FakeConnection(system="jira", project_key="JIRA", base_url="https://jira.company.com")
        self.provider = JiraProvider(self.conn, "jira-token")

    def test_capabilities(self) -> None:
        caps = self.provider.get_capabilities()
        self.assertTrue(caps["TEST_CRUD"])
        self.assertTrue(caps["DEFECT_LINKAGE"])
        self.assertTrue(caps["REQUIREMENTS"])
        self.assertTrue(caps["RELEASES_VERSIONS"])

    async def test_create_and_get_test_case(self) -> None:
        with patch.object(self.provider.client, "_request", new_callable=AsyncMock) as mock_req, \
             patch.object(self.provider.client, "get_issue", new_callable=AsyncMock) as mock_get:
            mock_req.return_value = {"key": "JIRA-200", "id": "5000"}
            mock_get.return_value = {
                "key": "JIRA-200",
                "fields": {
                    "summary": "Jira Native Test Story",
                    "description": "Test specification",
                    "status": {"name": "In Progress"},
                    "labels": ["regression"],
                },
            }
            case = CanonicalTestCase(
                id="case-jira-local",
                application_id="app-1",
                title="Jira Native Test Story",
                description="Test specification",
                steps=[],
            )
            created = await self.provider.create_test_case(case)
            self.assertEqual(created.id, "case-jira-JIRA-200")

            fetched = await self.provider.get_test_case("JIRA-200")
            self.assertEqual(fetched.id, "case-jira-JIRA-200")
            self.assertEqual(fetched.title, "Jira Native Test Story")


class TestQTestProvider(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.conn = FakeConnection(system="qtest", project_id="999", base_url="https://company.qtestnet.com")
        self.provider = QTestProvider(self.conn, "qtest-token")

    def test_capabilities(self) -> None:
        caps = self.provider.get_capabilities()
        self.assertTrue(caps["TEST_CRUD"])
        self.assertTrue(caps["TEST_PLANS"])
        self.assertTrue(caps["TEST_SETS"])
        self.assertTrue(caps["TEST_EXECUTIONS"])
        self.assertTrue(caps["DEFECT_LINKAGE"])

    async def test_create_and_get_test_case(self) -> None:
        with patch.object(self.provider.client, "export_test_case", new_callable=AsyncMock) as mock_export, \
             patch.object(self.provider.client, "_project_id", new_callable=AsyncMock) as mock_pid, \
             patch.object(self.provider.client, "_request", new_callable=AsyncMock) as mock_req:
            mock_export.return_value = {"id": 8888, "test_case_id": 8888}
            mock_pid.return_value = "999"
            mock_req.return_value = {
                "id": 8888,
                "name": "qTest Payment Verification",
                "description": "Ensure stripe checkout functions",
                "test_steps": [{"description": "Click pay", "expected_result": "200 Success"}],
            }
            case = CanonicalTestCase(
                id="case-qt-local",
                application_id="app-1",
                title="qTest Payment Verification",
                description="Ensure stripe checkout functions",
                steps=[CanonicalTestStep(step_number=1, action="Click pay", expected_result="200 Success")],
            )
            created = await self.provider.create_test_case(case)
            self.assertEqual(created.id, "case-qtest-8888")

            fetched = await self.provider.get_test_case("8888")
            self.assertEqual(fetched.id, "case-qtest-8888")
            self.assertEqual(fetched.title, "qTest Payment Verification")


if __name__ == "__main__":
    unittest.main()
