"""Unit tests for the Agent Tasks REST API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import Base, SessionLocal, engine
from app.models.agent_task import AgentTask
from app.models.user import User

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield


def _auth_headers() -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "DemoPassword123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@patch("app.api.v1.agent_tasks._run_agent_task", new_callable=AsyncMock)
def test_create_and_get_agent_task(mock_run):
    headers = _auth_headers()

    # 1. Create task
    create_res = client.post(
        "/api/v1/agent/tasks",
        json={
            "objective": "Explore homepage navigation and find all broken links",
            "max_iterations": 10,
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    data = create_res.json()
    task_id = data["id"]
    assert task_id
    assert data["objective"] == "Explore homepage navigation and find all broken links"
    assert data["status"] in ("queued", "planning")

    # 2. List tasks
    list_res = client.get("/api/v1/agent/tasks", headers=headers)
    assert list_res.status_code == 200
    tasks = list_res.json()
    assert any(t["id"] == task_id for t in tasks)

    # 3. Get task detail
    get_res = client.get(f"/api/v1/agent/tasks/{task_id}", headers=headers)
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["id"] == task_id
    assert detail["objective"] == "Explore homepage navigation and find all broken links"

    # 4. Get task trace
    trace_res = client.get(f"/api/v1/agent/tasks/{task_id}/trace", headers=headers)
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert trace_data["task_id"] == task_id
    assert isinstance(trace_data["trace"], list)


def test_agent_task_approval_workflow():
    headers = _auth_headers()

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "demo@example.com").first()
        task = AgentTask(
            id="test-approval-task",
            objective="Delete old test runs",
            created_by=user.id,
            status="waiting_approval",
            plan={
                "steps": [
                    {
                        "id": "step-1",
                        "goal": "Purge test run logs",
                        "description": "Permanently delete historical test records",
                        "requires_approval": True,
                        "status": "waiting_approval",
                    }
                ]
            },
        )
        db.merge(task)
        db.commit()

    # Approve step
    approve_res = client.post(
        "/api/v1/agent/tasks/test-approval-task/approve",
        json={
            "step_id": "step-1",
            "approved": True,
            "feedback": "Proceed with cautious deletion",
        },
        headers=headers,
    )
    assert approve_res.status_code == 200
    updated = approve_res.json()
    assert updated["status"] == "executing"
    assert updated["plan"]["steps"][0]["status"] == "in_progress"


def test_agent_task_cancel():
    headers = _auth_headers()

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "demo@example.com").first()
        task = AgentTask(
            id="test-cancel-task",
            objective="Long running scan",
            created_by=user.id,
            status="executing",
        )
        db.merge(task)
        db.commit()

    # Cancel task
    cancel_res = client.post(
        "/api/v1/agent/tasks/test-cancel-task/cancel",
        headers=headers,
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
