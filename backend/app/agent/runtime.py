"""Agent Runtime — the ReAct (Reasoning + Acting) execution loop.

This is the heart of the agentic system. It implements the cycle:
  Observe → Think → Act → Observe
with LLM-driven tool selection, self-correction, and dynamic replanning.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.agent.memory import WorkingMemory
from app.agent.planner import AgentPlanner
from app.agent.tool_registry import ToolRegistry
from app.agent.types import (
    AgentState,
    PlanStep,
    StepStatus,
    TaskStatus,
    ToolCallRequest,
    ToolCallResult,
    TraceEntry,
)
from app.services.llm_client import LLMClient, LLMClientError

logger = logging.getLogger("ai-qa-engine.agent.runtime")


EXECUTOR_SYSTEM_PROMPT = """You are an AI QA Automation Agent. You execute a plan step by step using available tools.

Current step:
- Goal: {step_goal}
- Description: {step_description}
- Suggested tools: {suggested_tools}
- Success criteria: {step_criteria}
- Attempt: {attempt} of {max_attempts}

Available tools:
{tool_schemas}

Instructions:
1. Analyze the current step and the working memory context.
2. Select the most appropriate tool and provide the required arguments.
3. If the previous attempt for this step failed, try a different approach.
4. Call exactly ONE tool per turn. The system will execute it and show you the result.
5. After seeing the result, you will be asked to evaluate whether the step succeeded.

Call a tool by responding with the appropriate function call."""


EVALUATOR_SYSTEM_PROMPT = """You are evaluating whether an agent step succeeded.

Step goal: {step_goal}
Success criteria: {step_criteria}

Tool result:
{tool_result}

Respond with valid JSON only:
{{
  "succeeded": true/false,
  "reasoning": "Brief explanation of why this step succeeded or failed",
  "should_retry": true/false,
  "should_replan": false,
  "next_action": "proceed|retry|replan|fail",
  "summary": "One-line summary of what was accomplished or what went wrong"
}}"""


# Callback type for broadcasting trace events (used by WebSocket)
TraceCallback = Callable[[TraceEntry], None]


class AgentRuntime:
    """Core agent execution runtime implementing the ReAct loop.

    The runtime:
    1. Accepts an objective
    2. Creates a plan via the LLM planner
    3. For each step, uses the LLM to select and invoke tools
    4. Evaluates results and decides next actions
    5. Self-corrects on failures with retries and replanning
    6. Tracks all actions in a trace for observability
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        planner: AgentPlanner | None = None,
        trace_callback: TraceCallback | None = None,
    ) -> None:
        self.llm = llm_client
        self.tools = tool_registry
        self.planner = planner or AgentPlanner(llm_client, tool_registry)
        self.trace_callback = trace_callback

    async def execute(
        self,
        state: AgentState,
        context: dict[str, Any] | None = None,
    ) -> AgentState:
        """Execute an agent task from start to completion.

        Args:
            state: Pre-initialized AgentState with objective set.
            context: Optional application context for planning.

        Returns:
            Updated AgentState with results, trace, and artifacts.
        """
        state.status = TaskStatus.PLANNING
        state.started_at = datetime.now(timezone.utc).isoformat()

        memory = WorkingMemory(
            objective=state.objective,
            application_context=context or {},
        )

        # 1. Plan
        self._emit_trace(state, "planning_started", objective=state.objective)
        try:
            plan = await self.planner.create_plan(state.objective, context)
            state.plan = plan
            memory.plan = plan
            state.total_llm_calls += 1
            self._emit_trace(
                state,
                "plan_created",
                rationale=plan.rationale,
                step_count=len(plan.steps),
                steps=[s.goal for s in plan.steps],
            )
        except Exception as error:
            state.status = TaskStatus.FAILED
            state.error = f"Planning failed: {error}"
            state.completed_at = datetime.now(timezone.utc).isoformat()
            self._emit_trace(state, "planning_failed", error=str(error))
            return state

        # 2. Execute plan steps
        state.status = TaskStatus.EXECUTING
        iteration = 0

        while not plan.is_complete() and iteration < state.max_iterations:
            iteration += 1
            current_step = plan.current_step()
            if current_step is None:
                break

            # Check for approval gate
            if current_step.requires_approval and current_step.status == StepStatus.QUEUED:
                current_step.status = StepStatus.WAITING_APPROVAL
                state.status = TaskStatus.WAITING_APPROVAL
                self._emit_trace(
                    state,
                    "approval_requested",
                    step_id=current_step.id,
                    step_goal=current_step.goal,
                )
                return state  # Pause execution until approved

            current_step.status = StepStatus.RUNNING
            current_step.attempts += 1

            self._emit_trace(
                state,
                "step_started",
                step_id=current_step.id,
                step_goal=current_step.goal,
                attempt=current_step.attempts,
            )

            # 3. Select and execute tool
            try:
                tool_result = await self._execute_step(state, current_step, memory)
            except Exception as error:
                tool_result = ToolCallResult(
                    call_id="error",
                    tool_name="unknown",
                    success=False,
                    error=str(error),
                )

            memory.add_tool_result(tool_result)
            state.total_tool_calls += 1

            # 4. Evaluate result
            evaluation = await self._evaluate_step(state, current_step, tool_result, memory)
            next_action = evaluation.get("next_action", "fail")
            summary = evaluation.get("summary", "")

            memory.add_decision(f"Step '{current_step.goal}': {next_action} — {summary}")
            state.total_llm_calls += 1

            self._emit_trace(
                state,
                "step_evaluated",
                step_id=current_step.id,
                next_action=next_action,
                summary=summary,
                succeeded=evaluation.get("succeeded", False),
            )

            if next_action == "proceed":
                current_step.status = StepStatus.COMPLETED
                current_step.result_summary = summary
            elif next_action == "retry" and current_step.attempts < current_step.max_attempts:
                current_step.status = StepStatus.QUEUED  # Will re-enter the loop
                memory.add_observation(
                    f"Retrying step '{current_step.goal}': {summary}",
                    source="runtime",
                )
            elif next_action == "replan":
                # Dynamic replanning
                observations = [d for d in memory.decisions[-5:]]
                try:
                    plan = await self.planner.revise_plan(plan, observations)
                    state.plan = plan
                    memory.plan = plan
                    state.total_llm_calls += 1
                    self._emit_trace(
                        state,
                        "plan_revised",
                        revision=plan.revision_count,
                        new_step_count=len(plan.steps),
                    )
                except Exception as error:
                    logger.warning("Replanning failed: %s", error)
                    current_step.status = StepStatus.FAILED
                    current_step.result_summary = f"Replanning failed: {error}"
            else:
                current_step.status = StepStatus.FAILED
                current_step.result_summary = summary

            # Check if we should abort (too many consecutive failures)
            recent_failures = sum(
                1 for s in plan.steps
                if s.status == StepStatus.FAILED
            )
            if recent_failures >= 3:
                state.error = f"Too many step failures ({recent_failures}). Aborting."
                state.status = TaskStatus.FAILED
                self._emit_trace(state, "execution_aborted", reason=state.error)
                break

            # Check tool call budget
            if state.total_tool_calls >= state.max_tool_calls:
                state.error = f"Tool call budget exhausted ({state.max_tool_calls})."
                state.status = TaskStatus.FAILED
                self._emit_trace(state, "budget_exhausted", reason=state.error)
                break

        # 5. Finalize
        if state.status == TaskStatus.EXECUTING:
            if plan.is_complete():
                state.status = TaskStatus.COMPLETED
                state.artifacts = memory.artifacts
                self._emit_trace(
                    state,
                    "execution_completed",
                    total_tool_calls=state.total_tool_calls,
                    total_llm_calls=state.total_llm_calls,
                    artifact_count=len(memory.artifacts),
                )
            else:
                state.status = TaskStatus.FAILED
                state.error = state.error or "Plan did not complete within iteration limit."
                self._emit_trace(state, "execution_incomplete", error=state.error)

        state.completed_at = datetime.now(timezone.utc).isoformat()
        state.total_tokens_used = self.llm.cumulative_usage.total_tokens
        return state

    async def resume(self, state: AgentState) -> AgentState:
        """Resume a paused task (e.g., after human approval)."""
        if state.status != TaskStatus.WAITING_APPROVAL:
            return state

        if state.plan:
            for step in state.plan.steps:
                if step.status == StepStatus.WAITING_APPROVAL:
                    step.status = StepStatus.QUEUED
                    step.requires_approval = False  # Already approved
                    break

        state.status = TaskStatus.EXECUTING
        self._emit_trace(state, "execution_resumed")
        return await self.execute(state)

    async def _execute_step(
        self,
        state: AgentState,
        step: PlanStep,
        memory: WorkingMemory,
    ) -> ToolCallResult:
        """Use the LLM to select a tool and execute it for the current step."""
        tool_schemas = self.tools.function_schemas()

        system_prompt = EXECUTOR_SYSTEM_PROMPT.format(
            step_goal=step.goal,
            step_description=step.description,
            suggested_tools=", ".join(step.suggested_tools) or "any applicable tool",
            step_criteria=step.success_criteria,
            attempt=step.attempts,
            max_attempts=step.max_attempts,
            tool_schemas=self.tools.tool_descriptions_text(),
        )

        context_messages = memory.build_context_messages()
        messages = [
            {"role": "system", "content": system_prompt},
            *context_messages,
        ]

        try:
            response = await self.llm.complete_with_tools(
                messages=messages,
                tools=tool_schemas,
                temperature=0.1,
            )
            state.total_llm_calls += 1
        except LLMClientError as error:
            return ToolCallResult(
                call_id="llm_error",
                tool_name="llm",
                success=False,
                error=f"LLM tool selection failed: {error}",
            )

        # Extract tool call from response
        if response.tool_calls:
            tc = response.tool_calls[0]
            request = ToolCallRequest(
                tool_name=tc["name"],
                arguments=tc.get("arguments", {}),
                reasoning=response.content or "",
            )

            self._emit_trace(
                state,
                "tool_call",
                step_id=step.id,
                tool_name=request.tool_name,
                arguments=request.arguments,
                reasoning=request.reasoning[:200],
            )

            result = await self.tools.execute(request)

            self._emit_trace(
                state,
                "tool_result",
                step_id=step.id,
                tool_name=result.tool_name,
                success=result.success,
                summary=result.summary(max_length=300),
                duration_ms=result.duration_ms,
            )

            return result

        # Fallback: if LLM didn't use tools, try to match suggested tools
        if step.suggested_tools:
            tool_name = step.suggested_tools[0]
            if tool_name in self.tools:
                request = ToolCallRequest(
                    tool_name=tool_name,
                    arguments={},
                    reasoning="Fallback to suggested tool (LLM did not issue tool call)",
                )
                return await self.tools.execute(request)

        return ToolCallResult(
            call_id="no_tool",
            tool_name="none",
            success=False,
            error="LLM did not select any tool for this step. Response: " + response.content[:300],
        )

    async def _evaluate_step(
        self,
        state: AgentState,
        step: PlanStep,
        tool_result: ToolCallResult,
        memory: WorkingMemory,
    ) -> dict[str, Any]:
        """Use the LLM to evaluate whether a step succeeded."""
        system_prompt = EVALUATOR_SYSTEM_PROMPT.format(
            step_goal=step.goal,
            step_criteria=step.success_criteria,
            tool_result=tool_result.summary(max_length=2000),
        )

        try:
            result = await self.llm.complete_json(
                system_prompt=system_prompt,
                user_prompt="Evaluate the step result above.",
                temperature=0.0,
            )
            return result
        except LLMClientError:
            # Fallback: use tool result success as evaluation
            return {
                "succeeded": tool_result.success,
                "reasoning": "Evaluation based on tool result status (LLM evaluation failed).",
                "should_retry": not tool_result.success,
                "next_action": "proceed" if tool_result.success else "retry",
                "summary": tool_result.summary(max_length=200),
            }

    def _emit_trace(self, state: AgentState, event_type: str, **data: Any) -> None:
        """Add a trace entry and optionally broadcast via callback."""
        entry = state.add_trace(event_type, **data)
        if self.trace_callback:
            try:
                self.trace_callback(entry)
            except Exception:
                pass  # Don't let callback errors affect execution


def create_default_runtime(
    trace_callback: TraceCallback | None = None,
) -> tuple[AgentRuntime, ToolRegistry]:
    """Create an agent runtime with all default tools registered.

    Returns:
        Tuple of (AgentRuntime, ToolRegistry).
    """
    from app.agent.tools.browser import create_browser_tools
    from app.agent.tools.file_analyzer import create_file_tools
    from app.agent.tools.testing import create_testing_tools
    from app.agent.tools.integrations import create_integration_tools
    from app.services.llm_client import create_llm_client

    registry = ToolRegistry()
    registry.register_many(create_browser_tools())
    registry.register_many(create_file_tools())
    registry.register_many(create_testing_tools())
    registry.register_many(create_integration_tools())

    llm = create_llm_client()
    planner = AgentPlanner(llm, registry)
    runtime = AgentRuntime(llm, registry, planner, trace_callback)

    return runtime, registry
