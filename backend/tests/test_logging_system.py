"""Tests for SkyWatch logging subsystem, SecretMaskingFilter, GenerationLogger, and Log APIs."""

import logging
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import Base, engine, SessionLocal
from app.models.ai_generation_job import AIGenerationJob
from app.models.user import User
from app.core.logging import (
    SecretMaskingFilter,
    RingBufferLogHandler,
    configure_logging,
    get_recent_system_logs,
)
from app.services.generation_logger import GenerationLogger, get_active_generation_logger

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


def test_secret_masking_filter_patterns():
    filter_ = SecretMaskingFilter()

    # Gemini API key (starts with AIza)
    msg = "Configured key: AIzaMockTestingRedactionKey1234567890 ready"
    masked = filter_.mask_secrets(msg)
    assert "AIzaMockTesting" not in masked
    assert "***REDACTED***" in masked

    # Gemini alternate key prefix
    msg_aq = "Received AQ.MockTestingRedactionKey1234567890 ready"
    masked_aq = filter_.mask_secrets(msg_aq)
    assert "MockTesting" not in masked_aq
    assert "***REDACTED***" in masked_aq

    # OpenAI key (sk-...)
    msg_sk = "Using key sk-1234567890abcdef1234567890"
    masked_sk = filter_.mask_secrets(msg_sk)
    assert "sk-" not in masked_sk
    assert "***REDACTED***" in masked_sk

    # Bearer token
    msg_bearer = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    masked_bearer = filter_.mask_secrets(msg_bearer)
    assert "eyJhbGci" not in masked_bearer
    assert "Bearer ***REDACTED***" in masked_bearer

    # JSON password
    msg_json = 'User payload: {"email": "test@skywatch.ai", "password": "SuperSecretPassword123!"}'
    masked_json = filter_.mask_secrets(msg_json)
    assert "SuperSecretPassword123!" not in masked_json
    assert '"password": "***REDACTED***"' in masked_json


def test_ring_buffer_log_handler():
    handler = RingBufferLogHandler(capacity=5)
    formatter = logging.Formatter("%(levelname)s %(message)s")
    handler.setFormatter(formatter)

    test_logger = logging.getLogger("test_ring_buffer")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)

    test_logger.info("First message")
    test_logger.warning("Second warning")
    test_logger.error("Third error")
    test_logger.info("Fourth message")
    test_logger.debug("Fifth debug")
    test_logger.info("Sixth overflow message")  # Should evict "First message"

    logs = handler.get_logs(limit=10)
    assert len(logs) == 5
    assert logs[0]["message"] == "WARNING Second warning"
    assert logs[-1]["message"] == "INFO Sixth overflow message"

    # Filter by level
    error_logs = handler.get_logs(level="ERROR")
    assert len(error_logs) == 1
    assert error_logs[0]["level"] == "ERROR"

    # Filter by search keyword
    warn_logs = handler.get_logs(search="warning")
    assert len(warn_logs) == 1
    assert "Second warning" in warn_logs[0]["message"]


def test_generation_logger_lifecycle():
    job_id = "test-gen-job-uuid-1234"
    logger = GenerationLogger(job_id=job_id)

    assert get_active_generation_logger(job_id) is logger

    logger.set_stage("document_analysis")
    logger.info("Parsed 2 requirement documents", doc_count=2)
    logger.step("Target discovery completed on https://example.com")
    logger.llm("Planner synthesized 5 scenarios", provider="gemini", model="gemini-flash-latest", latency_ms=850.5)
    logger.warn("Transient rate limit backoff triggered", backoff_seconds=5)
    logger.error("Fake test failure", error_code="TEST_ERR")

    entries = logger.get_entries()
    assert len(entries) == 5
    assert entries[0]["level"] == "INFO"
    assert entries[0]["metadata"]["doc_count"] == 2
    assert entries[2]["level"] == "LLM"
    assert entries[2]["metadata"]["provider"] == "gemini"
    assert entries[3]["level"] == "WARN"
    assert entries[4]["level"] == "ERROR"

    # Test filtering by level
    llm_entries = logger.get_entries(level="LLM")
    assert len(llm_entries) == 1

    # Test text formatting
    text_log = logger.to_text()
    assert "test-gen-job-uuid-1234" not in text_log  # text has clean timestamp/level format
    assert "Parsed 2 requirement documents" in text_log
    assert "[LLM]" in text_log

    # Test flush to mock job
    class MockJob:
        result = {}

    job = MockJob()
    logger.flush_to_job(job)
    assert "logs" in job.result
    assert len(job.result["logs"]) == 5

    logger.close(job=job)
    assert get_active_generation_logger(job_id) is None


def test_observability_logs_endpoint():
    auth_headers = _auth_headers()
    configure_logging()
    app_logger = logging.getLogger("skywatch.test.api")
    app_logger.info("Observability API test log entry")

    response = client.get("/api/v1/observability/logs?limit=50", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "logs" in data
    assert isinstance(data["logs"], list)
    assert any("Observability API test log entry" in l["message"] for l in data["logs"])


def test_generation_job_logs_endpoint():
    auth_headers = _auth_headers()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "demo@example.com").first()
        assert user is not None
        job = AIGenerationJob(
            id="job-test-logs-endpoint",
            application_id=1,
            created_by=user.id,
            status="completed",
            phase="completed",
            result={
                "logs": [
                    {"level": "INFO", "stage": "intake", "message": "Extracted requirements", "iso_time": "2026-09-19T18:00:00Z"},
                    {"level": "LLM", "stage": "planner", "message": "Synthesized 3 blueprints", "iso_time": "2026-09-19T18:00:02Z"},
                ]
            }
        )
        db.merge(job)
        db.commit()

    # Query as JSON
    res_json = client.get("/api/v1/ai-generation/jobs/job-test-logs-endpoint/logs", headers=auth_headers)
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["job_id"] == "job-test-logs-endpoint"
    assert data["total_entries"] == 2
    assert len(data["logs"]) == 2

    # Query as text
    res_text = client.get("/api/v1/ai-generation/jobs/job-test-logs-endpoint/logs?format=text", headers=auth_headers)
    assert res_text.status_code == 200
    assert "text/plain" in res_text.headers["content-type"]
    assert "Extracted requirements" in res_text.text
    assert "Synthesized 3 blueprints" in res_text.text
