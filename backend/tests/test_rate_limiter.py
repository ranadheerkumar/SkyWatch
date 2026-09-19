"""Unit tests for SkyWatch Rate Limiter & Observability Middleware."""

import asyncio
import time

import pytest
from app.core.rate_limiter import (
    DEFAULT_RATE_RULES,
    EndpointGroupMetrics,
    MetricsCollector,
    RateLimiterEngine,
    RateLimitRule,
    TokenBucket,
)


# ---------------------------------------------------------------------------
# Token Bucket Tests
# ---------------------------------------------------------------------------


def test_token_bucket_initial_capacity():
    bucket = TokenBucket(rate_per_second=1.0, burst_size=10)
    assert bucket.remaining == 10


def test_token_bucket_consume():
    bucket = TokenBucket(rate_per_second=1.0, burst_size=5)
    assert bucket.consume() is True
    assert bucket.remaining == 4
    assert bucket.consume() is True
    assert bucket.remaining == 3


def test_token_bucket_exhaustion():
    bucket = TokenBucket(rate_per_second=0.1, burst_size=2)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False  # Exhausted


def test_token_bucket_refill():
    bucket = TokenBucket(rate_per_second=100.0, burst_size=5)  # Very fast refill
    # Drain
    for _ in range(5):
        bucket.consume()
    assert bucket.remaining == 0
    # Wait for refill
    time.sleep(0.05)  # Should refill several tokens at 100/sec
    assert bucket.consume() is True


def test_token_bucket_retry_after():
    bucket = TokenBucket(rate_per_second=1.0, burst_size=1)
    bucket.consume()  # Use the only token
    retry = bucket.retry_after_seconds
    assert retry >= 0.0


# ---------------------------------------------------------------------------
# Rate Limiter Engine Tests
# ---------------------------------------------------------------------------


def test_rate_limiter_resolve_group():
    engine = RateLimiterEngine()
    group, rule = engine._resolve_group("/api/v1/orchestrator/campaigns")
    assert rule.name == "orchestrator"


def test_rate_limiter_resolve_group_general_api():
    engine = RateLimiterEngine()
    group, rule = engine._resolve_group("/api/v1/test-cases")
    assert rule.name == "api-general"


def test_rate_limiter_resolve_group_health():
    engine = RateLimiterEngine()
    group, rule = engine._resolve_group("/health")
    assert rule.name == "health"


def test_rate_limiter_resolve_group_default():
    engine = RateLimiterEngine()
    group, rule = engine._resolve_group("/unknown/path")
    assert rule.name == "default"


def test_rate_limiter_allows_within_limit():
    engine = RateLimiterEngine(rules={
        "/test": RateLimitRule(requests_per_minute=60, burst_size=10),
    })
    allowed, group, bucket = engine.check_rate_limit("10.0.0.1", "/test/endpoint")
    assert allowed is True


def test_rate_limiter_blocks_after_burst():
    engine = RateLimiterEngine(rules={
        "/test": RateLimitRule(requests_per_minute=60, burst_size=3),
    })
    for _ in range(3):
        allowed, _, _ = engine.check_rate_limit("10.0.0.1", "/test")
        assert allowed is True

    # 4th request should be blocked
    allowed, group, bucket = engine.check_rate_limit("10.0.0.1", "/test")
    assert allowed is False
    assert bucket is not None


def test_rate_limiter_ip_allowlist_bypass():
    engine = RateLimiterEngine(
        rules={"/test": RateLimitRule(requests_per_minute=1, burst_size=1)},
        ip_allowlist={"10.0.0.1"},
    )
    # Use all tokens
    engine.check_rate_limit("10.0.0.2", "/test")
    allowed, _, _ = engine.check_rate_limit("10.0.0.2", "/test")
    assert allowed is False

    # Allowlisted IP should always pass
    allowed, group, _ = engine.check_rate_limit("10.0.0.1", "/test")
    assert allowed is True
    assert group == "allowlisted"


def test_rate_limiter_disabled():
    engine = RateLimiterEngine(enabled=False)
    allowed, group, _ = engine.check_rate_limit("10.0.0.1", "/api/v1/test")
    assert allowed is True
    assert group == "disabled"


def test_rate_limiter_different_ips_separate_buckets():
    engine = RateLimiterEngine(rules={
        "/test": RateLimitRule(requests_per_minute=60, burst_size=2),
    })
    # IP A exhausts its bucket
    engine.check_rate_limit("ip_a", "/test")
    engine.check_rate_limit("ip_a", "/test")
    allowed_a, _, _ = engine.check_rate_limit("ip_a", "/test")
    assert allowed_a is False

    # IP B should still have tokens
    allowed_b, _, _ = engine.check_rate_limit("ip_b", "/test")
    assert allowed_b is True


def test_rate_limiter_cleanup_stale_buckets():
    engine = RateLimiterEngine(rules={
        "/test": RateLimitRule(requests_per_minute=60, burst_size=10),
    })
    engine.check_rate_limit("10.0.0.1", "/test")
    engine.check_rate_limit("10.0.0.2", "/test")
    assert len(engine._buckets) == 2

    # Cleanup with max_age=0 should remove all
    removed = engine.cleanup_stale_buckets(max_age_seconds=0.0)
    assert removed == 2
    assert len(engine._buckets) == 0


# ---------------------------------------------------------------------------
# Metrics Collector Tests
# ---------------------------------------------------------------------------


def test_metrics_collector_record():
    collector = MetricsCollector()
    collector.record("api-general", 200, 50.0)
    collector.record("api-general", 200, 100.0)
    collector.record("api-general", 500, 200.0)
    collector.record("auth", 429, 10.0)

    snapshot = collector.snapshot()
    assert snapshot["total_requests"] == 4
    assert "api-general" in snapshot["endpoint_groups"]
    assert "auth" in snapshot["endpoint_groups"]

    api_metrics = snapshot["endpoint_groups"]["api-general"]
    assert api_metrics["total_requests"] == 3
    assert api_metrics["successful_requests"] == 2
    assert api_metrics["error_requests"] == 1
    assert api_metrics["avg_latency_ms"] > 0

    auth_metrics = snapshot["endpoint_groups"]["auth"]
    assert auth_metrics["rate_limited_requests"] == 1


def test_metrics_collector_reset():
    collector = MetricsCollector()
    collector.record("test", 200, 10.0)
    assert collector.snapshot()["total_requests"] == 1
    collector.reset()
    assert collector.snapshot()["total_requests"] == 0


def test_endpoint_group_metrics_error_rate():
    m = EndpointGroupMetrics()
    m.total_requests = 10
    m.error_requests = 3
    assert m.error_rate == 30.0


def test_endpoint_group_metrics_zero_requests():
    m = EndpointGroupMetrics()
    assert m.avg_latency_ms == 0.0
    assert m.error_rate == 0.0


def test_endpoint_group_metrics_serialization():
    m = EndpointGroupMetrics()
    m.total_requests = 5
    m.successful_requests = 4
    m.error_requests = 1
    m.total_latency_ms = 250.0
    m.min_latency_ms = 20.0
    m.max_latency_ms = 100.0

    d = m.to_dict()
    assert d["total_requests"] == 5
    assert d["avg_latency_ms"] == 50.0
    assert d["min_latency_ms"] == 20.0
    assert d["max_latency_ms"] == 100.0
    assert d["error_rate_pct"] == 20.0


# ---------------------------------------------------------------------------
# Default Rules Tests
# ---------------------------------------------------------------------------


def test_default_rate_rules_exist():
    assert len(DEFAULT_RATE_RULES) >= 4
    assert "/api/v1/orchestrator" in DEFAULT_RATE_RULES
    assert "/api/v1/auth" in DEFAULT_RATE_RULES
    assert "/health" in DEFAULT_RATE_RULES


def test_orchestrator_rate_is_restrictive():
    rule = DEFAULT_RATE_RULES["/api/v1/orchestrator"]
    assert rule.requests_per_minute <= 15  # Should be low for expensive operations
    assert rule.burst_size <= 10
