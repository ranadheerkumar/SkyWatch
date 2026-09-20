"""Unit tests for the SkyWatch Dynamic Capability Orchestrator."""

import asyncio
import os
import sys
import types
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if "app.services" not in sys.modules:
    dummy_services = types.ModuleType("app.services")
    dummy_services.__path__ = [os.path.join(BACKEND_DIR, "app", "services")]
    sys.modules["app.services"] = dummy_services

from app.core.capabilities import PlatformCapability
from app.services.capability_orchestrator import CapabilityOrchestrator, default_capability_orchestrator


class TestCapabilityOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = CapabilityOrchestrator()

    def test_plan_api_objective(self) -> None:
        plan = self.orchestrator.plan_objective(
            objective="Validate REST API endpoint responses and schema resilience",
            application_id=5,
        )
        self.assertIsNotNone(plan.plan_id)
        self.assertIn(PlatformCapability.API_AUTOMATION.value, plan.capabilities_discovered)
        self.assertIn("tool.api.rest", plan.tools_selected)
        self.assertGreaterEqual(len(plan.steps), 2)  # API check + Reporting

    def test_plan_ui_script_and_git_objective(self) -> None:
        plan = self.orchestrator.plan_objective(
            objective="Generate Cypress automation scripts and commit to git repo",
            application_id=10,
            context={"framework": "cypress", "git_repo": "owner/repo"},
        )
        self.assertIn("tool.generator.script", plan.tools_selected)
        self.assertIn("tool.vcs.github", plan.tools_selected)
        tool_ids = [s.tool_id for s in plan.steps]
        self.assertIn("tool.generator.script", tool_ids)
        self.assertIn("tool.vcs.github", tool_ids)

    def test_plan_execution(self) -> None:
        plan = self.orchestrator.plan_objective(
            objective="Synthesize test data and compile quality report",
            application_id=1,
        )
        executed_plan = asyncio.run(self.orchestrator.execute_plan(plan))
        self.assertEqual(executed_plan.status, "completed")
        self.assertTrue(all(s.status == "completed" for s in executed_plan.steps))


if __name__ == "__main__":
    unittest.main()
