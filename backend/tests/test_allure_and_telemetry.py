"""Tests for OpenTelemetry distributed tracing and Allure 2 reporting integrations."""

import pytest
from app.core.telemetry import trace_span, traced, TraceSpan
from app.services.allure_reporter import (
    generate_allure_result_from_run,
    export_allure_suite,
    _status_to_allure,
)


def test_status_to_allure_mapping():
    assert _status_to_allure("passed") == "passed"
    assert _status_to_allure("pass") == "passed"
    assert _status_to_allure("failed") == "failed"
    assert _status_to_allure("error") == "broken"
    assert _status_to_allure("skipped") == "skipped"
    assert _status_to_allure("unknown_val") == "unknown"


def test_generate_allure_result_from_run():
    result = generate_allure_result_from_run(
        run_id="run-12345678",
        test_case_title="TC01 - Verify User Login",
        status="passed",
        duration_ms=1250,
        steps=[
            {"name": "Open login page", "status": "passed", "duration_ms": 300},
            {"name": "Enter credentials", "status": "passed", "duration_ms": 450},
            {"name": "Assert dashboard", "status": "passed", "duration_ms": 500},
        ],
        suite_name="Auth Test Suite",
        labels={"feature": "Authentication", "severity": "critical"},
        parameters={"browser": "chromium"},
    )

    assert result["name"] == "TC01 - Verify User Login"
    assert result["status"] == "passed"
    assert result["stage"] == "finished"
    assert len(result["steps"]) == 3
    assert result["steps"][0]["name"] == "Open login page"
    assert result["steps"][0]["status"] == "passed"
    assert any(label["name"] == "feature" and label["value"] == "Authentication" for label in result["labels"])
    assert any(param["name"] == "browser" and param["value"] == "chromium" for param in result["parameters"])


def test_export_allure_suite():
    res1 = generate_allure_result_from_run(
        run_id="run-1",
        test_case_title="TC01",
        status="passed",
    )
    res2 = generate_allure_result_from_run(
        run_id="run-2",
        test_case_title="TC02",
        status="failed",
        error_message="Element not found",
    )

    suite = export_allure_suite([res1, res2])
    assert suite["format"] == "allure2"
    assert suite["summary"]["total"] == 2
    assert suite["summary"]["passed"] == 1
    assert suite["summary"]["failed"] == 1
    assert suite["summary"]["pass_rate"] == 50.0


def test_telemetry_trace_span_context():
    with trace_span("test_operation", {"service": "qa_engine", "operation": "test"}) as span:
        assert isinstance(span, TraceSpan)
        assert span.name == "test_operation"
        assert span.attributes["service"] == "qa_engine"
        span.set_attribute("custom_key", "custom_val")
        assert span.attributes["custom_key"] == "custom_val"

    assert span.duration_ms >= 0
    assert span.status == "ok"


def test_telemetry_trace_span_exception():
    with pytest.raises(ValueError, match="test error"):
        with trace_span("failing_operation") as span:
            raise ValueError("test error")

    assert span.status == "error"
    assert isinstance(span.error, ValueError)


@pytest.mark.asyncio
async def test_telemetry_traced_decorator():
    @traced("async_computation")
    async def sample_async_func(x: int, y: int) -> int:
        return x + y

    result = await sample_async_func(3, 7)
    assert result == 10
