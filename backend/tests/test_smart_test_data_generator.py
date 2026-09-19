import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import current_user, require_roles
from app.api.v1.test_data import router
from app.core.database import Base, get_db
from app.models.application import Application
from app.models.user import User
from app.services.self_learning import SelfLearningEngine, clear_learning_cache
from app.services.test_data_generator import TestDataGeneratorService


@pytest.fixture()
def test_data_api() -> tuple[TestClient, Session, User, Application]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()
    user = User(email="test-lead@example.test", password_hash="hash", role="qa_lead")
    application = Application(name="Pet Care Portal", platform="web", target="https://pet.example.test", created_by=1)
    db.add_all([user, application])
    db.flush()
    application.created_by = user.id
    db.commit()

    test_app = FastAPI()
    test_app.include_router(router)

    def override_db():
        yield db

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[current_user] = lambda: user
    test_app.dependency_overrides[require_roles("tester", "qa_lead", "admin")] = lambda: user

    with TestClient(test_app) as client:
        yield client, db, user, application


def test_test_data_generator_service_synthesis():
    clear_learning_cache()
    service = TestDataGeneratorService(application_id=12)

    # Seed live learned entities
    service.learner.record_discovered_entities("pet_name", ["Bella", "Max", "Charlie"])
    service.learner.record_discovered_entities("owner_name", ["Smith", "Franklin", "Davis"])

    rows = asyncio.run(service.generate_dataset(
        dataset_name="Pet Owners Suite",
        field_names=["owner_name", "pet_name", "barcode", "email", "phone"],
        scenario_types=["valid", "invalid", "boundary", "edge"],
        row_count=8,
    ))

    assert len(rows) == 8
    scenarios = [r["_scenario"] for r in rows]
    assert "valid" in scenarios
    assert "invalid" in scenarios
    assert "boundary" in scenarios
    assert "edge" in scenarios

    # Check that valid rows utilized discovered entities
    valid_row = next(r for r in rows if r["_scenario"] == "valid")
    assert any(name in valid_row["owner_name"] for name in ["Smith", "Franklin", "Davis", "John"])
    assert any(name in valid_row["pet_name"] for name in ["Bella", "Max", "Charlie"])


def test_smart_test_data_generate_endpoint(test_data_api):
    client, db, user, application = test_data_api

    payload = {
        "name": "E2E Checkout Dataset",
        "field_names": ["first_name", "last_name", "email", "order_id"],
        "row_count": 5,
        "scenario_types": ["valid", "boundary"],
        "save_to_database": True,
    }

    res = client.post(f"/test-data/generate/{application.id}", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["application_id"] == application.id
    assert data["row_count"] == 5
    assert len(data["data_rows"]) == 5
    assert data["dataset_id"] is not None


def test_get_learned_application_entities(test_data_api):
    client, db, user, application = test_data_api

    learner = SelfLearningEngine(application.id)
    learner.record_discovered_entities("barcode", ["1234567890", "9876543210"])
    learner.record_discovered_entities("owner_name", ["Alice Smith", "Bob Johnson"])

    res = client.get(f"/test-data/learned/{application.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["application_id"] == application.id
    pools = data["discovered_entity_pools"]
    assert "barcode" in pools
    assert "1234567890" in pools["barcode"]
    assert "owner_name" in pools


def test_execution_parameter_interpolation_with_adaptive_entities():
    clear_learning_cache()
    from app.services.test_execution import _lookup_parameter, _interpolate_parameter_value
    learner = SelfLearningEngine(application_id=99)
    learner.record_discovered_entities("barcode", ["BARCODE-9999"])
    learner.record_discovered_entities("pet_name", ["Milo"])

    # Explicit parameter overrides learned entity
    assert _lookup_parameter("barcode", {"barcode": "CUSTOM-111"}, application_id=99) == "CUSTOM-111"

    # Missing parameter falls back to discovered entity
    assert _lookup_parameter("barcode", {}, application_id=99) == "BARCODE-9999"
    assert _interpolate_parameter_value("Scan {{barcode}} for {{pet_name}}", {}, application_id=99) == "Scan BARCODE-9999 for Milo"


def test_resolve_application_parameters_endpoint(test_data_api):
    from app.models.test_case import TestCase
    client, db, user, application = test_data_api

    tc = TestCase(
        title="TC01 - Search Clinic by Zip",
        description="Search clinic with zipcode",
        preconditions="User is logged in",
        steps="1. Enter {{zip_code}} into search\n2. Select {{brand}} from dropdown\n3. Click Find Clinics",
        expected_result="Clinics matching {{zip_code}} are listed",
        application_id=application.id,
        created_by=user.id,
    )
    db.add(tc)
    db.commit()

    learner = SelfLearningEngine(application.id)
    learner.record_discovered_entities("zip_code", ["37201"])
    learner.record_discovered_entities("brand", ["VIP Petcare"])

    res = client.get(f"/test-data/resolve-parameters/{application.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["application_id"] == application.id
    assert "zip_code" in data["detected_keys"]
    assert "brand" in data["detected_keys"]

    param_map = {p["key"]: p["value"] for p in data["parameters"]}
    assert param_map.get("zip_code") in ["37201", "10001", "90210"] or len(param_map.get("zip_code", "")) > 0
    assert "login_email" in param_map
    assert "login_password" in param_map


def test_auto_parameterize_case_steps_converts_sample_literals():
    from app.services.ai_service import auto_parameterize_case_steps

    raw_steps = (
        "1. Navigate to https://apollo.example.test/owners/find\n"
        "2. Enter 'John Doe' into the 'Owner Name' field\n"
        "3. Enter 'Bella' into 'Pet Name'\n"
        "4. Search for 'Golden Retriever' in Breed\n"
        "5. Enter 'admin@example.com' into Email\n"
        "6. Click the 'Find Owner' button\n"
        "7. Verify that the results table displays rows matching 'John Doe'"
    )
    expected = "Verify that the results table displays rows matching 'John Doe' and pet 'Bella'"

    param_steps, param_expected, test_data = auto_parameterize_case_steps(
        raw_steps,
        expected_result=expected,
        category="positive",
    )

    # Verify steps contain template placeholders
    assert "{{owner_name}}" in param_steps
    assert "{{pet_name}}" in param_steps
    assert "{{breed}}" in param_steps
    assert "{{email}}" in param_steps or "{{login_email}}" in param_steps
    assert "'John Doe'" not in param_steps
    assert "'Bella'" not in param_steps

    # Verify expected result has matching tokens
    assert "{{owner_name}}" in param_expected
    assert "{{pet_name}}" in param_expected
    assert "'John Doe'" not in param_expected
    assert "'Bella'" not in param_expected

    # Verify test_data dictionary is correctly populated
    assert test_data["owner_name"] == "John Doe"
    assert test_data["pet_name"] == "Bella"
    assert test_data["breed"] == "Golden Retriever"
    assert test_data.get("email") == "admin@example.com" or test_data.get("login_email") == "admin@example.com"


def test_playwright_spec_generation_with_parameterized_bindings():
    from app.models.test_case import TestCase
    from app.models.application import Application
    from app.services.automation_builder import generate_playwright_spec_code

    app = Application(name="Apollo Web", target="https://apollo.example.test")
    tc = TestCase(
        id=101,
        title="TC01 - Search Owner by Name",
        steps="1. Navigate to https://apollo.example.test/find\n2. Enter '{{owner_name}}' into 'Owner Name'\n3. Click 'Find Owner'",
        expected_result="Verify rows matching '{{owner_name}}' are shown",
        test_data={"owner_name": "Franklin", "login_email": "admin@example.test"},
        category="positive",
    )

    spec_code = generate_playwright_spec_code(tc, app)
    assert "const testData: Record<string, string>" in spec_code
    assert "owner_name: process.env.OWNER_NAME || 'Franklin'" in spec_code
    assert "testData['owner_name']" in spec_code
    assert "await page.goto(" in spec_code
