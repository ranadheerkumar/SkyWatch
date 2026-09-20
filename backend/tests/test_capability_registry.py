"""Unit tests for the SkyWatch Central Capability Registry."""

import os
import sys
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.capabilities import (
    CapabilityCategory,
    CapabilityDescriptor,
    CapabilityRegistry,
    PlatformCapability,
    default_capability_registry,
)


class TestCapabilityRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CapabilityRegistry()

    def test_default_capabilities_initialized(self) -> None:
        caps = self.registry.list_capabilities()
        self.assertGreaterEqual(len(caps), 18)
        names = [c.capability for c in caps]
        self.assertIn(PlatformCapability.UI_BROWSER_AUTOMATION, names)
        self.assertIn(PlatformCapability.API_AUTOMATION, names)
        self.assertIn(PlatformCapability.MOBILE_AUTOMATION, names)
        self.assertIn(PlatformCapability.DATABASE_VALIDATION, names)
        self.assertIn(PlatformCapability.SOURCE_CONTROL, names)
        self.assertIn(PlatformCapability.CLOUD_STORAGE, names)

    def test_filter_by_category(self) -> None:
        exec_caps = self.registry.list_capabilities(category=CapabilityCategory.EXECUTION)
        self.assertTrue(all(c.category == CapabilityCategory.EXECUTION for c in exec_caps))
        self.assertGreater(len(exec_caps), 0)

        design_caps = self.registry.list_capabilities(category=CapabilityCategory.DESIGN)
        self.assertTrue(all(c.category == CapabilityCategory.DESIGN for c in design_caps))

    def test_get_capability(self) -> None:
        desc = self.registry.get(PlatformCapability.UI_BROWSER_AUTOMATION)
        self.assertIsNotNone(desc)
        self.assertEqual(desc.name, "UI Browser Automation")

        desc_str = self.registry.get("UI_BROWSER_AUTOMATION")
        self.assertIsNotNone(desc_str)
        self.assertEqual(desc_str.name, "UI Browser Automation")

        invalid_desc = self.registry.get("NON_EXISTENT_CAPABILITY")
        self.assertIsNone(invalid_desc)

    def test_is_available(self) -> None:
        self.assertTrue(self.registry.is_available(PlatformCapability.API_AUTOMATION))
        self.assertFalse(self.registry.is_available("UNKNOWN_CAP"))

    def test_custom_capability_registration(self) -> None:
        custom_cap = CapabilityDescriptor(
            capability=PlatformCapability.CI_CD,
            name="Custom CI/CD Pipeline",
            category=CapabilityCategory.INFRASTRUCTURE,
            description="Custom integration",
            supported_environments=["cloud"],
            is_available=True,
        )
        self.registry.register(custom_cap)
        retrieved = self.registry.get(PlatformCapability.CI_CD)
        self.assertEqual(retrieved.name, "Custom CI/CD Pipeline")

    def test_serialization(self) -> None:
        data = self.registry.to_dict()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("capability", data[0])
        self.assertIn("category", data[0])


if __name__ == "__main__":
    unittest.main()
