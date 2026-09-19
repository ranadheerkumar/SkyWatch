"""Integration tools for Jira and qTest wrapping existing integration services."""

from __future__ import annotations

import logging
from typing import Any

from app.agent.tool_base import AgentTool, ToolParameter, ToolSchema
from app.agent.types import ToolCategory

logger = logging.getLogger("ai-qa-engine.agent.tools.integrations")


class JiraSearchTool(AgentTool):
    """Search Jira issues for relevant defects, stories, or requirements."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="jira_search",
            description=(
                "Search Jira for issues matching a JQL query or text search. "
                "Returns issue keys, summaries, statuses, and descriptions. "
                "Useful for finding existing defects, user stories, or requirements."
            ),
            category=ToolCategory.INTEGRATION,
            parameters=[
                ToolParameter(name="query", description="JQL query or free-text search string.", type="string"),
                ToolParameter(
                    name="max_results",
                    description="Maximum number of results to return (default 20).",
                    type="integer",
                    required=False,
                    default=20,
                ),
            ],
        )

    async def _execute(self, query: str, max_results: int = 20, **_: Any) -> dict[str, Any]:
        from app.services.integrations import JiraClient

        client = JiraClient.from_environment()
        if client is None:
            return {"error": "Jira is not configured. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN."}

        issues = await client.search_issues(query, max_results=min(max_results, 50))
        return {
            "total": len(issues),
            "issues": [
                {
                    "key": issue.get("key"),
                    "summary": issue.get("fields", {}).get("summary"),
                    "status": issue.get("fields", {}).get("status", {}).get("name"),
                    "type": issue.get("fields", {}).get("issuetype", {}).get("name"),
                    "priority": issue.get("fields", {}).get("priority", {}).get("name"),
                }
                for issue in issues[:max_results]
            ],
        }


class QTestGetTestCasesTool(AgentTool):
    """Retrieve test cases from qTest for comparison or import."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="qtest_get_test_cases",
            description=(
                "Retrieve test cases from a qTest project. Returns test case names, "
                "descriptions, and step counts. Useful for comparing existing qTest "
                "coverage with generated test cases."
            ),
            category=ToolCategory.INTEGRATION,
            parameters=[
                ToolParameter(
                    name="module_id",
                    description="Optional qTest module ID to filter test cases.",
                    type="string",
                    required=False,
                ),
                ToolParameter(
                    name="max_results",
                    description="Maximum number of test cases to return (default 50).",
                    type="integer",
                    required=False,
                    default=50,
                ),
            ],
        )

    async def _execute(self, module_id: str | None = None, max_results: int = 50, **_: Any) -> dict[str, Any]:
        from app.services.integrations import QTestClient

        client = QTestClient.from_environment()
        if client is None:
            return {"error": "qTest is not configured. Set QTEST_BASE_URL, QTEST_TOKEN, and QTEST_PROJECT_ID."}

        cases = await client.get_test_cases(module_id=module_id, max_results=min(max_results, 100))
        return {
            "total": len(cases),
            "test_cases": [
                {
                    "id": tc.get("id"),
                    "name": tc.get("name"),
                    "description": (tc.get("description") or "")[:200],
                }
                for tc in cases[:max_results]
            ],
        }


def create_integration_tools() -> list[AgentTool]:
    """Factory to create all integration tool instances."""
    return [
        JiraSearchTool(),
        QTestGetTestCasesTool(),
    ]
