"""SkyWatch Universal Quality Model & Ingestion/Egress Adapters.

Codifies the platform-neutral canonical testing model defined in Section 8 of the Master Architecture.
Shields core quality engineering logic from external vendor representations (Jira, qTest, Git, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class RequirementPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RequirementType(str, Enum):
    USER_STORY = "USER_STORY"
    FUNCTIONAL_SPEC = "FUNCTIONAL_SPEC"
    API_CONTRACT = "API_CONTRACT"
    NON_FUNCTIONAL = "NON_FUNCTIONAL"
    COMPLIANCE = "COMPLIANCE"


class ExecutionStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    BROKEN = "BROKEN"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    IN_PROGRESS = "IN_PROGRESS"


class DefectSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MODERATE = "MODERATE"
    MINOR = "MINOR"


class DefectStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class SyncConflictPolicy(str, Enum):
    """Conflict resolution policy for bidirectional synchronization."""
    SKYWATCH_AUTHORITATIVE = "skywatch_authoritative"
    EXTERNAL_AUTHORITATIVE = "external_authoritative"
    LATEST_TIMESTAMP = "latest_timestamp"
    MANUAL = "manual"


class SyncJobStatus(str, Enum):
    """Operational status of a synchronization or batch transfer job."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ==============================================================================
# Canonical Enterprise Quality Domain Models
# ==============================================================================

class CanonicalOrganization(BaseModel):
    """Top-level enterprise tenant boundary."""
    id: str
    name: str
    code: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanonicalTeam(BaseModel):
    """Team within an organization owning projects and tests."""
    id: str
    organization_id: str
    name: str
    lead_email: str | None = None
    members: list[str] = Field(default_factory=list)


class CanonicalProject(BaseModel):
    """Project grouping applications, requirements, and test suites."""
    id: str
    organization_id: str
    team_id: str | None = None
    name: str
    description: str | None = None
    key: str = "PROJ"


class CanonicalEnvironment(BaseModel):
    """Deployment or execution target environment."""
    id: str
    name: str  # e.g., dev, staging, uat, prod
    base_url: str
    variables: dict[str, str] = Field(default_factory=dict)
    is_ephemeral: bool = False


class CanonicalApplication(BaseModel):
    """System under test across Web, Mobile, API, Desktop, or Hybrid."""
    id: str
    project_id: str
    name: str
    app_type: str = "web"  # web, mobile_ios, mobile_android, api, desktop, database, hybrid
    target_url: str | None = None
    environments: list[CanonicalEnvironment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalRequirement(BaseModel):
    """Platform-neutral specification or user story."""
    id: str
    project_id: str
    external_source: str | None = None  # jira, confluence, manual, prd
    external_id: str | None = None
    title: str
    description: str
    req_type: RequirementType = RequirementType.USER_STORY
    priority: RequirementPriority = RequirementPriority.MEDIUM
    acceptance_criteria: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanonicalTestStep(BaseModel):
    """Individual atomic step or check in a test case."""
    step_number: int
    action: str
    target: str | None = None
    value: str | None = None
    expected_result: str
    is_assertion: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalTestData(BaseModel):
    """Type-safe parameter data attached to test executions."""
    id: str
    name: str
    category: str = "valid"  # valid, invalid, boundary, edge
    parameters: dict[str, Any] = Field(default_factory=dict)


class CanonicalTestCase(BaseModel):
    """Platform-neutral test case specification."""
    id: str
    application_id: str
    requirement_ids: list[str] = Field(default_factory=list)
    title: str
    description: str | None = None
    category: str = "functional"  # positive, negative, boundary, security, accessibility
    priority: RequirementPriority = RequirementPriority.MEDIUM
    preconditions: list[str] = Field(default_factory=list)
    steps: list[CanonicalTestStep] = Field(default_factory=list)
    test_data: list[CanonicalTestData] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: str = "ready"  # draft, ready, deprecated
    version: int = 1


class CanonicalTestSuite(BaseModel):
    """Group of canonical test cases organized for execution."""
    id: str
    application_id: str
    name: str
    description: str | None = None
    case_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CanonicalTestPlan(BaseModel):
    """High-level quality test plan for a release or cycle."""
    id: str
    project_id: str
    name: str
    objective: str
    suite_ids: list[str] = Field(default_factory=list)
    environment_id: str | None = None
    target_date: datetime | None = None


class CanonicalTestSet(BaseModel):
    """Platform-neutral test set grouping canonical test cases for execution."""
    id: str
    project_id: str
    name: str
    description: str | None = None
    case_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanonicalAttachment(BaseModel):
    """Evidence artifact attached to a test execution or defect."""
    id: str
    file_name: str
    content_type: str
    storage_path: str
    size_bytes: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanonicalEvidence(BaseModel):
    """Comprehensive diagnostic evidence bundle collected during test execution."""
    execution_id: str
    screenshots: list[CanonicalAttachment] = Field(default_factory=list)
    videos: list[CanonicalAttachment] = Field(default_factory=list)
    traces: list[CanonicalAttachment] = Field(default_factory=list)
    console_logs: list[str] = Field(default_factory=list)
    network_errors: list[dict[str, Any]] = Field(default_factory=list)
    dom_snapshot: str | None = None


class CanonicalExecutionResult(BaseModel):
    """Outcome of a single test step or assertion."""
    step_number: int
    status: ExecutionStatus
    duration_ms: float
    error_message: str | None = None
    screenshot_url: str | None = None


class CanonicalTestExecution(BaseModel):
    """Execution of a specific test case in a test run."""
    id: str
    run_id: str
    case_id: str
    status: ExecutionStatus = ExecutionStatus.IN_PROGRESS
    duration_ms: float = 0.0
    results: list[CanonicalExecutionResult] = Field(default_factory=list)
    evidence: CanonicalEvidence | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class CanonicalTestRun(BaseModel):
    """Batch execution of multiple test cases across worker pools."""
    id: str
    application_id: str
    environment: str
    trigger: str = "manual"  # manual, agent, ci_cd, webhook
    executions: list[CanonicalTestExecution] = Field(default_factory=list)
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    status: str = "in_progress"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanonicalDefect(BaseModel):
    """Platform-neutral defect representation linked to test executions."""
    id: str
    project_id: str
    external_id: str | None = None  # e.g., JIRA-1234
    title: str
    description: str
    severity: DefectSeverity = DefectSeverity.MAJOR
    status: DefectStatus = DefectStatus.OPEN
    failed_execution_id: str | None = None
    attachments: list[CanonicalAttachment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CanonicalReport(BaseModel):
    """Platform-neutral executive quality report."""
    id: str
    project_id: str
    title: str
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    quality_score: float = 100.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExternalObjectMapping(BaseModel):
    """Canonical mapping link tracking SkyWatch domain objects against external ALM systems."""
    id: str
    provider: str  # jira, xray, qtest, github
    integration_id: int
    project_id: str
    skywatch_object_type: str  # test_case, test_plan, test_set, execution, defect, requirement
    skywatch_object_id: str
    external_object_id: str
    external_key: str
    last_synced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sync_version: int = 1
    mapping_status: str = "synced"  # synced, modified, conflict, failed
    metadata: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# Canonical Enterprise Reporting Models (Jira + Xray + qTest + Execution Providers)
# ==============================================================================

class AutomationClassification(str, Enum):
    MANUAL = "MANUAL"
    AUTOMATED = "AUTOMATED"
    PARTIALLY_AUTOMATED = "PARTIALLY_AUTOMATED"
    CANDIDATE = "CANDIDATE"


class TraceabilityGapType(str, Enum):
    NONE = "NONE"
    REQUIREMENT_WITHOUT_TEST = "REQUIREMENT_WITHOUT_TEST"
    TEST_WITHOUT_REQUIREMENT = "TEST_WITHOUT_REQUIREMENT"
    UNTESTED_TEST = "UNTESTED_TEST"
    FAILING_WITHOUT_DEFECT = "FAILING_WITHOUT_DEFECT"
    DEFECT_WITHOUT_TEST = "DEFECT_WITHOUT_TEST"


class XrayPlanMetrics(BaseModel):
    """Canonical test plan progress metrics for Xray and ALM platforms."""
    plan_key: str
    plan_name: str
    total_tests: int = 0
    executed_tests: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0
    not_executed: int = 0
    pass_rate: float = 0.0
    remaining_tests: int = 0
    environment: str | None = None


class XraySetSummary(BaseModel):
    """Canonical test set summary grouping."""
    set_key: str
    name: str
    test_count: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0


class AutomationCoverageMetrics(BaseModel):
    """Deep automation posture distinguishing manual, automated, partial, and candidates."""
    total_tests: int = 0
    manual_tests: int = 0
    automated_tests: int = 0
    partially_automated_tests: int = 0
    automation_candidates: int = 0
    automation_coverage_rate: float = 0.0
    automation_execution_rate: float = 0.0
    automation_pass_rate: float = 0.0
    manual_pass_rate: float = 0.0


class TraceabilityLink(BaseModel):
    """End-to-end traceability correlation across Requirements, Tests, Executions, and Defects."""
    requirement_id: str | None = None
    requirement_key: str | None = None
    requirement_title: str | None = None
    requirement_source: str | None = None  # jira, xray, qtest, skywatch
    test_id: str
    test_title: str
    test_source: str = "skywatch"  # skywatch, xray, qtest
    test_automation_status: str = "manual"
    last_execution_id: str | None = None
    execution_provider: str | None = None  # local, azure, gcp, aws, sauce_labs, lambdatest
    execution_status: str | None = None  # PASSED, FAILED, etc.
    execution_duration_ms: float | None = None
    defect_id: str | None = None
    defect_key: str | None = None
    defect_title: str | None = None
    defect_status: str | None = None
    defect_severity: str | None = None
    defect_url: str | None = None
    release_version: str | None = None
    gap_type: TraceabilityGapType = TraceabilityGapType.NONE


class IntegrationHealthStatus(BaseModel):
    """Live health posture of an ALM or external execution provider integration."""
    system: str  # jira, xray, qtest, git, saucelabs, etc.
    name: str
    status: str = "connected"  # connected, degraded, disconnected, unconfigured
    latency_ms: float | None = None
    last_sync_at: str | None = None
    last_error: str | None = None
    failed_sync_count: int = 0
    pending_jobs: int = 0


class UnifiedExecutionItem(BaseModel):
    """Unified test execution across any execution provider and test management tool."""
    run_id: str
    test_case_id: int | None = None
    test_title: str
    source_system: str = "skywatch"  # skywatch, xray, qtest
    execution_provider: str = "local"  # local, azure, gcp, aws, sauce_labs, lambdatest
    environment: str = "production"
    browser: str | None = None
    device: str | None = None
    status: str = "passed"
    duration_ms: float = 0.0
    started_at: str | None = None
    finished_at: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    external_references: list[dict[str, Any]] = Field(default_factory=list)


class DataFreshnessInfo(BaseModel):
    """Synchronization freshness metadata for external ALM data."""
    system: str
    last_synced_at: str | None = None
    is_live: bool = False
    sync_status: str = "synced"  # synced, syncing, stale, error


class UnifiedQualityReport(BaseModel):
    """Consolidated enterprise quality report unifying SkyWatch with Jira, Xray, and qTest."""
    id: str
    project_id: str
    generated_at: str
    summary: dict[str, Any]
    source_breakdown: dict[str, Any]  # skywatch, xray, jira, qtest counts
    provider_breakdown: dict[str, Any]  # local, azure, gcp, aws, sauce_labs, lambdatest counts
    xray_plans: list[XrayPlanMetrics] = Field(default_factory=list)
    xray_sets: list[XraySetSummary] = Field(default_factory=list)
    automation_metrics: AutomationCoverageMetrics = Field(default_factory=AutomationCoverageMetrics)
    defect_metrics: dict[str, Any] = Field(default_factory=dict)
    data_freshness: dict[str, DataFreshnessInfo] = Field(default_factory=dict)
    ai_insights: dict[str, list[str]] = Field(default_factory=dict)


# ==============================================================================
# Ingestion & Egress Adapters (Mapping External Schemas to Canonical Models)
# ==============================================================================

class UniversalModelAdapter:
    """Provides bidirectional translation between vendor APIs and the Canonical Model."""

    @staticmethod
    def jira_issue_to_canonical_requirement(jira_data: dict[str, Any], project_id: str) -> CanonicalRequirement:
        """Translate a Jira Cloud REST API issue into a CanonicalRequirement."""
        fields = jira_data.get("fields", {})
        summary = fields.get("summary", "Untitled Jira Requirement")
        desc_obj = fields.get("description")
        description_text = str(desc_obj) if desc_obj else ""
        issue_key = jira_data.get("key", "JIRA-UNKNOWN")
        priority_name = (fields.get("priority") or {}).get("name", "Medium").upper()
        priority_map = {
            "HIGHEST": RequirementPriority.CRITICAL,
            "HIGH": RequirementPriority.HIGH,
            "MEDIUM": RequirementPriority.MEDIUM,
            "LOW": RequirementPriority.LOW,
            "LOWEST": RequirementPriority.LOW,
        }
        return CanonicalRequirement(
            id=f"req-jira-{issue_key}",
            project_id=project_id,
            external_source="jira",
            external_id=issue_key,
            title=summary,
            description=description_text,
            priority=priority_map.get(priority_name, RequirementPriority.MEDIUM),
            tags=fields.get("labels", []),
        )

    @staticmethod
    def canonical_defect_to_jira_payload(defect: CanonicalDefect, project_key: str, issue_type: str = "Bug") -> dict[str, Any]:
        """Translate a CanonicalDefect into Jira REST API payload."""
        severity_map = {
            DefectSeverity.CRITICAL: "Highest",
            DefectSeverity.MAJOR: "High",
            DefectSeverity.MODERATE: "Medium",
            DefectSeverity.MINOR: "Low",
        }
        return {
            "fields": {
                "project": {"key": project_key},
                "summary": defect.title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": defect.description}],
                        }
                    ],
                },
                "issuetype": {"name": issue_type},
                "priority": {"name": severity_map.get(defect.severity, "Medium")},
            }
        }

    @staticmethod
    def qtest_test_case_to_canonical(qtest_data: dict[str, Any], app_id: str) -> CanonicalTestCase:
        """Translate a Tricentis qTest test case into a CanonicalTestCase."""
        qtest_id = str(qtest_data.get("id", "0"))
        name = qtest_data.get("name", f"qTest Case {qtest_id}")
        description = qtest_data.get("description", "")
        raw_steps = qtest_data.get("test_steps", [])
        canonical_steps = []
        for idx, step in enumerate(raw_steps, start=1):
            canonical_steps.append(
                CanonicalTestStep(
                    step_number=idx,
                    action=step.get("description", "Execute action"),
                    expected_result=step.get("expected_result", "Expected outcome verified"),
                )
            )
        return CanonicalTestCase(
            id=f"case-qtest-{qtest_id}",
            application_id=app_id,
            title=name,
            description=description,
            steps=canonical_steps,
        )

    @staticmethod
    def git_commit_to_traceability(git_data: dict[str, Any]) -> dict[str, Any]:
        """Extract traceability context from a Git commit record."""
        return {
            "sha": git_data.get("sha", ""),
            "author": git_data.get("author", {}).get("name", "Unknown"),
            "message": git_data.get("message", ""),
            "branch": git_data.get("branch", "develop"),
            "timestamp": git_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }

    @staticmethod
    def xray_test_to_canonical_test_case(xray_data: dict[str, Any], app_id: str) -> CanonicalTestCase:
        """Translate an Xray Test entity (Cloud or Server) into a CanonicalTestCase."""
        test_key = xray_data.get("key") or xray_data.get("testKey", "XRAY-TEST-0")
        summary = xray_data.get("summary") or (xray_data.get("fields", {}).get("summary", f"Xray Test {test_key}"))
        description = xray_data.get("description") or (xray_data.get("fields", {}).get("description", ""))
        if isinstance(description, dict):
            description = description.get("text", "") or str(description)

        raw_steps = xray_data.get("steps") or xray_data.get("testSteps") or []
        canonical_steps = []
        for idx, step in enumerate(raw_steps, start=1):
            action_text = step.get("action") or step.get("step") or step.get("description", "Execute test action")
            expected_text = step.get("result") or step.get("expectedResult") or "Expected outcome verified"
            canonical_steps.append(
                CanonicalTestStep(
                    step_number=idx,
                    action=str(action_text),
                    expected_result=str(expected_text),
                )
            )

        status_raw = xray_data.get("status") or xray_data.get("fields", {}).get("status", {}).get("name", "ready")
        return CanonicalTestCase(
            id=f"case-xray-{test_key}",
            application_id=app_id,
            title=summary,
            description=description,
            steps=canonical_steps,
            status="ready" if str(status_raw).lower() in ("pass", "passed", "ready", "approved") else "draft",
        )

    @staticmethod
    def canonical_test_case_to_xray_payload(case: CanonicalTestCase, project_key: str) -> dict[str, Any]:
        """Translate a CanonicalTestCase into an Xray Test issue creation payload."""
        steps_payload = []
        for step in case.steps:
            steps_payload.append({
                "action": step.action,
                "data": step.value or "",
                "result": step.expected_result,
            })
        return {
            "fields": {
                "project": {"key": project_key},
                "summary": case.title,
                "description": case.description or "",
                "issuetype": {"name": "Test"},
            },
            "xrayFields": {
                "testType": {"name": "Manual"},
                "steps": steps_payload,
            },
        }

    @staticmethod
    def canonical_execution_to_xray_result(execution: CanonicalTestExecution, test_key: str) -> dict[str, Any]:
        """Translate a CanonicalTestExecution into Xray standard execution JSON result."""
        status_map = {
            ExecutionStatus.PASSED: "PASSED",
            ExecutionStatus.FAILED: "FAILED",
            ExecutionStatus.BROKEN: "FAILED",
            ExecutionStatus.SKIPPED: "SKIPPED",
            ExecutionStatus.BLOCKED: "BLOCKED",
            ExecutionStatus.IN_PROGRESS: "EXECUTING",
        }
        step_results = []
        for r in execution.results:
            step_results.append({
                "status": status_map.get(r.status, "FAILED"),
                "comment": r.error_message or "Verified successfully",
                "actualResult": "Passed" if r.status == ExecutionStatus.PASSED else (r.error_message or "Failed"),
            })
        return {
            "testKey": test_key,
            "status": status_map.get(execution.status, "FAILED"),
            "start": execution.started_at.isoformat(),
            "finish": (execution.finished_at or datetime.now(timezone.utc)).isoformat(),
            "steps": step_results,
        }

    @staticmethod
    def xray_test_plan_to_canonical(xray_plan: dict[str, Any], project_id: str) -> CanonicalTestPlan:
        """Translate an Xray Test Plan issue into a CanonicalTestPlan."""
        plan_key = xray_plan.get("key", "PLAN-0")
        summary = xray_plan.get("summary") or xray_plan.get("fields", {}).get("summary", f"Test Plan {plan_key}")
        description = xray_plan.get("description") or xray_plan.get("fields", {}).get("description", "")
        return CanonicalTestPlan(
            id=f"plan-xray-{plan_key}",
            project_id=project_id,
            name=summary,
            objective=str(description),
        )

