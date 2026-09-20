"""Unit tests for the SkyWatch Universal Quality Model and Adapters."""

import os
import sys
import types
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if "app.schemas" not in sys.modules:
    dummy_schemas = types.ModuleType("app.schemas")
    dummy_schemas.__path__ = [os.path.join(BACKEND_DIR, "app", "schemas")]
    sys.modules["app.schemas"] = dummy_schemas

from app.schemas.universal_quality_model import (
    CanonicalDefect,
    CanonicalOrganization,
    CanonicalRequirement,
    CanonicalTestCase,
    CanonicalTestExecution,
    CanonicalTestRun,
    CanonicalTestSet,
    CanonicalTestStep,
    DefectSeverity,
    DefectStatus,
    ExecutionStatus,
    RequirementPriority,
    UniversalModelAdapter,
)


class TestUniversalQualityModel(unittest.TestCase):
    def test_canonical_test_case_creation(self) -> None:
        case = CanonicalTestCase(
            id="case-101",
            application_id="app-1",
            title="Verify user checkout with credit card",
            steps=[
                CanonicalTestStep(
                    step_number=1,
                    action="Navigate to checkout page",
                    expected_result="Checkout page rendered",
                ),
                CanonicalTestStep(
                    step_number=2,
                    action="Click submit order",
                    expected_result="Order confirmation displayed",
                    is_assertion=True,
                ),
            ],
            priority=RequirementPriority.CRITICAL,
        )
        self.assertEqual(case.id, "case-101")
        self.assertEqual(len(case.steps), 2)
        self.assertTrue(case.steps[1].is_assertion)

    def test_jira_issue_to_canonical_requirement(self) -> None:
        jira_payload = {
            "key": "PROJ-452",
            "fields": {
                "summary": "Implement single sign-on via SAML",
                "description": "All corporate users must be able to authenticate with Okta SAML.",
                "priority": {"name": "High"},
                "labels": ["security", "auth"],
            },
        }
        req = UniversalModelAdapter.jira_issue_to_canonical_requirement(jira_payload, project_id="proj-1")
        self.assertEqual(req.id, "req-jira-PROJ-452")
        self.assertEqual(req.external_id, "PROJ-452")
        self.assertEqual(req.priority, RequirementPriority.HIGH)
        self.assertIn("security", req.tags)

    def test_canonical_defect_to_jira_payload(self) -> None:
        defect = CanonicalDefect(
            id="def-1",
            project_id="proj-1",
            title="Cart calculation discrepancy on multi-item discounts",
            description="Total price does not reflect 15% promotional discount.",
            severity=DefectSeverity.CRITICAL,
            status=DefectStatus.OPEN,
        )
        payload = UniversalModelAdapter.canonical_defect_to_jira_payload(defect, project_key="PROJ")
        self.assertEqual(payload["fields"]["project"]["key"], "PROJ")
        self.assertEqual(payload["fields"]["summary"], defect.title)
        self.assertEqual(payload["fields"]["priority"]["name"], "Highest")

    def test_qtest_test_case_to_canonical(self) -> None:
        qtest_payload = {
            "id": 98765,
            "name": "Search for agricultural products",
            "description": "Validate keyword search returns in-stock items.",
            "test_steps": [
                {"description": "Enter tractor in search bar", "expected_result": "Dropdown shows suggestions"},
                {"description": "Press Enter", "expected_result": "Search results list displayed"},
            ],
        }
        case = UniversalModelAdapter.qtest_test_case_to_canonical(qtest_payload, app_id="app-42")
        self.assertEqual(case.id, "case-qtest-98765")
        self.assertEqual(case.title, "Search for agricultural products")
        self.assertEqual(len(case.steps), 2)

    def test_canonical_test_set_creation(self) -> None:
        test_set = CanonicalTestSet(
            id="set-101",
            project_id="proj-1",
            name="Smoke Regression Suite",
            description="High priority smoke regression tests",
            case_ids=["case-1", "case-2", "case-3"],
            environment="staging",
        )
        self.assertEqual(test_set.id, "set-101")
        self.assertEqual(len(test_set.case_ids), 3)

    def test_xray_test_to_canonical_test_case(self) -> None:
        xray_payload = {
            "key": "QA-1001",
            "summary": "Verify Multi-Factor Authentication prompt",
            "description": "Ensure OTP modal renders upon valid credentials.",
            "testType": "Manual",
            "steps": [
                {"action": "Submit username and password", "result": "OTP modal rendered"},
                {"action": "Enter 6-digit OTP code", "result": "Dashboard rendered"},
            ],
            "status": "ready",
        }
        case = UniversalModelAdapter.xray_test_to_canonical_test_case(xray_payload, app_id="app-sec")
        self.assertEqual(case.id, "case-xray-QA-1001")
        self.assertEqual(case.title, "Verify Multi-Factor Authentication prompt")
        self.assertEqual(len(case.steps), 2)
        self.assertEqual(case.status, "ready")

    def test_canonical_test_case_to_xray_payload(self) -> None:
        case = CanonicalTestCase(
            id="case-200",
            application_id="app-1",
            title="Checkout cart total calculation",
            description="Verify taxes and discounts are applied",
            steps=[
                CanonicalTestStep(step_number=1, action="Add items to cart", expected_result="Cart badge shows 2"),
                CanonicalTestStep(step_number=2, action="Proceed to checkout", expected_result="Tax line added", is_assertion=True),
            ],
        )
        xray = UniversalModelAdapter.canonical_test_case_to_xray_payload(case, project_key="FIN")
        self.assertEqual(xray["fields"]["project"]["key"], "FIN")
        self.assertEqual(xray["fields"]["summary"], case.title)
        self.assertEqual(len(xray["xrayFields"]["steps"]), 2)
        self.assertEqual(xray["xrayFields"]["steps"][0]["action"], "Add items to cart")

    def test_canonical_execution_to_xray_result(self) -> None:
        execution = CanonicalTestExecution(
            id="exec-55",
            run_id="run-1",
            case_id="case-xray-QA-1001",
            status=ExecutionStatus.PASSED,
            duration_ms=1250,
        )
        result = UniversalModelAdapter.canonical_execution_to_xray_result(execution, test_key="QA-1001")
        self.assertEqual(result["testKey"], "QA-1001")
        self.assertEqual(result["status"], "PASSED")

    def test_xray_test_plan_to_canonical(self) -> None:
        plan_payload = {
            "key": "QA-P1",
            "summary": "Release 2.7 Quality Gate Plan",
            "description": "Validation for v2.7 release candidate",
        }
        plan = UniversalModelAdapter.xray_test_plan_to_canonical(plan_payload, project_id="proj-1")
        self.assertEqual(plan.id, "plan-xray-QA-P1")
        self.assertEqual(plan.name, "Release 2.7 Quality Gate Plan")
        self.assertEqual(plan.project_id, "proj-1")


if __name__ == "__main__":
    unittest.main()
