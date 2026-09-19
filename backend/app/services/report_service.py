"""Comprehensive QA & Automation Report Generation Service.

Provides executive summaries, test run analysis, quality risk assessment,
and export functionality in Markdown, HTML, and JSON formats.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.defect import Defect
from app.models.test_case import TestCase
from app.models.test_run import TestRun

logger = logging.getLogger("ai-qa-engine.services.report_service")


class ReportService:
    """Service for generating comprehensive QA quality reports and summaries."""

    @staticmethod
    def generate_application_quality_report(
        application_id: int,
        db: Session,
        include_ai_summary: bool = False,
    ) -> dict[str, Any]:
        """Generate a complete quality and coverage report for an application."""
        app = db.get(Application, application_id)
        if not app:
            raise ValueError(f"Application {application_id} not found")

        test_cases = (
            db.query(TestCase)
            .filter(TestCase.application_id == application_id)
            .all()
        )
        total_cases = len(test_cases)
        automated_cases = sum(
            1 for c in test_cases
            if c.automation_status == "automated" or (c.tags and "ai_generated" in c.tags)
        )
        ready_cases = sum(1 for c in test_cases if c.status == "ready")
        draft_cases = sum(1 for c in test_cases if c.status == "draft")

        # Category breakdown
        by_category: dict[str, int] = {}
        for c in test_cases:
            cat = c.category or "functional"
            by_category[cat] = by_category.get(cat, 0) + 1

        # Priority breakdown
        by_priority: dict[str, int] = {}
        for c in test_cases:
            prio = c.priority or "medium"
            by_priority[prio] = by_priority.get(prio, 0) + 1

        # Execution statistics
        runs = (
            db.query(TestRun)
            .filter(TestRun.application_id == application_id)
            .order_by(TestRun.created_at.desc())
            .limit(100)
            .all()
        )
        total_runs = len(runs)
        passed_runs = sum(1 for r in runs if r.status == "passed")
        failed_runs = sum(1 for r in runs if r.status == "failed")
        error_runs = sum(1 for r in runs if r.status == "error")
        completed_runs = passed_runs + failed_runs + error_runs
        pass_rate = round((passed_runs / completed_runs * 100), 1) if completed_runs > 0 else 0.0

        # Defects
        defects = (
            db.query(Defect)
            .filter(Defect.application_id == application_id)
            .all()
        )
        open_defects = [d for d in defects if d.status != "closed"]
        critical_defects = [d for d in open_defects if d.severity in ("critical", "high")]

        # Quality & Risk scoring
        coverage_rate = round((automated_cases / total_cases * 100), 1) if total_cases > 0 else 0.0
        risk_score = max(
            0,
            min(
                100,
                int(
                    (100 - pass_rate) * 0.4
                    + len(critical_defects) * 15
                    + len(open_defects) * 3
                    + (100 - coverage_rate) * 0.2
                ),
            ),
        )
        quality_score = max(0, min(100, 100 - risk_score))

        release_readiness = (
            "READY"
            if quality_score >= 80 and len(critical_defects) == 0
            else "NEEDS_REVIEW"
            if quality_score >= 60 and len(critical_defects) <= 1
            else "BLOCKED"
        )

        return {
            "application_id": app.id,
            "application_name": app.name,
            "target_url": getattr(app, "target", getattr(app, "url", "N/A")),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "quality_score": quality_score,
                "risk_score": risk_score,
                "release_readiness": release_readiness,
                "pass_rate_percent": pass_rate,
                "automation_coverage_percent": coverage_rate,
                "total_test_cases": total_cases,
                "automated_cases": automated_cases,
                "ready_cases": ready_cases,
                "draft_cases": draft_cases,
                "total_runs_analyzed": total_runs,
                "passed_runs": passed_runs,
                "failed_runs": failed_runs,
                "error_runs": error_runs,
                "open_defects_count": len(open_defects),
                "critical_defects_count": len(critical_defects),
            },
            "breakdown": {
                "by_category": by_category,
                "by_priority": by_priority,
            },
            "recent_runs": [
                {
                    "id": r.id,
                    "status": r.status,
                    "duration_ms": (r.result or {}).get("duration_ms") if isinstance(r.result, dict) else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in runs[:10]
            ],
            "open_defects": [
                {
                    "id": d.id,
                    "title": d.title,
                    "severity": d.severity,
                    "status": d.status,
                }
                for d in open_defects[:10]
            ],
        }

    @staticmethod
    def format_as_markdown(report_data: dict[str, Any]) -> str:
        """Render a quality report as clean Markdown."""
        metrics = report_data.get("metrics", {})
        app_name = report_data.get("application_name", "Application")
        app_url = report_data.get("target_url", "N/A")
        generated_at = report_data.get("generated_at", "")

        readiness_badge = {
            "READY": "🟢 READY FOR RELEASE",
            "NEEDS_REVIEW": "🟡 NEEDS REVIEW",
            "BLOCKED": "🔴 RELEASE BLOCKED",
        }.get(metrics.get("release_readiness", ""), "UNKNOWN")

        lines = [
            f"# QA Quality & Release Readiness Report: {app_name}",
            f"**Target URL:** {app_url}  ",
            f"**Generated:** {generated_at}  ",
            f"**Status:** {readiness_badge}",
            "",
            "## Executive Summary",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| **Quality Score** | {metrics.get('quality_score', 0)} / 100 |",
            f"| **Risk Score** | {metrics.get('risk_score', 0)} / 100 |",
            f"| **Pass Rate** | {metrics.get('pass_rate_percent', 0.0)}% |",
            f"| **Automation Coverage** | {metrics.get('automation_coverage_percent', 0.0)}% |",
            f"| **Total Test Cases** | {metrics.get('total_test_cases', 0)} |",
            f"| **Open Defects** | {metrics.get('open_defects_count', 0)} ({metrics.get('critical_defects_count', 0)} Critical/High) |",
            "",
            "## Test Suite Breakdown",
            "",
            "### By Category",
        ]

        for cat, count in report_data.get("breakdown", {}).get("by_category", {}).items():
            lines.append(f"- **{cat.capitalize()}**: {count} tests")

        lines.extend([
            "",
            "### By Priority",
        ])

        for prio, count in report_data.get("breakdown", {}).get("by_priority", {}).items():
            lines.append(f"- **{prio.capitalize()}**: {count} tests")

        lines.extend([
            "",
            "## Open Defects",
            "",
        ])

        defects = report_data.get("open_defects", [])
        if not defects:
            lines.append("No open defects found.")
        else:
            lines.append("| ID | Title | Severity | Status |")
            lines.append("|---|---|---|---|")
            for d in defects:
                lines.append(f"| #{d.get('id')} | {d.get('title')} | {d.get('severity')} | {d.get('status')} |")

        lines.append("")
        return "\n".join(lines)
