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


if __name__ == "__main__":
    unittest.main()
