import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.application import Application
from app.models.defect import Defect
from app.models.test_case import TestCase
from app.models.test_run import TestRun
from app.schemas.execution import ExecutionResponse, StepResult, CheckResult
from app.services.defect_service import DefectService


def test_auto_defect_creation_on_failed_execution():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()

    app = Application(name="Test Portal", platform="web", target="https://portal.test", created_by=1)
    tc = TestCase(application_id=1, created_by=1, title="TC01 - Checkout Payment Failure", priority="high")
    run = TestRun(id="run-defect-test-1", application_id=1, created_by=1, status="failed")
    db.add_all([app, tc, run])
    db.commit()

    class MockCaseExecution:
        test_case_id = tc.id

    exec_response = ExecutionResponse(
        run_id="run-defect-test-1",
        url="https://portal.test/checkout",
        status="failed",
        title="staging: Checkout",
        failure_type="ASSERTION",
        failure_summary="Order confirmation banner was not displayed.",
        duration_ms=4500,
        checks=[
            CheckResult(type="text_contains", value="Order Placed", passed=False, message="Text not found"),
        ],
        step_results=[
            StepResult(index=1, action="navigate", passed=True, message="Navigated to /checkout", duration_ms=500),
            StepResult(index=2, action="click", selector="button.submit", passed=False, message="Element not clickable", duration_ms=2000),
        ],
        error="AssertionError: confirmation banner missing",
        console_errors=["[error] checkout widget failed to render"],
        network_errors=["GET https://portal.test/api/checkout :: request failed"],
    )

    defect = DefectService.record_execution_failure(
        db,
        run=run,
        case_execution=MockCaseExecution(),
        result=exec_response,
    )

    assert defect is not None
    assert defect.title == "Test Failure: TC01 - Checkout Payment Failure"
    assert defect.status == "open"
    assert defect.severity == "major"
    assert defect.priority == "high"
    assert "Failed Step(s):" in defect.description
    assert "Failed Check(s):" in defect.description
    assert "button.submit" in defect.description
    assert "Page title:** staging: Checkout" in defect.description
    assert "What this means:** The workflow reached an assertion" in defect.description
    assert "Exception / Error:" in defect.description
    assert "Console Errors:" in defect.description
    assert "Network Errors:" in defect.description

    # Test deduplication - running again should update instead of creating duplicate
    defect_again = DefectService.record_execution_failure(
        db,
        run=run,
        case_execution=MockCaseExecution(),
        result=exec_response,
    )
    assert defect_again.id == defect.id
    all_defects = db.query(Defect).all()
    assert len(all_defects) == 1
