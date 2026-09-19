"""LLM-driven task decomposition and dynamic planning.

The planner takes a high-level objective and uses the LLM to decompose it
into executable steps. Plans can be revised based on intermediate results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.types import AgentPlan, PlanStep, StepStatus
from app.agent.tool_registry import ToolRegistry
from app.services.llm_client import LLMClient, LLMClientError

logger = logging.getLogger("ai-qa-engine.agent.planner")


PLANNER_SYSTEM_PROMPT = """You are the Planning Agent for an AI-powered QA Automation platform.

Your job is to take a high-level objective and decompose it into concrete, executable steps.
Each step should be achievable using the available tools.

Available tools:
{tool_descriptions}

Rules:
1. Each step must have a clear goal and success criteria.
2. Steps should be ordered logically — dependencies before dependents.
3. Suggest specific tools for each step from the available tools list.
4. Keep the plan focused — avoid unnecessary steps.
5. If the objective involves testing a web application, include discovery (browser_navigate), test generation (generate_test_cases), and execution (execute_test_case) steps.
6. If documents are mentioned, include an analyze_document step first.
7. Mark steps that modify external systems (e.g., creating Jira issues) as requires_approval: true.

Respond with valid JSON only:
{{
  "rationale": "Brief explanation of the plan strategy",
  "steps": [
    {{
      "goal": "What this step accomplishes",
      "description": "Detailed description of what to do",
      "suggested_tools": ["tool_name_1"],
      "success_criteria": "How to know this step succeeded",
      "requires_approval": false
    }}
  ]
}}"""


REPLAN_SYSTEM_PROMPT = """You are the Planning Agent. The current plan needs revision based on execution results.

Current plan state:
{plan_state}

Recent observations:
{observations}

Available tools:
{tool_descriptions}

Revise the plan by adjusting remaining steps based on what has been learned.
Keep completed steps as-is. You may add, remove, or modify queued steps.

Respond with valid JSON:
{{
  "rationale": "Why the plan was revised",
  "steps": [
    {{
      "goal": "Step goal",
      "description": "Step description",
      "suggested_tools": ["tool_name"],
      "success_criteria": "Success criteria",
      "requires_approval": false,
      "status": "completed|queued"
    }}
  ]
}}"""


class AgentPlanner:
    """LLM-driven task planner that decomposes objectives into executable steps."""

    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry) -> None:
        self.llm = llm_client
        self.tools = tool_registry

    async def create_plan(self, objective: str, context: dict[str, Any] | None = None) -> AgentPlan:
        """Create an execution plan for a high-level objective.

        Args:
            objective: Natural language description of what to accomplish.
            context: Optional application context (URL, name, etc.).

        Returns:
            AgentPlan with decomposed steps.
        """
        tool_descriptions = self.tools.tool_descriptions_text()
        system_prompt = PLANNER_SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions)

        user_prompt = f"Objective: {objective}"
        if context:
            user_prompt += f"\n\nApplication context:\n{json.dumps(context, indent=2)[:4000]}"

        try:
            result = await self.llm.complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
            )
        except LLMClientError as error:
            logger.error("Planning failed: %s", error)
            # Fallback: create a minimal plan
            return AgentPlan(
                objective=objective,
                rationale=f"Planning failed ({error}), using minimal fallback plan.",
                steps=[
                    PlanStep(
                        goal="Investigate the objective manually",
                        description=str(error),
                        success_criteria="Error resolved",
                    )
                ],
            )

        return self._parse_plan(objective, result)

    async def revise_plan(
        self,
        plan: AgentPlan,
        observations: list[str],
    ) -> AgentPlan:
        """Revise the plan based on execution observations.

        Args:
            plan: Current plan with completed and pending steps.
            observations: Recent observations from execution.

        Returns:
            Revised AgentPlan.
        """
        plan_state = json.dumps(plan.to_dict(), indent=2)[:6000]
        obs_text = "\n".join(f"- {o[:300]}" for o in observations[-10:])
        tool_descriptions = self.tools.tool_descriptions_text()

        system_prompt = REPLAN_SYSTEM_PROMPT.format(
            plan_state=plan_state,
            observations=obs_text,
            tool_descriptions=tool_descriptions,
        )

        try:
            result = await self.llm.complete_json(
                system_prompt=system_prompt,
                user_prompt="Revise the plan based on the observations above.",
                temperature=0.1,
            )
        except LLMClientError as error:
            logger.warning("Plan revision failed: %s — keeping current plan", error)
            return plan

        revised = self._parse_plan(plan.objective, result)
        revised.revision_count = plan.revision_count + 1
        return revised

    def _parse_plan(self, objective: str, result: dict[str, Any]) -> AgentPlan:
        """Parse LLM planner output into an AgentPlan."""
        raw_steps = result.get("steps", [])
        steps: list[PlanStep] = []
        for raw in raw_steps:
            if not isinstance(raw, dict):
                continue
            status_str = str(raw.get("status", "queued")).lower()
            status = StepStatus.COMPLETED if status_str == "completed" else StepStatus.QUEUED
            steps.append(PlanStep(
                goal=str(raw.get("goal", "")).strip()[:300],
                description=str(raw.get("description", "")).strip()[:500],
                suggested_tools=[str(t) for t in (raw.get("suggested_tools") or [])],
                success_criteria=str(raw.get("success_criteria", "")).strip()[:300],
                requires_approval=bool(raw.get("requires_approval", False)),
                status=status,
            ))

        if not steps:
            steps = [PlanStep(
                goal="Execute the objective directly",
                description=objective,
                success_criteria="Objective completed",
            )]

        return AgentPlan(
            objective=objective,
            steps=steps,
            rationale=str(result.get("rationale", "")).strip()[:500],
            estimated_tool_calls=len(steps),
        )
