import asyncio
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1 import ai_generation, evidence, settings as settings_api
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.ai_generation_job import AIGenerationJob
from app.models.application import Application
from app.models.agent_recommendation import AgentRecommendation
from app.models.audit_log import AuditLog
from app.models.test_case import TestCase
from app.models.user import User
from app.models import test_run
from app.schemas.execution import ExecutionRequest
from app.services import ai_service
from app.services.ai_generation_jobs import AIQueueUnavailableError, enqueue_ai_generation
from app.services.run_queue import QueueUnavailableError, enqueue_run


client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "DemoPassword123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health_exposes_correlation_id() -> None:
    response = client.get("/health", headers={"X-Correlation-ID": "test-correlation"})
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "test-correlation"
    assert response.headers["X-Request-Duration-Ms"]


def test_test_case_list_supports_pagination_metadata() -> None:
    response = client.get(
        "/api/v1/test-cases?limit=1&offset=0",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) <= 1
    assert int(response.headers["X-Total-Count"]) >= len(response.json())


def test_test_case_review_updates_approval_status() -> None:
    headers = _auth_headers()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == settings.INITIAL_ADMIN_EMAIL).first()
        assert user is not None
        application = db.query(Application).filter(Application.created_by == user.id).first()
        assert application is not None
        test_case = TestCase(
            application_id=application.id,
            created_by=user.id,
            title="Disposable review contract case",
            steps="1. Open the review workflow\n2. Verify the result",
            expected_result="The result is visible",
            status="draft",
        )
        db.add(test_case)
        db.commit()
        db.refresh(test_case)
        test_case_id = test_case.id

    try:
        approved = client.post(
            f"/api/v1/test-cases/{test_case_id}/review",
            headers=headers,
            json={"action": "approve"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "ready"

        rejected = client.post(
            f"/api/v1/test-cases/{test_case_id}/review",
            headers=headers,
            json={"action": "reject"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"
    finally:
        with SessionLocal() as db:
            db.query(TestCase).filter(TestCase.id == test_case_id).delete()
            db.commit()


def test_trace_zip_artifact_is_served(monkeypatch, tmp_path) -> None:
    trace_directory = tmp_path / "traces"
    trace_directory.mkdir()
    artifact_name = "run-failed.zip"
    (trace_directory / artifact_name).write_bytes(b"PK\x03\x04trace")
    monkeypatch.setattr(evidence, "SCREENSHOT_DIR", tmp_path)

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == settings.INITIAL_ADMIN_EMAIL).first()
        assert user is not None
        run = test_run.TestRun(
            id="artifact-contract-run",
            application_id=1,
            created_by=user.id,
            status="failed",
            steps=[],
            result={"artifacts": [{"type": "trace", "path": str(trace_directory / artifact_name), "label": "Trace"}]},
        )
        db.merge(run)
        db.commit()

    try:
        unscoped_response = client.get(
            f"/api/v1/evidence/file/{artifact_name}",
            headers=_auth_headers(),
        )
        assert unscoped_response.status_code == 422

        unknown_run_response = client.get(
            f"/api/v1/evidence/file/{artifact_name}?run_id=missing-artifact-run",
            headers=_auth_headers(),
        )
        assert unknown_run_response.status_code == 404

        response = client.get(
            f"/api/v1/evidence/file/{artifact_name}?run_id=artifact-contract-run",
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/zip")
    finally:
        with SessionLocal() as db:
            db.query(test_run.TestRun).filter(test_run.TestRun.id == "artifact-contract-run").delete()
            db.commit()


def test_execution_captures_video_by_default() -> None:
    request = ExecutionRequest(url="https://example.com")

    assert request.capture_screenshot is True
    assert request.capture_video is True
    assert request.capture_audio is True
    assert request.voice_gender == "male"


def test_redis_queue_mode_fails_closed_without_broker(monkeypatch) -> None:
    monkeypatch.setenv("AI_QA_ENGINE_QUEUE_BACKEND", "redis")
    monkeypatch.delenv("AI_QA_ENGINE_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(QueueUnavailableError):
        enqueue_run("missing-run", ExecutionRequest(url="https://example.com"))
    with pytest.raises(AIQueueUnavailableError):
        enqueue_ai_generation("missing-job")


def test_ai_generation_job_creation_returns_durable_job(monkeypatch) -> None:
    monkeypatch.setattr(ai_generation, "enqueue_ai_generation", lambda job_id: None)
    headers = _auth_headers()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == settings.INITIAL_ADMIN_EMAIL).first()
        assert user is not None
        application = db.query(Application).filter(Application.created_by == user.id).first()
        assert application is not None
        application_id = application.id

    response = client.post(
        f"/api/v1/ai-generation/jobs?application_id={application_id}",
        headers=headers,
        json={"prompt": "Generate login smoke coverage", "provider": "github_copilot", "model": "test-model"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["application_id"] == application_id
    assert payload["provider"] == "github_copilot"
    assert payload["model"] == "test-model"

    with SessionLocal() as db:
        db.query(AIGenerationJob).filter(AIGenerationJob.id == payload["id"]).delete()
        db.commit()


def test_agent_recommendation_review_preserves_review_notes() -> None:
    headers = _auth_headers()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == settings.INITIAL_ADMIN_EMAIL).first()
        assert user is not None
        application = db.query(Application).filter(Application.created_by == user.id).first()
        assert application is not None
        recommendation = AgentRecommendation(
            application_id=application.id,
            recommendation_type="missing_validation",
            title="Contract review recommendation",
            description="Disposable recommendation for the review contract test.",
            proposed_steps=[{"action": "click", "selector": "#submit"}],
            proposed_checks=[{"type": "visible", "value": "#result"}],
            status="pending",
            created_by=user.id,
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)
        recommendation_id = recommendation.id

    try:
        response = client.post(
            f"/api/v1/agents/recommendations/{recommendation_id}/review",
            headers=headers,
            json={"action": "approve", "review_notes": "Validated the proposed assertion."},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        with SessionLocal() as db:
            audit = (
                db.query(AuditLog)
                .filter(
                    AuditLog.action == "agent.recommendation.approve",
                    AuditLog.resource_id == str(recommendation_id),
                )
                .order_by(AuditLog.id.desc())
                .first()
            )
            assert audit is not None
            assert audit.metadata_json["review_notes"] == "Validated the proposed assertion."
    finally:
        with SessionLocal() as db:
            db.query(AuditLog).filter(
                AuditLog.action == "agent.recommendation.approve",
                AuditLog.resource_id == str(recommendation_id),
            ).delete(synchronize_session=False)
            db.query(AgentRecommendation).filter(AgentRecommendation.id == recommendation_id).delete()
            db.commit()


def test_agents_manifest_endpoint_returns_registered_agents() -> None:
    headers = _auth_headers()
    response = client.get("/api/v1/agents/manifest", headers=headers)
    assert response.status_code == 200
    agents = response.json()
    assert isinstance(agents, list)
    assert len(agents) >= 12
    keys = {item["key"] for item in agents}
    assert "discovery" in keys
    assert "planner" in keys
    assert "generator" in keys
    assert "test_data" in keys
    assert "authoring" in keys
    assert "selection" in keys
    assert "deduplication" in keys
    assert "failure_analysis" in keys
    assert "maintenance" in keys
    assert "reporting" in keys



def test_provider_probe_uses_selected_provider_endpoint_and_credentials(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": '{"status":"ok"}'}}]}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, endpoint, *, headers, json):
            captured["endpoint"] = endpoint
            captured["headers"] = headers
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(ai_service.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        ai_service.test_ai_provider_connection(
            provider="openai",
            model="gpt-4o-mini",
            api_key="openai-test-token",
            endpoint="http://provider.test/v1",
        )
    )

    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-mini"
    assert captured["endpoint"] == "http://provider.test/v1/chat/completions"
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer openai-test-token",
    }
    assert captured["payload"]["model"] == "gpt-4o-mini"
    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_settings_key_resolution_does_not_cross_use_github_token(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "github-test-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-token")

    assert settings_api._provider_key("openai") == "openai-test-token"
