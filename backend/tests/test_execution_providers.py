"""Unit tests for Multi-Environment Execution Providers."""

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
    PlatformType,
    ProviderType,
)
from app.services.execution_providers.local_provider import LocalExecutionProvider
from app.services.execution_providers.sauce_labs_provider import SauceLabsExecutionProvider
from app.services.execution_providers.lambdatest_provider import LambdaTestExecutionProvider
from app.services.execution_providers.cloud_container_provider import CloudContainerExecutionProvider
from app.services.execution_providers.registry import ExecutionProviderRegistry


class TestExecutionProviders(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ExecutionProviderRegistry()

    def test_local_provider_capabilities(self) -> None:
        provider = LocalExecutionProvider()
        caps = provider.get_capabilities()
        self.assertEqual(caps.provider_id, "local")
        self.assertEqual(caps.provider_type, ProviderType.LOCAL)
        self.assertIn(BrowserType.CHROMIUM, caps.supported_browsers)
        self.assertIn(BrowserType.FIREFOX, caps.supported_browsers)
        self.assertIn(BrowserType.WEBKIT, caps.supported_browsers)
        self.assertFalse(caps.requires_credentials)
        self.assertTrue(caps.has_valid_credentials)

    def test_local_provider_health(self) -> None:
        provider = LocalExecutionProvider()
        health = asyncio.run(provider.check_health())
        self.assertTrue(health.is_available)
        self.assertEqual(health.status, "healthy")

    def test_sauce_labs_unconfigured_health(self) -> None:
        provider = SauceLabsExecutionProvider(username="", access_key="")
        health = asyncio.run(provider.check_health())
        self.assertFalse(health.is_available)
        self.assertEqual(health.status, "unconfigured")

    def test_sauce_labs_capabilities(self) -> None:
        provider = SauceLabsExecutionProvider(username="demo", access_key="secret")
        caps = provider.get_capabilities()
        self.assertEqual(caps.provider_type, ProviderType.SAUCE_LABS)
        self.assertTrue(caps.supports_real_devices)
        self.assertTrue(caps.supports_tunnels)
        self.assertTrue(caps.has_valid_credentials)

    def test_sauce_labs_execution_simulation(self) -> None:
        provider = SauceLabsExecutionProvider(username="demo", access_key="secret")
        req = CanonicalExecutionRequest(
            run_id="run-sauce-1",
            target_url="https://example.com",
            browser=BrowserType.CHROMIUM,
            steps=[{"action": "click", "selector": "#login-btn"}],
            checks=[{"type": "visible", "value": "#dashboard"}],
        )
        res = asyncio.run(provider.execute(req))
        self.assertEqual(res.status, "passed")
        self.assertEqual(res.provider_id, "sauce_labs")
        self.assertIsNotNone(res.remote_session_id)
        self.assertIn("saucelabs.com", res.remote_dashboard_url or "")
        self.assertEqual(len(res.step_results), 1)

    def test_lambdatest_unconfigured_health(self) -> None:
        provider = LambdaTestExecutionProvider(username="", access_key="")
        health = asyncio.run(provider.check_health())
        self.assertFalse(health.is_available)
        self.assertEqual(health.status, "unconfigured")

    def test_lambdatest_capabilities(self) -> None:
        provider = LambdaTestExecutionProvider(username="lt_user", access_key="lt_key")
        caps = provider.get_capabilities()
        self.assertEqual(caps.provider_type, ProviderType.LAMBDATEST)
        self.assertTrue(caps.supports_real_devices)
        self.assertTrue(caps.supports_tunnels)
        self.assertTrue(caps.has_valid_credentials)

    def test_lambdatest_execution_simulation(self) -> None:
        provider = LambdaTestExecutionProvider(username="lt_user", access_key="lt_key")
        req = CanonicalExecutionRequest(
            run_id="run-lt-1",
            target_url="https://example.com",
            browser=BrowserType.CHROME,
            steps=[{"action": "type", "selector": "#search", "value": "test"}],
        )
        res = asyncio.run(provider.execute(req))
        self.assertEqual(res.status, "passed")
        self.assertEqual(res.provider_id, "lambdatest")
        self.assertIsNotNone(res.remote_session_id)
        self.assertIn("lambdatest.com", res.remote_dashboard_url or "")

    def test_cloud_container_provider(self) -> None:
        docker_provider = CloudContainerExecutionProvider(cloud_target="docker")
        caps = docker_provider.get_capabilities()
        self.assertEqual(caps.provider_type, ProviderType.DOCKER)
        self.assertIn(BrowserType.CHROMIUM, caps.supported_browsers)

        req = CanonicalExecutionRequest(
            run_id="run-docker-1",
            target_url="https://example.com",
            browser=BrowserType.FIREFOX,
            steps=[{"action": "click", "selector": "#btn"}],
        )
        res = asyncio.run(docker_provider.execute(req))
        self.assertEqual(res.status, "passed")
        self.assertIn("job-docker-", res.remote_session_id or "")

    def test_registry_default_resolution(self) -> None:
        default_prov = self.registry.get_default_provider()
        self.assertEqual(default_prov.provider_id, "local")
        self.assertEqual(default_prov.provider_type, ProviderType.LOCAL)

    def test_registry_find_best_provider_fallback(self) -> None:
        # With unconfigured cloud credentials, requests fall back safely to local
        best = self.registry.find_best_provider(target_platform="web", browser="chromium")
        self.assertEqual(best.provider_id, "local")


if __name__ == "__main__":
    unittest.main()
