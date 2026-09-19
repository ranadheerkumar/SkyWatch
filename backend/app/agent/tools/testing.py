"""Test generation and execution tools wrapping existing services.

Provides tools for generating AI test cases and executing Playwright tests
through the agent runtime, delegating to the existing generation pipeline
and test execution engine.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.tool_base import AgentTool, ToolParameter, ToolSchema
from app.agent.types import ToolCategory

logger = logging.getLogger("ai-qa-engine.agent.tools.testing")


class GenerateTestCasesTool(AgentTool):
    """Generate AI-powered test cases for a web application."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="generate_test_cases",
            description=(
                "Generate AI-powered test cases for a web application. Uses the existing "
                "multi-agent pipeline: Document Analysis → Discovery → Context → Planner → "
                "Scenario → Generator → Test Data → Validation → Repository. Returns the "
                "generated test cases with executable Playwright automation steps."
            ),
            category=ToolCategory.TEST_GENERATION,
            parameters=[
                ToolParameter(name="application_id", description="Database ID of the target application.", type="integer"),
                ToolParameter(name="prompt", description="Natural language description of what to test and any specific requirements.", type="string"),
                ToolParameter(name="target_url", description="URL of the application to test.", type="string"),
                ToolParameter(
                    name="max_cases",
                    description="Maximum number of test cases to generate.",
                    type="integer",
                    required=False,
                ),
                ToolParameter(
                    name="include_negative",
                    description="Include negative scenario test cases.",
                    type="boolean",
                    required=False,
                    default=True,
                ),
                ToolParameter(
                    name="include_accessibility",
                    description="Include accessibility validation test cases.",
                    type="boolean",
                    required=False,
                    default=True,
                ),
                ToolParameter(
                    name="document_context",
                    description="Extracted text from uploaded requirement documents.",
                    type="string",
                    required=False,
                ),
                ToolParameter(
                    name="login_email",
                    description="Login email for authenticated testing.",
                    type="string",
                    required=False,
                ),
                ToolParameter(
                    name="login_password",
                    description="Login password for authenticated testing.",
                    type="string",
                    required=False,
                ),
            ],
        )

    async def _execute(
        self,
        application_id: int,
        prompt: str,
        target_url: str,
        max_cases: int | None = None,
        include_negative: bool = True,
        include_accessibility: bool = True,
        document_context: str | None = None,
        login_email: str | None = None,
        login_password: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        from app.core.database import SessionLocal
        from app.models.application import Application

        with SessionLocal() as db:
            app = db.get(Application, application_id)
            if not app:
                raise ValueError(f"Application {application_id} not found")
            application_name = app.name
            platform = app.platform or "web"

        from app.services.ai_service import generate_ai_test_cases

        result = await generate_ai_test_cases(
            application_name=application_name,
            platform=platform,
            target=target_url,
            user_prompt=prompt,
            max_cases=max_cases,
            include_authenticated_snapshot=bool(login_email and login_password),
            login_email_selector=None,
            login_password_selector=None,
            login_submit_selector=None,
            min_steps_per_case=3,
            max_steps_per_case=18,
            include_negative_scenarios=include_negative,
            include_accessibility_checks=include_accessibility,
            include_api_validations=False,
            module_focus="",
            document_context=document_context,
            login_email=login_email,
            login_password=login_password,
        )

        cases_summary = [
            {
                "title": tc.title,
                "priority": tc.priority,
                "category": tc.category,
                "steps_count": len(tc.steps.splitlines()) if tc.steps else 0,
            }
            for tc in result.test_cases[:50]
        ]

        return {
            "total_generated": len(result.test_cases),
            "generation_mode": result.generation_mode,
            "provider": result.provider,
            "model": result.model,
            "cases": cases_summary,
        }


class ExecuteTestCaseTool(AgentTool):
    """Execute a Playwright test case against a web application."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="execute_test_case",
            description=(
                "Execute a single Playwright test case against a web application. "
                "Runs the compiled automation steps in a real browser, captures screenshots, "
                "and returns pass/fail results with detailed step and check outcomes."
            ),
            category=ToolCategory.TEST_EXECUTION,
            parameters=[
                ToolParameter(name="test_case_id", description="Database ID of the test case to execute.", type="integer"),
                ToolParameter(name="application_id", description="Database ID of the target application.", type="integer"),
                ToolParameter(
                    name="execution_mode",
                    description="How to run the test: 'background' (headless) or 'watch_live' (visible browser).",
                    type="string",
                    required=False,
                    default="background",
                    enum=["background", "watch_live"],
                ),
            ],
        )

    async def _execute(
        self,
        test_case_id: int,
        application_id: int,
        execution_mode: str = "background",
        **_: Any,
    ) -> dict[str, Any]:
        from app.core.database import SessionLocal
        from app.models.application import Application
        from app.models.test_case import TestCase
        from app.models.test_case_automation import TestCaseAutomation
        from app.schemas.execution import ExecutionRequest, Step, Check
        from app.services.test_execution import execute_web_target

        with SessionLocal() as db:
            app = db.get(Application, application_id)
            tc = db.get(TestCase, test_case_id)
            automation = db.get(TestCaseAutomation, test_case_id)

            if not app or not tc:
                raise ValueError(f"Application {application_id} or TestCase {test_case_id} not found")
            if not automation or not automation.steps:
                raise ValueError(f"TestCase {test_case_id} has no compiled automation steps")

            steps = [Step.model_validate(s) for s in automation.steps]
            checks = [Check.model_validate(c) for c in (automation.checks or [])]

            request = ExecutionRequest(
                target=app.url or "",
                steps=steps,
                checks=checks,
                execution_mode=execution_mode,
                headless=execution_mode == "background",
            )

        result = await execute_web_target(request, application_id=application_id)

        return {
            "status": result.status,
            "duration_ms": result.duration_ms,
            "steps_passed": sum(1 for s in (result.step_results or []) if s.passed),
            "steps_failed": sum(1 for s in (result.step_results or []) if not s.passed),
            "checks_passed": sum(1 for c in (result.checks or []) if c.passed),
            "checks_failed": sum(1 for c in (result.checks or []) if not c.passed),
            "failure_type": result.failure_type,
            "failure_summary": result.failure_summary,
            "error": result.error,
            "screenshot_count": len(result.artifacts or []),
        }


def create_testing_tools() -> list[AgentTool]:
    """Factory to create all testing tool instances."""
    return [
        GenerateTestCasesTool(),
        ExecuteTestCaseTool(),
    ]
