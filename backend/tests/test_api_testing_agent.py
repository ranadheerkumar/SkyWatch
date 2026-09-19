"""Unit tests for SkyWatch API Testing Agent."""

import json
import pytest
from app.agent.api_testing_agent import (
    AutonomousAPITestingAgent,
    _extract_schema_properties,
    _safe_json_preview,
    NEGATIVE_PAYLOADS,
)
from app.agent.types import (
    APIAuditReport,
    APITestCase,
    APITestResult,
    APITestStatus,
    ContractViolation,
)


def test_extract_schema_properties():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "active": {"type": "boolean"},
        },
        "required": ["name"],
    }
    props = _extract_schema_properties(schema)
    assert props == {"name": "string", "age": "integer", "active": "boolean"}


def test_extract_schema_properties_empty():
    assert _extract_schema_properties({}) == {}
    assert _extract_schema_properties({"type": "object"}) == {}


def test_safe_json_preview_truncation():
    data = {"key": "x" * 1000}
    preview = _safe_json_preview(data, max_length=50)
    assert len(preview) <= 50


def test_safe_json_preview_normal():
    data = {"status": "ok"}
    preview = _safe_json_preview(data)
    assert "ok" in preview


def test_negative_payloads_coverage():
    # Ensure all types have negative payloads defined
    expected_types = {"string", "integer", "number", "boolean", "array", "object"}
    assert set(NEGATIVE_PAYLOADS.keys()) == expected_types
    for type_name, values in NEGATIVE_PAYLOADS.items():
        assert len(values) >= 3, f"Need at least 3 negative payloads for {type_name}"


def test_generate_contract_tests_from_spec():
    agent = AutonomousAPITestingAgent()
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {
                "get": {
                    "operationId": "listUsers",
                    "summary": "List all users",
                    "responses": {"200": {"description": "Success"}},
                },
                "post": {
                    "operationId": "createUser",
                    "summary": "Create a user",
                    "responses": {"201": {"description": "Created"}},
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "email": {"type": "string"},
                                    },
                                    "required": ["name", "email"],
                                },
                            }
                        }
                    },
                },
            },
            "/health": {
                "get": {
                    "operationId": "healthCheck",
                    "responses": {"200": {}},
                },
            },
        },
    }

    tests = agent.generate_contract_tests(spec)
    assert len(tests) >= 3  # GET /users, POST /users, GET /health + negative tests

    # Should have positive contract tests
    positive_tests = [t for t in tests if not t.is_negative_test]
    assert len(positive_tests) >= 3

    # Should have negative tests for POST /users
    negative_tests = [t for t in tests if t.is_negative_test]
    assert len(negative_tests) > 0

    # POST /users should expect 201
    post_test = next(t for t in positive_tests if t.method == "POST" and t.path == "/users")
    assert post_test.expected_status == 201


def test_generate_contract_tests_empty_spec():
    agent = AutonomousAPITestingAgent()
    tests = agent.generate_contract_tests({})
    assert tests == []


def test_negative_test_generation():
    agent = AutonomousAPITestingAgent(max_negative_tests_per_endpoint=5)
    tests = agent._generate_negative_tests(
        path="/api/items",
        method="POST",
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "count": {"type": "integer"},
                "active": {"type": "boolean"},
            },
            "required": ["title", "count"],
        },
        operation_id="createItem",
    )
    assert len(tests) > 0
    assert all(t.is_negative_test for t in tests)
    # Should have missing required field tests
    missing_tests = [t for t in tests if "Missing required" in t.description]
    assert len(missing_tests) >= 1


def test_type_matching():
    agent = AutonomousAPITestingAgent()
    assert agent._type_matches("hello", "string") is True
    assert agent._type_matches(42, "integer") is True
    assert agent._type_matches(3.14, "number") is True
    assert agent._type_matches(True, "boolean") is True
    assert agent._type_matches([], "array") is True
    assert agent._type_matches({}, "object") is True

    # Mismatches
    assert agent._type_matches(42, "string") is False
    assert agent._type_matches("hello", "integer") is False
    assert agent._type_matches([], "object") is False


def test_api_test_result_serialization():
    result = APITestResult(
        test_id="test-001",
        method="GET",
        path="/users",
        status=APITestStatus.FAILED,
        response_status_code=500,
        response_time_ms=123.45,
        violations=[
            ContractViolation(field="status_code", expected="200", actual="500"),
        ],
    )
    d = result.to_dict()
    assert d["test_id"] == "test-001"
    assert d["status"] == "failed"
    assert d["response_status_code"] == 500
    assert len(d["violations"]) == 1
    assert d["violations"][0]["field"] == "status_code"


def test_api_audit_report_serialization():
    report = APIAuditReport(
        base_url="https://api.example.com",
        total_tests=10,
        passed=8,
        failed=1,
        errors=1,
        contract_violations=2,
        avg_response_time_ms=50.5,
        p50_response_time_ms=45.0,
        p90_response_time_ms=120.0,
        p99_response_time_ms=200.0,
        discovered_endpoints=5,
    )
    d = report.to_dict()
    assert d["base_url"] == "https://api.example.com"
    assert d["total_tests"] == 10
    assert d["passed"] == 8
    assert d["p90_response_time_ms"] == 120.0


def test_contract_violation_serialization():
    v = ContractViolation(
        field="content_type",
        expected="application/json",
        actual="text/html",
        severity="warning",
    )
    d = v.to_dict()
    assert d["field"] == "content_type"
    assert d["severity"] == "warning"


def test_auth_header_construction():
    # With token
    agent = AutonomousAPITestingAgent(auth_token="my-secret-token")
    headers = agent._build_auth_headers()
    assert headers["Authorization"] == "Bearer my-secret-token"

    # Without token
    agent_no_auth = AutonomousAPITestingAgent()
    headers_empty = agent_no_auth._build_auth_headers()
    assert headers_empty == {}

    # Custom header/prefix
    agent_custom = AutonomousAPITestingAgent(
        auth_token="key123",
        auth_header="X-API-Key",
        auth_prefix="Token",
    )
    headers_custom = agent_custom._build_auth_headers()
    assert headers_custom["X-API-Key"] == "Token key123"


def test_schema_validation():
    agent = AutonomousAPITestingAgent()
    body = {"name": "John", "age": "not_a_number"}
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name", "age"],
    }
    violations = agent._validate_response_schema(body, schema)
    # 'age' should be flagged as wrong type
    type_violations = [v for v in violations if v.field == "age"]
    assert len(type_violations) == 1
    assert type_violations[0].expected == "integer"


def test_schema_validation_missing_required():
    agent = AutonomousAPITestingAgent()
    body = {"name": "John"}
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
        },
        "required": ["name", "email"],
    }
    violations = agent._validate_response_schema(body, schema)
    missing = [v for v in violations if v.field == "email"]
    assert len(missing) == 1
    assert "missing" in missing[0].actual
