"""Defect Management Service for AI QA Engine.

Handles automated defect capture from failed test runs, failure categorization,
audit logging, and defect lifecycle metrics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.defect import Defect
from app.models.test_case import TestCase
from app.models.test_run import TestRun
from app.schemas.execution import ExecutionResponse
from app.services.audit import log_audit_event

logger = logging.getLogger("ai-qa-engine.defect_service")

_FAILURE_GUIDANCE = {
    "LOCATOR": "The requested element was not found or was not visible. Verify the selector against the current page DOM.",
    "TIMING": "The page or element did not become ready before the wait expired. Check page load state, selector stability, and target responsiveness.",
    "NAVIGATION": "Navigation did not reach the expected page or URL. Verify the preceding action and session state.",
    "AUTHENTICATION": "The run was not authenticated as expected. Verify credentials, login state, and protected-page redirects.",
    "TEST_DATA": "The workflow reached a data-dependent step but the supplied value was missing, invalid, or not present in the target environment.",
    "ENVIRONMENT": "The browser or execution environment became unavailable before the run completed.",
    "NETWORK": "The target or a dependent request failed at the network layer. Check service availability and request diagnostics.",
    "ASSERTION": "The workflow reached an assertion, but the expected text, title, URL, or state was not present.",
    "APPLICATION_DEFECT": "The workflow completed far enough to expose behavior that does not match the expected application result.",
    "AUTOMATION_DEFECT": "The generated action or selector does not match the target page interaction.",
}


def _failure_guidance(failure_type: str) -> str:
    return _FAILURE_GUIDANCE.get(
        failure_type,
        "The execution failed before a more specific failure category could be established.",
    )


class DefectService:
    """Service managing defect creation, classification, and metrics."""

    @staticmethod
    def record_execution_failure(
        db: Session,
        *,
        run: TestRun,
        case_execution: Any | None = None,
        result: ExecutionResponse,
    ) -> Defect | None:
        """
        Automatically records an open defect when a test execution confirms a real failure.
        Deduplicates against existing open defects for the same test case / application.
        """
        if result.status not in {"failed", "error"}:
            return None

        try:
            test_case_id = getattr(case_execution, "test_case_id", None)
            tc: TestCase | None = db.get(TestCase, test_case_id) if test_case_id else None

            tc_title = tc.title if tc else (result.title or f"Test Run {run.id[:8]}")
            defect_title = f"Test Failure: {tc_title}"[:200]

            # 1. Deduplicate: check if an open defect already exists
            existing_defect = (
                db.query(Defect)
                .filter(
                    Defect.application_id == run.application_id,
                    Defect.title == defect_title,
                    Defect.status == "open",
                )
                .first()
            )

            failure_type = result.failure_type or "APPLICATION_DEFECT"
            failure_detail = result.failure_summary or result.error or "Test execution encountered a failure."
            failure_guidance = _failure_guidance(failure_type)

            # Collect detailed step and check failure traces
            step_failures = [
                f"- Step {sr.index} ({sr.action} on '{sr.selector}'): {sr.message}"
                for sr in (result.step_results or [])
                if not sr.passed
            ]
            check_failures = [
                f"- Check {c.type} ('{c.value}'): {c.message}"
                for c in (result.checks or [])
                if not c.passed
            ]

            trace_sections = []
            if step_failures:
                trace_sections.append("Failed Step(s):\n" + "\n".join(step_failures))
            if check_failures:
                trace_sections.append("Failed Check(s):\n" + "\n".join(check_failures))
            if result.error:
                trace_sections.append("Exception / Error:\n" + result.error[:2000])
            if result.console_errors:
                trace_sections.append("Console Errors:\n" + "\n".join(result.console_errors[:5]))
            if result.network_errors:
                trace_sections.append("Network Errors:\n" + "\n".join(result.network_errors[:5]))
            evidence = [
                f"- {artifact.label}: `{artifact.path}`"
                for artifact in [*(result.artifacts or []), *(result.step_artifacts or [])][:12]
            ]
            if evidence:
                trace_sections.append("Evidence:\n" + "\n".join(evidence))

            formatted_trace = "\n\n".join(trace_sections) if trace_sections else failure_detail

            description = (
                f"Automated test execution failed for run `{run.id}` on application `{run.application_id}`.\n\n"
                f"**Classification:** {failure_type}\n"
                f"**What this means:** {failure_guidance}\n"
                f"**Summary:** {failure_detail}\n\n"
                f"{formatted_trace}\n\n"
                f"**Target URL:** {result.url}\n"
                f"**Page title:** {result.title or 'Unavailable'}\n"
                f"**Run ID:** `{run.id}`\n"
                f"**Duration:** {result.duration_ms}ms"
            )

            # Determine severity based on failure classification and test case priority
            if failure_type in {"AUTHENTICATION", "SECURITY", "CRITICAL"}:
                severity = "critical"
            elif failure_type in {"APPLICATION_DEFECT", "ASSERTION"}:
                severity = "major"
            else:
                severity = "medium"

            priority = "high" if tc and tc.priority in {"high", "critical"} else "medium"

            if existing_defect:
                # Update existing defect description with latest run trace
                existing_defect.description = description
                existing_defect.severity = severity
                existing_defect.updated_at = datetime.now(timezone.utc)
                db.add(existing_defect)
                db.flush()
                logger.info("Updated existing defect #%d for test case %s", existing_defect.id, tc_title)
                return existing_defect

            # Create new defect
            new_defect = Defect(
                title=defect_title,
                description=description,
                priority=priority,
                severity=severity,
                status="open",
                application_id=run.application_id,
                created_by=run.created_by,
            )
            db.add(new_defect)
            db.flush()

            log_audit_event(
                db,
                user_id=run.created_by,
                action="defect.auto_created",
                resource_type="defect",
                resource_id=new_defect.id,
                metadata={
                    "run_id": run.id,
                    "test_case_id": test_case_id,
                    "failure_type": failure_type,
                    "application_id": run.application_id,
                },
            )
            logger.info("Auto-created defect #%d for failed run %s", new_defect.id, run.id)
            return new_defect

        except Exception as error:
            logger.warning("Failed to automatically record defect for run %s: %s", run.id, error)
            return None

    @staticmethod
    def get_defects(
        db: Session,
        *,
        user_id: int,
        application_id: int | None = None,
        status: str | None = None,
    ) -> list[Defect]:
        query = db.query(Defect).filter(Defect.created_by == user_id)
        if application_id is not None:
            query = query.filter(Defect.application_id == application_id)
        if status is not None:
            query = query.filter(Defect.status == status)
        return query.order_by(Defect.id.desc()).all()
