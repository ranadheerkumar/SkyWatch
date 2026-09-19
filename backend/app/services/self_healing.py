import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_recommendation import AgentRecommendation
from app.models.test_case import TestCase
from app.models.test_case_automation import TestCaseAutomation
from app.schemas.execution import Step
from app.services.audit import log_audit_event


HEALABLE_ELEMENT_ACTIONS = {
    "click",
    "type",
    "select",
    "check",
    "uncheck",
    "assert_visible",
    "assert_text",
}


@dataclass(frozen=True)
class HealingLearningResult:
    applied_indexes: tuple[int, ...] = ()
    skipped_count: int = 0
    recommendation_id: int | None = None
    error: str | None = None


def _step_matches_original(current: Step, original: object) -> bool:
    if not isinstance(original, dict):
        return False
    return (
        original.get("action") == current.action
        and original.get("selector") == current.selector
        and original.get("secret_name") == current.secret_name
    )


def _safe_recommendation_step(step: Step) -> dict[str, Any]:
    safe_step = step.model_dump(exclude_none=True)
    selector = str(safe_step.get("selector") or "")
    if safe_step.get("secret_name") or (
        step.action == "type" and re.search(r"password|secret|token|credential", selector, re.IGNORECASE)
    ):
        safe_step["value"] = "[redacted]"
    return safe_step


def merge_healed_steps(
    current_steps: list[dict] | None,
    healed_steps: list[dict] | None,
) -> tuple[list[dict], tuple[int, ...], list[dict[str, Any]], int]:
    updated_steps = list(current_steps or [])
    applied_indexes: list[int] = []
    safe_replacements: list[dict[str, Any]] = []
    skipped_count = 0

    for repair in healed_steps or []:
        if not isinstance(repair, dict):
            skipped_count += 1
            continue
        index = repair.get("index")
        raw_healed_step = repair.get("healed_step")
        if not isinstance(index, int) or isinstance(index, bool) or index < 1 or index > len(updated_steps):
            skipped_count += 1
            continue
        try:
            current_step = Step.model_validate(updated_steps[index - 1])
            healed_step = Step.model_validate(raw_healed_step)
        except Exception:
            skipped_count += 1
            continue
        if current_step.action not in HEALABLE_ELEMENT_ACTIONS:
            skipped_count += 1
            continue
        if healed_step.action != current_step.action or not healed_step.selector:
            skipped_count += 1
            continue
        if not _step_matches_original(current_step, repair.get("original_step")):
            skipped_count += 1
            continue

        learned_step = healed_step.model_copy(
            update={
                "value": current_step.value,
                "secret_name": current_step.secret_name,
            },
        )
        updated_steps[index - 1] = learned_step.model_dump(exclude_none=True)
        applied_indexes.append(index)
        safe_replacements.append(_safe_recommendation_step(learned_step))

    return updated_steps, tuple(applied_indexes), safe_replacements, skipped_count


def persist_healing_learning(
    db: Session,
    *,
    run_id: str,
    application_id: int,
    test_case_id: int,
    created_by: int,
    healed_steps: list[dict] | None,
) -> HealingLearningResult:
    if not healed_steps:
        return HealingLearningResult()

    automation = db.get(TestCaseAutomation, test_case_id)
    test_case = db.get(TestCase, test_case_id)
    if not automation or not test_case or test_case.application_id != application_id:
        return HealingLearningResult(skipped_count=len(healed_steps))

    updated_steps, applied_indexes, safe_replacements, skipped_count = merge_healed_steps(
        automation.steps,
        healed_steps,
    )
    if not applied_indexes:
        return HealingLearningResult(skipped_count=skipped_count)

    try:
        automation.steps = updated_steps
        automation.updated_by = created_by
        recommendation = AgentRecommendation(
            application_id=application_id,
            test_case_id=test_case_id,
            recommendation_type="healing",
            title=f"Self-healed selectors for {test_case.title}",
            description=(
                f"Playwright Test Healer repaired {len(applied_indexes)} locator(s) during run "
                f"{run_id[:12]}. Validated replacements were applied to future executions."
            ),
            proposed_steps=safe_replacements,
            proposed_checks=None,
            status="auto_applied",
            created_by=created_by,
        )
        db.add(recommendation)
        db.flush()

        # Update fast-path self-learning locator knowledge base
        from app.services.self_learning import SelfLearningEngine
        learner = SelfLearningEngine(application_id)
        for repair in healed_steps or []:
            if isinstance(repair, dict):
                orig = repair.get("original_step", {})
                healed = repair.get("healed_step", {})
                if isinstance(orig, dict) and isinstance(healed, dict):
                    act = str(orig.get("action") or "")
                    raw_sel = str(orig.get("selector") or "")
                    healed_sel = str(healed.get("selector") or "")
                    if act and raw_sel and healed_sel:
                        learner.record_successful_locator(act, raw_sel, healed_sel, source="healer")
        log_audit_event(
            db,
            user_id=created_by,
            action="execution.healing.learned",
            resource_type="test_case",
            resource_id=test_case_id,
            metadata={
                "application_id": application_id,
                "run_id": run_id,
                "applied_step_indexes": list(applied_indexes),
                "skipped_repair_count": skipped_count,
                "recommendation_id": recommendation.id,
            },
        )
        try:
            import asyncio
            from app.services.vector_service import VectorStoreService
            vstore = VectorStoreService(application_id)
            for repair in healed_steps:
                if isinstance(repair, dict):
                    orig = repair.get("original_step") or {}
                    healed = repair.get("healed_step") or {}
                    orig_sel = str(orig.get("selector") or "")
                    healed_sel = str(healed.get("selector") or "")
                    if orig_sel and healed_sel:
                        try:
                            try:
                                loop = asyncio.get_running_loop()
                                asyncio.create_task(vstore.index_healing_repair(
                                    run_id=run_id,
                                    step_index=int(repair.get("index") or 1),
                                    action=str(orig.get("action") or "click"),
                                    failed_selector=orig_sel,
                                    healed_selector=healed_sel,
                                    failure_message=str(repair.get("reason") or "Locator drift healed"),
                                    reason=repair.get("reason"),
                                ))
                            except RuntimeError:
                                asyncio.run(vstore.index_healing_repair(
                                    run_id=run_id,
                                    step_index=int(repair.get("index") or 1),
                                    action=str(orig.get("action") or "click"),
                                    failed_selector=orig_sel,
                                    healed_selector=healed_sel,
                                    failure_message=str(repair.get("reason") or "Locator drift healed"),
                                    reason=repair.get("reason"),
                                ))
                        except Exception:
                            pass
        except Exception:
            pass

        return HealingLearningResult(
            applied_indexes=applied_indexes,
            skipped_count=skipped_count,
            recommendation_id=recommendation.id,
        )
    except Exception as error:
        db.rollback()
        return HealingLearningResult(
            skipped_count=skipped_count + len(applied_indexes),
            error=f"{type(error).__name__}: {str(error)[:240]}",
        )
