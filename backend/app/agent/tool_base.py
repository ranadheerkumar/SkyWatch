"""Abstract base class for all agent tools.

Every tool the agent can invoke must implement this interface. The tool registry
discovers and registers tools at startup, presenting their schemas to the LLM
for dynamic tool selection.
"""

from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.agent.types import ToolCallResult, ToolCategory

logger = logging.getLogger("ai-qa-engine.agent.tool")


@dataclass(frozen=True)
class ToolParameter:
    """Schema for a single tool parameter, presented to the LLM."""
    name: str
    description: str
    type: str = "string"  # string, integer, number, boolean, array, object
    required: bool = True
    enum: list[str] | None = None
    default: Any = None


@dataclass(frozen=True)
class ToolSchema:
    """Complete schema describing a tool's interface for LLM consumption."""
    name: str
    description: str
    category: ToolCategory
    parameters: list[ToolParameter] = field(default_factory=list)
    requires_approval: bool = False  # If True, agent must get human approval before executing

    def to_function_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling compatible schema."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class AgentTool(ABC):
    """Abstract base class for agent tools.

    Subclasses must implement:
    - schema: class property returning the ToolSchema
    - _execute: the actual tool logic

    The base class provides:
    - Timing and error handling wrappers
    - Consistent result formatting
    - Logging
    """

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Return the tool's schema for LLM consumption."""
        ...

    @abstractmethod
    async def _execute(self, **kwargs: Any) -> Any:
        """Execute the tool with the given arguments. Return the result payload."""
        ...

    async def execute(self, **kwargs: Any) -> ToolCallResult:
        """Execute the tool with timing, error handling, and structured result."""
        call_id = kwargs.pop("_call_id", "")
        start = time.perf_counter()
        try:
            output = await self._execute(**kwargs)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "tool_executed tool=%s duration_ms=%.2f success=true",
                self.schema.name,
                duration_ms,
            )
            return ToolCallResult(
                call_id=call_id,
                tool_name=self.schema.name,
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as error:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            error_message = f"{type(error).__name__}: {str(error)[:500]}"
            logger.warning(
                "tool_failed tool=%s duration_ms=%.2f error=%s",
                self.schema.name,
                duration_ms,
                error_message,
            )
            return ToolCallResult(
                call_id=call_id,
                tool_name=self.schema.name,
                success=False,
                error=error_message,
                duration_ms=duration_ms,
            )
