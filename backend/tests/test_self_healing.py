from app.core.config import settings
from app.core.database import SessionLocal
from app.models.agent_recommendation import AgentRecommendation
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.test_case import TestCase as _CaseModel
from app.models.test_case_automation import TestCaseAutomation as _AutomationModel
from app.models.user import User
from app.services.self_healing import merge_healed_steps, persist_healing_learning


def test_merge_healed_steps_requires_same_action_and_original_locator() -> None:
    current_steps = [
        {"action": "click", "selector": "#old-submit"},
        {"action": "type", "selector": "#password", "secret_name": "LOGIN_PASSWORD"},
    ]
    healed_steps = [
        {
            "index": 1,
            "original_step": {"action": "click", "selector": "#old-submit"},
            "healed_step": {"action": "click", "selector": "role=button[name=Submit]"},
        },
        {
            "index": 2,
            "original_step": {"action": "type", "selector": "#different-password", "secret_name": "LOGIN_PASSWORD"},
            "healed_step": {"action": "type", "selector": "label=Password", "value": "secret-leak"},
        },
    ]

    merged, applied_indexes, safe_replacements, skipped_count = merge_healed_steps(current_steps, healed_steps)

    assert applied_indexes == (1,)
    assert skipped_count == 1
    assert merged[0]["selector"] == "role=button[name=Submit]"
    assert merged[1]["selector"] == "#password"
    assert safe_replacements == [{"action": "click", "selector": "role=button[name=Submit]"}]


def test_persist_healing_learning_updates_automation_and_audit_records() -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == settings.INITIAL_ADMIN_EMAIL).first()
        assert user is not None
        application = db.query(Application).filter(Application.created_by == user.id).first()
        assert application is not None
        test_case = _CaseModel(
            application_id=application.id,
            created_by=user.id,
            title="Self-learning selector case",
            steps="1. Click the submit button\n2. Verify the result",
            status="ready",
        )
        db.add(test_case)
        db.flush()
        automation = _AutomationModel(
            test_case_id=test_case.id,
            steps=[
                {"action": "click", "selector": "#old-submit"},
                {"action": "assert_visible", "selector": "body"},
            ],
            checks=[],
            updated_by=user.id,
        )
        db.add(automation)
        db.commit()
        test_case_id = test_case.id
        application_id = application.id
        user_id = user.id
        db.query(AgentRecommendation).filter(AgentRecommendation.test_case_id == test_case_id).delete(synchronize_session=False)
        db.commit()

    try:
        with SessionLocal() as db:
            result = persist_healing_learning(
                db,
                run_id="self-learning-run-001",
                application_id=application_id,
                test_case_id=test_case_id,
                created_by=user_id,
                healed_steps=[
                    {
                        "index": 1,
                        "original_step": {"action": "click", "selector": "#old-submit"},
                        "healed_step": {"action": "click", "selector": "role=button[name=Submit]"},
                    },
                ],
            )
            db.commit()
            updated_automation = db.get(_AutomationModel, test_case_id)
            recommendations = db.query(AgentRecommendation).filter(
                AgentRecommendation.test_case_id == test_case_id,
                AgentRecommendation.recommendation_type == "healing",
            ).all()
            recommendation = recommendations[-1]
            audit = db.query(AuditLog).filter(
                AuditLog.action == "execution.healing.learned",
                AuditLog.resource_id == str(test_case_id),
            ).order_by(AuditLog.id.desc()).first()

            assert result.applied_indexes == (1,)
            assert updated_automation is not None
            assert updated_automation.steps[0]["selector"] == "role=button[name=Submit]"
            assert recommendation.status == "auto_applied"
            assert recommendation.proposed_steps == [{"action": "click", "selector": "role=button[name=Submit]"}]
            assert audit.metadata_json["run_id"] == "self-learning-run-001"
    finally:
        with SessionLocal() as db:
            db.query(AuditLog).filter(
                AuditLog.action == "execution.healing.learned",
                AuditLog.resource_id == str(test_case_id),
            ).delete(synchronize_session=False)
            db.query(AgentRecommendation).filter(AgentRecommendation.test_case_id == test_case_id).delete(synchronize_session=False)
            db.query(_AutomationModel).filter(_AutomationModel.test_case_id == test_case_id).delete(synchronize_session=False)
            db.query(_CaseModel).filter(_CaseModel.id == test_case_id).delete(synchronize_session=False)
            db.commit()
