"""Comprehensive unit tests for the Unified Reporting Engine and ALM Integrations.

Tests multi-source aggregation across SkyWatch, Jira, Xray, and qTest,
including automated classification, defect aging, traceability matrices,
gap detection, provider breakdown, and export formats.
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

class ColumnMock:
    def __init__(self, name: str = "") -> None:
        self.name = name

    def __eq__(self, other: Any) -> ColumnMock:
        return self

    def __ne__(self, other: Any) -> ColumnMock:
        return self

    def __ge__(self, other: Any) -> ColumnMock:
        return self

    def __le__(self, other: Any) -> ColumnMock:
        return self

    def __gt__(self, other: Any) -> ColumnMock:
        return self

    def __lt__(self, other: Any) -> ColumnMock:
        return self

    def desc(self) -> ColumnMock:
        return self

    def asc(self) -> ColumnMock:
        return self


class ModelMeta(type):
    def __getattr__(cls, name: str) -> ColumnMock:
        return ColumnMock(name)


class DummyModelBase(metaclass=ModelMeta):
    pass


# Package module isolation to prevent loading full DB drivers in unit tests
if "app.models" not in sys.modules:
    dummy_models = types.ModuleType("app.models")
    dummy_models.__path__ = [os.path.join(BACKEND_DIR, "app", "models")]
    sys.modules["app.models"] = dummy_models

if "app.services" not in sys.modules:
    dummy_services = types.ModuleType("app.services")
    dummy_services.__path__ = [os.path.join(BACKEND_DIR, "app", "services")]
    sys.modules["app.services"] = dummy_services

if "app.schemas" not in sys.modules:
    dummy_schemas = types.ModuleType("app.schemas")
    dummy_schemas.__path__ = [os.path.join(BACKEND_DIR, "app", "schemas")]
    sys.modules["app.schemas"] = dummy_schemas

for mod_name, cls_name in [
    ("app.models.application", "Application"),
    ("app.models.defect", "Defect"),
    ("app.models.test_case", "TestCase"),
    ("app.models.test_run", "TestRun"),
    ("app.models.user", "User"),
    ("app.models.external_issue_link", "ExternalIssueLink"),
    ("app.models.integration_connection", "IntegrationConnection"),
]:
    m = types.ModuleType(mod_name)
    cls_type = type(cls_name, (DummyModelBase,), {})
    setattr(m, cls_name, cls_type)
    sys.modules[mod_name] = m

from app.schemas.universal_quality_model import (
    AutomationClassification,
    TraceabilityGapType,
)
from app.services.report_service import ReportService, UnifiedReportingEngine


class MockTestCase:
    def __init__(self, id: int, title: str, app_id: int = 1, status: str = "ready", automation_status: str = "automated", priority: str = "high", tags: list[str] | None = None, created_by: int = 1):
        self.id = id
        self.title = title
        self.description = f"Description for {title}"
        self.application_id = app_id
        self.status = status
        self.automation_status = automation_status
        self.priority = priority
        self.tags = tags or []
        self.created_by = created_by


class MockTestRun:
    def __init__(self, id: str, app_id: int = 1, status: str = "passed", provider: str = "local", duration_ms: float = 1200.0, created_at: datetime | None = None, created_by: int = 1):
        self.id = id
        self.application_id = app_id
        self.status = status
        self.result = {"provider": provider, "duration_ms": duration_ms, "title": f"Run {id}"}
        self.created_at = created_at or datetime.now(timezone.utc)
        self.finished_at = self.created_at
        self.created_by = created_by


class MockDefect:
    def __init__(self, id: int, title: str, app_id: int = 1, severity: str = "high", status: str = "open", created_at: datetime | None = None, created_by: int = 1):
        self.id = id
        self.title = title
        self.application_id = app_id
        self.severity = severity
        self.priority = severity
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)
        self.created_by = created_by


class MockExternalIssueLink:
    def __init__(self, system: str, external_key: str, external_url: str, test_case_id: int | None = None, run_id: str | None = None, defect_id: int | None = None, created_by: int = 1):
        self.system = system
        self.external_key = external_key
        self.external_url = external_url
        self.test_case_id = test_case_id
        self.run_id = run_id
        self.defect_id = defect_id
        self.created_by = created_by


class MockIntegrationConnection:
    def __init__(self, system: str, name: str, status: str = "active", project_key: str = "XSP", username: str = "client123", created_by: int = 1):
        self.id = 1
        self.system = system
        self.name = name
        self.status = status
        self.project_key = project_key
        self.username = username
        self.created_by = created_by
        self.updated_at = datetime.now(timezone.utc)
        self.last_tested_at = datetime.now(timezone.utc)
        self.created_at = datetime.now(timezone.utc)
        self.last_test_latency_ms = 95.0
        self.last_test_status = "passed"
        self.last_test_message = "OK"
        self.base_url = "https://xray.cloud.getxray.app"
        self.last_metadata = {}


class MockDbQuery:
    def __init__(self, data: list[Any]):
        self._data = data

    def filter(self, *args: Any, **kwargs: Any) -> MockDbQuery:
        return self

    def order_by(self, *args: Any, **kwargs: Any) -> MockDbQuery:
        return self

    def limit(self, count: int) -> MockDbQuery:
        return MockDbQuery(self._data[:count])

    def all(self) -> list[Any]:
        return list(self._data)

    def count(self) -> int:
        return len(self._data)

    def first(self) -> Any:
        return self._data[0] if self._data else None


class MockDbSession:
    def __init__(self, cases: list[Any], runs: list[Any], defects: list[Any], links: list[Any], conns: list[Any]):
        self.cases = cases
        self.runs = runs
        self.defects = defects
        self.links = links
        self.conns = conns

    def query(self, model: Any) -> MockDbQuery:
        name = getattr(model, "__name__", str(model))
        if "TestCase" in name:
            return MockDbQuery(self.cases)
        if "TestRun" in name:
            return MockDbQuery(self.runs)
        if "Defect" in name:
            return MockDbQuery(self.defects)
        if "ExternalIssueLink" in name:
            return MockDbQuery(self.links)
        if "IntegrationConnection" in name:
            return MockDbQuery(self.conns)
        return MockDbQuery([])

    def get(self, model: Any, ident: Any) -> Any:
        m = MagicMock()
        m.id = ident
        m.name = "Test Application"
        m.target = "https://example.com"
        return m


class TestUnifiedReportingEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = UnifiedReportingEngine()
        self.engine._cache.clear()

        # Build sample dataset
        self.cases = [
            MockTestCase(1, "Verify Login Success", app_id=1, status="ready", automation_status="automated"),
            MockTestCase(2, "Verify Checkout Flow", app_id=1, status="ready", automation_status="manual", priority="critical"),
            MockTestCase(3, "Verify Promo Code", app_id=1, status="draft", automation_status="partially_automated"),
        ]

        now = datetime.now(timezone.utc)
        self.runs = [
            MockTestRun("run-1", app_id=1, status="passed", provider="local", duration_ms=1100.0, created_at=now),
            MockTestRun("run-2", app_id=1, status="passed", provider="sauce_labs", duration_ms=2500.0, created_at=now),
            MockTestRun("run-3", app_id=1, status="failed", provider="lambdatest", duration_ms=3200.0, created_at=now),
        ]

        self.defects = [
            MockDefect(101, "Cart timeout on checkout", app_id=1, severity="critical", status="open", created_at=now - timedelta(days=2)),
            MockDefect(102, "Typo in footer link", app_id=1, severity="low", status="open", created_at=now - timedelta(days=8)),
            MockDefect(103, "Legacy session leak", app_id=1, severity="medium", status="closed", created_at=now - timedelta(days=20)),
        ]

        self.links = [
            MockExternalIssueLink(system="jira", external_key="JIRA-101", external_url="https://jira.example.com/browse/JIRA-101", test_case_id=1),
            MockExternalIssueLink(system="xray", external_key="XSP-39", external_url="https://xray.cloud.getxray.app", test_case_id=2, run_id="run-2"),
            MockExternalIssueLink(system="jira", external_key="JIRA-DEF-1", external_url="https://jira.example.com/browse/JIRA-DEF-1", defect_id=101),
        ]

        self.conns = [
            MockIntegrationConnection(system="xray", name="Xray Cloud", status="active", project_key="XSP"),
            MockIntegrationConnection(system="jira", name="Atlassian Jira", status="active", project_key="PROJ"),
        ]

        self.db = MockDbSession(self.cases, self.runs, self.defects, self.links, self.conns)

    def test_cache_mechanism(self) -> None:
        self.engine._put_in_cache("test_key", {"val": 42})
        cached = self.engine._get_from_cache("test_key")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["val"], 42)

        # Cache miss
        self.assertIsNone(self.engine._get_from_cache("non_existent"))

    def test_unified_quality_report_metrics(self) -> None:
        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=None):
            report = self.engine.get_unified_quality_report(user_id=1, db=self.db, days=14)
            self.assertIn("summary", report)
            summary = report["summary"]

            self.assertEqual(summary["total_cases"], 3)
            self.assertEqual(summary["total_runs"], 3)
            self.assertEqual(summary["passed_runs"], 2)
            self.assertEqual(summary["failed_runs"], 1)
            self.assertAlmostEqual(summary["pass_rate"], 66.7, places=1)
            self.assertEqual(summary["open_defects"], 2)
            self.assertEqual(summary["critical_defects"], 1)
            self.assertEqual(summary["resolved_defects"], 1)

    def test_automation_classification(self) -> None:
        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=None):
            report = self.engine.get_unified_quality_report(user_id=1, db=self.db, days=14)
            auto_metrics = report["automation_metrics"]

            self.assertEqual(auto_metrics["total_tests"], 3)
            self.assertEqual(auto_metrics["automated_tests"], 1)
            self.assertEqual(auto_metrics["partially_automated_tests"], 1)
            # Case 2 is manual + critical priority -> flagged as automation candidate
            self.assertEqual(auto_metrics["automation_candidates"], 1)
            self.assertAlmostEqual(auto_metrics["automation_coverage_rate"], 33.3, places=1)

    def test_provider_and_source_breakdown(self) -> None:
        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=None):
            report = self.engine.get_unified_quality_report(user_id=1, db=self.db, days=14)
            prov = report["provider_breakdown"]
            self.assertEqual(prov.get("local"), 1)
            self.assertEqual(prov.get("sauce_labs"), 1)
            self.assertEqual(prov.get("lambdatest"), 1)

            source = report["source_breakdown"]
            self.assertGreaterEqual(source.get("skywatch", 0), 1)
            self.assertGreaterEqual(source.get("jira", 0), 1)
            self.assertGreaterEqual(source.get("xray", 0), 1)

    def test_defect_aging_breakdown(self) -> None:
        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=None):
            report = self.engine.get_unified_quality_report(user_id=1, db=self.db, days=14)
            aging = report["defect_metrics"]["aging"]
            # Defect 101 is 2 days old (<3d)
            self.assertEqual(aging["under_3d"], 1)
            # Defect 102 is 8 days old (7_to_14d)
            self.assertEqual(aging["7_to_14d"], 1)

    def test_ai_insights_structure(self) -> None:
        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=None):
            report = self.engine.get_unified_quality_report(user_id=1, db=self.db, days=14)
            insights = report["ai_insights"]
            self.assertIn("facts", insights)
            self.assertIn("analysis", insights)
            self.assertIn("recommendations", insights)
            self.assertTrue(len(insights["facts"]) >= 1)
            self.assertTrue(len(insights["analysis"]) >= 1)
            self.assertTrue(len(insights["recommendations"]) >= 1)

    def test_get_unified_executions(self) -> None:
        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=None):
            execs = self.engine.get_unified_executions(user_id=1, db=self.db)
            self.assertEqual(len(execs), 3)

            first = execs[0]
            self.assertIn("run_id", first)
            self.assertIn("execution_provider", first)
            self.assertIn("status", first)
            self.assertIn("external_references", first)

            # Filter by provider
            sauce_execs = self.engine.get_unified_executions(user_id=1, db=self.db, provider="sauce_labs")
            self.assertEqual(len(sauce_execs), 1)
            self.assertEqual(sauce_execs[0]["execution_provider"], "sauce_labs")

    def test_traceability_matrix_and_gap_detection(self) -> None:
        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=None):
            matrix = self.engine.get_traceability_matrix(user_id=1, db=self.db)
            self.assertTrue(len(matrix) >= 3)

            case1_row = next(r for r in matrix if r["test_id"] == "1")
            self.assertEqual(case1_row["requirement_key"], "JIRA-101")
            self.assertEqual(case1_row["test_source"], "jira")
            self.assertEqual(case1_row["test_automation_status"], "automated")

    def test_integration_health(self) -> None:
        health = self.engine.get_integration_health(user_id=1, db=self.db)
        self.assertEqual(len(health), 4)  # jira, xray, qtest, github

        xray_h = next(h for h in health if h["system"] == "xray")
        self.assertEqual(xray_h["status"], "connected")
        self.assertEqual(xray_h["latency_ms"], 95.0)

        qtest_h = next(h for h in health if h["system"] == "qtest")
        self.assertEqual(qtest_h["status"], "unconfigured")

    def test_export_unified_report(self) -> None:
        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=None):
            json_export = self.engine.export_unified_report(user_id=1, db=self.db, format_type="json")
            self.assertIsInstance(json_export, dict)
            self.assertIn("summary", json_export)

            csv_export = self.engine.export_unified_report(user_id=1, db=self.db, format_type="csv")
            self.assertIsInstance(csv_export, str)
            self.assertIn("Executive Summary", csv_export)
            self.assertIn("Quality Score", csv_export)

            md_export = self.engine.export_unified_report(user_id=1, db=self.db, format_type="markdown")
            self.assertIsInstance(md_export, str)
            self.assertIn("# QA Quality & Release Readiness Report", md_export)

    def test_mock_live_xray_cloud_ingestion(self) -> None:
        mock_gql_payload = {
            "getTestPlans": {
                "total": 1,
                "results": [{
                    "issueId": "100",
                    "jira": {"key": "XSP-99", "summary": "Sprint 5 Plan"},
                    "tests": {"total": 5, "results": [{"issueId": "101"}]},
                }],
            },
            "getTestExecutions": {
                "total": 1,
                "results": [{
                    "issueId": "200",
                    "jira": {"key": "XSP-100", "summary": "Nightly Regression"},
                    "testRuns": {"total": 1, "results": [{"status": {"name": "PASSED"}}]},
                }],
            },
            "getTests": {
                "total": 2,
                "results": [
                    {"issueId": "301", "jira": {"key": "XSP-1", "summary": "Test 1"}, "testType": {"name": "Manual"}},
                    {"issueId": "302", "jira": {"key": "XSP-2", "summary": "Test 2"}, "testType": {"name": "Cucumber"}},
                ],
            },
        }

        with patch.object(self.engine, "_fetch_live_xray_cloud", return_value=mock_gql_payload):
            rep = self.engine.get_unified_quality_report(user_id=1, db=self.db)
            self.assertEqual(len(rep["xray_plans"]), 1)
            self.assertEqual(rep["xray_plans"][0]["plan_key"], "XSP-99")
            self.assertEqual(len(rep["xray_sets"]), 1)


if __name__ == "__main__":
    unittest.main()
