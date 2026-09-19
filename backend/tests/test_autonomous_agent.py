"""Unit tests for SkyWatch Autonomous Agentic Engine."""

import pytest
from app.agent.analysis_agent import AutonomousAnalysisAgent
from app.agent.autonomous_orchestrator import AutonomousAgentOrchestrator
from app.agent.discovery_agent import AutonomousDiscoveryAgent
from app.agent.healing_agent import AutonomousHealingAgent
from app.agent.parallel_executor import CircuitBreaker, ParallelExecutor
from app.agent.types import FailureCategory


def test_discovery_selector_bundle_generation():
    agent = AutonomousDiscoveryAgent()
    bundle = agent._generate_selector_bundle(
        tag="button",
        el_id="submit-order-btn",
        test_id="checkout-submit",
        aria_label="Complete Checkout",
        text="Place Order Now",
        el_type="submit",
    )
    assert len(bundle) >= 4
    # TestID should be prioritized
    assert "[data-testid='checkout-submit']" in bundle[0] or "[data-test='checkout-submit']" in bundle[0]
    # Id and text should be present
    assert any("#submit-order-btn" in s for s in bundle)
    assert any("Place Order Now" in s for s in bundle)


@pytest.mark.asyncio
async def test_analysis_agent_diagnose_selector_drift():
    agent = AutonomousAnalysisAgent()
    diagnosis = await agent.diagnose_failure(
        action="click",
        selector="#login-button",
        error_message="Error: waiting for locator('#login-button') to be visible: timeout 30000ms exceeded",
        page_url="https://example.com/login",
    )
    assert diagnosis.category == FailureCategory.SELECTOR_DRIFT
    assert diagnosis.confidence >= 0.80
    assert len(diagnosis.candidate_selectors) > 0


@pytest.mark.asyncio
async def test_analysis_agent_diagnose_regression_bug():
    agent = AutonomousAnalysisAgent()
    diagnosis = await agent.diagnose_failure(
        action="click",
        selector="button[type=submit]",
        error_message="Request failed with status code 500",
        dom_snippet="<div>Internal Server Error: Uncaught TypeError in OrderService</div>",
        status_code=500,
    )
    assert diagnosis.category == FailureCategory.REGRESSION_BUG
    assert diagnosis.confidence >= 0.85
    assert "500" in diagnosis.root_cause or "Internal Server Error" in diagnosis.root_cause


@pytest.mark.asyncio
async def test_analysis_agent_diagnose_environment_flake():
    agent = AutonomousAnalysisAgent()
    diagnosis = await agent.diagnose_failure(
        action="navigate",
        selector=None,
        error_message="net::ERR_CONNECTION_RESET at https://example.com/api/orders",
        status_code=504,
    )
    assert diagnosis.category == FailureCategory.ENVIRONMENT_FLAKE
    assert diagnosis.confidence >= 0.90


@pytest.mark.asyncio
async def test_healing_agent_attempt_heal():
    healer = AutonomousHealingAgent(min_confidence=0.70)
    record = await healer.attempt_heal_step(
        app_id=1,
        test_id="test_001",
        step_index=2,
        action="click",
        failing_selector="#submit-order-btn",
        candidate_selectors=["button:has-text('Submit')", "[data-testid='submit-btn']"],
        page_instance=None,  # offline validation mode
    )
    assert record is not None
    assert record.original_selector == "#submit-order-btn"
    assert record.healed_selector in ["button:has-text('Submit')", "[data-testid='submit-btn']"]
    assert record.confidence >= 0.70


def test_circuit_breaker_trip():
    cb = CircuitBreaker(failure_threshold=0.5, min_samples=4)
    cb.record_result(success=True)
    cb.record_result(success=False)
    cb.record_result(success=False)
    cb.record_result(success=False)
    assert cb.is_open is True
    assert "failure rate" in cb.trip_reason


def test_circuit_breaker_consecutive_auth_failures():
    cb = CircuitBreaker(max_consecutive_auth_failures=2)
    cb.record_result(success=False, is_auth_failure=True)
    assert cb.is_open is False
    cb.record_result(success=False, is_auth_failure=True)
    assert cb.is_open is True
    assert "consecutive authentication failures" in cb.trip_reason


@pytest.mark.asyncio
async def test_parallel_executor_concurrency():
    executor = ParallelExecutor(max_concurrency=2)
    test_cases = [
        {"id": "tc1", "title": "Test 1", "steps": [{"action": "click", "selector": "#btn"}]},
        {"id": "tc2", "title": "Test 2", "steps": [{"action": "click", "selector": "#btn"}]},
        {"id": "tc3", "title": "Test 3", "steps": [{"action": "click", "selector": "#btn"}]},
    ]

    async def dummy_runner(tc):
        return {"status": "passed", "test_id": tc["id"]}

    summary = await executor.execute_suite(test_cases, dummy_runner)
    assert summary["total_tests"] == 3
    assert summary["passed"] == 3
    assert summary["failed"] == 0
    assert summary["pass_rate_percentage"] == 100.0


@pytest.mark.asyncio
async def test_autonomous_orchestrator_closed_loop():
    orchestrator = AutonomousAgentOrchestrator(max_concurrency=2, auto_heal_enabled=True)
    report = await orchestrator.run_autonomous_campaign(
        application_id=99,
        target_url="https://example.com",
        objective="Smoke test autonomous run",
    )
    assert report["campaign_id"] == orchestrator.campaign_id
    assert report["status"] == "completed"
    assert "quality_score" in report
    assert "discovery" in report
    assert "execution" in report
    assert "self_healing" in report
    assert report["quality_score"] > 0
