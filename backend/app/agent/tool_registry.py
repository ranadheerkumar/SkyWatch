"""Dynamic tool registry for the agent runtime.

Provides tool registration, discovery, and lookup. Presents tool schemas
to the LLM in OpenAI function-calling format so the agent can dynamically
select which tool to use.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.tool_base import AgentTool, ToolSchema
from app.agent.types import ToolCallRequest, ToolCallResult, ToolCategory

logger = logging.getLogger("ai-qa-engine.agent.registry")


class ToolRegistry:
    """Central registry of all available agent tools.

    Tools self-register on construction. The runtime queries the registry
    to build the tool list for LLM function-calling and to execute tool calls.
    """

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        """Register a tool instance. Replaces any existing tool with the same name."""
        name = tool.schema.name
        if name in self._tools:
            logger.debug("Replacing existing tool registration: %s", name)
        self._tools[name] = tool
        logger.debug("Registered tool: %s (%s)", name, tool.schema.category.value)

    def register_many(self, tools: list[AgentTool]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> AgentTool | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    def list_tools(self, category: ToolCategory | None = None) -> list[ToolSchema]:
        """List all registered tool schemas, optionally filtered by category."""
        schemas = [tool.schema for tool in self._tools.values()]
        if category is not None:
            schemas = [s for s in schemas if s.category == category]
        return schemas

    def tool_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def function_schemas(self, category: ToolCategory | None = None) -> list[dict[str, Any]]:
        """Return OpenAI function-calling schemas for all registered tools."""
        return [schema.to_function_schema() for schema in self.list_tools(category)]

    def tool_descriptions_text(self) -> str:
        """Return a compact text listing of all tools for prompt injection."""
        lines: list[str] = []
        for schema in self.list_tools():
            param_names = ", ".join(p.name for p in schema.parameters)
            approval_note = " [REQUIRES APPROVAL]" if schema.requires_approval else ""
            lines.append(f"- {schema.name}({param_names}): {schema.description}{approval_note}")
        return "\n".join(lines)

    async def execute(self, request: ToolCallRequest) -> ToolCallResult:
        """Execute a tool call request. Returns a structured result."""
        tool = self.get(request.tool_name)
        if tool is None:
            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                error=f"Unknown tool '{request.tool_name}'. Available: {', '.join(self.tool_names())}",
            )
        return await tool.execute(_call_id=request.call_id, **request.arguments)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
