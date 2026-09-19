import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.models.integration_connection import IntegrationConnection


MAX_EXTERNAL_RESPONSE_BYTES = settings.INTEGRATION_MAX_RESPONSE_BYTES
MAX_ASSET_ITEMS = settings.INTEGRATION_MAX_ASSET_ITEMS
EXTERNAL_TIMEOUT_SECONDS = settings.INTEGRATION_TIMEOUT_SECONDS


class IntegrationClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class IntegrationTestResult:
    message: str
    metadata: dict[str, Any]


def _safe_text(value: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def extract_jira_issue_key(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    match = re.search(r"(?:/browse/|[A-Za-z0-9_]+-)?([A-Za-z][A-Za-z0-9_]*-\d+)", raw)
    if match:
        return match.group(1).upper()
    direct_match = re.search(r"\b([A-Za-z][A-Za-z0-9_]*-\d+)\b", raw)
    if direct_match:
        return direct_match.group(1).upper()
    return None


def _adf_to_text(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_adf_to_text(child) for child in node)
    if isinstance(node, dict):
        node_type = str(node.get("type") or "")
        content = node.get("content") or []
        if node_type == "text":
            return str(node.get("text") or "")
        if node_type == "paragraph":
            inner = "".join(_adf_to_text(child) for child in content).strip()
            return f"{inner}\n\n" if inner else "\n"
        if node_type == "heading":
            level = min(6, max(1, int(node.get("attrs", {}).get("level", 3))))
            inner = "".join(_adf_to_text(child) for child in content).strip()
            return f"{'#' * level} {inner}\n\n"
        if node_type in {"bulletList", "orderedList"}:
            items = []
            for i, child in enumerate(content, start=1):
                child_text = _adf_to_text(child).strip()
                prefix = f"{i}. " if node_type == "orderedList" else "- "
                if child_text:
                    items.append(f"{prefix}{child_text}")
            return "\n".join(items) + "\n\n" if items else ""
        if node_type == "listItem":
            return "".join(_adf_to_text(child) for child in content)
        if node_type == "codeBlock":
            lang = str(node.get("attrs", {}).get("language") or "")
            code = "".join(_adf_to_text(child) for child in content)
            return f"```{lang}\n{code}\n```\n\n"
        if node_type in {"hardBreak", "rule"}:
            return "\n"
        if content:
            return "".join(_adf_to_text(child) for child in content)
    return ""


def _bounded_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = payload.get("items") or payload.get("results") or payload.get("data") or payload.get("issues") or []
    else:
        raw_items = []
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items[:MAX_ASSET_ITEMS] if isinstance(item, dict)]


class IntegrationClient:
    def __init__(self, connection: IntegrationConnection, credential: str) -> None:
        self.connection = connection
        self.credential = credential

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if settings.INTEGRATION_USER_AGENT:
            headers["User-Agent"] = settings.INTEGRATION_USER_AGENT
        return headers

    def _auth(self) -> httpx.Auth | None:
        username = self.connection.username or (settings.JIRA_EMAIL if self.connection.system == "jira" else "")
        if self.connection.auth_type == "basic_api_token":
            if not username:
                raise IntegrationClientError("Username is required for basic API-token authentication")
            return httpx.BasicAuth(username, self.credential)
        if self.connection.auth_type == "api_token" and username:
            return httpx.BasicAuth(username, self.credential)
        return None

    def _authorization_headers(self) -> dict[str, str]:
        if self.connection.auth_type in {"bearer_token", "api_token"} and not self.connection.username:
            return {"Authorization": f"Bearer {self.credential}"}
        return {}

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_method = method.upper()
        if normalized_method not in {"GET", "HEAD"}:
            raise IntegrationClientError("This integration operation allows read-only GET or HEAD requests")
        headers = {**self._headers(), **self._authorization_headers()}
        auth = self._auth()
        try:
            async with httpx.AsyncClient(timeout=EXTERNAL_TIMEOUT_SECONDS, follow_redirects=False) as client:
                response = await client.request(normalized_method, url, params=params, headers=headers, auth=auth)
        except httpx.HTTPError as error:
            raise IntegrationClientError(f"Unable to reach {self.connection.system} endpoint") from error
        if 300 <= response.status_code < 400:
            raise IntegrationClientError(f"{self.connection.system} endpoint returned an unexpected redirect", status_code=response.status_code)
        if len(response.content) > MAX_EXTERNAL_RESPONSE_BYTES:
            raise IntegrationClientError(f"{self.connection.system} response exceeded the configured size limit", status_code=response.status_code)
        if response.status_code >= 400:
            raise IntegrationClientError(
                f"{self.connection.system} returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        if normalized_method == "HEAD" or not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as error:
            raise IntegrationClientError(f"{self.connection.system} returned an invalid JSON response") from error
        if not isinstance(payload, dict):
            raise IntegrationClientError(f"{self.connection.system} returned an unsupported response shape")
        return payload


class JiraClient(IntegrationClient):
    def __init__(self, connection: IntegrationConnection, credential: str) -> None:
        super().__init__(connection, credential)
        base_url = (connection.base_url or settings.JIRA_BASE_URL).rstrip("/")
        for suffix in ("/rest/api/3", "/rest/api/2"):
            if base_url.lower().endswith(suffix):
                base_url = base_url[: -len(suffix)]
        self.base_url = base_url
        self.project_key = (connection.project_key or settings.JIRA_PROJECT_KEY).strip()
        self.environment_backed = connection.created_by == 0 and connection.id < 0

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    async def test_connection(self) -> IntegrationTestResult:
        user = await self._request("GET", self._url("rest/api/3/myself"))
        project: dict[str, Any] = {}
        if self.project_key:
            project = await self._request("GET", self._url(f"rest/api/3/project/{quote(self.project_key, safe='')}"))
        return IntegrationTestResult(
            message=f"Jira read-only connection verified{f' for project {self.project_key}' if self.project_key else ''}.",
            metadata={
                "account": _safe_text(user.get("displayName") or user.get("emailAddress") or user.get("accountId"), 160),
                "project": _safe_text(project.get("name") or self.project_key, 200),
                "project_key": self.project_key,
                "read_only": True,
            },
        )

    async def list_requirements(self, *, page: int, page_size: int) -> tuple[list[dict[str, Any]], int | None]:
        safe_page = max(1, page)
        safe_size = max(1, min(50, page_size))
        filter_id = os.environ.get("JIRA_FILTER_ID", settings.JIRA_FILTER_ID).strip()
        use_environment_filter = self.environment_backed and filter_id.isdigit()
        if not self.project_key and not use_environment_filter:
            raise IntegrationClientError("Jira project key or numeric JIRA_FILTER_ID is not configured")
        jql_query = (
            f"filter = {filter_id} ORDER BY updated DESC"
            if use_environment_filter
            else f"project = {self.project_key} ORDER BY updated DESC"
        )
        try:
            payload = await self._request(
                "GET",
                self._url("rest/api/3/search/jql"),
                params={
                    "jql": jql_query,
                    "maxResults": safe_size,
                    "fields": "summary,description,issuetype,status,priority,labels,components,fixVersions,project,created,updated",
                },
            )
        except IntegrationClientError as error:
            if getattr(error, "status_code", None) in {400, 404, 410}:
                payload = await self._request(
                    "GET",
                    self._url("rest/api/3/search"),
                    params={
                        "jql": jql_query,
                        "startAt": (safe_page - 1) * safe_size,
                        "maxResults": safe_size,
                        "fields": "summary,description,issuetype,status,priority,labels,components,fixVersions,project,created,updated",
                    },
                )
            else:
                raise
        items: list[dict[str, Any]] = []
        for issue in _bounded_items(payload):
            fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
            items.append(
                {
                    "id": _safe_text(issue.get("id"), 120),
                    "key": _safe_text(issue.get("key"), 120),
                    "summary": _safe_text(fields.get("summary"), 500),
                    "description": _safe_text(fields.get("description"), 2000),
                    "issue_type": _safe_text((fields.get("issuetype") or {}).get("name"), 120),
                    "status": _safe_text((fields.get("status") or {}).get("name"), 120),
                    "priority": _safe_text((fields.get("priority") or {}).get("name"), 120),
                    "labels": [_safe_text(value, 120) for value in (fields.get("labels") or [])[:20]],
                    "components": [_safe_text(item.get("name"), 120) for item in (fields.get("components") or [])[:20] if isinstance(item, dict)],
                    "fix_versions": [_safe_text(item.get("name"), 120) for item in (fields.get("fixVersions") or [])[:20] if isinstance(item, dict)],
                    "created": _safe_text(fields.get("created"), 80),
                    "updated": _safe_text(fields.get("updated"), 80),
                }
            )
        total = payload.get("total")
        next_page = safe_page + 1 if isinstance(total, int) and safe_page * safe_size < total else None
        return items, next_page

    def _extract_acceptance_criteria(self, fields: dict[str, Any], names: dict[str, str]) -> str | None:
        for field_id, field_val in fields.items():
            if not field_val:
                continue
            field_name = (names.get(field_id) or field_id).lower().replace("_", " ").strip()
            if any(term in field_name for term in ("acceptance criteria", "acceptance criterion", "acceptance-criteria", "validation criteria", "acceptance")):
                if isinstance(field_val, (dict, list)):
                    parsed = _adf_to_text(field_val).strip()
                    if parsed:
                        return parsed
                elif isinstance(field_val, str) and field_val.strip():
                    return field_val.strip()
        return None

    def _extract_recent_comments(self, fields: dict[str, Any]) -> list[str]:
        comment_obj = fields.get("comment")
        if not isinstance(comment_obj, dict):
            return []
        comments_list = comment_obj.get("comments")
        if not isinstance(comments_list, list):
            return []
        extracted = []
        for c in comments_list[-5:]:
            if not isinstance(c, dict):
                continue
            author = (c.get("author") or {}).get("displayName") or "User"
            body = c.get("body")
            body_text = _adf_to_text(body).strip() if isinstance(body, (dict, list)) else _safe_text(body, 500)
            if body_text:
                extracted.append(f"{author}: {body_text}")
        return extracted

    def _normalize_issue(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = _safe_text(payload.get("key"), 120)
        issue_id = _safe_text(payload.get("id"), 120)
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        rendered = payload.get("renderedFields") if isinstance(payload.get("renderedFields"), dict) else {}
        names = payload.get("names") if isinstance(payload.get("names"), dict) else {}

        summary = _safe_text(fields.get("summary"), 500)
        raw_desc = fields.get("description")
        if isinstance(raw_desc, (dict, list)):
            description = _adf_to_text(raw_desc).strip()
        elif raw_desc:
            description = _safe_text(raw_desc, 5000)
        else:
            description = _safe_text(rendered.get("description"), 5000)

        issue_type = _safe_text((fields.get("issuetype") or {}).get("name"), 120) or None
        status = _safe_text((fields.get("status") or {}).get("name"), 120) or None
        priority = _safe_text((fields.get("priority") or {}).get("name"), 120) or None
        labels = [_safe_text(v, 120) for v in (fields.get("labels") or []) if v][:20]
        components = [_safe_text(item.get("name"), 120) for item in (fields.get("components") or []) if isinstance(item, dict) and item.get("name")][:20]
        fix_versions = [_safe_text(item.get("name"), 120) for item in (fields.get("fixVersions") or []) if isinstance(item, dict) and item.get("name")][:20]
        assignee = _safe_text((fields.get("assignee") or {}).get("displayName"), 160) or None
        reporter = _safe_text((fields.get("reporter") or {}).get("displayName"), 160) or None
        url = f"{self.base_url}/browse/{key}" if key else None
        acceptance_criteria = self._extract_acceptance_criteria(fields, names)
        comments = self._extract_recent_comments(fields)

        context_lines = [
            f"### JIRA ISSUE: {key} - {summary}",
            f"- **Key:** {key}",
            f"- **Type:** {issue_type or 'Unknown'}",
            f"- **Status:** {status or 'Unknown'}",
            f"- **Priority:** {priority or 'None'}",
            f"- **Assignee:** {assignee or 'Unassigned'}",
            f"- **Reporter:** {reporter or 'None'}",
        ]
        if labels:
            context_lines.append(f"- **Labels:** {', '.join(labels)}")
        if components:
            context_lines.append(f"- **Components:** {', '.join(components)}")
        if url:
            context_lines.append(f"- **Direct Link:** {url}")
        context_lines.append(f"\n#### Summary & Goal:\n{summary}")
        if description:
            context_lines.append(f"\n#### Description & Business Context:\n{description}")
        if acceptance_criteria:
            context_lines.append(f"\n#### Acceptance Criteria:\n{acceptance_criteria}")
        if comments:
            context_lines.append("\n#### Recent Discussion / Notes:")
            for c in comments:
                context_lines.append(f"- {c}")

        context_text = "\n".join(context_lines)

        return {
            "key": key,
            "id": issue_id or None,
            "summary": summary,
            "description": description or None,
            "issue_type": issue_type,
            "status": status,
            "priority": priority,
            "labels": labels,
            "components": components,
            "fix_versions": fix_versions,
            "assignee": assignee,
            "reporter": reporter,
            "url": url,
            "acceptance_criteria": acceptance_criteria,
            "comments": comments,
            "context_text": context_text,
            "connection_id": self.connection.id,
            "read_only": True,
        }

    async def get_issue(self, issue_key_or_url: str) -> dict[str, Any]:
        key = extract_jira_issue_key(issue_key_or_url)
        if not key:
            raise IntegrationClientError(f"Could not extract a valid Jira issue key from '{issue_key_or_url}'")
        payload = await self._request(
            "GET",
            self._url(f"rest/api/3/issue/{quote(key, safe='')}"),
            params={"fields": "*all", "expand": "renderedFields,names"},
        )
        return self._normalize_issue(payload)

    async def create_defect(
        self,
        *,
        summary: str,
        description: str,
        project_key: str | None = None,
        issue_type: str = "Bug",
        priority: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        target_project = (project_key or self.project_key).strip()
        if not target_project:
            raise IntegrationClientError("Jira project key is required to log a defect")
        payload = {
            "fields": {
                "project": {"key": target_project},
                "summary": summary[:250],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description[:30000]}],
                        }
                    ],
                },
                "issuetype": {"name": issue_type or "Bug"},
            }
        }
        if priority:
            payload["fields"]["priority"] = {"name": priority}
        if labels:
            payload["fields"]["labels"] = [re.sub(r"\s+", "_", str(l)) for l in labels if l]

        try:
            res = await self._request("POST", self._url("rest/api/3/issue"), json=payload)
        except IntegrationClientError as error:
            if getattr(error, "status_code", None) in {400, 404}:
                payload_v2 = {
                    "fields": {
                        "project": {"key": target_project},
                        "summary": summary[:250],
                        "description": description[:30000],
                        "issuetype": {"name": issue_type or "Bug"},
                    }
                }
                if priority:
                    payload_v2["fields"]["priority"] = {"name": priority}
                if labels:
                    payload_v2["fields"]["labels"] = [re.sub(r"\s+", "_", str(l)) for l in labels if l]
                res = await self._request("POST", self._url("rest/api/2/issue"), json=payload_v2)
            else:
                raise
        return {
            "id": res.get("id"),
            "key": res.get("key"),
            "url": f"{self.base_url}/browse/{res.get('key')}" if res.get("key") else None,
        }

class QTestClient(IntegrationClient):
    def __init__(self, connection: IntegrationConnection, credential: str) -> None:
        super().__init__(connection, credential)
        base_url = (connection.base_url or settings.QTEST_BASE_URL).rstrip("/")
        self.base_url = base_url[:-7] if base_url.lower().endswith("/api/v3") else base_url

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v3/{path.lstrip('/')}"

    async def _project_id(self) -> str:
        if self.connection.project_id or settings.QTEST_PROJECT_ID:
            return self.connection.project_id or settings.QTEST_PROJECT_ID
        payload = await self._request(
            "GET",
            self._url("projects"),
            params={"page": 1, "size": 50, "search": self.connection.project_name or settings.QTEST_PROJECT_NAME},
        )
        for item in _bounded_items(payload):
            if _safe_text(item.get("name"), 200).casefold() == (self.connection.project_name or settings.QTEST_PROJECT_NAME).casefold():
                project_id = _safe_text(item.get("id"), 120)
                if project_id:
                    return project_id
        raise IntegrationClientError("qTest project could not be found by name")

    async def test_connection(self) -> IntegrationTestResult:
        project_id = await self._project_id()
        project = await self._request("GET", self._url(f"projects/{quote(project_id, safe='')}"))
        return IntegrationTestResult(
            message=f"qTest connection verified for project {project_id}.",
            metadata={
                "project_id": project_id,
                "project_name": _safe_text(project.get("name") or self.connection.project_name or settings.QTEST_PROJECT_NAME, 200),
            },
        )

    async def list_assets(self, asset_type: str, *, page: int, page_size: int) -> tuple[list[dict[str, Any]], int | None]:
        project_id = await self._project_id()
        safe_page = max(1, page)
        safe_size = max(1, min(50, page_size))
        path_map = {
            "requirements": "requirements",
            "modules": "modules",
            "releases": "releases",
            "cycles": "test-cycles",
            "test_suites": "test-suites",
            "test_cases": "test-cases",
            "test_runs": "test-runs",
            "test_logs": "test-logs",
        }
        if asset_type == "metadata":
            payload = await self._request("GET", self._url(f"projects/{quote(project_id, safe='')}"))
            return [payload], None
        payload = await self._request(
            "GET",
            self._url(f"projects/{quote(project_id, safe='')}/{path_map[asset_type]}"),
            params={"page": safe_page, "size": safe_size},
        )
        items = _bounded_items(payload)
        total = payload.get("total")
        next_page = safe_page + 1 if isinstance(total, int) and safe_page * safe_size < total else None
        return items, next_page

    async def create_defect(
        self,
        *,
        summary: str,
        description: str,
        severity: str | None = None,
    ) -> dict[str, Any]:
        project_id = await self._project_id()
        payload = {
            "properties": [
                {"field_name": "Summary", "field_value": summary[:250]},
                {"field_name": "Description", "field_value": description[:10000]},
            ]
        }
        res = await self._request("POST", self._url(f"projects/{quote(str(project_id), safe='')}/defects"), json=payload)
        defect_id = str(res.get("id") or "")
        return {
            "id": defect_id,
            "key": f"QTEST-{defect_id}" if defect_id else "QTEST-DEFECT",
            "url": f"{self.base_url}/p/{project_id}/portal/project#tab=defects&object=4&id={defect_id}" if defect_id else None,
        }
