"""Unit tests for Agentic Execution Provider Selection and Dynamic Orchestration."""

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

if "app.services" not in sys.modules:
    dummy_services = types.ModuleType("app.services")
    dummy_services.__path__ = [os.path.join(BACKEND_DIR, "app", "services")]
    sys.modules["app.services"] = dummy_services

from app.services.capability_orchestrator import CapabilityOrchestrator
from app.services.execution_providers.registry import execution_registry
from app.services.execution_providers.sauce_labs_provider import SauceLabsExecutionProvider
from app.services.execution_providers.lambdatest_provider import LambdaTestExecutionProvider


class TestAgenticProviderSelection(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = CapabilityOrchestrator()

    def test_default_web_objective_selects_local(self) -> None:
        selection = self.orchestrator.select_execution_provider(
            objective="Run smoke test suite on dashboard web application",
        )
        self.assertEqual(selection.selected_provider_id, "local")
        self.assertFalse(selection.is_cloud_grid)
        self.assertEqual(selection.recommended_browser, "chromium")
        self.assertIn("Local Playwright Runner", selection.rationale)

    def test_safari_objective_selects_webkit(self) -> None:
        selection = self.orchestrator.select_execution_provider(
            objective="Verify shopping cart layout on Safari browser",
        )
        self.assertEqual(selection.recommended_browser, "webkit")

    def test_firefox_objective_selects_firefox(self) -> None:
        selection = self.orchestrator.select_execution_provider(
            objective="Verify form accessibility on Firefox",
        )
        self.assertEqual(selection.recommended_browser, "firefox")

    def test_mobile_unconfigured_falls_back_to_local_with_emulation(self) -> None:
        # In default testing environment, cloud credentials are empty
        selection = self.orchestrator.select_execution_provider(
            objective="Test checkout flow on iPad Safari",
        )
        self.assertEqual(selection.selected_provider_id, "local")
        self.assertIn("falling back", selection.rationale.lower())
        self.assertTrue(selection.provider_config.get("emulate_mobile"))

    def test_mobile_with_configured_lambdatest(self) -> None:
        # Register a mock configured LambdaTest provider
        configured_lt = LambdaTestExecutionProvider(username="valid_user", access_key="valid_key")
        execution_registry.register(configured_lt)

        try:
            selection = self.orchestrator.select_execution_provider(
                objective="Execute mobile test on iPhone 15 real device",
            )
            self.assertEqual(selection.selected_provider_id, "lambdatest")
            self.assertTrue(selection.is_cloud_grid)
            self.assertEqual(selection.recommended_platform, "mobile")
        finally:
            # Restore unconfigured instance
            execution_registry.register(LambdaTestExecutionProvider())

    def test_mobile_with_configured_sauce_labs(self) -> None:
        # Register a mock configured Sauce Labs provider
        configured_sauce = SauceLabsExecutionProvider(username="sauce_user", access_key="sauce_key")
        execution_registry.register(configured_sauce)

        try:
            selection = self.orchestrator.select_execution_provider(
                objective="Run test suite on real Android device in cloud farm",
                requested_provider="sauce_labs",
            )
            self.assertEqual(selection.selected_provider_id, "sauce_labs")
            self.assertTrue(selection.is_cloud_grid)
        finally:
            execution_registry.register(SauceLabsExecutionProvider())

    def test_containerized_objective_selects_container(self) -> None:
        selection = self.orchestrator.select_execution_provider(
            objective="Execute tests inside isolated Docker container",
        )
        self.assertEqual(selection.selected_provider_id, "docker")
        self.assertIn("ephemeral containerized", selection.rationale)

    def test_plan_objective_integrates_execution_step(self) -> None:
        plan = self.orchestrator.plan_objective(
            objective="Run automated verification on staging environment",
            context={"target_url": "https://staging.example.com"},
        )
        # Verify an execution step is included
        exec_steps = [s for s in plan.steps if s.capability == "TEST_EXECUTION"]
        self.assertGreaterEqual(len(exec_steps), 1)
        step = exec_steps[0]
        self.assertEqual(step.tool_id, "tool.execution.dispatcher")
        self.assertEqual(step.arguments.get("provider"), "local")


if __name__ == "__main__":
    unittest.main()
