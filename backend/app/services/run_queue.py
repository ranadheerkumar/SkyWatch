import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.build_execution import BuildExecution
from app.models.case_execution import CaseExecution
from app.models.test_run import TestRun
from app.schemas.execution import ExecutionRequest
from app.services.test_execution import execute_web_target
from app.services.self_healing import persist_healing_learning


class QueueUnavailableError(RuntimeError):
    pass


@dataclass
class ActiveRunContext:
    run_id: str
    batch_id: str | None
    loop: asyncio.AbstractEventLoop
    task: asyncio.Task | None = None
    browser: Any = None
    context: Any = None
    page: Any = None
    is_cancelled: bool = False


_ACTIVE_RUNS_LOCK = Lock()
_ACTIVE_RUNS: dict[str, ActiveRunContext] = {}


def register_active_run(
    run_id: str,
    batch_id: str | None,
    loop: asyncio.AbstractEventLoop,
    task: asyncio.Task | None = None,
) -> None:
    with _ACTIVE_RUNS_LOCK:
        _ACTIVE_RUNS[run_id] = ActiveRunContext(
            run_id=run_id,
            batch_id=batch_id,
            loop=loop,
            task=task,
        )


def attach_run_browser(
    run_id: str,
    browser: Any = None,
    context: Any = None,
    page: Any = None,
) -> None:
    with _ACTIVE_RUNS_LOCK:
        ctx = _ACTIVE_RUNS.get(run_id)
        if ctx:
            if browser is not None:
                ctx.browser = browser
            if context is not None:
                ctx.context = context
            if page is not None:
                ctx.page = page


def is_run_cancelled_in_memory(run_id: str) -> bool:
    with _ACTIVE_RUNS_LOCK:
        ctx = _ACTIVE_RUNS.get(run_id)
        return bool(ctx and ctx.is_cancelled)


def unregister_active_run(run_id: str) -> None:
    with _ACTIVE_RUNS_LOCK:
        _ACTIVE_RUNS.pop(run_id, None)


def abort_active_run(run_id: str) -> None:
    with _ACTIVE_RUNS_LOCK:
        ctx = _ACTIVE_RUNS.get(run_id)
        if not ctx:
            return
        ctx.is_cancelled = True
        loop = ctx.loop
        task = ctx.task
        browser = ctx.browser
        context = ctx.context
        page = ctx.page

    if loop and loop.is_running():
        async def _force_close_resources():
            if page:
                try:
                    await page.close()
                except BaseException:
                    pass
            if context:
                try:
                    await context.close()
                except BaseException:
                    pass
            if browser:
                try:
                    await browser.close()
                except BaseException:
                    pass
            if task and not task.done():
                task.cancel()

        try:
            asyncio.run_coroutine_threadsafe(_force_close_resources(), loop)
        except Exception:
            pass


def abort_active_batch(batch_id: str) -> int:
    with _ACTIVE_RUNS_LOCK:
        target_run_ids = [
            run_id for run_id, ctx in _ACTIVE_RUNS.items()
            if ctx.batch_id == batch_id
        ]
    for r_id in target_run_ids:
        abort_active_run(r_id)
    return len(target_run_ids)


def sync_build_execution_status(db: Session, batch_id: str | None) -> None:
    if not batch_id:
        return
    try:
        build = db.get(BuildExecution, batch_id)
        if not build:
            return

        runs = db.query(TestRun).filter(TestRun.batch_id == batch_id).all()
        if not runs:
            return

        total_cases = len(runs)
        passed_count = sum(1 for r in runs if r.status == "passed")
        failed_count = sum(1 for r in runs if r.status == "failed")
        cancelled_count = sum(1 for r in runs if r.status == "cancelled")
        error_count = sum(1 for r in runs if r.status in ("error", "cancelled"))
        queued_count = sum(1 for r in runs if r.status == "queued")
        running_count = sum(1 for r in runs if r.status == "running")
        total_duration_ms = sum(
            float((r.result or {}).get("duration_ms", 0.0) or 0.0)
            for r in runs
            if isinstance((r.result or {}).get("duration_ms"), (int, float))
        )

        build.total_cases = total_cases
        build.passed_count = passed_count
        build.failed_count = failed_count
        build.error_count = error_count
        build.duration_ms = total_duration_ms

        if queued_count == 0 and running_count == 0:
            if failed_count > 0:
                build.status = "failed"
            elif cancelled_count > 0 and error_count == cancelled_count and passed_count == 0:
                build.status = "cancelled"
            elif error_count > 0:
                build.status = "error"
            else:
                build.status = "passed"
            finished_dates = [r.finished_at for r in runs if r.finished_at]
            build.finished_at = max(finished_dates) if finished_dates else datetime.now(timezone.utc)
        elif running_count > 0:
            build.status = "running"
            if not build.started_at:
                build.started_at = datetime.now(timezone.utc)
        else:
            build.status = "queued"

        db.commit()
    except Exception:
        pass


def _format_live_event(state: str, message: str) -> str:
	normalized_state = (state or "").strip().upper().replace(" ", "_")
	normalized_message = " ".join((message or "").split())
	return f"LIVE_EVENT|{normalized_state}|{normalized_message}"


def _queue_backend() -> str:
    return os.getenv("AI_QA_ENGINE_QUEUE_BACKEND", "local").strip().lower() or "local"


def _queue_name() -> str:
    return os.getenv("AI_QA_ENGINE_QUEUE_NAME", "ai-qa-engine-runs").strip() or "ai-qa-engine-runs"


def _redis_url() -> str:
    return os.getenv("AI_QA_ENGINE_REDIS_URL", "").strip() or os.getenv("REDIS_URL", "").strip()


def _append_run_log(run_id: str, message: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(TestRun, run_id)
        if not run:
            return
        existing = run.log or ""
        run.log = f"{existing}{message.rstrip()}\n"
        db.commit()
    finally:
        db.close()


async def process_run(
    run_id: str,
    request: ExecutionRequest,
) -> None:
    db: Session = SessionLocal()

    try:
        run = db.get(TestRun, run_id)

        if not run:
            return

        with _ACTIVE_RUNS_LOCK:
            if run_id in _ACTIVE_RUNS:
                _ACTIVE_RUNS[run_id].batch_id = run.batch_id

        if run.status == "cancelled" or is_run_cancelled_in_memory(run_id):
            run.status = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
            case_execution = db.query(CaseExecution).filter(CaseExecution.run_id == run_id).first()
            if case_execution:
                case_execution.status = "cancelled"
                case_execution.finished_at = datetime.now(timezone.utc)
            db.commit()
            sync_build_execution_status(db, run.batch_id)
            return

        case_execution = (
            db.query(CaseExecution)
            .filter(CaseExecution.run_id == run_id)
            .first()
        )

        run.status = "running"
        run.log = (run.log or "") + "Browser worker started\nAbout to execute tests...\n"

        if case_execution:
            case_execution.status = "running"

        db.commit()
        sync_build_execution_status(db, run.batch_id)
        _append_run_log(
            run_id,
            _format_live_event(
                "STARTING",
                "Browser worker started and is preparing execution.",
            ),
        )

        async def emit_live_event(state: str, message: str) -> None:
            _append_run_log(run_id, _format_live_event(state, message))

        result = await execute_web_target(request, run_id=run_id, event_callback=emit_live_event)

        db.refresh(run)
        healing_learning = None
        if case_execution and run.application_id and result.healed_steps:
            healing_learning = persist_healing_learning(
                db,
                run_id=run_id,
                application_id=run.application_id,
                test_case_id=case_execution.test_case_id,
                created_by=run.created_by,
                healed_steps=result.healed_steps,
            )

        if run.status == "cancelled" or result.status == "cancelled" or is_run_cancelled_in_memory(run_id):
            run.status = "cancelled"
            if case_execution:
                case_execution.status = "cancelled"
                case_execution.finished_at = datetime.now(timezone.utc)
        else:
            run.status = result.status
            if case_execution:
                case_execution.status = result.status
                case_execution.finished_at = datetime.now(timezone.utc)

        run.result = result.model_dump()

        run.log += f"Target loaded: {result.title or result.url}\n"

        if result.step_results:
            step_summary = ", ".join(
                f"#{step.index} {step.action}={'pass' if step.passed else 'fail'}"
                for step in result.step_results
            )
            run.log += f"Steps: {step_summary}\n"
        else:
            run.log += "Steps: none executed\n"

        run.log += "Checks completed\n"
        if result.checks:
            passed_checks = sum(1 for check in result.checks if check.passed)
            run.log += f"Checks summary: {passed_checks}/{len(result.checks)} passed\n"
        else:
            run.log += "Checks summary: none configured\n"

        if result.artifacts:
            artifact_entries = ", ".join(artifact.path for artifact in result.artifacts)
            run.log += f"Artifacts: {artifact_entries}\n"

        if result.console_errors:
            run.log += "Console diagnostics:\n" + "\n".join(result.console_errors) + "\n"

        if result.network_errors:
            run.log += "Network diagnostics:\n" + "\n".join(result.network_errors) + "\n"

        if result.error:
            run.log += f"Error details:\n{result.error}\n"
        else:
            run.log += "No error message received\n"

        if healing_learning and healing_learning.applied_indexes:
            run.log += (
                "Self-healing learned and applied for future executions: "
                f"step(s) {', '.join(str(index) for index in healing_learning.applied_indexes)}\n"
            )
        elif healing_learning and healing_learning.error:
            run.log += f"Self-healing learning was not persisted: {healing_learning.error}\n"

        run.finished_at = datetime.now(timezone.utc)

        if result.status in {"failed", "error"} and run.status != "cancelled":
            try:
                from app.services.defect_service import DefectService
                DefectService.record_execution_failure(
                    db,
                    run=run,
                    case_execution=case_execution,
                    result=result,
                )
            except Exception as defect_err:
                pass

        db.commit()
        sync_build_execution_status(db, run.batch_id)

    except asyncio.CancelledError:
        run = db.get(TestRun, run_id)
        if run:
            run.status = "cancelled"
            run.log = (run.log or "") + "\nLIVE_EVENT|CANCELLED|Execution cancelled by user.\n"
            run.finished_at = datetime.now(timezone.utc)
        case_execution = (
            db.query(CaseExecution)
            .filter(CaseExecution.run_id == run_id)
            .first()
        )
        if case_execution:
            case_execution.status = "cancelled"
            case_execution.finished_at = datetime.now(timezone.utc)
        db.commit()
        if run:
            sync_build_execution_status(db, run.batch_id)

    except Exception as error:
        import traceback

        error_msg = f"{type(error).__name__}: {str(error)}".strip()
        if error_msg.endswith(":") or not error_msg:
            error_msg = repr(error) or type(error).__name__

        run = db.get(TestRun, run_id)

        if run:
            db.refresh(run)
            if is_run_cancelled_in_memory(run_id) or run.status == "cancelled":
                run.status = "cancelled"
            else:
                run.status = "error"
                run.log = (
                    (run.log or "")
                    + f"Worker error: {error_msg}\n{traceback.format_exc()}\n"
                )
            run.finished_at = datetime.now(timezone.utc)

        case_execution = (
            db.query(CaseExecution)
            .filter(CaseExecution.run_id == run_id)
            .first()
        )

        if case_execution:
            if is_run_cancelled_in_memory(run_id) or (run and run.status == "cancelled"):
                case_execution.status = "cancelled"
            else:
                case_execution.status = "error"
            case_execution.finished_at = datetime.now(timezone.utc)

        db.commit()
        if run:
            sync_build_execution_status(db, run.batch_id)

    finally:
        db.close()


def process_run_sync(
    run_id: str,
    request_payload: dict,
) -> None:
    request = ExecutionRequest.model_validate(request_payload)
    asyncio.run(process_run(run_id, request))


def _start_local_worker(
    run_id: str,
    request: ExecutionRequest,
) -> None:
    def worker() -> None:
        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            task = loop.create_task(process_run(run_id, request))
            register_active_run(
                run_id=run_id,
                batch_id=None,
                loop=loop,
                task=task,
            )
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
        except Exception as error:
            db = SessionLocal()
            try:
                run = db.get(TestRun, run_id)
                if run:
                    run.status = "error"
                    run.log = (run.log or "") + f"Worker startup error: {type(error).__name__}: {error}\n"
                    run.finished_at = datetime.now(timezone.utc)
                    case_execution = db.query(CaseExecution).filter(CaseExecution.run_id == run_id).first()
                    if case_execution:
                        case_execution.status = "error"
                        case_execution.finished_at = datetime.now(timezone.utc)
                    db.commit()
            finally:
                db.close()
        finally:
            unregister_active_run(run_id)
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for t in pending:
                    t.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            loop.close()

    Thread(
        target=worker,
        name=f"ai-qa-engine-run-{run_id[:8]}",
        daemon=True,
    ).start()


def _enqueue_redis(
    run_id: str,
    request: ExecutionRequest,
    ) -> None:
    redis_url = _redis_url()
    if not redis_url:
        raise QueueUnavailableError("AI_QA_ENGINE_REDIS_URL/REDIS_URL is not configured")
    try:
        import redis
        from rq import Queue
    except ImportError as error:
        raise QueueUnavailableError("Redis queue dependencies are not installed") from error

    try:
        connection = redis.from_url(redis_url)
        connection.ping()
        queue = Queue(name=_queue_name(), connection=connection)
        queue.enqueue(
            process_run_sync,
            run_id,
            request.model_dump(mode="json"),
            job_id=run_id,
            result_ttl=3600,
            failure_ttl=24 * 3600,
        )
        _append_run_log(run_id, f"Run queued via Redis queue '{_queue_name()}'.")
        _append_run_log(run_id, _format_live_event("QUEUED", f"Run queued via Redis queue '{_queue_name()}'."))
    except Exception as error:
        raise QueueUnavailableError(f"Redis enqueue failed: {type(error).__name__}") from error


def enqueue_run(
    run_id: str,
    request: ExecutionRequest,
) -> None:
    backend = _queue_backend()
    if backend == "redis":
        _enqueue_redis(run_id, request)
        return
    if backend != "local":
        raise QueueUnavailableError(f"Unsupported queue backend '{backend}'")
    _append_run_log(run_id, "Run queued via local in-process worker.")
    _append_run_log(run_id, _format_live_event("QUEUED", "Run queued via local in-process worker."))
    _start_local_worker(run_id, request)
