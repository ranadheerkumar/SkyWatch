"""Allure 2 test reporting integration for SkyWatch QA Platform.

Generates industry-standard Allure 2 JSON result files, test suites,
step breakdowns, attachments, and container metadata from test execution runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any
from uuid import uuid4

logger = logging.getLogger("ai-qa-engine.allure_reporter")


def _status_to_allure(status: str) -> str:
    normalized = (status or "").lower().strip()
    if normalized in {"passed", "pass", "success"}:
        return "passed"
    if normalized in {"failed", "fail", "failure"}:
        return "failed"
    if normalized in {"skipped", "skip", "pending"}:
        return "skipped"
    if normalized in {"broken", "error"}:
        return "broken"
    return "unknown"


def generate_allure_result_from_run(
    run_id: str,
    test_case_title: str,
    status: str,
    start_time: float | None = None,
    end_time: float | None = None,
    duration_ms: float | None = None,
    error_message: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    suite_name: str = "SkyWatch Autonomous Test Suite",
    labels: dict[str, str] | None = None,
    parameters: dict[str, Any] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a standard Allure 2 test result JSON object."""
    test_uuid = str(uuid4())
    history_source = f"{suite_name}:{test_case_title}"
    history_id = hashlib.md5(history_source.encode("utf-8")).hexdigest()

    now_ms = int(time.time() * 1000)
    dur_ms = int(duration_ms or 0)
    start_ms = int((start_time * 1000) if start_time else (now_ms - dur_ms))
    stop_ms = int((end_time * 1000) if end_time else now_ms)

    allure_status = _status_to_allure(status)

    allure_steps = []
    if steps:
        step_cursor = start_ms
        for i, step in enumerate(steps):
            step_name = step.get("description") or step.get("name") or step.get("step") or f"Step {i + 1}"
            step_status = _status_to_allure(step.get("status", "passed"))
            step_dur = int(step.get("duration_ms", 100))
            allure_steps.append({
                "name": step_name,
                "status": step_status,
                "stage": "finished",
                "start": step_cursor,
                "stop": step_cursor + step_dur,
                "parameters": [],
                "steps": [],
                "attachments": [],
            })
            step_cursor += step_dur

    label_list = [
        {"name": "suite", "value": suite_name},
        {"name": "framework", "value": "SkyWatch-QA-Engine"},
        {"name": "host", "value": "localhost"},
        {"name": "language", "value": "python"},
    ]
    if labels:
        for k, v in labels.items():
            label_list.append({"name": k, "value": str(v)})

    param_list = []
    if parameters:
        for k, v in parameters.items():
            param_list.append({"name": k, "value": str(v)})

    result: dict[str, Any] = {
        "uuid": test_uuid,
        "historyId": history_id,
        "testCaseId": history_id,
        "fullName": f"{suite_name}#{test_case_title}",
        "name": test_case_title,
        "status": allure_status,
        "statusDetails": {
            "known": False,
            "muted": False,
            "flaky": False,
            "message": error_message or "",
            "trace": error_message or "",
        },
        "stage": "finished",
        "steps": allure_steps,
        "attachments": attachments or [],
        "parameters": param_list,
        "labels": label_list,
        "links": [],
        "start": start_ms,
        "stop": stop_ms,
    }

    return result


def export_allure_suite(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Package multiple test run results into an Allure report payload."""
    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    broken = sum(1 for r in results if r.get("status") == "broken")

    return {
        "format": "allure2",
        "version": "2.0",
        "generated_at": int(time.time() * 1000),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "broken": broken,
            "pass_rate": round(passed / len(results) * 100, 1) if results else 100.0,
        },
        "results": results,
    }
