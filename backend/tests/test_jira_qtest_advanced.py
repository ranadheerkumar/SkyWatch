"""Comprehensive unit and contract tests for Advanced Jira v3 & Tricentis qTest Integration."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.models.integration_connection import IntegrationConnection
from app.services.integrations import (
    ADFBuilder,
    IntegrationClientError,
    JiraClient,
    QTestClient,
)
from app.services.integration_secrets import encrypt_integration_secret


def _mock_jira_conn() -> IntegrationConnection:
    return IntegrationConnection(
        id=1,
        system="jira",
        name="Jira Cloud Production",
        base_url="https://company.atlassian.net",
        project_key="SKY",
        auth_type="basic_api_token",
        username="qa@company.com",
        encrypted_secret=encrypt_integration_secret("jira-test-token"),
        status="active",
        created_by=1,
    )


def _mock_qtest_conn() -> IntegrationConnection:
    return IntegrationConnection(
        id=2,
        system="qtest",
        name="qTest SaaS",
        base_url="https://company.qtestnet.com",
        project_id="12345",
        project_name="SkyWatch Project",
        auth_type="bearer_token",
        encrypted_secret=encrypt_integration_secret("qtest-test-token"),
        status="active",
        created_by=1,
    )


# ---------------------------------------------------------------------------
# ADFBuilder Tests
# ---------------------------------------------------------------------------


def test_adf_builder_paragraph():
    node = ADFBuilder.paragraph("Hello world")
    assert node["type"] == "paragraph"
    assert node["content"][0]["text"] == "Hello world"


def test_adf_builder_heading():
    node = ADFBuilder.heading("Architecture Review", level=2)
    assert node["type"] == "heading"
    assert node["attrs"]["level"] == 2
    assert node["content"][0]["text"] == "Architecture Review"


def test_adf_builder_panel():
    node = ADFBuilder.panel("Critical visual delta detected", panel_type="error")
    assert node["type"] == "panel"
    assert node["attrs"]["panelType"] == "error"
    assert node["content"][0]["content"][0]["text"] == "Critical visual delta detected"


def test_adf_builder_code_block():
    node = ADFBuilder.code_block('{"status": 500}', language="json")
    assert node["type"] == "codeBlock"
    assert node["attrs"]["language"] == "json"
    assert '{"status": 500}' in node["content"][0]["text"]


def test_adf_builder_table():
    headers = ["#", "Action", "Expected"]
    rows = [["1", "Click login", "Redirected to /dashboard"]]
    table = ADFBuilder.table(headers, rows)
    assert table["type"] == "table"
    assert len(table["content"]) == 2  # header row + 1 data row


def test_adf_builder_full_defect_doc():
    doc = ADFBuilder.build_defect_doc(
        summary="Login button layout shift",
        description="Visual baseline comparison failed with 4.2% pixel diff.",
        steps=[{"action": "Navigate to /login", "expected": "Button at (120, 300)"}],
        expected="Button aligned to grid",
        actual="Button overlapping input field",
        stack_trace="AssertionError: pixel diff 4.2% exceeds threshold 0.5%",
        metadata={"viewport": "1920x1080", "route": "/login"},
    )
    assert doc["type"] == "doc"
    assert doc["version"] == 1
    assert len(doc["content"]) >= 5
    # Contains panel, description, steps table, results table, code block
    types = [item["type"] for item in doc["content"]]
    assert "panel" in types
    assert "table" in types
    assert "codeBlock" in types


# ---------------------------------------------------------------------------
# JiraClient Advanced Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jira_create_defect_with_rich_adf():
    client = JiraClient(_mock_jira_conn(), "api-token-123")

    captured_requests = []

    async def fake_request(method, url, **kwargs):
        captured_requests.append((method, url, kwargs))
        return {"id": "10050", "key": "SKY-100"}

    with patch.object(client, "_request", side_effect=fake_request):
        result = await client.create_defect(
            summary="API contract violation on /auth/token",
            description="Unexpected 500 internal server error",
            steps=[{"action": "POST /auth/token", "expected": "200 with JWT"}],
            expected="200 OK",
            actual="500 Internal Error",
            stack_trace="InternalServerError: database lock",
            priority="High",
            labels=["automated-qa", "api-regression"],
        )

    assert result["id"] == "10050"
    assert result["key"] == "SKY-100"
    assert len(captured_requests) == 1
    method, url, kwargs = captured_requests[0]
    assert method == "POST"
    assert url.endswith("/rest/api/3/issue")
    json_payload = kwargs["json"]
    assert json_payload["fields"]["project"]["key"] == "SKY"
    assert json_payload["fields"]["description"]["type"] == "doc"
    assert json_payload["fields"]["priority"]["name"] == "High"
    assert "api-regression" in json_payload["fields"]["labels"]


@pytest.mark.asyncio
async def test_jira_upload_attachment():
    client = JiraClient(_mock_jira_conn(), "api-token-123")

    async def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/rest/api/3/issue/SKY-100/attachments")
        assert kwargs.get("extra_headers") == {"X-Atlassian-Token": "no-check"}
        assert "file" in kwargs.get("files", {})
        return {
            "items": [
                {
                    "id": "2001",
                    "filename": "diff_snapshot.png",
                    "size": 1024,
                    "content": "https://company.atlassian.net/attachments/2001",
                }
            ]
        }

    with patch.object(client, "_request", side_effect=fake_request):
        res = await client.upload_attachment(
            issue_key="SKY-100",
            filename="diff_snapshot.png",
            content=b"\x89PNGfakeimagebytes",
            content_type="image/png",
        )

    assert res["id"] == "2001"
    assert res["filename"] == "diff_snapshot.png"
    assert res["url"] == "https://company.atlassian.net/attachments/2001"


@pytest.mark.asyncio
async def test_jira_link_issues():
    client = JiraClient(_mock_jira_conn(), "api-token-123")

    async def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/rest/api/3/issueLink")
        payload = kwargs.get("json")
        assert payload["type"]["name"] == "Blocks"
        assert payload["inwardIssue"]["key"] == "SKY-100"
        assert payload["outwardIssue"]["key"] == "SKY-42"
        return {}

    with patch.object(client, "_request", side_effect=fake_request):
        res = await client.link_issues(
            inward_key="SKY-100",
            outward_key="SKY-42",
            link_type="Blocks",
            comment="Linked autonomously by SkyWatch",
        )

    assert res["status"] == "linked"
    assert res["inward"] == "SKY-100"
    assert res["outward"] == "SKY-42"


@pytest.mark.asyncio
async def test_jira_get_transitions():
    client = JiraClient(_mock_jira_conn(), "api-token-123")

    async def fake_request(method, url, **kwargs):
        return {
            "transitions": [
                {"id": "11", "name": "To Do", "to": {"name": "Backlog"}},
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
                {"id": "31", "name": "Resolve Issue", "to": {"name": "Resolved"}},
            ]
        }

    with patch.object(client, "_request", side_effect=fake_request):
        transitions = await client.get_transitions("SKY-100")

    assert len(transitions) == 3
    assert transitions[2]["id"] == "31"
    assert transitions[2]["name"] == "Resolve Issue"


@pytest.mark.asyncio
async def test_jira_transition_issue():
    client = JiraClient(_mock_jira_conn(), "api-token-123")

    async def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/rest/api/3/issue/SKY-100/transitions")
        payload = kwargs.get("json")
        assert payload["transition"]["id"] == "31"
        return {}

    with patch.object(client, "_request", side_effect=fake_request):
        res = await client.transition_issue(
            "SKY-100",
            transition_id="31",
            comment="Verified resolved by SkyWatch campaign #12.",
        )

    assert res["status"] == "transitioned"
    assert res["issue_key"] == "SKY-100"
    assert res["transition_id"] == "31"


@pytest.mark.asyncio
async def test_jira_add_comment():
    client = JiraClient(_mock_jira_conn(), "api-token-123")

    async def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/rest/api/3/issue/SKY-100/comment")
        return {"id": "9001", "created": "2026-09-19T12:00:00Z"}

    with patch.object(client, "_request", side_effect=fake_request):
        res = await client.add_comment("SKY-100", "Autonomous test run completed: 100% pass.")

    assert res["id"] == "9001"
    assert res["issue_key"] == "SKY-100"


# ---------------------------------------------------------------------------
# QTestClient Advanced Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qtest_get_build_fields():
    client = QTestClient(_mock_qtest_conn(), "token-qtest")

    async def fake_request(method, url, **kwargs):
        assert url.endswith("/settings/builds/fields")
        return [
            {"id": -65, "label": "Status", "original_name": "Status"},
            {"id": -66, "label": "Build Date", "original_name": "Build Date"},
            {"id": -67, "label": "Build Note", "original_name": "Note"},
        ]

    with patch.object(client, "_request", side_effect=fake_request):
        fields = await client.get_build_fields()

    assert len(fields) == 3
    assert fields[0]["label"] == "Status"


@pytest.mark.asyncio
async def test_qtest_get_builds_under_release():
    client = QTestClient(_mock_qtest_conn(), "token-qtest")

    async def fake_request(method, url, **kwargs):
        assert url.endswith("/builds")
        assert kwargs.get("params", {}).get("releaseId") == "62218"
        return [
            {"id": 131516, "name": "Build 1.0", "pid": "BL-29"},
            {"id": 131517, "name": "Build 1.1", "pid": "BL-30"},
        ]

    with patch.object(client, "_request", side_effect=fake_request):
        builds = await client.get_builds(62218)

    assert len(builds) == 2
    assert builds[0]["name"] == "Build 1.0"


@pytest.mark.asyncio
async def test_qtest_create_build():
    client = QTestClient(_mock_qtest_conn(), "token-qtest")

    async def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/builds")
        payload = kwargs.get("json")
        assert payload["name"] == "SkyWatch-CI-2026.09.19"
        assert payload["release"]["id"] == 62218
        assert payload["properties"][0]["field_name"] == "Note"
        return {"id": 131599, "name": "SkyWatch-CI-2026.09.19", "pid": "BL-45"}

    with patch.object(client, "_request", side_effect=fake_request):
        res = await client.create_build(
            release_id=62218,
            build_name="SkyWatch-CI-2026.09.19",
            build_note="Automated test build from master branch",
        )

    assert res["id"] == 131599
    assert res["pid"] == "BL-45"
    assert res["name"] == "SkyWatch-CI-2026.09.19"


@pytest.mark.asyncio
async def test_qtest_submit_auto_test_log():
    client = QTestClient(_mock_qtest_conn(), "token-qtest")

    async def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert "/test-runs/5544/auto-test-logs" in url
        payload = kwargs.get("json")
        assert payload["status"] == "PASSED"
        assert len(payload["test_step_logs"]) == 2
        return {"id": 88001}

    with patch.object(client, "_request", side_effect=fake_request):
        res = await client.submit_auto_test_log(
            test_run_id=5544,
            status="PASSED",
            start_time="2026-09-19T12:00:00Z",
            end_time="2026-09-19T12:01:30Z",
            name="Smoke Suite - Authentication",
            steps=[
                {"description": "Navigate to login", "expected": "Form shown", "actual": "Form rendered", "status": "PASSED"},
                {"description": "Submit credentials", "expected": "Token issued", "actual": "Token issued", "status": "PASSED"},
            ],
        )

    assert res["id"] == 88001
    assert res["status"] == "PASSED"


@pytest.mark.asyncio
async def test_qtest_export_test_case():
    client = QTestClient(_mock_qtest_conn(), "token-qtest")

    async def fake_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/test-cases")
        payload = kwargs.get("json")
        assert payload["name"] == "Verify Token Refresh"
        assert len(payload["test_steps"]) == 1
        return {"id": 99001, "name": "Verify Token Refresh", "pid": "TC-123"}

    with patch.object(client, "_request", side_effect=fake_request):
        res = await client.export_test_case(
            name="Verify Token Refresh",
            description="Autonomous token refresh validation",
            steps=[{"description": "POST /auth/refresh with token", "expected": "200 new token"}],
            parent_id=7766,
        )

    assert res["id"] == 99001
    assert res["pid"] == "TC-123"


# ---------------------------------------------------------------------------
# API Route Tests (FastAPI TestClient)
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api.dependencies import current_user, get_db
from app.api.v1.integrations import router as integrations_router
from app.core.database import Base
from app.models.user import User


@pytest.fixture()
def api_test_setup():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()
    user = User(email="tester@company.com", password_hash="hash", role="admin")
    jira_conn = _mock_jira_conn()
    qtest_conn = _mock_qtest_conn()
    db.add_all([user, jira_conn, qtest_conn])
    db.commit()

    app = FastAPI()
    app.include_router(integrations_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: user

    client = TestClient(app)
    return client, db


def test_api_upload_jira_attachment(api_test_setup):
    client, db = api_test_setup

    async def fake_upload(self, issue_key, filename, content, content_type):
        return {"id": "501", "filename": filename, "size": len(content)}

    with patch.object(JiraClient, "upload_attachment", fake_upload):
        response = client.post(
            "/integrations/jira/issues/SKY-100/attachments?connection_id=1",
            files={"file": ("screenshot.png", b"\x89PNGdata", "image/png")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "501"
    assert data["filename"] == "screenshot.png"


def test_api_create_jira_issue_link(api_test_setup):
    client, db = api_test_setup

    async def fake_link(self, inward_key, outward_key, link_type, comment=None):
        return {"status": "linked", "inward": inward_key, "outward": outward_key, "type": link_type}

    with patch.object(JiraClient, "link_issues", fake_link):
        response = client.post(
            "/integrations/jira/issues/SKY-100/links?connection_id=1",
            json={"outward_key": "SKY-50", "link_type": "Blocks"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "linked"
    assert data["inward"] == "SKY-100"
    assert data["outward"] == "SKY-50"


def test_api_jira_transitions(api_test_setup):
    client, db = api_test_setup

    async def fake_get_trans(self, issue_key):
        return [{"id": "31", "name": "Resolve", "to": "Resolved"}]

    async def fake_do_trans(self, issue_key, transition_id, comment=None):
        return {"status": "transitioned", "issue_key": issue_key, "transition_id": transition_id}

    with patch.object(JiraClient, "get_transitions", fake_get_trans), patch.object(JiraClient, "transition_issue", fake_do_trans):
        get_res = client.get("/integrations/jira/issues/SKY-100/transitions?connection_id=1")
        assert get_res.status_code == 200
        assert get_res.json()[0]["id"] == "31"

        post_res = client.post(
            "/integrations/jira/issues/SKY-100/transitions?connection_id=1",
            json={"transition_id": "31", "comment": "Fixed in build 42"},
        )
        assert post_res.status_code == 200
        assert post_res.json()["status"] == "transitioned"


def test_api_qtest_builds(api_test_setup):
    client, db = api_test_setup

    async def fake_get_builds(self, release_id):
        return [{"id": 131516, "name": "Build 1.0"}]

    async def fake_create_build(self, release_id, build_name, build_note=""):
        return {"id": 131599, "name": build_name, "release_id": release_id}

    with patch.object(QTestClient, "get_builds", fake_get_builds), patch.object(QTestClient, "create_build", fake_create_build):
        list_res = client.get("/integrations/qtest/builds?release_id=62218&connection_id=2")
        assert list_res.status_code == 200
        assert list_res.json()[0]["name"] == "Build 1.0"

        create_res = client.post(
            "/integrations/qtest/builds?connection_id=2",
            json={"release_id": "62218", "build_name": "SkyWatch-CI-1.2"},
        )
        assert create_res.status_code == 200
        assert create_res.json()["name"] == "SkyWatch-CI-1.2"


def test_api_webhooks(api_test_setup):
    client, _ = api_test_setup

    jira_res = client.post(
        "/integrations/webhooks/jira",
        json={"webhookEvent": "jira:issue_updated", "issue": {"key": "SKY-100"}},
    )
    assert jira_res.status_code == 200
    assert jira_res.json()["status"] == "received"
    assert jira_res.json()["issue_key"] == "SKY-100"

    qtest_res = client.post(
        "/integrations/webhooks/qtest",
        json={"event": "build_created", "project_id": 12345},
    )
    assert qtest_res.status_code == 200
    assert qtest_res.json()["status"] == "received"


