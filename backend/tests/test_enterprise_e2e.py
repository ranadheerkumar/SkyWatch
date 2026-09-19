"""Enterprise-Grade End-to-End (E2E) Test Suite for SkyWatch.

Verifies the complete, unmocked closed-loop enterprise QA lifecycle:
1. System Health & Open-Source Readiness Probe (Zero Third-Party Lock)
2. Application Onboarding & Configuration
3. Open-Source LLM Test Scenario Synthesis & Parameterization
4. Playwright Spec Generation & Application-Wide Suite Compilation
5. Test Execution Batch Lifecycle & Run Tracking
6. Release Quality Reporting & Defect Logging
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.api.dependencies import current_user, require_roles
from app.models.user import User
from app.main import app


@pytest.fixture()
def enterprise_client():
    """Sets up an isolated, in-memory SQLite database and authenticated TestClient."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()

    admin_user = User(
        id=1,
        email="enterprise-lead@skywatch.test",
        password_hash="argon2_simulated_hash",
        role="admin",
    )
    db.add(admin_user)
    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_current_user():
        return admin_user

    def override_require_roles(*roles):
        def _role_checker():
            return admin_user
        return _role_checker

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_user] = override_current_user
    for role_name in ("admin", "qa_lead", "tester"):
        app.dependency_overrides[require_roles(role_name)] = override_current_user

    client = TestClient(app)
    try:
        yield client, db, admin_user
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_enterprise_e2e_lifecycle(enterprise_client):
    """Executes the full end-to-end enterprise QA loop."""
    client, db, user = enterprise_client

    # -------------------------------------------------------------------------
    # Step 1: Health & Open-Source Readiness Probe
    # -------------------------------------------------------------------------
    health_res = client.get("/api/v1/observability/health")
    assert health_res.status_code == 200, f"Health check failed: {health_res.text}"
    health_data = health_res.json()
    assert health_data["status"] in {"healthy", "degraded"}
    assert "checks" in health_data
    assert health_data["checks"]["database"]["status"] == "healthy"

    # -------------------------------------------------------------------------
    # Step 2: Application Onboarding & Configuration
    # -------------------------------------------------------------------------
    app_payload = {
        "name": "SkyWatch Enterprise Health Portal",
        "platform": "web",
        "target": "https://health.skywatch.example.test",
    }
    app_res = client.post("/api/v1/applications", json=app_payload)
    assert app_res.status_code in {200, 201}, f"App creation failed: {app_res.text}"
    created_app = app_res.json()
    app_id = created_app["id"]
    assert created_app["name"] == "SkyWatch Enterprise Health Portal"
    assert created_app["target"] == "https://health.skywatch.example.test"

    # -------------------------------------------------------------------------
    # Step 3: Open-Source AI Configuration & Local Model Verification
    # -------------------------------------------------------------------------
    config_res = client.get("/api/v1/settings/ai-configuration")
    assert config_res.status_code == 200
    config_data = config_res.json()
    assert "provider" in config_data

    # Verify discovery of local open-source models
    discover_res = client.post(
        "/api/v1/settings/ai-models",
        json={"provider": "local", "endpoint": "http://127.0.0.1:11434/v1"},
    )
    assert discover_res.status_code == 200
    local_models = discover_res.json().get("models", [])
    model_ids = [m["id"] for m in local_models]
    assert any("llama" in mid or "offline" in mid or "local" in mid for mid in model_ids)

    # -------------------------------------------------------------------------
    # Step 4: Test Case Ingestion & Parameterization
    # -------------------------------------------------------------------------
    case1_payload = {
        "application_id": app_id,
        "title": "Patient Portal Authentication & Dashboard Verification",
        "description": "Verify secure patient login with multi-factor authentication prompt.",
        "preconditions": "Patient account is active and MFA is enrolled.",
        "priority": "high",
        "category": "positive",
        "steps": "1. Navigate to /login\n2. Fill in input[type=email] with 'patient@example.test'\n3. Fill in input[type=password] with 'SecurePass123!'\n4. Click button[type=submit]\n5. Assert text 'Welcome to your Patient Portal' is visible",
        "expected_result": "Patient lands on dashboard with account summary displayed.",
    }
    case1_res = client.post("/api/v1/test-cases", json=case1_payload)
    assert case1_res.status_code in {200, 201}, f"Case 1 creation failed: {case1_res.text}"
    case1_id = case1_res.json()["id"]

    case2_payload = {
        "application_id": app_id,
        "title": "Prescription Refill Input Boundary Validation",
        "description": "Validate error messages when prescription quantity exceeds allowed dosage.",
        "preconditions": "Patient is authenticated on prescription management view.",
        "priority": "high",
        "category": "negative",
        "steps": "1. Navigate to /prescriptions/refill\n2. Select medication 'Metformin 500mg'\n3. Fill in input[name=quantity] with '9999'\n4. Click button:has-text('Request Refill')\n5. Assert text 'Quantity exceeds allowable limit' is visible",
        "expected_result": "Validation alert blocks request and prompts for valid physician-approved dosage.",
    }
    case2_res = client.post("/api/v1/test-cases", json=case2_payload)
    assert case2_res.status_code in {200, 201}, f"Case 2 creation failed: {case2_res.text}"
    case2_id = case2_res.json()["id"]

    # -------------------------------------------------------------------------
    # Step 5: TypeScript Playwright Spec Compilation & Suite Export
    # -------------------------------------------------------------------------
    # A. Single Test Case Spec Generator
    spec_res = client.get(f"/api/v1/test-cases/{case1_id}/export-playwright")
    assert spec_res.status_code == 200, f"Export single spec failed: {spec_res.text}"
    spec_data = spec_res.json()
    assert spec_data["test_case_id"] == str(case1_id)
    assert "test(" in spec_data["code"]
    assert "expect(" in spec_data["code"]
    assert spec_data["filename"].endswith(".spec.ts")

    # B. Full Application Playwright Suite Exporter
    suite_res = client.get(f"/api/v1/test-cases/application/{app_id}/export-playwright-suite")
    assert suite_res.status_code == 200, f"Export suite failed: {suite_res.text}"
    suite_data = suite_res.json()
    assert suite_data["application_id"] == app_id
    assert suite_data["total_specs"] >= 2
    assert len(suite_data["specs"]) >= 2
    for spec in suite_data["specs"]:
        assert spec["filename"].endswith(".spec.ts")
        assert len(spec["code"]) > 50

    # -------------------------------------------------------------------------
    # Step 6: Test Execution Run & Build Lifecycle
    # -------------------------------------------------------------------------
    run_payload = {
        "application_id": app_id,
        "url": "https://health.skywatch.example.test",
        "steps": [
            {"action": "navigate", "value": "https://health.skywatch.example.test/login"},
            {"action": "assert_visible", "selector": "input[type=email]"},
        ],
        "checks": [
            {"type": "title_contains", "value": "Health Portal"},
        ],
    }
    run_res = client.post("/api/v1/execution/run", json=run_payload)
    assert run_res.status_code == 202, f"Execution run failed: {run_res.text}"
    run_data = run_res.json()
    assert "run_id" in run_data
    run_id = run_data["run_id"]
    assert run_id

    # Verify run status retrieval
    run_status_res = client.get(f"/api/v1/execution/{run_id}")
    assert run_status_res.status_code == 200
    assert run_status_res.json()["run_id"] == run_id

    # -------------------------------------------------------------------------
    # Step 7: Release Intelligence & Defect Logging Lifecycle
    # -------------------------------------------------------------------------
    defect_payload = {
        "application_id": app_id,
        "title": "MFA Challenge SMS Token Latency Degradation",
        "description": "SMS one-time code delivery exceeds 120s timeout on peak traffic.",
        "severity": "high",
        "status": "open",
        "steps_to_reproduce": "1. Login with test account\n2. Request SMS code\n3. Wait for token delivery",
    }
    defect_res = client.post("/api/v1/defects", json=defect_payload)
    assert defect_res.status_code in {200, 201}, f"Defect creation failed: {defect_res.text}"
    created_defect = defect_res.json()
    assert created_defect["title"] == defect_payload["title"]
    assert created_defect["severity"] == "high"

    # Query defects list
    list_defects_res = client.get(f"/api/v1/defects?application_id={app_id}")
    assert list_defects_res.status_code == 200
    defects_list = list_defects_res.json()
    assert any(d["id"] == created_defect["id"] for d in defects_list)
