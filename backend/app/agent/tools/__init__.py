"""Agent tool implementations and standard registry initialization."""

from __future__ import annotations

from app.agent.tool_registry import ToolRegistry
from app.agent.tools.browser import create_browser_tools
from app.agent.tools.file_analyzer import create_file_tools
from app.agent.tools.integrations import create_integration_tools
from app.agent.tools.reporting import create_reporting_tools
from app.agent.tools.testing import create_testing_tools


def get_default_tool_registry() -> ToolRegistry:
    """Create and initialize a ToolRegistry with all standard tools."""
    registry = ToolRegistry()
    registry.register_many(create_browser_tools())
    registry.register_many(create_file_tools())
    registry.register_many(create_testing_tools())
    registry.register_many(create_integration_tools())
    registry.register_many(create_reporting_tools())
    return registry


__all__ = [
    "create_browser_tools",
    "create_file_tools",
    "create_integration_tools",
    "create_reporting_tools",
    "create_testing_tools",
    "get_default_tool_registry",
]
