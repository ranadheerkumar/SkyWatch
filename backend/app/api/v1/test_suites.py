from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.application import Application
from app.models.test_case import TestCase
from app.models.test_suite import TestSuite
from app.models.user import User
from app.schemas.test_suite import TestSuiteCreate, TestSuiteResponse, TestSuiteUpdate
from app.services.audit import log_audit_event


router = APIRouter(prefix="/test-suites", tags=["test-suites"])


def _load_owned_application(db: DbSession, application_id: int, user_id: int) -> Application:
    application = (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.created_by == user_id,
        )
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


def _validate_suite_case_ids(
    db: DbSession,
    *,
    application_id: int,
    case_ids: list[int],
    user_id: int,
) -> list[int]:
    if not case_ids:
        return []
    rows = (
        db.query(TestCase.id)
        .filter(
            TestCase.application_id == application_id,
            TestCase.created_by == user_id,
            TestCase.id.in_(case_ids),
        )
        .all()
    )
    valid_case_ids = {row.id for row in rows}
    invalid_case_ids = [case_id for case_id in case_ids if case_id not in valid_case_ids]
    if invalid_case_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid case_ids for application {application_id}: {invalid_case_ids[:10]}",
        )
    return [case_id for case_id in case_ids if case_id in valid_case_ids]


def _to_suite_response(suite: TestSuite) -> TestSuiteResponse:
    case_ids = [int(case_id) for case_id in (suite.case_ids or [])]
    return TestSuiteResponse(
        id=suite.id,
        application_id=suite.application_id,
        name=suite.name,
        description=suite.description,
        case_ids=case_ids,
        case_count=len(case_ids),
        created_by=suite.created_by,
        created_at=suite.created_at,
        updated_at=suite.updated_at,
    )


@router.get("", response_model=list[TestSuiteResponse])
def list_test_suites(
    db: DbSession,
    user: User = Depends(current_user),
    application_id: int | None = Query(default=None, ge=1),
) -> list[TestSuiteResponse]:
    query = (
        db.query(TestSuite)
        .join(Application, Application.id == TestSuite.application_id)
        .filter(Application.created_by == user.id)
    )
    if application_id is not None:
        query = query.filter(TestSuite.application_id == application_id)
    suites = query.order_by(TestSuite.updated_at.desc(), TestSuite.id.desc()).all()
    return [_to_suite_response(suite) for suite in suites]


@router.get("/{suite_id}", response_model=TestSuiteResponse)
def get_test_suite(
    suite_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> TestSuiteResponse:
    suite = (
        db.query(TestSuite)
        .join(Application, Application.id == TestSuite.application_id)
        .filter(
            TestSuite.id == suite_id,
            Application.created_by == user.id,
        )
        .first()
    )
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test suite not found")
    return _to_suite_response(suite)


@router.post("", response_model=TestSuiteResponse, status_code=201)
def create_test_suite(
    request: TestSuiteCreate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestSuiteResponse:
    _load_owned_application(db, request.application_id, user.id)
    existing = (
        db.query(TestSuite)
        .filter(
            TestSuite.application_id == request.application_id,
            TestSuite.created_by == user.id,
            TestSuite.name == request.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test suite with this name already exists")
    case_ids = _validate_suite_case_ids(
        db,
        application_id=request.application_id,
        case_ids=request.case_ids,
        user_id=user.id,
    )
    suite = TestSuite(
        application_id=request.application_id,
        name=request.name,
        description=request.description,
        case_ids=case_ids,
        created_by=user.id,
    )
    db.add(suite)
    db.flush()
    log_audit_event(
        db,
        user_id=user.id,
        action="test_suite.create",
        resource_type="test_suite",
        resource_id=suite.id,
        metadata={
            "application_id": request.application_id,
            "case_count": len(case_ids),
        },
    )
    db.commit()
    db.refresh(suite)
    return _to_suite_response(suite)


@router.put("/{suite_id}", response_model=TestSuiteResponse)
def update_test_suite(
    suite_id: int,
    request: TestSuiteUpdate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestSuiteResponse:
    suite = (
        db.query(TestSuite)
        .join(Application, Application.id == TestSuite.application_id)
        .filter(
            TestSuite.id == suite_id,
            Application.created_by == user.id,
        )
        .first()
    )
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test suite not found")

    if request.name is not None:
        duplicate = (
            db.query(TestSuite.id)
            .filter(
                TestSuite.application_id == suite.application_id,
                TestSuite.created_by == user.id,
                TestSuite.id != suite_id,
                TestSuite.name == request.name,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test suite with this name already exists")
        suite.name = request.name
    if request.description is not None:
        suite.description = request.description
    if request.case_ids is not None:
        suite.case_ids = _validate_suite_case_ids(
            db,
            application_id=suite.application_id,
            case_ids=request.case_ids,
            user_id=user.id,
        )
    suite.updated_at = datetime.now(timezone.utc)
    db.add(suite)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_suite.update",
        resource_type="test_suite",
        resource_id=suite.id,
        metadata={
            "application_id": suite.application_id,
            "case_count": len(suite.case_ids or []),
        },
    )
    db.commit()
    db.refresh(suite)
    return _to_suite_response(suite)


@router.delete("/{suite_id}", status_code=204)
def delete_test_suite(
    suite_id: int,
    db: DbSession,
    user: User = Depends(require_roles("qa_lead", "admin")),
) -> None:
    suite = (
        db.query(TestSuite)
        .join(Application, Application.id == TestSuite.application_id)
        .filter(
            TestSuite.id == suite_id,
            Application.created_by == user.id,
        )
        .first()
    )
    if not suite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test suite not found")
    log_audit_event(
        db,
        user_id=user.id,
        action="test_suite.delete",
        resource_type="test_suite",
        resource_id=suite.id,
        metadata={"application_id": suite.application_id, "case_count": len(suite.case_ids or [])},
    )
    db.delete(suite)
    db.commit()