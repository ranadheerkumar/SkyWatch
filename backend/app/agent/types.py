"""Core types for the Agent Runtime.

Defines the data structures used throughout the agentic execution pipeline:
AgentState, ToolCall, Observation, AgentPlan, AgentTask, and enums for
status tracking and tool categories.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """Lifecycle status of an agent task."""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Status of an individual plan step."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


class ToolCategory(str, Enum):
    """Logical grouping of tools for schema presentation to the LLM."""
    BROWSER = "browser"
    FILE = "file"
    TEST_GENERATION = "test_generation"
    TEST_EXECUTION = "test_execution"
    INTEGRATION = "integration"
    REPORTING = "reporting"
    UTILITY = "utility"
    CUSTOM = "custom"


@dataclass
class ToolCallRequest:
    """A request from the LLM to invoke a specific tool."""
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    reasoning: str = ""


@dataclass
class ToolCallResult:
    """The result of executing a tool call."""
    call_id: str
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def summary(self, max_length: int = 500) -> str:
        """Compact text summary for inclusion in LLM context."""
        if self.error:
            return f"[FAILED] {self.tool_name}: {self.error[:max_length]}"
        text = str(self.output) if self.output is not None else "(no output)"
        if len(text) > max_length:
            text = text[:max_length] + "…"
        return f"[OK] {self.tool_name}: {text}"


@dataclass
class Observation:
    """An observation produced during agent execution — either from a tool result or environment."""
    content: str
    source: str  # tool name, "environment", "user", "system"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanStep:
    """A single step in the agent's execution plan."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    goal: str = ""
    description: str = ""
    suggested_tools: list[str] = field(default_factory=list)
    success_criteria: str = ""
    status: StepStatus = StepStatus.QUEUED
    result_summary: str = ""
    attempts: int = 0
    max_attempts: int = 3
    requires_approval: bool = False


@dataclass
class AgentPlan:
    """A decomposed execution plan produced by the LLM planner."""
    objective: str
    steps: list[PlanStep] = field(default_factory=list)
    rationale: str = ""
    estimated_tool_calls: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    revised_at: str | None = None
    revision_count: int = 0

    def current_step(self) -> PlanStep | None:
        """Returns the next step that is not yet completed."""
        for step in self.steps:
            if step.status in {StepStatus.QUEUED, StepStatus.RUNNING, StepStatus.WAITING_APPROVAL}:
                return step
        return None

    def is_complete(self) -> bool:
        return all(
            step.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
            for step in self.steps
        )

    def progress_percentage(self) -> int:
        if not self.steps:
            return 0
        done = sum(
            1 for step in self.steps
            if step.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
        )
        return int(100 * done / len(self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "steps": [
                {
                    "id": s.id,
                    "goal": s.goal,
                    "description": s.description,
                    "suggested_tools": s.suggested_tools,
                    "success_criteria": s.success_criteria,
                    "status": s.status.value,
                    "result_summary": s.result_summary,
                    "attempts": s.attempts,
                    "requires_approval": s.requires_approval,
                }
                for s in self.steps
            ],
            "rationale": self.rationale,
            "estimated_tool_calls": self.estimated_tool_calls,
            "created_at": self.created_at,
            "revised_at": self.revised_at,
            "revision_count": self.revision_count,
        }


@dataclass
class TraceEntry:
    """A single entry in the agent's execution trace for full observability."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str = ""  # "plan_created", "tool_call", "tool_result", "observation", "decision", "error", "approval_request"
    step_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
        }
        if self.step_id:
            result["step_id"] = self.step_id
        result["data"] = self.data
        return result


@dataclass
class AgentState:
    """Complete runtime state of an executing agent."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    objective: str = ""
    status: TaskStatus = TaskStatus.PENDING
    plan: AgentPlan | None = None
    trace: list[TraceEntry] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    total_tool_calls: int = 0
    total_llm_calls: int = 0
    total_tokens_used: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    created_by: int = 0
    application_id: int | None = None

    # Runtime limits
    max_iterations: int = 50
    max_tool_calls: int = 100
    timeout_seconds: int = 600

    def add_trace(self, event_type: str, step_id: str | None = None, **data: Any) -> TraceEntry:
        entry = TraceEntry(event_type=event_type, step_id=step_id, data=data)
        self.trace.append(entry)
        return entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "status": self.status.value,
            "plan": self.plan.to_dict() if self.plan else None,
            "trace": [t.to_dict() for t in self.trace[-100:]],  # last 100 for API response
            "artifacts": self.artifacts,
            "error": self.error,
            "total_tool_calls": self.total_tool_calls,
            "total_llm_calls": self.total_llm_calls,
            "total_tokens_used": self.total_tokens_used,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress": self.plan.progress_percentage() if self.plan else 0,
        }


class FailureCategory(str, Enum):
    """Categorization of test execution step failure."""
    SELECTOR_DRIFT = "selector_drift"
    REGRESSION_BUG = "regression_bug"
    ENVIRONMENT_FLAKE = "environment_flake"
    AUTH_FAILURE = "auth_failure"
    TIMING_ISSUE = "timing_issue"
    ASSERTION_FAILURE = "assertion_failure"
    UNKNOWN = "unknown"


@dataclass
class FailureDiagnosis:
    """Diagnostic assessment produced by AutonomousAnalysisAgent."""
    category: FailureCategory
    confidence: float
    root_cause: str
    suggested_fix: str
    evidence: dict[str, Any] = field(default_factory=dict)
    candidate_selectors: list[str] = field(default_factory=list)


@dataclass
class InteractiveElementBlueprint:
    """Blueprint of an interactive UI element discovered on a page."""
    element_id: str
    tag: str
    role: str | None = None
    accessible_name: str | None = None
    text_content: str | None = None
    primary_selector: str = ""
    resilient_selectors: list[str] = field(default_factory=list)
    action_type: str = "click"  # click | type | select | check
    is_form_submit: bool = False
    parent_form: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class PageBlueprint:
    """Discovered page model with structure, interactions, and route transitions."""
    url: str
    title: str
    elements: list[InteractiveElementBlueprint] = field(default_factory=list)
    outbound_links: list[str] = field(default_factory=list)
    forms: list[dict[str, Any]] = field(default_factory=list)
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AutonomousCampaignStatus(str, Enum):
    """Status lifecycle of an autonomous testing campaign."""
    IDLE = "idle"
    DISCOVERING = "discovering"
    PLANNING = "planning"
    EXECUTING = "executing"
    ANALYZING = "analyzing"
    HEALING = "healing"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class HealingRecord:
    """Audit record of a self-healed test step."""
    test_id: str
    step_index: int
    original_selector: str
    healed_selector: str
    strategy: str  # learned_cache | fuzzy_text | aria_role | structural | proximity
    confidence: float
    validated_live: bool
    duration_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

