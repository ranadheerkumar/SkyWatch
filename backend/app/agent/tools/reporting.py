"""Reporting tool for agent runtime.

Allows the agent to generate application quality reports and markdown summaries.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.tool_base import AgentTool, ToolParameter, ToolSchema
from app.agent.types import ToolCategory

logger = logging.getLogger("ai-qa-engine.agent.tools.reporting")


class GenerateReportTool(AgentTool):
    """Generate a QA quality and release readiness report."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="generate_qa_report",
            description=(
                "Generate a comprehensive QA quality, pass rate, and release readiness report "
                "for an application. Returns quality scores, risk metrics, defect summaries, "
                "and formatted Markdown report."
            ),
            category=ToolCategory.REPORTING,
            parameters=[
                ToolParameter(
                    name="application_id",
                    description="Database ID of the application to generate report for.",
                    type="integer",
                ),
            ],
        )

    async def _execute(self, application_id: int, **_: Any) -> dict[str, Any]:
        from app.core.database import SessionLocal
        from app.services.report_service import ReportService

        with SessionLocal() as db:
            report_data = ReportService.generate_application_quality_report(
                application_id=application_id,
                db=db,
            )
            markdown = ReportService.format_as_markdown(report_data)

        return {
            "application_name": report_data.get("application_name"),
            "quality_score": report_data.get("metrics", {}).get("quality_score"),
            "risk_score": report_data.get("metrics", {}).get("risk_score"),
            "release_readiness": report_data.get("metrics", {}).get("release_readiness"),
            "pass_rate_percent": report_data.get("metrics", {}).get("pass_rate_percent"),
            "total_test_cases": report_data.get("metrics", {}).get("total_test_cases"),
            "open_defects": report_data.get("metrics", {}).get("open_defects_count"),
            "markdown_report": markdown,
        }


def create_reporting_tools() -> list[AgentTool]:
    """Factory to create all reporting tool instances."""
    return [
        GenerateReportTool(),
    ]
