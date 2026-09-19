from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.application import Application
from app.models.execution_plan import ExecutionPlan
from app.models.user import User
from app.schemas.execution_plan import (
    ExecutionPlanCreate,
    ExecutionPlanResponse,
    ExecutionPlanUpdate,
)
from app.services.audit import log_audit_event

router = APIRouter(prefix="/execution-plans", tags=["execution-plans"])


@router.get("", response_model=list[ExecutionPlanResponse])
def list_execution_plans(
    db: DbSession,
    user: User = Depends(current_user),
) -> list[ExecutionPlan]:
    return (
        db.query(ExecutionPlan)
        .join(Application, Application.id == ExecutionPlan.application_id)
        .filter(Application.created_by == user.id)
        .order_by(ExecutionPlan.id.desc())
        .all()
    )


@router.get("/application/{application_id}", response_model=list[ExecutionPlanResponse])
def list_application_execution_plans(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> list[ExecutionPlan]:
    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return (
        db.query(ExecutionPlan)
        .filter(ExecutionPlan.application_id == application_id, ExecutionPlan.created_by == user.id)
        .order_by(ExecutionPlan.id.desc())
        .all()
    )


@router.get("/{plan_id}", response_model=ExecutionPlanResponse)
def get_execution_plan(
    plan_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> ExecutionPlan:
    plan = (
        db.query(ExecutionPlan)
        .join(Application, Application.id == ExecutionPlan.application_id)
        .filter(ExecutionPlan.id == plan_id, Application.created_by == user.id)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution plan not found")
    return plan


@router.post("", response_model=ExecutionPlanResponse, status_code=status.HTTP_201_CREATED)
def create_execution_plan(
    request: ExecutionPlanCreate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> ExecutionPlan:
    application = (
        db.query(Application)
        .filter(Application.id == request.application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    plan = ExecutionPlan(
        application_id=request.application_id,
        name=request.name.strip(),
        description=request.description,
        target_type=request.target_type,
        case_ids=request.case_ids,
        suite_ids=request.suite_ids,
        execution_mode=request.execution_mode,
        schedule_cron=request.schedule_cron,
        status=request.status,
        created_by=user.id,
    )
    db.add(plan)
    db.flush()
    log_audit_event(
        db,
        user_id=user.id,
        action="execution_plan.create",
        resource_type="execution_plan",
        resource_id=plan.id,
        metadata={"name": plan.name, "target_type": plan.target_type},
    )
    db.commit()
    db.refresh(plan)
    return plan


@router.put("/{plan_id}", response_model=ExecutionPlanResponse)
def update_execution_plan(
    plan_id: int,
    request: ExecutionPlanUpdate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> ExecutionPlan:
    plan = (
        db.query(ExecutionPlan)
        .join(Application, Application.id == ExecutionPlan.application_id)
        .filter(ExecutionPlan.id == plan_id, Application.created_by == user.id)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution plan not found")

    old_snapshot = {
        "name": plan.name,
        "target_type": plan.target_type,
        "case_ids": plan.case_ids,
        "execution_mode": plan.execution_mode,
    }

    if request.name is not None:
        plan.name = request.name.strip()
    if request.description is not None:
        plan.description = request.description
    if request.target_type is not None:
        plan.target_type = request.target_type
    if request.case_ids is not None:
        plan.case_ids = request.case_ids
    if request.suite_ids is not None:
        plan.suite_ids = request.suite_ids
    if request.execution_mode is not None:
        plan.execution_mode = request.execution_mode
    if request.schedule_cron is not None:
        plan.schedule_cron = request.schedule_cron
    if request.status is not None:
        plan.status = request.status

    db.add(plan)
    log_audit_event(
        db,
        user_id=user.id,
        action="execution_plan.update",
        resource_type="execution_plan",
        resource_id=plan.id,
        metadata={"old": old_snapshot, "new": {"name": plan.name, "target_type": plan.target_type}},
    )
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_execution_plan(
    plan_id: int,
    db: DbSession,
    user: User = Depends(require_roles("qa_lead", "admin")),
) -> None:
    plan = (
        db.query(ExecutionPlan)
        .join(Application, Application.id == ExecutionPlan.application_id)
        .filter(ExecutionPlan.id == plan_id, Application.created_by == user.id)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution plan not found")

    db.delete(plan)
    log_audit_event(
        db,
        user_id=user.id,
        action="execution_plan.delete",
        resource_type="execution_plan",
        resource_id=plan_id,
        metadata={"deleted_name": plan.name},
    )
    db.commit()
