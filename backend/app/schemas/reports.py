from typing import Any
from pydantic import BaseModel, Field


class ExecutionTrendPoint(BaseModel):
    date: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0


class DefectSeverityCount(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0


class DefectStatusCount(BaseModel):
    open: int = 0
    in_progress: int = 0
    resolved: int = 0
    closed: int = 0


class TopFailingCase(BaseModel):
    test_case_id: int
    title: str
    failure_count: int
    last_failure_reason: str | None = None


class AppExecutionHealth(BaseModel):
    application_id: int
    application_name: str
    platform: str
    total_cases: int
    ready_cases: int
    pass_rate: float
    health_label: str
    open_defects: int


class ApplicationSummary(BaseModel):
    id: int
    name: str
    platform: str
    target: str | None = None
    test_case_count: int = 0
    ready_case_count: int = 0


class ReportDashboardMetrics(BaseModel):
    total_applications: int
    total_test_cases: int
    ai_generated_test_cases: int
    manual_test_cases: int
    total_executions: int
    pass_rate: float
    release_readiness_score: int
    risk_score: int
    quality_score: int
    coverage_percentage: float
    defect_leakage_rate: float
    open_defects: int
    daily_trends_14d: list[ExecutionTrendPoint]
    applications_health: list[AppExecutionHealth]
