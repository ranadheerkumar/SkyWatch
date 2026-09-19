from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import DbSession, current_user
from app.models.application import Application
from app.models.defect import Defect
from app.models.test_case import TestCase
from app.models.test_run import TestRun
from app.models.user import User


router = APIRouter(prefix="/reports", tags=["reports"])


def _empty_trend(days: int) -> list[dict]:
    today = datetime.now(tz=timezone.utc).date()
    points: list[dict] = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        points.append({"date": day.isoformat(), "total": 0, "passed": 0, "failed": 0, "error": 0})
    return points


@router.get("/application/{application_id}/overview")
def get_application_overview(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> dict:
    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    test_case_count = (
        db.query(TestCase)
        .filter(TestCase.application_id == application_id, TestCase.created_by == user.id)
        .count()
    )
    defect_open_count = (
        db.query(Defect)
        .filter(Defect.application_id == application_id, Defect.created_by == user.id, Defect.status != "closed")
        .count()
    )
    runs = (
        db.query(TestRun)
        .filter(TestRun.application_id == application_id, TestRun.created_by == user.id)
        .order_by(TestRun.created_at.desc())
        .limit(500)
        .all()
    )
    pass_count = sum(1 for run in runs if run.status == "passed")
    fail_count = sum(1 for run in runs if run.status == "failed")
    error_count = sum(1 for run in runs if run.status == "error")
    completed = pass_count + fail_count + error_count
    pass_rate = round((pass_count / completed) * 100, 2) if completed else 0.0

    trend = _empty_trend(14)
    index_by_date = {item["date"]: item for item in trend}
    for run in runs:
        if not run.created_at:
            continue
        key = run.created_at.date().isoformat()
        point = index_by_date.get(key)
        if not point:
            continue
        point["total"] += 1
        if run.status == "passed":
            point["passed"] += 1
        elif run.status == "failed":
            point["failed"] += 1
        elif run.status == "error":
            point["error"] += 1

    return {
        "application_id": application.id,
        "application_name": application.name,
        "test_case_count": test_case_count,
        "run_count": len(runs),
        "completed_run_count": completed,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "error_count": error_count,
        "pass_rate": pass_rate,
        "open_defect_count": defect_open_count,
        "daily_trend_14d": trend,
    }


@router.get("/executive/overview")
def get_executive_overview(
    db: DbSession,
    user: User = Depends(current_user),
) -> dict:
    applications = db.query(Application).filter(Application.created_by == user.id).all()
    runs = db.query(TestRun).filter(TestRun.created_by == user.id).all()
    defects = db.query(Defect).filter(Defect.created_by == user.id).all()
    cases = db.query(TestCase).filter(TestCase.created_by == user.id).all()

    total_cases = len(cases)
    ready_cases = sum(1 for c in cases if c.status == "ready")
    ai_generated_cases = sum(1 for c in cases if c.automation_status == "automated" or (c.tags and "ai_generated" in c.tags))
    manual_cases = total_cases - ai_generated_cases

    pass_runs = sum(1 for r in runs if r.status == "passed")
    fail_runs = sum(1 for r in runs if r.status in {"failed", "error"})
    completed_runs = pass_runs + fail_runs
    pass_rate = round((pass_runs / completed_runs * 100), 1) if completed_runs > 0 else 0.0

    coverage_percentage = round((ready_cases / total_cases * 100), 1) if total_cases > 0 else 0.0
    open_defects_count = sum(1 for d in defects if d.status != "closed")
    defect_leakage_rate = round((open_defects_count / max(1, total_cases) * 100), 1)

    # Calculate Quality Score & Risk Score & Release Readiness
    quality_score = max(0, min(100, int(pass_rate * 0.6 + coverage_percentage * 0.4 - (open_defects_count * 2))))
    risk_score = max(0, min(100, int((100 - pass_rate) * 0.5 + (open_defects_count * 5) + (100 - coverage_percentage) * 0.2)))
    release_readiness_score = max(0, min(100, int(pass_rate * 0.5 + coverage_percentage * 0.3 + (100 - risk_score) * 0.2)))

    daily_trend = _empty_trend(14)
    index_by_date = {item["date"]: item for item in daily_trend}
    for run in runs:
        if not run.created_at:
            continue
        key = run.created_at.date().isoformat()
        point = index_by_date.get(key)
        if point:
            point["total"] += 1
            if run.status == "passed":
                point["passed"] += 1
            elif run.status == "failed":
                point["failed"] += 1
            elif run.status == "error":
                point["error"] += 1

    app_health_list = []
    for app in applications:
        app_cases = [c for c in cases if c.application_id == app.id]
        app_runs = [r for r in runs if r.application_id == app.id]
        app_pass = sum(1 for r in app_runs if r.status == "passed")
        app_comp = sum(1 for r in app_runs if r.status in {"passed", "failed", "error"})
        app_rate = round((app_pass / app_comp * 100), 1) if app_comp > 0 else 0.0
        app_defects = sum(1 for d in defects if d.application_id == app.id and d.status != "closed")
        app_health_label = "Optimal" if app_rate >= 80 and app_defects == 0 else ("Watch" if app_rate >= 50 else "Critical")

        app_health_list.append({
            "application_id": app.id,
            "application_name": app.name,
            "platform": app.platform,
            "total_cases": len(app_cases),
            "ready_cases": sum(1 for c in app_cases if c.status == "ready"),
            "pass_rate": app_rate,
            "health_label": app_health_label,
            "open_defects": app_defects,
        })

    return {
        "total_applications": len(applications),
        "total_test_cases": total_cases,
        "ai_generated_test_cases": ai_generated_cases,
        "manual_test_cases": max(0, manual_cases),
        "total_executions": len(runs),
        "pass_rate": pass_rate,
        "release_readiness_score": release_readiness_score,
        "risk_score": risk_score,
        "quality_score": quality_score,
        "coverage_percentage": coverage_percentage,
        "defect_leakage_rate": defect_leakage_rate,
        "open_defects": open_defects_count,
        "daily_trends_14d": daily_trend,
        "applications_health": app_health_list,
    }


@router.get("/engineering/analytics")
def get_engineering_analytics(
    db: DbSession,
    application_id: int | None = None,
    user: User = Depends(current_user),
) -> dict:
    runs_query = db.query(TestRun).filter(TestRun.created_by == user.id)
    if application_id:
        runs_query = runs_query.filter(TestRun.application_id == application_id)
    runs = runs_query.order_by(TestRun.created_at.desc()).limit(200).all()

    failure_categories: dict[str, int] = defaultdict(int)
    recent_failures: list[dict] = []

    for run in runs:
        if run.status in {"failed", "error"}:
            res = run.result or {}
            ftype = res.get("failure_type") or "UNKNOWN"
            failure_categories[ftype] += 1
            if len(recent_failures) < 15:
                recent_failures.append({
                    "run_id": run.id,
                    "application_id": run.application_id,
                    "failure_type": ftype,
                    "failure_summary": res.get("failure_summary") or res.get("error") or "Execution failed",
                    "url": res.get("url"),
                    "duration_ms": res.get("duration_ms"),
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "console_errors": res.get("console_errors") or [],
                    "network_errors": res.get("network_errors") or [],
                })

    return {
        "total_analyzed_runs": len(runs),
        "failure_categories": dict(failure_categories),
        "recent_failures": recent_failures,
    }