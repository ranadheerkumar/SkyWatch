from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.api.dependencies import current_user, require_roles
from app.api.v1.execution import router
from app.core.database import Base, get_db
from app.models.application import Application
from app.models.build_execution import BuildExecution
from app.models.case_execution import CaseExecution
from app.models.test_case import TestCase
from app.models.test_run import TestRun
from app.models.user import User
from app.services.run_queue import sync_build_execution_status


@pytest.fixture()
def execution_api() -> tuple[TestClient, Session, User, Application, list[TestCase]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()
    user = User(email="qa-lead@example.test", password_hash="hash", role="qa_lead")
    application = Application(name="E-Commerce Target", platform="web", target="https://shop.example.test", created_by=1)
    db.add_all([user, application])
    db.flush()
    application.created_by = user.id

    case1 = TestCase(
        application_id=application.id,
        created_by=user.id,
        title="Login Validation",
        steps="1. Open login\n2. Enter credentials\n3. Click Submit",
        expected_result="Dashboard visible",
    )
    case2 = TestCase(
        application_id=application.id,
        created_by=user.id,
        title="Cart Checkout Flow",
        steps="1. Add item\n2. View cart\n3. Complete checkout",
        expected_result="Order confirmation displayed",
    )
    db.add_all([case1, case2])
    db.commit()

    test_app = FastAPI()
    test_app.include_router(router)

    def override_db():
        yield db

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[current_user] = lambda: user
    test_app.dependency_overrides[require_roles("tester", "qa_lead", "admin")] = lambda: user

    with TestClient(test_app) as client:
        yield client, db, user, application, [case1, case2]


def test_build_execution_lifecycle_and_sync(execution_api):
    client, db, user, application, cases = execution_api

    build_id = "build-test-001"
    build = BuildExecution(
        id=build_id,
        application_id=application.id,
        created_by=user.id,
        name="Smoke Test Build #1",
        status="queued",
        trigger_source="manual",
        total_cases=2,
    )
    db.add(build)

    run1 = TestRun(
        id="run-001",
        application_id=application.id,
        created_by=user.id,
        status="passed",
        batch_id=build_id,
        build_name="Smoke Test Build #1",
        trigger_source="manual",
        result={"duration_ms": 1200, "checks": [{"type": "visible", "value": "body", "passed": True}]},
        finished_at=datetime.now(timezone.utc),
    )
    run2 = TestRun(
        id="run-002",
        application_id=application.id,
        created_by=user.id,
        status="failed",
        batch_id=build_id,
        build_name="Smoke Test Build #1",
        trigger_source="manual",
        result={"duration_ms": 1800, "checks": [{"type": "visible", "value": "checkout", "passed": False}], "failure_type": "LOCATOR", "error": "Checkout button missing"},
        finished_at=datetime.now(timezone.utc),
    )
    case_exec1 = CaseExecution(run_id="run-001", test_case_id=cases[0].id, status="passed")
    case_exec2 = CaseExecution(run_id="run-002", test_case_id=cases[1].id, status="failed")

    db.add_all([run1, run2, case_exec1, case_exec2])
    db.commit()

    # Sync build status
    sync_build_execution_status(db, build_id)
    db.refresh(build)

    assert build.total_cases == 2
    assert build.passed_count == 1
    assert build.failed_count == 1
    assert build.status == "failed"
    assert build.duration_ms == 3000.0


def test_cancel_batch_execution_api(execution_api):
    client, db, user, application, cases = execution_api

    build_id = "build-test-cancel-001"
    build = BuildExecution(
        id=build_id,
        application_id=application.id,
        created_by=user.id,
        name="Active Build to Cancel",
        status="running",
        trigger_source="manual",
        total_cases=2,
    )
    db.add(build)

    run1 = TestRun(
        id="run-cancel-001",
        application_id=application.id,
        created_by=user.id,
        status="running",
        batch_id=build_id,
        build_name="Active Build to Cancel",
    )
    case_exec1 = CaseExecution(run_id="run-cancel-001", test_case_id=cases[0].id, status="running")
    db.add_all([run1, case_exec1])
    db.commit()

    res = client.post(f"/execution/batch/{build_id}/cancel")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "cancelled"
    assert data["cancelled_runs"] == 1

    db.refresh(run1)
    db.refresh(case_exec1)
    db.refresh(build)
    assert run1.status == "cancelled"
    assert case_exec1.status == "cancelled"
    assert build.status == "cancelled"


def test_list_and_get_build_executions_api(execution_api):
    client, db, user, application, cases = execution_api

    build_id = "build-test-002"
    build = BuildExecution(
        id=build_id,
        application_id=application.id,
        created_by=user.id,
        name="Regression Build #2",
        status="passed",
        trigger_source="suite",
        total_cases=2,
        passed_count=2,
        failed_count=0,
        error_count=0,
        duration_ms=2500.0,
    )
    db.add(build)

    run1 = TestRun(
        id="run-003",
        application_id=application.id,
        created_by=user.id,
        status="passed",
        batch_id=build_id,
        build_name="Regression Build #2",
        trigger_source="suite",
        result={"duration_ms": 1100, "checks": [{"type": "visible", "value": "body", "passed": True}]},
    )
    run2 = TestRun(
        id="run-004",
        application_id=application.id,
        created_by=user.id,
        status="passed",
        batch_id=build_id,
        build_name="Regression Build #2",
        trigger_source="suite",
        result={"duration_ms": 1400, "checks": [{"type": "visible", "value": "body", "passed": True}]},
    )
    case_exec1 = CaseExecution(run_id="run-003", test_case_id=cases[0].id, status="passed")
    case_exec2 = CaseExecution(run_id="run-004", test_case_id=cases[1].id, status="passed")
    db.add_all([run1, run2, case_exec1, case_exec2])
    db.commit()

    # Test list builds endpoint
    list_res = client.get(f"/execution/builds/{application.id}")
    assert list_res.status_code == 200
    builds = list_res.json()
    assert len(builds) >= 1
    found_build = next((b for b in builds if b["build_id"] == build_id), None)
    assert found_build is not None
    assert found_build["name"] == "Regression Build #2"
    assert found_build["total_cases"] == 2
    assert found_build["passed_count"] == 2
    assert found_build["pass_rate"] == 100.0

    # Test get build detail endpoint
    detail_res = client.get(f"/execution/builds/{build_id}/detail")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["build_id"] == build_id
    assert detail["status"] == "passed"
    assert len(detail["cases"]) == 2
    assert detail["cases"][0]["title"] == cases[0].title
