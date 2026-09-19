"""Agent Task Management REST & WebSocket API endpoints.

Enables submitting high-level QA objectives, monitoring execution traces,
approving human-in-the-loop decisions, and streaming real-time agent thought/actions.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session

from app.agent.runtime import AgentRuntime
from app.agent.tools import get_default_tool_registry
from app.agent.types import AgentState, TaskStatus, TraceEntry
from app.api.dependencies import DbSession, current_user
from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.agent_task import AgentTask
from app.models.application import Application
from app.models.user import User
from app.schemas.agent_task import (
    AgentTaskApproveRequest,
    AgentTaskCreate,
    AgentTaskListItem,
    AgentTaskResponse,
    AgentTaskTraceResponse,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger("ai-qa-engine.api.agent_tasks")

router = APIRouter(prefix="/agent/tasks", tags=["agent-tasks"])


class WebSocketConnectionManager:
    """Manages active WebSocket connections per task for live trace streaming."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[task_id].append(websocket)
        logger.debug("WebSocket client connected to task %s", task_id)

    def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        if task_id in self.active_connections:
            self.active_connections[task_id] = [
                ws for ws in self.active_connections[task_id] if ws != websocket
            ]
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        logger.debug("WebSocket client disconnected from task %s", task_id)

    async def broadcast(self, task_id: str, data: dict[str, Any]) -> None:
        if task_id in self.active_connections:
            for connection in list(self.active_connections[task_id]):
                try:
                    await connection.send_json(data)
                except Exception as error:
                    logger.debug("Error sending to WS client: %s", error)


ws_manager = WebSocketConnectionManager()
# In-memory tracking of active runtime instances for approval & cancellation
active_task_runtimes: dict[str, asyncio.Task] = {}


async def _run_agent_task(
    task_id: str,
    objective: str,
    user_id: int,
    application_id: int | None,
    max_iterations: int,
    context: dict[str, Any],
) -> None:
    """Background task executing the ReAct agent loop and updating the DB."""
    logger.info("Starting background agent task %s: %s", task_id, objective[:80])

    state = AgentState(
        task_id=task_id,
        objective=objective,
        max_iterations=max_iterations,
    )

    llm_client = LLMClient()
    tool_registry = get_default_tool_registry()

    def trace_callback(entry: TraceEntry) -> None:
        """Broadcast live trace event to WebSocket clients and sync to DB."""
        payload = {
            "type": "trace_entry",
            "task_id": task_id,
            "entry": entry.model_dump(),
        }
        # Fire-and-forget WS broadcast
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(ws_manager.broadcast(task_id, payload))
        except RuntimeError:
            pass

    runtime = AgentRuntime(
        llm_client=llm_client,
        tool_registry=tool_registry,
        trace_callback=trace_callback,
    )

    # Initial DB status update: planning
    with SessionLocal() as db:
        db_task = db.get(AgentTask, task_id)
        if db_task:
            db_task.status = "planning"
            db_task.started_at = datetime.now(timezone.utc)
            db.commit()

    try:
        final_state = await runtime.execute(state, context=context)
    except asyncio.CancelledError:
        logger.info("Agent task %s was cancelled", task_id)
        final_state = state
        final_state.status = TaskStatus.CANCELLED
    except Exception as error:
        logger.exception("Agent task %s encountered an error: %s", task_id, error)
        final_state = state
        final_state.status = TaskStatus.FAILED
        final_state.error = str(error)

    # Final DB persist
    with SessionLocal() as db:
        db_task = db.get(AgentTask, task_id)
        if db_task:
            db_task.status = final_state.status.value
            db_task.plan = final_state.plan.model_dump() if final_state.plan else None
            db_task.trace = [t.model_dump() for t in final_state.trace]
            db_task.artifacts = final_state.artifacts
            db_task.error = final_state.error
            db_task.total_steps = len(final_state.plan.steps) if final_state.plan else 0
            db_task.completed_steps = (
                sum(1 for s in final_state.plan.steps if s.status.value == "completed")
                if final_state.plan
                else 0
            )
            db_task.total_llm_calls = final_state.total_llm_calls
            db_task.duration_ms = final_state.duration_ms
            db_task.completed_at = datetime.now(timezone.utc)
            db.commit()

    # Broadcast task completion
    await ws_manager.broadcast(
        task_id,
        {
            "type": "task_completed",
            "task_id": task_id,
            "status": final_state.status.value,
            "duration_ms": final_state.duration_ms,
            "error": final_state.error,
        },
    )

    active_task_runtimes.pop(task_id, None)


@router.post("", response_model=AgentTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_task(
    payload: AgentTaskCreate,
    db: DbSession,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
) -> AgentTask:
    """Submit a high-level objective to create an autonomous AgentTask."""
    app = None
    if payload.application_id:
        app = db.get(Application, payload.application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application {payload.application_id} not found",
            )

    task_id = str(uuid.uuid4())
    context = dict(payload.context)
    if payload.application_id and app:
        context.setdefault("application_id", app.id)
        context.setdefault("application_name", app.name)
        context.setdefault("target_url", getattr(app, "target", getattr(app, "url", "")))

    db_task = AgentTask(
        id=task_id,
        objective=payload.objective,
        application_id=payload.application_id,
        created_by=user.id,
        status="queued",
        total_steps=0,
        completed_steps=0,
        total_llm_calls=0,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    # Launch background async task
    task_coro = _run_agent_task(
        task_id=task_id,
        objective=payload.objective,
        user_id=user.id,
        application_id=payload.application_id,
        max_iterations=payload.max_iterations,
        context=context,
    )
    running_task = asyncio.create_task(task_coro)
    active_task_runtimes[task_id] = running_task

    return db_task


@router.get("", response_model=list[AgentTaskListItem])
def list_agent_tasks(
    db: DbSession,
    user: User = Depends(current_user),
    application_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[AgentTask]:
    """List agent tasks created by the user with optional filtering."""
    query = db.query(AgentTask).filter(AgentTask.created_by == user.id)
    if application_id is not None:
        query = query.filter(AgentTask.application_id == application_id)
    if status_filter:
        query = query.filter(AgentTask.status == status_filter)

    return query.order_by(AgentTask.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{task_id}", response_model=AgentTaskResponse)
def get_agent_task(
    task_id: str,
    db: DbSession,
    user: User = Depends(current_user),
) -> AgentTask:
    """Retrieve full details of an AgentTask."""
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent task not found")
    if task.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return task


@router.get("/{task_id}/trace", response_model=AgentTaskTraceResponse)
def get_agent_task_trace(
    task_id: str,
    db: DbSession,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retrieve the execution trace events for an AgentTask."""
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent task not found")
    if task.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    trace = task.trace or []
    return {
        "task_id": task.id,
        "status": task.status,
        "trace_count": len(trace),
        "trace": trace,
    }


@router.post("/{task_id}/approve", response_model=AgentTaskResponse)
def approve_agent_task_step(
    task_id: str,
    payload: AgentTaskApproveRequest,
    db: DbSession,
    user: User = Depends(current_user),
) -> AgentTask:
    """Approve or reject a step waiting for human confirmation."""
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent task not found")
    if task.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if task.status != "waiting_approval":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is in status '{task.status}', not waiting for approval",
        )

    # Update plan step approval
    import copy
    from sqlalchemy.orm.attributes import flag_modified

    plan = copy.deepcopy(task.plan or {})
    steps = plan.get("steps", [])
    for step in steps:
        if payload.step_id is None or step.get("id") == payload.step_id:
            step["status"] = "in_progress" if payload.approved else "failed"
            step["approval_feedback"] = payload.feedback
            break

    task.plan = plan
    flag_modified(task, "plan")
    task.status = "executing" if payload.approved else "failed"
    db.commit()
    db.refresh(task)

    return task


@router.post("/{task_id}/cancel", response_model=AgentTaskResponse)
def cancel_agent_task(
    task_id: str,
    db: DbSession,
    user: User = Depends(current_user),
) -> AgentTask:
    """Cancel a running AgentTask."""
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent task not found")
    if task.created_by != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if task.status in ("completed", "failed", "cancelled"):
        return task

    running = active_task_runtimes.get(task_id)
    if running and not running.done():
        running.cancel()

    task.status = "cancelled"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)

    return task


@router.websocket("/{task_id}/ws")
async def agent_task_websocket(
    websocket: WebSocket,
    task_id: str,
    token: str | None = Query(default=None),
) -> None:
    """Real-time WebSocket endpoint streaming agent thoughts, tool calls, and observations."""
    if token:
        try:
            decode_access_token(token)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await ws_manager.connect(task_id, websocket)

    # Send current state snapshot immediately on connect
    with SessionLocal() as db:
        task = db.get(AgentTask, task_id)
        if task:
            await websocket.send_json({
                "type": "initial_state",
                "task_id": task.id,
                "status": task.status,
                "objective": task.objective,
                "plan": task.plan,
                "trace": task.trace or [],
                "artifacts": task.artifacts or {},
            })

    try:
        while True:
            # Keep-alive ping/pong and listen for incoming client commands
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(task_id, websocket)
    except Exception as error:
        logger.debug("WebSocket error for task %s: %s", task_id, error)
        ws_manager.disconnect(task_id, websocket)
