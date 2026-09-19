import csv
import io
import os
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.application import Application
from app.models.build_execution import BuildExecution
from app.models.case_execution import CaseExecution
from app.models.execution_plan import ExecutionPlan
from app.models.test_case import TestCase
from app.models.test_case_automation import TestCaseAutomation
from app.models.test_run import TestRun
from app.models.user import User
from app.schemas.execution import (
    BatchExecutionCreated,
    BatchExecutionRequest,
    BuildCaseExecutionItem,
    BuildExecutionDetail,
    BuildExecutionSummary,
    Check,
    CheckResult,
    ExecutionArtifact,
    ExecutionRequest,
    ExecutionResponse,
    RunCreated,
    RunStatus,
    RunSummary,
    Step,
    StepResult,
)
from app.schemas.test_case import MultiFormatIngestRequest
from app.services.run_queue import (
    QueueUnavailableError,
    abort_active_batch,
    abort_active_run,
    enqueue_run,
    sync_build_execution_status,
)
from app.services.automation_builder import build_case_automation_from_text, has_invalid_credential_instruction
from app.services.test_execution import validate_target
from app.services.audit import log_audit_event


router = APIRouter(prefix="/execution", tags=["execution"])


def _automation_uses_login_secrets(steps: list[dict] | None) -> bool:
    return any(
        isinstance(step, dict)
        and step.get("action") == "type"
        and "login" in str(step.get("secret_name") or "").casefold()
        and any(term in str(step.get("secret_name") or "").casefold() for term in ("email", "username", "password", "passcode"))
        for step in (steps or [])
    )


def _credential_step_kind(step: object) -> str | None:
    if not isinstance(step, dict) or step.get("action") != "type":
        return None
    signal = " ".join(
        str(step.get(key) or "")
        for key in ("selector", "secret_name", "value")
    ).casefold()
    if re.search(r"password|passcode|passwd|pwd", signal):
        return "password"
    if re.search(r"email|username|user[_\s-]*name|identifier", signal):
        return "email"
    return None


def _login_selector_error(steps: list[dict] | None) -> str | None:
    email_selectors: list[str] = []
    password_selectors: list[str] = []
    for step in steps or []:
        kind = _credential_step_kind(step)
        selector = str(step.get("selector") or "").strip() if isinstance(step, dict) else ""
        if not kind or not selector:
            continue
        normalized_selector = re.sub(r"\s+", " ", selector).casefold()
        selector_has_password = bool(re.search(r"password|passcode|passwd|pwd", normalized_selector))
        selector_has_identity = bool(re.search(r"email|username|user[_\s-]*name|identifier", normalized_selector))
        if kind == "password":
            if selector_has_identity and not selector_has_password:
                return "Login password step points to an email/username selector. Use a distinct password field selector such as #user_password."
            password_selectors.append(normalized_selector)
        else:
            if selector_has_password:
                return "Login email/username step points to a password selector. Use a distinct email/username field selector such as #user_email."
            email_selectors.append(normalized_selector)

    if set(email_selectors).intersection(password_selectors):
        return "Login email and password steps use the same selector. Configure separate fields before starting execution."
    return None


def _format_duration_for_export(duration_ms: object) -> str:
    if not isinstance(duration_ms, (int, float)) or duration_ms <= 0:
        return ""
    total_seconds = float(duration_ms) / 1000
    if total_seconds < 0.1:
        return "<0.1 s"
    if total_seconds < 10:
        return f"{total_seconds:.1f} s"

    rounded_seconds = int(total_seconds + 0.5)
    if rounded_seconds < 60:
        return f"{rounded_seconds} s"

    total_minutes, remaining_seconds = divmod(rounded_seconds, 60)
    if total_minutes < 60:
        return f"{total_minutes} min {remaining_seconds} s" if remaining_seconds else f"{total_minutes} min"

    total_hours, remaining_minutes = divmod(total_minutes, 60)
    return f"{total_hours} hr {remaining_minutes} min" if remaining_minutes else f"{total_hours} hr"


def _mark_run_queue_failure(db: Session, run_id: str, error: Exception) -> None:
    run = db.get(TestRun, run_id)
    if not run:
        return
    failure_message = f"Queue unavailable: {type(error).__name__}"
    run.status = "error"
    run.finished_at = datetime.now(timezone.utc)
    run.log = f"{run.log or ''}{failure_message}\n"
    case_execution = db.query(CaseExecution).filter(CaseExecution.run_id == run_id).first()
    if case_execution:
        case_execution.status = "error"
        case_execution.finished_at = run.finished_at
    log_audit_event(
        db,
        user_id=run.created_by,
        action="execution.queue.failed",
        resource_type="test_run",
        resource_id=run_id,
        metadata={"error_type": type(error).__name__},
    )
    db.commit()


def _enqueue_run_or_raise(db: Session, run_id: str, request: ExecutionRequest) -> None:
    try:
        enqueue_run(run_id, request)
    except QueueUnavailableError as error:
        _mark_run_queue_failure(db, run_id, error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution queue is unavailable. Start Redis or select the local queue explicitly.",
        ) from error


def _latest_live_event(log_text: str) -> tuple[str | None, str | None]:
    if not log_text:
        return None, None
    for line in reversed(log_text.splitlines()):
        if not line.startswith("LIVE_EVENT|"):
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        state = parts[1].strip() or None
        message = parts[2].strip() or None
        return state, message
    return None, None


def _is_valid_concrete_val(val: object) -> bool:
    if not val:
        return False
    s = str(val).strip()
    return bool(s and not s.startswith("{{") and not s.startswith("${"))


def _resolve_application_credentials_and_parameters(
    db: Session,
    application: Application | None,
    raw_parameters: dict[str, str] | None = None,
) -> dict[str, str]:
    merged = {
        k: str(v)
        for k, v in (raw_parameters or {}).items()
        if _is_valid_concrete_val(v)
    }
    if not application:
        return merged

    if not _is_valid_concrete_val(merged.get("login_email")) or not _is_valid_concrete_val(merged.get("login_password")):
        from app.models.ai_generation_job import AIGenerationJob
        from app.services.ai_service import _extract_credentials_from_text
        latest_job = (
            db.query(AIGenerationJob)
            .filter(AIGenerationJob.application_id == application.id)
            .order_by(AIGenerationJob.created_at.desc())
            .first()
        )
        if latest_job:
            payload = latest_job.request_payload or {}
            intake = (latest_job.result or {}).get("intake_signals") or {}
            job_email = payload.get("login_email") or intake.get("username")
            job_pass = payload.get("login_password") or intake.get("password")
            if not _is_valid_concrete_val(job_email) or not _is_valid_concrete_val(job_pass):
                extracted_e, extracted_p = _extract_credentials_from_text(payload.get("prompt"), payload.get("document_context"))
                job_email = job_email if _is_valid_concrete_val(job_email) else extracted_e
                job_pass = job_pass if _is_valid_concrete_val(job_pass) else extracted_p
            if _is_valid_concrete_val(job_email) and not _is_valid_concrete_val(merged.get("login_email")):
                merged["login_email"] = str(job_email)
            if _is_valid_concrete_val(job_pass) and not _is_valid_concrete_val(merged.get("login_password")):
                merged["login_password"] = str(job_pass)

        # Optional generic environment variable fallback
        env_email = os.getenv("DEFAULT_LOGIN_EMAIL") or os.getenv("STAGING_EMAIL")
        env_pass = os.getenv("DEFAULT_LOGIN_PASSWORD") or os.getenv("STAGING_PASSWORD")
        if env_email and not _is_valid_concrete_val(merged.get("login_email")):
            merged["login_email"] = env_email
        if env_pass and not _is_valid_concrete_val(merged.get("login_password")):
            merged["login_password"] = env_pass

    # Ensure aliases are populated for any referenced token format
    if _is_valid_concrete_val(merged.get("login_email")):
        resolved_e = str(merged["login_email"])
        if not merged.get("email"):
            merged["email"] = resolved_e
        if not merged.get("username"):
            merged["username"] = resolved_e
        if not merged.get("user"):
            merged["user"] = resolved_e
    elif _is_valid_concrete_val(merged.get("email")) or _is_valid_concrete_val(merged.get("username")):
        resolved_e = str(merged.get("email") or merged.get("username"))
        if resolved_e:
            merged["login_email"] = resolved_e
            if not merged.get("email"):
                merged["email"] = resolved_e
            if not merged.get("username"):
                merged["username"] = resolved_e

    if _is_valid_concrete_val(merged.get("login_password")):
        resolved_p = str(merged["login_password"])
        if not merged.get("password"):
            merged["password"] = resolved_p
        if not merged.get("pass"):
            merged["pass"] = resolved_p
    elif _is_valid_concrete_val(merged.get("password")):
        resolved_p = str(merged["password"])
        if resolved_p:
            merged["login_password"] = resolved_p
            if not merged.get("pass"):
                merged["pass"] = resolved_p

    return merged


@router.post("/run", response_model=RunCreated, status_code=202)
async def run_web_execution(
    request: ExecutionRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> RunCreated:
    application_id = None
    application = None
    try:
        validate_target(str(request.url))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    selector_error = _login_selector_error([step.model_dump() for step in request.steps])
    if selector_error:
        raise HTTPException(status_code=400, detail=selector_error)

    if request.application_id is not None and request.application_id > 0:
        application = (
            db.query(Application)
            .filter(
                Application.id == request.application_id,
                Application.created_by == user.id,
            )
            .first()
        )
        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found",
            )
        if application.platform != "web":
            raise HTTPException(
                status_code=400,
                detail="Only web applications can be run by the Playwright worker",
            )
        application_id = request.application_id
    else:
        application = (
            db.query(Application)
            .filter(
                Application.target == str(request.url),
                Application.created_by == user.id,
            )
            .first()
        )
        if application:
            application_id = application.id

    request.parameters = _resolve_application_credentials_and_parameters(db, application, request.parameters)

    stored_steps = []
    for step in request.steps:
        step_data = step.model_dump()
        if step.action == "type" and ("password" in (step.selector or "").lower() or step.secret_name):
            step_data["value"] = "[redacted]"
        stored_steps.append(step_data)

    run = TestRun(
        id=uuid4().hex,
        application_id=application_id,
        created_by=user.id,
        status="queued",
        steps=stored_steps,
    )

    db.add(run)
    log_audit_event(
        db,
        user_id=user.id,
        action="execution.run.queued",
        resource_type="test_run",
        resource_id=run.id,
        metadata={
            "application_id": application_id,
            "step_count": len(stored_steps),
            "execution_mode": request.execution_mode,
            "headless": request.headless,
            "slow_mode": request.slow_mode,
            "trace_mode": request.trace_mode,
            "capture_audio": request.capture_audio,
            "voice_gender": request.voice_gender,
            "highlight_actions": request.highlight_actions,
            "parameter_key_count": len(request.parameters),
        },
    )
    db.commit()

    _enqueue_run_or_raise(db, run.id, request)

    return RunCreated(
        run_id=run.id,
        status="queued",
    )


@router.post(
    "/test-case/{test_case_id}",
    response_model=RunCreated,
    status_code=202,
)
async def run_test_case(
    test_case_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
    batch_id: str | None = Query(default=None, max_length=64),
    build_name: str | None = Query(default=None, max_length=200),
    trigger_source: str | None = Query(default="manual", max_length=50),
    capture_screenshot: bool = True,
    capture_video: bool = True,
    capture_audio: bool = True,
    voice_gender: Literal["male", "female"] = "male",
    execution_mode: Literal["watch_live", "background"] = "watch_live",
    trace_mode: Literal["off", "on_failure", "always"] = "on_failure",
    slow_mode: Literal["normal", "demo", "showcase"] = "normal",
    keep_browser_open_on_failure: bool = True,
    keep_browser_open_seconds: int | None = None,
    healing_enabled: bool = True,
    healing_attempts: int = Query(default=1, ge=0, le=2),
    ai_provider: str | None = Query(default=None, max_length=100),
    ai_model: str | None = Query(default=None, max_length=100),
    highlight_actions: bool = Query(default=True),
    parameters: dict[str, str] | None = Body(default=None, embed=True),
) -> RunCreated:

    # ---------------------------------------------------------
    # 1. Load test case and verify ownership
    # ---------------------------------------------------------

    test_case = (
        db.query(TestCase)
        .join(
            Application,
            Application.id == TestCase.application_id,
        )
        .filter(
            TestCase.id == test_case_id,
            Application.created_by == user.id,
        )
        .first()
    )

    if not test_case:
        raise HTTPException(
            status_code=404,
            detail="Test case not found",
        )

    # ---------------------------------------------------------
    # 2. Load application
    # ---------------------------------------------------------

    application = (
        db.query(Application)
        .filter(
            Application.id == test_case.application_id,
            Application.created_by == user.id,
        )
        .first()
    )

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    if application.platform != "web":
        raise HTTPException(
            status_code=400,
            detail="Only web applications can currently be executed",
        )

    if not application.target:
        raise HTTPException(
            status_code=400,
            detail="Application does not have a target URL",
        )

    # ---------------------------------------------------------
    # 3. Load saved automation
    # ---------------------------------------------------------

    automation = db.get(
        TestCaseAutomation,
        test_case_id,
    )

    if automation:
        steps = automation.steps or []
        checks = automation.checks or []
        needs_rebuild = (
            (has_invalid_credential_instruction(test_case.steps) and _automation_uses_login_secrets(steps))
            or any(s.get("selector") == "" for s in steps if isinstance(s, dict) and s.get("action") in {"type", "click"})
            or any(isinstance(s, dict) and s.get("action") == "assert_text" and str(s.get("value", "")).startswith("/") for s in steps)
            or any(isinstance(s, dict) and s.get("action") == "check" and "label=for " in str(s.get("selector", "")) for s in steps)
            or any(isinstance(s, dict) and s.get("action") == "assert_title" and str(s.get("value", "")).lower() in {"visible", "present", "loaded", "displayed"} for s in steps)
        )
        if needs_rebuild or not steps:
            steps, checks = build_case_automation_from_text(test_case, application)
            automation.steps = steps
            automation.checks = checks
            db.add(automation)
            db.commit()
    else:
        steps, checks = build_case_automation_from_text(test_case, application)

    if not steps and not checks:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Test case {test_case_id} has no executable steps or checks."
            ),
        )

    selector_error = _login_selector_error(steps)
    if selector_error:
        raise HTTPException(status_code=400, detail=selector_error)

    # ---------------------------------------------------------
    # 4. Build execution request from persisted automation
    # ---------------------------------------------------------

    raw_parameters = parameters if isinstance(parameters, dict) else {}
    case_data: dict[str, str] = {}
    if test_case.test_data:
        if isinstance(test_case.test_data, dict):
            case_data = {str(k): str(v) for k, v in test_case.test_data.items() if not str(k).startswith("_") and _is_valid_concrete_val(v)}
        elif isinstance(test_case.test_data, str):
            try:
                import json
                parsed_td = json.loads(test_case.test_data)
                if isinstance(parsed_td, dict):
                    case_data = {str(k): str(v) for k, v in parsed_td.items() if not str(k).startswith("_") and _is_valid_concrete_val(v)}
                elif isinstance(parsed_td, list) and parsed_td and isinstance(parsed_td[0], dict):
                    case_data = {str(k): str(v) for k, v in parsed_td[0].items() if not str(k).startswith("_") and _is_valid_concrete_val(v)}
            except Exception:
                pass
    valid_raw_params = {str(k): str(v) for k, v in raw_parameters.items() if _is_valid_concrete_val(v)}
    combined_raw_params = {**case_data, **valid_raw_params}
    merged_parameters = _resolve_application_credentials_and_parameters(db, application, combined_raw_params)

    default_visible_hold_seconds = 6
    if keep_browser_open_seconds is None:
        resolved_keep_open_seconds = 0 if execution_mode == "background" else default_visible_hold_seconds
    else:
        resolved_keep_open_seconds = max(0, min(120, keep_browser_open_seconds))

    resolved_healing_attempts = healing_attempts if isinstance(healing_attempts, int) else 1
    resolved_ai_provider = ai_provider if isinstance(ai_provider, str) else None
    resolved_ai_model = ai_model if isinstance(ai_model, str) else None
    resolved_highlight_actions = bool(highlight_actions) if isinstance(highlight_actions, bool) else True

    request = ExecutionRequest(
        application_id=application.id,
        url=application.target,
        steps=steps,
        checks=checks,
        timeout_ms=30_000,
        capture_screenshot=capture_screenshot,
        capture_video=capture_video,
        capture_audio=capture_audio,
        voice_gender=voice_gender,
        execution_mode=execution_mode,
        headless=(execution_mode == "background"),
        slow_mode=slow_mode,
        trace_mode=trace_mode,
        keep_browser_open_seconds=resolved_keep_open_seconds,
        keep_browser_open_on_failure=keep_browser_open_on_failure,
        healing_enabled=healing_enabled,
        healing_attempts=resolved_healing_attempts,
        ai_provider=resolved_ai_provider,
        ai_model=resolved_ai_model,
        highlight_actions=resolved_highlight_actions,
        parameters=merged_parameters,
    )

    # ---------------------------------------------------------
    # 5. Create TestRun
    # ---------------------------------------------------------

    run_id = uuid4().hex

    stored_steps = []

    for step in steps:
        step_data = dict(step)

        if step_data.get("action") == "type" and (
            "password" in str(step_data.get("selector", "")).lower()
            or step_data.get("secret_name")
        ):
            step_data["value"] = "[redacted]"

        stored_steps.append(step_data)

    run = TestRun(
        id=run_id,
        application_id=application.id,
        created_by=user.id,
        status="queued",
        steps=stored_steps,
        batch_id=batch_id,
        build_name=build_name,
        trigger_source=trigger_source or "manual",
    )

    db.add(run)

    if batch_id:
        existing_build = db.get(BuildExecution, batch_id)
        if not existing_build:
            display_build_name = build_name or f"Build #{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
            db.add(
                BuildExecution(
                    id=batch_id,
                    application_id=application.id,
                    created_by=user.id,
                    name=display_build_name,
                    status="queued",
                    trigger_source=trigger_source or "manual",
                    total_cases=1,
                )
            )
        else:
            existing_build.total_cases = db.query(TestRun).filter(TestRun.batch_id == batch_id).count() + 1

    # ---------------------------------------------------------
    # 6. Create CaseExecution
    # ---------------------------------------------------------

    case_execution = CaseExecution(
        run_id=run_id,
        test_case_id=test_case.id,
        status="queued",
    )

    db.add(case_execution)
    log_audit_event(
        db,
        user_id=user.id,
        action="execution.test_case.queued",
        resource_type="test_case",
        resource_id=test_case.id,
        metadata={
            "run_id": run_id,
            "application_id": application.id,
            "capture_screenshot": capture_screenshot,
            "capture_video": capture_video,
            "capture_audio": capture_audio,
            "voice_gender": voice_gender,
            "execution_mode": execution_mode,
            "headless": execution_mode == "background",
            "slow_mode": slow_mode,
            "trace_mode": trace_mode,
            "keep_browser_open_on_failure": keep_browser_open_on_failure,
            "highlight_actions": resolved_highlight_actions,
            "parameter_key_count": len(merged_parameters),
            "keep_browser_open_seconds": resolved_keep_open_seconds,
            "healing_enabled": healing_enabled,
            "healing_attempts": resolved_healing_attempts,
            "ai_provider": resolved_ai_provider,
            "ai_model": resolved_ai_model,
        },
    )

    db.commit()

    # ---------------------------------------------------------
    # 7. Start Playwright worker
    # ---------------------------------------------------------

    _enqueue_run_or_raise(db, run_id, request)

    return RunCreated(
        run_id=run_id,
        status="queued",
    )


@router.get("/{run_id}", response_model=RunStatus)
def get_run(
    run_id: str,
    db: DbSession,
    user: User = Depends(current_user),
) -> RunStatus:

    run = (
        db.query(TestRun)
        .filter(
            TestRun.id == run_id,
            TestRun.created_by == user.id,
        )
        .first()
    )

    if not run:
        raise HTTPException(
            status_code=404,
            detail="Run not found",
        )
    live_state, current_action = _latest_live_event(run.log or "")

    return RunStatus(
        run_id=run.id,
        status=run.status,
        application_id=run.application_id,
        url=(run.result or {}).get("url", ""),
        steps=run.steps or [],
        result=run.result,
        log=run.log,
        live_state=live_state,
        current_action=current_action,
    )


@router.post("/{run_id}/cancel")
def cancel_run(
    run_id: str,
    db: DbSession,
    user: User = Depends(current_user),
):
    abort_active_run(run_id)

    run = (
        db.query(TestRun)
        .outerjoin(Application, Application.id == TestRun.application_id)
        .filter(
            TestRun.id == run_id,
            (TestRun.created_by == user.id) | (Application.created_by == user.id),
        )
        .first()
    )

    if not run:
        raise HTTPException(
            status_code=404,
            detail="Run not found",
        )

    if run.status in {"passed", "failed", "error", "cancelled"}:
        return {"status": run.status, "message": "Run is already finished"}

    now = datetime.now(timezone.utc)
    run.status = "cancelled"
    run.finished_at = now
    run.log = (run.log or "") + "\nLIVE_EVENT|CANCELLED|Execution cancelled by user.\nExecution cancelled by user.\n"
    if not run.result:
        run.result = {
            "run_id": run.id,
            "url": "",
            "status": "cancelled",
            "duration_ms": 0,
            "checks": [],
            "error": "Execution cancelled by user.",
        }

    case_execution = (
        db.query(CaseExecution)
        .filter(CaseExecution.run_id == run_id)
        .first()
    )
    if case_execution and case_execution.status not in {"passed", "failed", "error", "cancelled"}:
        case_execution.status = "cancelled"
        case_execution.finished_at = now

    db.commit()
    if run.batch_id:
        sync_build_execution_status(db, run.batch_id)
    return {"status": "cancelled", "message": "Run cancelled successfully"}


@router.post("/batch/{batch_id}/cancel")
def cancel_batch_execution(
    batch_id: str,
    db: DbSession,
    user: User = Depends(current_user),
):
    abort_active_batch(batch_id)

    runs = (
        db.query(TestRun)
        .outerjoin(Application, Application.id == TestRun.application_id)
        .filter(
            TestRun.batch_id == batch_id,
            (TestRun.created_by == user.id) | (Application.created_by == user.id),
        )
        .all()
    )
    build = db.get(BuildExecution, batch_id)
    if not runs and not build:
        raise HTTPException(
            status_code=404,
            detail="Batch execution not found",
        )

    now = datetime.now(timezone.utc)
    cancelled_count = 0
    for run in runs:
        if run.status not in {"passed", "failed", "error", "cancelled"}:
            run.status = "cancelled"
            run.finished_at = now
            run.log = (run.log or "") + "\nLIVE_EVENT|CANCELLED|Execution cancelled by user.\nExecution cancelled by user.\n"
            if not run.result:
                run.result = {
                    "run_id": run.id,
                    "url": "",
                    "status": "cancelled",
                    "duration_ms": 0,
                    "checks": [],
                    "error": "Execution cancelled by user.",
                }
            cancelled_count += 1

            case_exec = (
                db.query(CaseExecution)
                .filter(CaseExecution.run_id == run.id)
                .first()
            )
            if case_exec and case_exec.status not in {"passed", "failed", "error", "cancelled"}:
                case_exec.status = "cancelled"
                case_exec.finished_at = now

    if build and build.status not in {"passed", "failed", "error", "cancelled"}:
        build.status = "cancelled"
        build.finished_at = now

    db.commit()
    sync_build_execution_status(db, batch_id)
    return {
        "status": "cancelled",
        "cancelled_runs": cancelled_count,
        "message": f"Cancelled batch execution and {cancelled_count} running test(s)",
    }


@router.post("/clear-cache")
def clear_all_execution_cache(
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
    application_id: int | None = Query(default=None),
):
    """Purges all in-memory LRU learning caches, vector databases, and resets corrupted automations."""
    from app.services.self_learning import purge_all_learning_and_vector_cache
    from app.models.agent_recommendation import AgentRecommendation

    purge_all_learning_and_vector_cache()

    # Clean up stale/auto_applied healing recommendations that may contain bad selectors
    query = db.query(AgentRecommendation)
    if application_id is not None:
        query = query.filter(AgentRecommendation.application_id == application_id)
    deleted_recs = query.delete(synchronize_session=False)

    # Rebuild all automations cleanly from canonical test case text
    tc_query = db.query(TestCase)
    if application_id is not None:
        tc_query = tc_query.filter(TestCase.application_id == application_id)
    test_cases = tc_query.all()

    rebuilt_count = 0
    for tc in test_cases:
        app = db.get(Application, tc.application_id)
        if app:
            steps, checks = build_case_automation_from_text(tc, app)
            auto = db.get(TestCaseAutomation, tc.id)
            if auto:
                auto.steps = steps
                auto.checks = checks
            else:
                db.add(TestCaseAutomation(test_case_id=tc.id, steps=steps, checks=checks, created_by=user.id))
            rebuilt_count += 1

    db.commit()

    return {
        "status": "ok",
        "deleted_recommendations": deleted_recs,
        "rebuilt_automations": rebuilt_count,
        "message": f"Cleared vector & learning cache, removed {deleted_recs} recommendation(s), and cleanly rebuilt {rebuilt_count} automation definition(s).",
    }


@router.get("/{run_id}/case")
def get_case_execution(
    run_id: str,
    db: DbSession,
    user: User = Depends(current_user),
):
    run = (
        db.query(TestRun)
        .filter(
            TestRun.id == run_id,
            TestRun.created_by == user.id,
        )
        .first()
    )

    if not run:
        raise HTTPException(
            status_code=404,
            detail="Run not found",
        )

    case_execution = (
        db.query(CaseExecution)
        .filter(
            CaseExecution.run_id == run_id,
        )
        .first()
    )
    live_state, current_action = _latest_live_event(run.log or "")

    return {
        "run_id": run.id,
        "test_case_id": (
            case_execution.test_case_id
            if case_execution
            else None
        ),
        "status": (
            case_execution.status
            if case_execution
            else run.status
        ),
        "application_id": run.application_id,
        "steps": run.steps or [],
        "created_at": (
            (case_execution.created_at if case_execution else run.created_at).isoformat()
            if (case_execution.created_at if case_execution else run.created_at)
            else None
        ),
        "finished_at": (
            (case_execution.finished_at if case_execution else run.finished_at).isoformat()
            if (case_execution.finished_at if case_execution else run.finished_at)
            else None
        ),
        "run_status": run.status,
        "result": run.result,
        "log": run.log,
        "live_state": live_state,
        "current_action": current_action,
    }


@router.get("/cases/{application_id}")
def list_case_executions(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
):
    application = (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.created_by == user.id,
        )
        .first()
    )

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    rows = (
        db.query(CaseExecution, TestCase, TestRun)
        .join(
            TestCase,
            TestCase.id == CaseExecution.test_case_id,
        )
        .join(
            TestRun,
            TestRun.id == CaseExecution.run_id,
        )
        .filter(
            TestCase.application_id == application_id,
            TestRun.created_by == user.id,
        )
        .order_by(CaseExecution.created_at.desc())
        .all()
    )

    history = []
    for execution, test_case, run in rows:
        result = run.result or {}
        checks = result.get("checks") or []
        passed_checks = sum(1 for check in checks if isinstance(check, dict) and check.get("passed"))
        history.append(
            {
                "run_id": execution.run_id,
                "test_case_id": execution.test_case_id,
                "title": test_case.title,
                "status": execution.status,
                "run_status": run.status,
                "url": result.get("url", ""),
                "duration_ms": result.get("duration_ms"),
                "check_summary": f"{passed_checks}/{len(checks)} passed" if checks else "No checks",
                "failure_type": result.get("failure_type"),
                "failure_summary": result.get("failure_summary"),
                "created_at": (
                    execution.created_at.isoformat()
                    if execution.created_at
                    else None
                ),
                "finished_at": (
                    execution.finished_at.isoformat()
                    if execution.finished_at
                    else None
                ),
            }
        )
    return history


@router.get("", response_model=list[RunSummary])
def list_runs(
    db: DbSession,
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
) -> list[RunSummary]:

    query = (
        db.query(TestRun)
        .filter(TestRun.created_by == user.id)
        .order_by(TestRun.created_at.desc())
    )
    response.headers["X-Total-Count"] = str(query.count())
    runs = query.offset(offset).limit(limit).all()

    return [
        RunSummary(
            run_id=run.id,
            status=run.status,
            application_id=run.application_id,
            batch_id=run.batch_id,
            build_name=run.build_name,
            trigger_source=run.trigger_source,
            created_at=(
                run.created_at.isoformat()
                if run.created_at
                else None
            ),
            finished_at=(
                run.finished_at.isoformat()
                if run.finished_at
                else None
            ),
        )
        for run in runs
    ]


@router.post("/ingest-and-run", response_model=RunCreated, status_code=202)
async def ingest_and_run(
    request: MultiFormatIngestRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
    execution_mode: Literal["watch_live", "background"] = "watch_live",
    capture_screenshot: bool = True,
    capture_video: bool = False,
    capture_audio: bool = False,
    voice_gender: Literal["male", "female"] = "male",
    slow_mode: Literal["normal", "demo", "showcase"] = "normal",
) -> RunCreated:
    application = (
        db.query(Application)
        .filter(Application.id == request.application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    target_url = request.target_url or application.target
    if not target_url:
        raise HTTPException(status_code=400, detail="Target URL is required")

    temp_case = TestCase(
        application_id=application.id,
        title=f"Dynamic Scenario - {request.format.upper()}",
        description=f"Auto-ingested {request.format} scenario",
        preconditions=request.preconditions,
        steps=request.content,
        expected_result="Autonomous validation succeeds",
        status="ready",
        created_by=user.id,
    )
    db.add(temp_case)
    db.flush()

    steps, checks = build_case_automation_from_text(temp_case, application)
    if not steps:
        steps = [{"action": "navigate", "value": target_url}, {"action": "assert_visible", "selector": "body"}]
    if not checks:
        checks = [{"type": "visible", "value": "body"}]

    exec_req = ExecutionRequest(
        application_id=application.id,
        url=target_url,
        steps=steps,
        checks=checks,
        timeout_ms=30_000,
        capture_screenshot=capture_screenshot,
        capture_video=capture_video,
        capture_audio=capture_audio,
        voice_gender=voice_gender,
        execution_mode=execution_mode,
        headless=(execution_mode == "background"),
        slow_mode=slow_mode,
    )

    run_id = uuid4().hex
    stored_steps = []
    for step in steps:
        step_data = dict(step)
        if step_data.get("action") == "type" and ("password" in str(step_data.get("selector", "")).lower() or step_data.get("secret_name")):
            step_data["value"] = "[redacted]"
        stored_steps.append(step_data)

    run = TestRun(
        id=run_id,
        application_id=application.id,
        created_by=user.id,
        status="queued",
        steps=stored_steps,
    )
    db.add(run)
    db.add(CaseExecution(run_id=run_id, test_case_id=temp_case.id, status="queued"))
    log_audit_event(
        db,
        user_id=user.id,
        action="execution.ingest_and_run.queued",
        resource_type="test_run",
        resource_id=run_id,
        metadata={"application_id": application.id, "format": request.format, "step_count": len(steps)},
    )
    db.commit()

    _enqueue_run_or_raise(db, run_id, exec_req)

    return RunCreated(run_id=run_id, status="queued")


@router.post("/plan/{plan_id}", response_model=list[RunCreated], status_code=202)
def run_execution_plan(
    plan_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> list[RunCreated]:
    plan = (
        db.query(ExecutionPlan)
        .join(Application, Application.id == ExecutionPlan.application_id)
        .filter(ExecutionPlan.id == plan_id, Application.created_by == user.id)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Execution plan not found")

    application = db.query(Application).filter(Application.id == plan.application_id).first()
    if not application or not application.target:
        raise HTTPException(status_code=400, detail="Application or target URL missing")

    case_ids_to_run = list(plan.case_ids or [])
    if plan.suite_ids:
        from app.models.test_suite import TestSuite
        suites = db.query(TestSuite).filter(TestSuite.id.in_(plan.suite_ids)).all()
        for s in suites:
            case_ids_to_run.extend(s.case_ids or [])

    case_ids_to_run = list(dict.fromkeys(case_ids_to_run))
    if not case_ids_to_run:
        cases = db.query(TestCase).filter(TestCase.application_id == application.id).all()
        case_ids_to_run = [c.id for c in cases]

    application_parameters = _resolve_application_credentials_and_parameters(db, application)
    created_runs = []
    queued_requests: list[tuple[str, ExecutionRequest]] = []
    plan_batch_id = f"plan-{plan_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    valid_cases = [db.get(TestCase, cid) for cid in case_ids_to_run[:20]]
    valid_cases = [tc for tc in valid_cases if tc is not None]

    if valid_cases:
        db.add(
            BuildExecution(
                id=plan_batch_id,
                application_id=application.id,
                created_by=user.id,
                name=f"Plan: {plan.name}",
                status="queued",
                trigger_source="plan",
                total_cases=len(valid_cases),
            )
        )

    for tc in valid_cases:
        auto = db.get(TestCaseAutomation, tc.id)
        steps = auto.steps if auto and auto.steps else None
        checks = auto.checks if auto and auto.checks else None
        if not steps or (has_invalid_credential_instruction(tc.steps) and _automation_uses_login_secrets(steps)):
            steps, checks = build_case_automation_from_text(tc, application)
            if auto:
                auto.steps = steps
                auto.checks = checks
                db.add(auto)

        exec_req = ExecutionRequest(
            application_id=application.id,
            url=application.target,
            steps=steps,
            checks=checks or [{"type": "visible", "value": "body"}],
            execution_mode=plan.execution_mode or "watch_live",
            headless=(plan.execution_mode == "background"),
            healing_enabled=True,
            healing_attempts=1,
            highlight_actions=True,
            parameters=application_parameters,
        )
        run_id = uuid4().hex
        db_run = TestRun(
            id=run_id,
            application_id=application.id,
            created_by=user.id,
            status="queued",
            steps=steps,
            batch_id=plan_batch_id,
            build_name=f"Plan: {plan.name}",
            trigger_source="plan",
        )
        db.add(db_run)
        db.add(CaseExecution(run_id=run_id, test_case_id=tc.id, status="queued"))
        queued_requests.append((run_id, exec_req))
        created_runs.append(RunCreated(run_id=run_id, status="queued"))

    log_audit_event(
        db,
        user_id=user.id,
        action="execution_plan.run.queued",
        resource_type="execution_plan",
        resource_id=plan_id,
        metadata={"queued_runs_count": len(created_runs), "batch_id": plan_batch_id},
    )
    db.commit()

    for index, (run_id, exec_req) in enumerate(queued_requests):
        try:
            enqueue_run(run_id, exec_req)
        except QueueUnavailableError as error:
            _mark_run_queue_failure(db, run_id, error)
            created_runs[index] = RunCreated(run_id=run_id, status="error")

    if valid_cases:
        sync_build_execution_status(db, plan_batch_id)

    return created_runs


@router.get("/metrics/summary")
def get_run_metrics(
    db: DbSession,
    user: User = Depends(current_user),
) -> dict:
    status_rows = (
        db.query(TestRun.status, func.count(TestRun.id))
        .filter(TestRun.created_by == user.id)
        .group_by(TestRun.status)
        .all()
    )
    status_counts = {status: count for status, count in status_rows}
    completed_runs = (
        db.query(TestRun)
        .filter(
            TestRun.created_by == user.id,
            TestRun.finished_at.isnot(None),
        )
        .order_by(TestRun.created_at.desc())
        .limit(200)
        .all()
    )
    durations = [
        int((run.result or {}).get("duration_ms"))
        for run in completed_runs
        if isinstance((run.result or {}).get("duration_ms"), (int, float))
    ]
    average_duration_ms = round(sum(durations) / len(durations), 2) if durations else None
    return {
        "total_runs": sum(status_counts.values()),
        "status_counts": status_counts,
        "average_duration_ms": average_duration_ms,
        "sample_size": len(durations),
    }


@router.get("/export/{application_id}")
def export_execution_history(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> Response:

    application = (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.created_by == user.id,
        )
        .first()
    )

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    runs = (
        db.query(TestRun)
        .filter(
            TestRun.application_id == application_id,
            TestRun.created_by == user.id,
        )
        .order_by(TestRun.created_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Application", application.name])
    writer.writerow([])

    writer.writerow([
        "Run ID",
        "Status",
        "Target URL",
        "Page Title",
        "Duration",
        "Checks",
        "Error",
        "Created At",
        "Finished At",
    ])

    for run in runs:
        result = run.result or {}
        checks = result.get("checks") or []

        writer.writerow([
            run.id,
            run.status,
            result.get("url", application.target),
            result.get("title", ""),
            _format_duration_for_export(result.get("duration_ms")),
            (
                f"{sum(1 for check in checks if check.get('passed'))}"
                f"/{len(checks)} passed"
                if checks
                else ""
            ),
            result.get("error", ""),
            run.created_at.isoformat()
            if run.created_at
            else "",
            run.finished_at.isoformat()
            if run.finished_at
            else "",
        ])

    filename = (
        "".join(
            character if character.isalnum() else "-"
            for character in application.name
        ).strip("-")
        or "execution"
    )

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}-execution-history.csv"'
            )
        },
    )


@router.post(
    "/batch",
    response_model=BatchExecutionCreated,
    status_code=202,
)
async def run_test_cases_batch(
    request: BatchExecutionRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> BatchExecutionCreated:
    application = (
        db.query(Application)
        .filter(
            Application.id == request.application_id,
            Application.created_by == user.id,
        )
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.platform != "web":
        raise HTTPException(status_code=400, detail="Only web applications can currently be executed")
    if not application.target:
        raise HTTPException(status_code=400, detail="Application does not have a target URL")

    unique_case_ids = list(dict.fromkeys(request.case_ids))
    test_cases = (
        db.query(TestCase)
        .filter(
            TestCase.id.in_(unique_case_ids),
            TestCase.application_id == application.id,
        )
        .all()
    )
    if not test_cases:
        raise HTTPException(status_code=404, detail="No matching test cases found for this application")

    build_id = f"build-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    display_name = request.build_name or f"Build #{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
    build_execution = BuildExecution(
        id=build_id,
        application_id=application.id,
        created_by=user.id,
        name=display_name,
        status="queued",
        trigger_source=request.trigger_source or "manual",
        total_cases=len(test_cases),
        passed_count=0,
        failed_count=0,
        error_count=0,
        duration_ms=0.0,
    )
    db.add(build_execution)

    merged_parameters = _resolve_application_credentials_and_parameters(db, application, request.parameters)
    resolved_keep_open_seconds = (
        0 if request.execution_mode == "background" else 6
    ) if request.keep_browser_open_seconds is None else max(0, min(120, request.keep_browser_open_seconds))

    created_runs: list[RunCreated] = []
    queued_requests: list[tuple[str, ExecutionRequest]] = []

    for tc in test_cases:
        automation = db.get(TestCaseAutomation, tc.id)
        if automation:
            steps = automation.steps or []
            checks = automation.checks or []
            needs_rebuild = (
                (has_invalid_credential_instruction(tc.steps) and _automation_uses_login_secrets(steps))
                or any(s.get("selector") == "" for s in steps if isinstance(s, dict) and s.get("action") in {"type", "click"})
                or any(isinstance(s, dict) and s.get("action") == "assert_text" and str(s.get("value", "")).startswith("/") for s in steps)
            )
            if needs_rebuild or not steps:
                steps, checks = build_case_automation_from_text(tc, application)
                automation.steps = steps
                automation.checks = checks
                db.add(automation)
        else:
            steps, checks = build_case_automation_from_text(tc, application)

        if not steps and not checks:
            steps = [{"action": "navigate", "value": application.target}, {"action": "assert_visible", "selector": "body"}]
            checks = [{"type": "visible", "value": "body"}]

        selector_error = _login_selector_error(steps)
        if selector_error:
            raise HTTPException(status_code=400, detail=selector_error)

        tc_case_data: dict[str, str] = {}
        if tc.test_data:
            if isinstance(tc.test_data, dict):
                tc_case_data = {str(k): str(v) for k, v in tc.test_data.items() if not str(k).startswith("_") and _is_valid_concrete_val(v)}
            elif isinstance(tc.test_data, str):
                try:
                    import json
                    parsed_td = json.loads(tc.test_data)
                    if isinstance(parsed_td, dict):
                        tc_case_data = {str(k): str(v) for k, v in parsed_td.items() if not str(k).startswith("_") and _is_valid_concrete_val(v)}
                    elif isinstance(parsed_td, list) and parsed_td and isinstance(parsed_td[0], dict):
                        tc_case_data = {str(k): str(v) for k, v in parsed_td[0].items() if not str(k).startswith("_") and _is_valid_concrete_val(v)}
                except Exception:
                    pass
        tc_combined_params = {**tc_case_data, **merged_parameters}

        exec_req = ExecutionRequest(
            application_id=application.id,
            url=application.target,
            steps=steps,
            checks=checks,
            timeout_ms=30_000,
            capture_screenshot=request.capture_screenshot,
            capture_video=request.capture_video,
            capture_audio=request.capture_audio,
            voice_gender=request.voice_gender,
            execution_mode=request.execution_mode,
            headless=(request.execution_mode == "background"),
            slow_mode=request.slow_mode,
            trace_mode=request.trace_mode,
            keep_browser_open_seconds=resolved_keep_open_seconds,
            keep_browser_open_on_failure=request.keep_browser_open_on_failure,
            healing_enabled=request.healing_enabled,
            healing_attempts=request.healing_attempts,
            ai_provider=request.ai_provider,
            ai_model=request.ai_model,
            highlight_actions=request.highlight_actions,
            parameters=tc_combined_params,
        )

        run_id = uuid4().hex
        stored_steps = []
        for step in steps:
            step_data = dict(step)
            if step_data.get("action") == "type" and (
                "password" in str(step_data.get("selector", "")).lower() or step_data.get("secret_name")
            ):
                step_data["value"] = "[redacted]"
            stored_steps.append(step_data)

        run = TestRun(
            id=run_id,
            application_id=application.id,
            created_by=user.id,
            status="queued",
            steps=stored_steps,
            batch_id=build_id,
            build_name=display_name,
            trigger_source=request.trigger_source or "manual",
        )
        db.add(run)
        db.add(CaseExecution(run_id=run_id, test_case_id=tc.id, status="queued"))
        queued_requests.append((run_id, exec_req))
        created_runs.append(RunCreated(run_id=run_id, status="queued"))

    log_audit_event(
        db,
        user_id=user.id,
        action="execution.batch.queued",
        resource_type="build_execution",
        resource_id=build_id,
        metadata={
            "build_id": build_id,
            "application_id": application.id,
            "case_count": len(test_cases),
            "execution_mode": request.execution_mode,
        },
    )
    db.commit()

    for idx, (r_id, e_req) in enumerate(queued_requests):
        try:
            enqueue_run(r_id, e_req)
        except QueueUnavailableError as error:
            _mark_run_queue_failure(db, r_id, error)
            created_runs[idx] = RunCreated(run_id=r_id, status="error")

    sync_build_execution_status(db, build_id)

    return BatchExecutionCreated(
        build_id=build_id,
        application_id=application.id,
        name=display_name,
        status="queued",
        total_cases=len(test_cases),
        runs=created_runs,
    )


@router.post(
    "/builds/{build_id}/rebuild",
    response_model=BatchExecutionCreated,
    status_code=202,
)
async def rebuild_execution_batch(
    build_id: str,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
    execution_mode: Literal["watch_live", "background"] = Query(default="watch_live"),
) -> BatchExecutionCreated:
    build = db.get(BuildExecution, build_id)
    app_id: int | None = None
    build_name: str | None = None
    if build:
        app_id = build.application_id
        build_name = f"Rebuild #{build_id[-6:].upper() if len(build_id) >= 6 else build_id}" if not build.name.startswith("Rebuild") else build.name

    runs = (
        db.query(TestRun, CaseExecution)
        .outerjoin(CaseExecution, CaseExecution.run_id == TestRun.id)
        .filter(TestRun.batch_id == build_id)
        .all()
    )
    if not runs and not build:
        # Check if single run
        single_run = db.get(TestRun, build_id)
        if single_run:
            app_id = single_run.application_id
            build_name = f"Re-run {single_run.id[:8]}"
            case_exec = db.query(CaseExecution).filter(CaseExecution.run_id == single_run.id).first()
            runs = [(single_run, case_exec)]

    if not runs:
        raise HTTPException(status_code=404, detail="No test runs found for this build batch")

    app_id = app_id or runs[0][0].application_id
    application = db.get(Application, app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    case_ids = []
    for run, case_exec in runs:
        if case_exec and case_exec.test_case_id:
            case_ids.append(case_exec.test_case_id)

    case_ids = list(dict.fromkeys(case_ids))
    if not case_ids:
        all_cases = db.query(TestCase.id).filter(TestCase.application_id == application.id).all()
        case_ids = [c[0] for c in all_cases]

    req = BatchExecutionRequest(
        application_id=application.id,
        case_ids=case_ids,
        build_name=build_name or f"Rebuild #{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}",
        execution_mode=execution_mode,
        trigger_source="rebuild",
    )
    return await run_test_cases_batch(req, db, user)


@router.get("/builds/{application_id}", response_model=list[BuildExecutionSummary])
def list_build_executions(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> list[BuildExecutionSummary]:
    application = (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.created_by == user.id,
        )
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    builds = (
        db.query(BuildExecution)
        .filter(
            BuildExecution.application_id == application_id,
            BuildExecution.created_by == user.id,
        )
        .order_by(BuildExecution.created_at.desc())
        .limit(100)
        .all()
    )

    summaries: list[BuildExecutionSummary] = []
    seen_build_ids: set[str] = set()

    for build in builds:
        seen_build_ids.add(build.id)
        sync_build_execution_status(db, build.id)
        pass_rate = (
            round((build.passed_count / build.total_cases * 100), 1)
            if build.total_cases > 0
            else 0.0
        )
        summaries.append(
            BuildExecutionSummary(
                build_id=build.id,
                application_id=build.application_id,
                name=build.name,
                status=build.status,  # type: ignore[arg-type]
                trigger_source=build.trigger_source,
                total_cases=build.total_cases,
                passed_count=build.passed_count,
                failed_count=build.failed_count,
                error_count=build.error_count,
                pass_rate=pass_rate,
                duration_ms=build.duration_ms,
                created_at=build.created_at.isoformat() if build.created_at else None,
                finished_at=build.finished_at.isoformat() if build.finished_at else None,
            )
        )

    # Check if there are runs with batch_id not in BuildExecution table or orphan runs
    orphan_batches = (
        db.query(TestRun.batch_id)
        .filter(
            TestRun.application_id == application_id,
            TestRun.created_by == user.id,
            TestRun.batch_id.isnot(None),
        )
        .distinct()
        .all()
    )

    for (batch_id,) in orphan_batches:
        if not batch_id or batch_id in seen_build_ids:
            continue
        seen_build_ids.add(batch_id)
        runs = (
            db.query(TestRun)
            .filter(
                TestRun.application_id == application_id,
                TestRun.batch_id == batch_id,
                TestRun.created_by == user.id,
            )
            .all()
        )
        if not runs:
            continue
        total = len(runs)
        passed = sum(1 for r in runs if r.status == "passed")
        failed = sum(1 for r in runs if r.status == "failed")
        error = sum(1 for r in runs if r.status in ("error", "cancelled"))
        queued = sum(1 for r in runs if r.status == "queued")
        running = sum(1 for r in runs if r.status == "running")
        dur = sum(
            float((r.result or {}).get("duration_ms", 0.0) or 0.0)
            for r in runs
            if isinstance((r.result or {}).get("duration_ms"), (int, float))
        )
        b_status = (
            "running" if running > 0
            else "queued" if queued > 0
            else "failed" if (failed > 0 or error > 0)
            else "passed"
        )
        b_name = runs[0].build_name or f"Batch {batch_id[:8]}"
        b_trigger = runs[0].trigger_source or "manual"
        b_created = runs[0].created_at
        b_finished = max((r.finished_at for r in runs if r.finished_at), default=None)
        pass_rate = round((passed / total * 100), 1) if total > 0 else 0.0

        summaries.append(
            BuildExecutionSummary(
                build_id=batch_id,
                application_id=application_id,
                name=b_name,
                status=b_status,  # type: ignore[arg-type]
                trigger_source=b_trigger,
                total_cases=total,
                passed_count=passed,
                failed_count=failed,
                error_count=error,
                pass_rate=pass_rate,
                duration_ms=dur,
                created_at=b_created.isoformat() if b_created else None,
                finished_at=b_finished.isoformat() if b_finished else None,
            )
        )

    summaries.sort(key=lambda b: b.created_at or b.finished_at or "", reverse=True)
    return summaries


@router.get("/builds/{build_id}/detail", response_model=BuildExecutionDetail)
def get_build_execution_detail(
    build_id: str,
    db: DbSession,
    user: User = Depends(current_user),
) -> BuildExecutionDetail:
    build = db.get(BuildExecution, build_id)
    runs_query = (
        db.query(TestRun, CaseExecution, TestCase)
        .outerjoin(CaseExecution, CaseExecution.run_id == TestRun.id)
        .outerjoin(TestCase, TestCase.id == CaseExecution.test_case_id)
        .filter(
            TestRun.created_by == user.id,
        )
    )
    if build:
        if build.created_by != user.id:
            raise HTTPException(status_code=404, detail="Build execution not found")
        application = db.get(Application, build.application_id)
        runs_query = runs_query.filter(TestRun.batch_id == build_id)
        app_name = application.name if application else "Application"
        target_url = application.target if application else ""
        build_name = build.name
        trigger_source = build.trigger_source
        build_created_at = build.created_at.isoformat() if build.created_at else None
        build_finished_at = build.finished_at.isoformat() if build.finished_at else None
    else:
        # Check if runs exist with this batch_id or if build_id is a single run_id
        runs_query = runs_query.filter((TestRun.batch_id == build_id) | (TestRun.id == build_id))
        first_row = runs_query.first()
        if not first_row:
            raise HTTPException(status_code=404, detail="Build execution not found")
        first_run, _, _ = first_row
        application = db.get(Application, first_run.application_id)
        app_name = application.name if application else "Application"
        target_url = application.target if application else ""
        build_name = first_run.build_name or f"Build #{build_id[:8]}"
        trigger_source = first_run.trigger_source or "manual"
        build_created_at = first_run.created_at.isoformat() if first_run.created_at else None
        build_finished_at = first_run.finished_at.isoformat() if first_run.finished_at else None

    rows = runs_query.order_by(TestRun.created_at.asc()).all()

    case_items: list[BuildCaseExecutionItem] = []
    total_cases = len(rows)
    passed_count = 0
    failed_count = 0
    error_count = 0
    total_duration_ms = 0.0

    for run, case_exec, test_case in rows:
        result = run.result or {}
        duration_ms = result.get("duration_ms")
        if isinstance(duration_ms, (int, float)):
            total_duration_ms += float(duration_ms)

        status = case_exec.status if case_exec else run.status
        if status == "passed":
            passed_count += 1
        elif status == "failed":
            failed_count += 1
        elif status in ("error", "cancelled"):
            error_count += 1

        checks = result.get("checks") or []
        passed_checks = sum(1 for c in checks if isinstance(c, dict) and c.get("passed"))
        check_summary = f"{passed_checks}/{len(checks)} passed" if checks else "No checks"
        title = test_case.title if test_case else (f"Test Case #{case_exec.test_case_id}" if case_exec and case_exec.test_case_id else f"Run {run.id[:8]}")

        case_items.append(
            BuildCaseExecutionItem(
                run_id=run.id,
                test_case_id=case_exec.test_case_id if case_exec else None,
                title=title,
                status=status,
                duration_ms=duration_ms if isinstance(duration_ms, int) else (int(duration_ms) if isinstance(duration_ms, float) else None),
                check_summary=check_summary,
                failure_type=result.get("failure_type"),
                failure_summary=result.get("failure_summary"),
                error=result.get("error"),
                created_at=run.created_at.isoformat() if run.created_at else None,
                finished_at=run.finished_at.isoformat() if run.finished_at else None,
                result=run.result or None,
            )
        )

    def _tc_sort_key(item: BuildCaseExecutionItem) -> tuple[int, int, str]:
        match = re.search(r"TC\s*0*(\d+)", item.title or "", re.IGNORECASE)
        num = int(match.group(1)) if match else 999999
        return (num, item.test_case_id or 999999, item.title or "")

    case_items.sort(key=_tc_sort_key)

    pass_rate = round((passed_count / total_cases * 100), 1) if total_cases > 0 else 0.0
    overall_status = (
        "running" if any(item.status == "running" for item in case_items)
        else "queued" if any(item.status == "queued" for item in case_items)
        else "failed" if (failed_count > 0 or error_count > 0)
        else "passed"
    )

    return BuildExecutionDetail(
        build_id=build_id,
        application_id=application.id if application else 0,
        application_name=app_name,
        target_url=target_url,
        name=build_name,
        status=overall_status,  # type: ignore[arg-type]
        trigger_source=trigger_source,
        total_cases=total_cases,
        passed_count=passed_count,
        failed_count=failed_count,
        error_count=error_count,
        pass_rate=pass_rate,
        duration_ms=total_duration_ms,
        created_at=build_created_at,
        finished_at=build_finished_at,
        cases=case_items,
    )
