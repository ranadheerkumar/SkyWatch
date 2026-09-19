"""Unit tests for the autonomous agent runtime, planner, memory, and tool registry."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agent.memory import WorkingMemory
from app.agent.planner import AgentPlanner
from app.agent.runtime import AgentRuntime
from app.agent.tool_base import AgentTool, ToolParameter, ToolSchema
from app.agent.tool_registry import ToolRegistry
from app.agent.types import (
    AgentState,
    PlanStep,
    StepStatus,
    TaskStatus,
    ToolCallRequest,
    ToolCategory,
)
from app.services.llm_client import LLMClient, LLMResponse, LLMUsage


class MockCalculatorTool(AgentTool):
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="calculator",
            description="Add two numbers.",
            category=ToolCategory.CUSTOM,
            parameters=[
                ToolParameter(name="a", description="First number", type="number"),
                ToolParameter(name="b", description="Second number", type="number"),
            ],
        )

    async def _execute(self, a: float, b: float, **kwargs) -> dict:
        return {"result": a + b}


class MockDestructiveTool(AgentTool):
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="delete_all",
            description="Destructive action requiring human approval.",
            category=ToolCategory.CUSTOM,
            parameters=[],
            requires_approval=True,
        )

    async def _execute(self, **kwargs) -> dict:
        return {"deleted": True}


def test_tool_registry_registration_and_schemas():
    registry = ToolRegistry()
    calc = MockCalculatorTool()
    registry.register(calc)

    assert "calculator" in registry
    assert len(registry) == 1
    assert registry.get("calculator") == calc

    schemas = registry.function_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "calculator"
    assert "a" in schemas[0]["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_tool_execution():
    registry = ToolRegistry()
    registry.register(MockCalculatorTool())

    req = ToolCallRequest(
        call_id="call-1",
        tool_name="calculator",
        arguments={"a": 10, "b": 25},
    )
    res = await registry.execute(req)

    assert res.success is True
    assert res.output == {"result": 35}
    assert res.call_id == "call-1"


@pytest.mark.asyncio
async def test_tool_execution_unknown():
    registry = ToolRegistry()
    req = ToolCallRequest(call_id="c1", tool_name="nonexistent", arguments={})
    res = await registry.execute(req)
    assert res.success is False
    assert "Unknown tool" in (res.error or "")


def test_working_memory_context():
    mem = WorkingMemory(
        objective="Verify login flow",
        application_context={"target_url": "https://example.com"},
    )
    mem.add_observation("Observed login button on navbar", {"selector": "#login-btn"})
    mem.add_decision("Will click login button")

    messages = mem.build_context_messages()
    assert len(messages) == 1
    content = messages[0]["content"]
    assert "Verify login flow" in content
    assert "Observed login button on navbar" in content
    assert "Will click login button" in content


@pytest.mark.asyncio
async def test_planner_create_plan():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value={
        "rationale": "Test authentication end-to-end",
        "steps": [
            {
                "goal": "Navigate to login",
                "description": "Open login page in browser",
                "suggested_tools": ["browser_navigate"],
                "success_criteria": "Page title is Login",
                "requires_approval": False,
            },
            {
                "goal": "Execute login test",
                "description": "Submit valid credentials",
                "suggested_tools": ["execute_test_case"],
                "success_criteria": "User is redirected to dashboard",
                "requires_approval": False,
            },
        ],
    })

    registry = ToolRegistry()
    planner = AgentPlanner(mock_llm, registry)

    plan = await planner.create_plan("Test login page", {"url": "http://app.com"})

    assert len(plan.steps) == 2
    assert plan.steps[0].goal == "Navigate to login"
    assert plan.steps[0].status == StepStatus.QUEUED


@pytest.mark.asyncio
async def test_agent_runtime_react_loop():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.cumulative_usage = LLMUsage()

    plan_dict = {
        "rationale": "Calculate sum",
        "steps": [
            {
                "goal": "Add 5 and 7",
                "description": "Use calculator tool",
                "suggested_tools": ["calculator"],
                "success_criteria": "Result is 12",
                "requires_approval": False,
            }
        ],
    }
    eval_dict = {
        "succeeded": True,
        "reasoning": "Result 12 matches criteria",
        "should_retry": False,
        "should_replan": False,
        "next_action": "proceed",
        "summary": "Calculated 5 + 7 = 12 successfully",
    }

    mock_llm.complete_json = AsyncMock(side_effect=[plan_dict, eval_dict])
    mock_llm.complete_with_tools = AsyncMock(return_value=LLMResponse(
        content="I will call the calculator tool.",
        tool_calls=[{"name": "calculator", "arguments": {"a": 5, "b": 7}}],
    ))

    registry = ToolRegistry()
    registry.register(MockCalculatorTool())

    traces = []
    runtime = AgentRuntime(
        llm_client=mock_llm,
        tool_registry=registry,
        trace_callback=lambda entry: traces.append(entry),
    )

    state = AgentState(
        task_id="test-task-1",
        objective="Calculate sum of 5 and 7",
    )

    final_state = await runtime.execute(state)

    assert final_state.status == TaskStatus.COMPLETED
    assert final_state.plan is not None
    assert final_state.plan.steps[0].status == StepStatus.COMPLETED
    assert len(traces) > 0
