import asyncio

import pytest
import httpx

from app.models.integration_connection import IntegrationConnection
from app.services import integrations
from app.services.integration_secrets import decrypt_integration_secret, encrypt_integration_secret
from app.services.integrations import IntegrationClientError, JiraClient, QTestClient


def _jira_connection() -> IntegrationConnection:
    return IntegrationConnection(
        id=1,
        system="jira",
        name="QA Jira",
        base_url="https://jira.example.test",
        project_key="QA",
        auth_type="basic_api_token",
        username="qa@example.test",
        created_by=1,
    )


def _qtest_connection() -> IntegrationConnection:
    return IntegrationConnection(
        id=2,
        system="qtest",
        name="QA qTest",
        base_url="https://qtest.example.test",
        project_id="42",
        auth_type="bearer_token",
        created_by=1,
    )


def test_integration_secret_is_encrypted_and_round_trips() -> None:
    encrypted = encrypt_integration_secret("super-secret-token")

    assert encrypted != "super-secret-token"
    assert decrypt_integration_secret(encrypted) == "super-secret-token"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_read_only_client_rejects_mutating_methods(method: str) -> None:
    client = JiraClient(_jira_connection(), "token")

    with pytest.raises(IntegrationClientError, match="read-only"):
        asyncio.run(client._request(method, "https://jira.example.test/rest/api/3/issue"))


def test_jira_connection_validation_uses_only_get_requests(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_request(self, method, url, **kwargs):
        calls.append(method)
        if url.endswith("/myself"):
            return {"displayName": "QA User", "accountId": "account-1"}
        if "/project/QA" in url:
            return {"name": "Quality"}
        return {"permissions": {"BROWSE_PROJECTS": {"havePermission": True}}}

    monkeypatch.setattr(JiraClient, "_request", fake_request)
    result = asyncio.run(JiraClient(_jira_connection(), "token").test_connection())

    assert calls == ["GET", "GET"]
    assert result.metadata["project_key"] == "QA"
    assert result.metadata["read_only"] is True


def test_jira_requirement_reads_are_bounded(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_request(self, method, url, **kwargs):
        calls.append((method, kwargs.get("params", {})))
        return {
            "total": 51,
            "issues": [{
                "id": "10001",
                "key": "QA-1",
                "fields": {
                    "summary": "Checkout requirement",
                    "description": "Customer can complete checkout.",
                    "issuetype": {"name": "Story"},
                    "status": {"name": "To Do"},
                    "labels": ["checkout"],
                    "components": [{"name": "Web"}],
                    "fixVersions": [{"name": "1.0"}],
                },
            }],
        }

    monkeypatch.setattr(JiraClient, "_request", fake_request)
    items, next_page = asyncio.run(JiraClient(_jira_connection(), "token").list_requirements(page=1, page_size=250))

    assert calls[0][0] == "GET"
    assert calls[0][1]["maxResults"] == 50
    assert items[0]["key"] == "QA-1"
    assert next_page == 2


def test_qtest_connection_and_asset_reads_are_get_only(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_request(self, method, url, **kwargs):
        calls.append(method)
        if url.endswith("/projects/42"):
            return {"id": 42, "name": "Quality"}
        return {"items": [{"id": 7, "name": "Checkout suite"}], "total": 1}

    monkeypatch.setattr(QTestClient, "_request", fake_request)
    client = QTestClient(_qtest_connection(), "token")
    test_result = asyncio.run(client.test_connection())
    items, next_page = asyncio.run(client.list_assets("test_suites", page=1, page_size=25))

    assert calls == ["GET", "GET"]
    assert test_result.metadata["project_id"] == "42"
    assert items == [{"id": 7, "name": "Checkout suite"}]
    assert next_page is None


def test_extract_jira_issue_key() -> None:
    assert integrations.extract_jira_issue_key("https://tractorsupplycompany.atlassian.net/browse/QA-37489") == "QA-37489"
    assert integrations.extract_jira_issue_key("https://company.atlassian.net/browse/PROJ-123?param=value") == "PROJ-123"
    assert integrations.extract_jira_issue_key("QA-37489") == "QA-37489"
    assert integrations.extract_jira_issue_key("  qa-999  ") == "QA-999"
    assert integrations.extract_jira_issue_key("invalid-string-no-digits") is None
    assert integrations.extract_jira_issue_key("") is None
    assert integrations.extract_jira_issue_key(None) is None


def test_adf_to_text() -> None:
    adf_doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "This is a paragraph."}],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Item 1"}]}],
                    },
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Item 2"}]}],
                    },
                ],
            },
        ],
    }
    text = integrations._adf_to_text(adf_doc)
    assert "This is a paragraph." in text
    assert "- Item 1" in text
    assert "- Item 2" in text


def test_jira_get_issue_normalizes_data_and_context(monkeypatch) -> None:
    async def fake_request(self, method, url, **kwargs):
        assert "QA-37489" in url
        return {
            "id": "353807",
            "key": "QA-37489",
            "fields": {
                "summary": 'Receiving "No STO" message with Status = "P"',
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "While in SAP in ZMBOP_SUB_STG table, we are seeing instances where Status = P.",
                                }
                            ],
                        }
                    ],
                },
                "issuetype": {"name": "Defect"},
                "status": {"name": "Assigned"},
                "priority": {"name": "Minor"},
                "labels": ["3PLEnablement", "DS_Phase1"],
                "components": [{"name": "SupplyChain"}],
                "assignee": {"displayName": "Vinod Bathula"},
                "reporter": {"displayName": "Adam Lang"},
                "customfield_10010": "STO must be generated when delivery date is valid.",
                "comment": {
                    "comments": [
                        {
                            "author": {"displayName": "Tester User"},
                            "body": "Verified in staging environment.",
                        }
                    ]
                },
            },
            "names": {
                "customfield_10010": "Acceptance Criteria",
            },
        }

    monkeypatch.setattr(JiraClient, "_request", fake_request)
    client = JiraClient(_jira_connection(), "token")
    issue = asyncio.run(client.get_issue("https://tractorsupplycompany.atlassian.net/browse/QA-37489"))

    assert issue["key"] == "QA-37489"
    assert issue["summary"] == 'Receiving "No STO" message with Status = "P"'
    assert "While in SAP" in issue["description"]
    assert issue["issue_type"] == "Defect"
    assert issue["status"] == "Assigned"
    assert issue["priority"] == "Minor"
    assert issue["assignee"] == "Vinod Bathula"
    assert issue["reporter"] == "Adam Lang"
    assert issue["acceptance_criteria"] == "STO must be generated when delivery date is valid."
    assert "Tester User: Verified in staging environment." in issue["comments"][0]
    assert "### JIRA ISSUE: QA-37489" in issue["context_text"]
    assert "Acceptance Criteria:" in issue["context_text"]


def test_external_redirects_and_oversized_responses_are_rejected(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, content: bytes) -> None:
            self.status_code = status_code
            self.content = content

        def json(self):
            return {}

    class FakeClient:
        response = FakeResponse(302, b"")

        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def request(self, *args, **kwargs):
            return self.response

    monkeypatch.setattr(integrations.httpx, "AsyncClient", FakeClient)
    client = JiraClient(_jira_connection(), "super-secret-token")

    with pytest.raises(IntegrationClientError, match="redirect"):
        asyncio.run(client._request("GET", "https://jira.example.test/rest/api/3/myself"))

    FakeClient.response = FakeResponse(200, b"x" * (integrations.MAX_EXTERNAL_RESPONSE_BYTES + 1))
    with pytest.raises(IntegrationClientError, match="size limit"):
        asyncio.run(client._request("GET", "https://jira.example.test/rest/api/3/myself"))


def test_external_network_errors_do_not_expose_credentials(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def request(self, *args, **kwargs):
            raise httpx.ConnectError("upstream rejected super-secret-token", request=httpx.Request("GET", args[1]))

    monkeypatch.setattr(integrations.httpx, "AsyncClient", FakeClient)

    with pytest.raises(IntegrationClientError) as error:
        asyncio.run(JiraClient(_jira_connection(), "super-secret-token")._request("GET", "https://jira.example.test/rest/api/3/myself"))

    assert "super-secret-token" not in str(error.value)
