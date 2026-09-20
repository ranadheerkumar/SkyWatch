"""Unit tests for the SkyWatch Enterprise Standardized Tool Registry."""

import asyncio
import os
import sys
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.capabilities import PlatformCapability
from app.core.tool_registry import (
    EnterpriseTool,
    EnterpriseToolDescriptor,
    EnterpriseToolRegistry,
    ToolExecutionResponse,
    default_tool_registry,
)


class DummyTool(EnterpriseTool):
    @property
    def descriptor(self) -> EnterpriseToolDescriptor:
        return EnterpriseToolDescriptor(
            tool_id="tool.dummy.test",
            name="Dummy Test Tool",
            description="Tool for testing registry contracts",
            capability=PlatformCapability.UI_BROWSER_AUTOMATION,
            version="1.0.0",
            input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        )

    async def execute(self, call_id: str = "", **arguments) -> ToolExecutionResponse:
        return ToolExecutionResponse(
            call_id=call_id,
            tool_id=self.descriptor.tool_id,
            success=True,
            data={"echo": arguments.get("msg", "default")},
        )


class TestEnterpriseToolRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = EnterpriseToolRegistry()

    def test_built_in_tools_registered(self) -> None:
        tools = self.registry.list_tools()
        self.assertGreaterEqual(len(tools), 8)
        tool_ids = [t.tool_id for t in tools]
        self.assertIn("tool.generator.script", tool_ids)
        self.assertIn("tool.vcs.github", tool_ids)
        self.assertIn("tool.api.rest", tool_ids)
        self.assertIn("tool.data.synthesizer", tool_ids)
        self.assertIn("tool.doc.analyzer", tool_ids)
        self.assertIn("tool.report.allure", tool_ids)
        self.assertIn("tool.alm.jira", tool_ids)
        self.assertIn("tool.alm.qtest", tool_ids)

    def test_filter_tools_by_capability(self) -> None:
        vcs_tools = self.registry.list_tools(capability=PlatformCapability.SOURCE_CONTROL)
        self.assertTrue(all(t.capability == PlatformCapability.SOURCE_CONTROL for t in vcs_tools))
        self.assertEqual(len(vcs_tools), 1)
        self.assertEqual(vcs_tools[0].tool_id, "tool.vcs.github")

    def test_get_tool(self) -> None:
        tool = self.registry.get("tool.api.rest")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.descriptor.capability, PlatformCapability.API_AUTOMATION)

    def test_openai_function_schema_generation(self) -> None:
        schemas = self.registry.get_openai_function_schemas()
        self.assertIsInstance(schemas, list)
        self.assertGreater(len(schemas), 0)
        first = schemas[0]
        self.assertEqual(first["type"], "function")
        self.assertIn("name", first["function"])
        self.assertIn("description", first["function"])

    def test_execute_tool(self) -> None:
        self.registry.register(DummyTool())
        res = asyncio.run(self.registry.execute("tool.dummy.test", {"msg": "hello skywatch"}, call_id="call-123"))
        self.assertTrue(res.success)
        self.assertEqual(res.tool_id, "tool.dummy.test")
        self.assertEqual(res.data["echo"], "hello skywatch")

    def test_execute_non_existent_tool(self) -> None:
        res = asyncio.run(self.registry.execute("non.existent.tool", {}))
        self.assertFalse(res.success)
        self.assertIn("not found", res.error)


if __name__ == "__main__":
    unittest.main()
