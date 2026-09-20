"""Contract tests verifying all Execution Providers adhere to the unified platform contract."""

import asyncio
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

from app.schemas.canonical_execution import (
    BrowserType,
    CanonicalExecutionRequest,
    CanonicalExecutionResult,
    ProviderCapabilities,
    ProviderHealthStatus,
)
from app.services.execution_providers.base import ExecutionProvider
from app.services.execution_providers.registry import execution_registry


class TestExecutionContract(unittest.TestCase):
    def test_all_providers_implement_contract(self) -> None:
        providers = execution_registry.list_all()
        self.assertGreaterEqual(len(providers), 5)

        for provider in providers:
            self.assertIsInstance(provider, ExecutionProvider)
            self.assertTrue(hasattr(provider, "provider_id"))
            self.assertTrue(hasattr(provider, "name"))
            self.assertTrue(hasattr(provider, "provider_type"))

            # Test get_capabilities() returns valid ProviderCapabilities
            caps = provider.get_capabilities()
            self.assertIsInstance(caps, ProviderCapabilities)
            self.assertEqual(caps.provider_id, provider.provider_id)
            self.assertIsInstance(caps.supported_browsers, list)
            self.assertGreater(len(caps.supported_browsers), 0)

            # Test check_health() returns valid ProviderHealthStatus
            health = asyncio.run(provider.check_health())
            self.assertIsInstance(health, ProviderHealthStatus)
            self.assertEqual(health.provider_id, provider.provider_id)
            self.assertIn(health.status, ("healthy", "degraded", "unreachable", "unconfigured"))

    def test_provider_execution_output_contract(self) -> None:
        """Verify that executing a CanonicalExecutionRequest against any provider returns a CanonicalExecutionResult."""
        req = CanonicalExecutionRequest(
            run_id="contract-run-101",
            target_url="https://example.com",
            browser=BrowserType.CHROMIUM,
            steps=[{"action": "navigate", "value": "https://example.com"}],
            checks=[{"type": "title_contains", "value": "Example"}],
        )

        for provider_id in ("sauce_labs", "lambdatest", "docker", "azure"):
            provider = execution_registry.get(provider_id)
            result = asyncio.run(provider.execute(req))
            self.assertIsInstance(result, CanonicalExecutionResult)
            self.assertEqual(result.run_id, req.run_id)
            self.assertEqual(result.provider_id, provider.provider_id)
            self.assertIn(result.status, ("passed", "failed", "error", "cancelled"))
            self.assertIsInstance(result.step_results, list)
            self.assertIsInstance(result.checks, list)


if __name__ == "__main__":
    unittest.main()
