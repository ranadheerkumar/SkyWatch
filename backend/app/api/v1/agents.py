from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.agent_recommendation import AgentRecommendation
from app.models.application import Application
from app.models.test_case import TestCase
from app.models.test_case_automation import TestCaseAutomation
from app.models.user import User
from app.schemas.agent import (
    AgentRecommendationAction,
    AgentRecommendationCreate,
    AgentRecommendationResponse,
    PreExecutionAnalysisRequest,
    PreExecutionAnalysisResponse,
)
from app.services.agent_definitions import (
    AGENT_FILE_MAP,
    AgentDefinitionError,
    get_agent_trace_metadata,
)
from app.services.audit import log_audit_event
from app.services.automation_builder import build_case_automation_from_text
from app.services.automation_quality import evaluate_automation_quality

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/manifest", response_model=list[dict[str, str]])
def get_agents_manifest(
    user: User = Depends(current_user),
) -> list[dict[str, str]]:
    del user
    try:
        return get_agent_trace_metadata(list(AGENT_FILE_MAP.keys()))
    except AgentDefinitionError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/recommendations", response_model=list[AgentRecommendationResponse])
def list_agent_recommendations(
    db: DbSession,
    application_id: int | None = None,
    status_filter: str | None = None,
    user: User = Depends(current_user),
) -> list[AgentRecommendation]:
    query = (
        db.query(AgentRecommendation)
        .join(Application, Application.id == AgentRecommendation.application_id)
        .filter(Application.created_by == user.id)
    )
    if application_id:
        query = query.filter(AgentRecommendation.application_id == application_id)
    if status_filter:
        query = query.filter(AgentRecommendation.status == status_filter)
    return query.order_by(AgentRecommendation.id.desc()).all()


@router.post("/analyze", response_model=PreExecutionAnalysisResponse)
def analyze_pre_execution_readiness(
    request: PreExecutionAnalysisRequest,
    db: DbSession,
    user: User = Depends(current_user),
) -> PreExecutionAnalysisResponse:
    application = (
        db.query(Application)
        .filter(Application.id == request.application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    cases_query = db.query(TestCase).filter(
        TestCase.application_id == request.application_id,
        TestCase.created_by == user.id,
    )
    if request.case_ids:
        cases_query = cases_query.filter(TestCase.id.in_(request.case_ids))
    cases = cases_query.order_by(TestCase.id.asc()).all()

    total_analyzed = len(cases)
    ready_count = 0
    at_risk_count = 0
    outdated_count = 0
    insights: list[str] = []
    generated_recommendations: list[AgentRecommendation] = []

    for test_case in cases:
        automation = db.get(TestCaseAutomation, test_case.id)
        steps = automation.steps if automation and automation.steps else None
        checks = automation.checks if automation and automation.checks else None
        if not steps:
            gen_steps, gen_checks = build_case_automation_from_text(test_case, application)
            steps = gen_steps
            checks = gen_checks

        quality = evaluate_automation_quality(steps, checks)
        if quality.confidence_label == "high":
            ready_count += 1
        elif quality.confidence_label == "medium":
            at_risk_count += 1
            rec = AgentRecommendation(
                application_id=application.id,
                test_case_id=test_case.id,
                recommendation_type="missing_validation",
                title=f"Strengthen Assertions for {test_case.title}",
                description=f"Confidence is {quality.confidence_score}%. Reasons: {', '.join(quality.reasons)}",
                proposed_steps=steps,
                proposed_checks=[{"type": "visible", "value": "body"}, {"type": "text_contains", "value": "Dashboard"}],
                status="pending",
                created_by=user.id,
            )
            db.add(rec)
            generated_recommendations.append(rec)
        else:
            outdated_count += 1
            rec = AgentRecommendation(
                application_id=application.id,
                test_case_id=test_case.id,
                recommendation_type="outdated_test",
                title=f"Selector Drift & Missing Automation for {test_case.title}",
                description=f"Low confidence ({quality.confidence_score}%). Automated steps need review. Reasons: {', '.join(quality.reasons)}",
                proposed_steps=steps,
                proposed_checks=checks,
                status="pending",
                created_by=user.id,
            )
            db.add(rec)
            generated_recommendations.append(rec)

    insights.append(f"Pre-execution analysis finished for {total_analyzed} test case(s).")
    if at_risk_count > 0:
        insights.append(f"{at_risk_count} test case(s) contain fragile text selectors or limited assertions.")
    if outdated_count > 0:
        insights.append(f"{outdated_count} test case(s) flagged as outdated or missing resilient locators.")
    if ready_count == total_analyzed:
        insights.append("All analyzed test cases exhibit high locator readiness.")

    db.commit()
    for rec in generated_recommendations:
        db.refresh(rec)

    return PreExecutionAnalysisResponse(
        application_id=application.id,
        total_analyzed=total_analyzed,
        ready_count=ready_count,
        at_risk_count=at_risk_count,
        outdated_count=outdated_count,
        insights=insights,
        recommendations=generated_recommendations,
    )


@router.post("/recommendations/{recommendation_id}/review", response_model=AgentRecommendationResponse)
def review_agent_recommendation(
    recommendation_id: int,
    action_body: AgentRecommendationAction,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> AgentRecommendation:
    rec = (
        db.query(AgentRecommendation)
        .join(Application, Application.id == AgentRecommendation.application_id)
        .filter(AgentRecommendation.id == recommendation_id, Application.created_by == user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent recommendation not found")

    rec.status = "approved" if action_body.action == "approve" else "rejected"
    rec.reviewed_by = user.id
    rec.reviewed_at = datetime.now(timezone.utc)

    # If approved and attached to a test case, apply proposed steps/checks to automation
    if rec.status == "approved" and rec.test_case_id and (rec.proposed_steps or rec.proposed_checks):
        automation = db.get(TestCaseAutomation, rec.test_case_id)
        if not automation:
            automation = TestCaseAutomation(test_case_id=rec.test_case_id, updated_by=user.id)
            db.add(automation)
        if rec.proposed_steps is not None:
            automation.steps = rec.proposed_steps
        if rec.proposed_checks is not None:
            automation.checks = rec.proposed_checks
        automation.updated_by = user.id

    log_audit_event(
        db,
        user_id=user.id,
        action=f"agent.recommendation.{action_body.action}",
        resource_type="agent_recommendation",
        resource_id=rec.id,
        metadata={
            "recommendation_type": rec.recommendation_type,
            "test_case_id": rec.test_case_id,
            "review_notes": action_body.review_notes,
            "approval_status": rec.status,
        },
    )
    db.commit()
    db.refresh(rec)
    return rec
