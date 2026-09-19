import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.api.dependencies import current_user
from app.api.v1.integrations import router
from app.core.database import Base, get_db
from app.models.application import Application
from app.models.defect import Defect
from app.models.integration_connection import IntegrationConnection
from app.models.test_case import TestCase
from app.models.user import User
from app.services import integration_service
from app.services.integrations import JiraClient


@pytest.fixture()
def integration_api() -> tuple[TestClient, Session, User, Application, Defect, TestCase]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()
    user = User(email="integration-admin@example.test", password_hash="hash", role="admin")
    application = Application(name="Integration App", platform="web", target="https://app.example.test", created_by=1)
    db.add_all([user, application])
    db.flush()
    application.created_by = user.id
    defect = Defect(title="Checkout failure", description="The checkout action fails.", created_by=user.id, application_id=application.id)
    test_case = TestCase(
        application_id=application.id,
        created_by=user.id,
        title="Checkout smoke",
        steps="1. Open checkout",
        expected_result="Checkout opens",
    )
    db.add_all([defect, test_case])
    db.commit()

    test_app = FastAPI()
    test_app.include_router(router)

    def override_db():
        yield db

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[current_user] = lambda: user

    with TestClient(test_app) as client:
        yield client, db, user, application, defect, test_case

    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _profile_payload() -> dict[str, str]:
    return {
        "system": "jira",
        "name": "QA Jira",
        "base_url": "https://jira.example.test",
        "project_key": "QA",
        "auth_type": "basic_api_token",
        "username": "qa@example.test",
        "credential": "super-secret-token",
    }


def test_profile_crud_masks_credential_and_never_returns_token(integration_api) -> None:
    client, db, user, *_ = integration_api

    created = client.post("/integrations/connections", json=_profile_payload())
    assert created.status_code == 201
    response = created.json()
    assert response["credential_configured"] is True
    assert "credential" not in response
    assert "super-secret-token" not in created.text

    profile = db.query(IntegrationConnection).filter(IntegrationConnection.created_by == user.id).one()
    assert profile.encrypted_secret != "super-secret-token"
    assert profile.secret_ref is None

    fetched = client.get(f"/integrations/connections/{profile.id}")
    assert fetched.status_code == 200
    assert "super-secret-token" not in fetched.text


def test_external_jira_mutation_is_blocked(integration_api) -> None:
    client, *_rest = integration_api

    response = client.post("/integrations/jira/1/defects")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"


def test_environment_configuration_updates_local_env_only(monkeypatch, tmp_path, integration_api) -> None:
    client, *_rest = integration_api
    env_path = tmp_path / ".env"
    monkeypatch.setattr(integration_service, "INTEGRATION_ENV_FILE_PATH", env_path)
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example.test")
    monkeypatch.setenv("JIRA_EMAIL", "qa@example.test")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "QA")
    monkeypatch.setenv("JIRA_FILTER_ID", "")
    monkeypatch.setenv("JIRA_PROFILE_NAME", "Jira test environment")
    monkeypatch.setenv("JIRA_API_TOKEN", "environment-token")

    response = client.put(
        "/integrations/environment",
        json={
            "jira": {
                "base_url": "https://jira.updated.example.test",
                "email": "updated@example.test",
                "project_key": "UPDATED",
                "filter_id": "",
                "profile_name": "Updated Jira environment",
                "api_token": "replacement-token",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["jira"]["base_url"] == "https://jira.updated.example.test"
    assert body["jira"]["username"] == "updated@example.test"
    assert body["jira"]["project_key"] == "UPDATED"
    assert body["jira"]["configured"] is True
    assert "replacement-token" not in response.text
    assert "JIRA_BASE_URL=https://jira.updated.example.test" in env_path.read_text(encoding="utf-8")
    assert "JIRA_API_TOKEN=replacement-token" in env_path.read_text(encoding="utf-8")


def test_connection_test_and_requirement_read_are_get_only(monkeypatch, integration_api) -> None:
    client, db, user, application, defect, test_case = integration_api
    profile_response = client.post("/integrations/connections", json=_profile_payload())
    assert profile_response.status_code == 201
    connection_id = profile_response.json()["id"]

    calls: list[str] = []

    async def fake_request(self, method, url, **kwargs):
        calls.append(method)
        if url.endswith("/myself"):
            return {"displayName": "QA User", "accountId": "account-1"}
        if "/project/QA" in url:
            return {"name": "Quality"}
        if url.endswith("/search") or url.endswith("/search/jql"):
            return {"total": 1, "issues": [{"id": "100", "key": "QA-100", "fields": {"summary": "Checkout", "issuetype": {"name": "Story"}, "status": {"name": "To Do"}}}]}
        return {}

    monkeypatch.setattr(JiraClient, "_request", fake_request)

    tested = client.post(f"/integrations/connections/{connection_id}/test")
    assert tested.status_code == 200
    assert tested.json()["status"] == "success"
    assert tested.json()["read_only"] is True

    requirements = client.get(f"/integrations/jira/{connection_id}/requirements?page=1&page_size=25")
    assert requirements.status_code == 200
    assert requirements.json()["items"][0]["key"] == "QA-100"
    assert calls == ["GET", "GET", "GET"]

    activated = client.post(f"/integrations/connections/{connection_id}/activate")
    assert activated.status_code == 200


def test_fetch_jira_issue_endpoint(monkeypatch, integration_api) -> None:
    client, db, user, application, defect, test_case = integration_api
    profile_response = client.post("/integrations/connections", json=_profile_payload())
    connection_id = profile_response.json()["id"]

    async def fake_request(self, method, url, **kwargs):
        if "QA-37489" in url:
            return {
                "id": "353807",
                "key": "QA-37489",
                "fields": {
                    "summary": 'Receiving "No STO" message with Status = "P"',
                    "description": "While in SAP in ZMBOP_SUB_STG table, we are seeing instances where Status = P.",
                    "issuetype": {"name": "Defect"},
                    "status": {"name": "Assigned"},
                    "priority": {"name": "Minor"},
                    "labels": ["DirectSales"],
                    "assignee": {"displayName": "Vinod Bathula"},
                    "reporter": {"displayName": "Adam Lang"},
                },
                "names": {},
            }
        return {}

    monkeypatch.setattr(JiraClient, "_request", fake_request)

    # Test POST /integrations/jira/fetch-issue
    post_res = client.post(
        "/integrations/jira/fetch-issue",
        json={"issue_key_or_url": "https://tractorsupplycompany.atlassian.net/browse/QA-37489", "connection_id": connection_id},
    )
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["key"] == "QA-37489"
    assert data["summary"] == 'Receiving "No STO" message with Status = "P"'
    assert data["issue_type"] == "Defect"
    assert "### JIRA ISSUE: QA-37489" in data["context_text"]
    assert data["read_only"] is True

    # Test GET /integrations/jira/issue/{issue_key}
    get_res = client.get(f"/integrations/jira/issue/QA-37489?connection_id={connection_id}")
    assert get_res.status_code == 200
    assert get_res.json()["key"] == "QA-37489"
