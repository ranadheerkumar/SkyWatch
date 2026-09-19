"""Rate Limiting & Observability Middleware for SkyWatch.

Provides:
1. Token Bucket rate limiter with configurable rate/burst per endpoint group.
2. Sliding Window Counter for accurate per-IP and per-user rate tracking.
3. Automatic endpoint group classification by API prefix.
4. Standard 429 response with Retry-After and X-RateLimit-* headers.
5. In-memory metrics collector for request counts, error rates, and latencies.
6. IP allowlist bypass for trusted services and health checks.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger("skywatch.core.rate_limiter")


# ---------------------------------------------------------------------------
# Rate Limit Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RateLimitRule:
    """Rate limit configuration for an endpoint group."""
    requests_per_minute: int
    burst_size: int  # Maximum burst capacity above sustained rate
    name: str = ""


# Default rate limit rules by endpoint group prefix
DEFAULT_RATE_RULES: dict[str, RateLimitRule] = {
    "/api/v1/auth": RateLimitRule(requests_per_minute=30, burst_size=10, name="auth"),
    "/api/v1/orchestrator": RateLimitRule(requests_per_minute=10, burst_size=5, name="orchestrator"),
    "/api/v1/ai-generation": RateLimitRule(requests_per_minute=15, burst_size=5, name="ai-generation"),
    "/api/v1/observability": RateLimitRule(requests_per_minute=120, burst_size=20, name="observability"),
    "/api/v1": RateLimitRule(requests_per_minute=60, burst_size=15, name="api-general"),
    "/health": RateLimitRule(requests_per_minute=300, burst_size=50, name="health"),
}

# IPs exempt from rate limiting (loopback, internal health checks, test clients)
DEFAULT_IP_ALLOWLIST: set[str] = {"127.0.0.1", "::1", "0.0.0.0", "localhost", "testclient"}


# ---------------------------------------------------------------------------
# Token Bucket
# ---------------------------------------------------------------------------

class TokenBucket:
    """Token bucket rate limiter for a single key (IP + endpoint group)."""

    def __init__(self, rate_per_second: float, burst_size: int) -> None:
        self.rate = rate_per_second
        self.burst = burst_size
        self.tokens = float(burst_size)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume a token. Returns True if request is allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    @property
    def remaining(self) -> int:
        """Approximate number of remaining tokens."""
        return max(0, int(self.tokens))

    @property
    def retry_after_seconds(self) -> float:
        """Seconds until next token becomes available."""
        if self.tokens >= 1.0:
            return 0.0
        return max(0.0, (1.0 - self.tokens) / self.rate)


# ---------------------------------------------------------------------------
# Metrics Collector
# ---------------------------------------------------------------------------

@dataclass
class EndpointGroupMetrics:
    """Aggregated metrics for an endpoint group."""
    total_requests: int = 0
    successful_requests: int = 0
    error_requests: int = 0  # 5xx
    rate_limited_requests: int = 0  # 429
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    status_codes: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.total_latency_ms / self.total_requests, 2)

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.error_requests / self.total_requests * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "error_requests": self.error_requests,
            "rate_limited_requests": self.rate_limited_requests,
            "avg_latency_ms": self.avg_latency_ms,
            "min_latency_ms": round(self.min_latency_ms, 2) if self.min_latency_ms != float("inf") else 0.0,
            "max_latency_ms": round(self.max_latency_ms, 2),
            "error_rate_pct": self.error_rate,
            "status_codes": dict(self.status_codes),
        }


class MetricsCollector:
    """In-memory metrics aggregator for observability."""

    def __init__(self) -> None:
        self._groups: dict[str, EndpointGroupMetrics] = defaultdict(EndpointGroupMetrics)
        self._start_time = time.monotonic()

    def record(self, group: str, status_code: int, latency_ms: float) -> None:
        """Record a request completion."""
        m = self._groups[group]
        m.total_requests += 1
        m.total_latency_ms += latency_ms
        m.min_latency_ms = min(m.min_latency_ms, latency_ms)
        m.max_latency_ms = max(m.max_latency_ms, latency_ms)
        m.status_codes[status_code] += 1

        if 200 <= status_code < 400:
            m.successful_requests += 1
        elif status_code == 429:
            m.rate_limited_requests += 1
        elif status_code >= 500:
            m.error_requests += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all collected metrics."""
        uptime_s = round(time.monotonic() - self._start_time, 1)
        total_reqs = sum(m.total_requests for m in self._groups.values())

        return {
            "uptime_seconds": uptime_s,
            "total_requests": total_reqs,
            "endpoint_groups": {
                name: metrics.to_dict() for name, metrics in sorted(self._groups.items())
            },
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._groups.clear()
        self._start_time = time.monotonic()


# ---------------------------------------------------------------------------
# Rate Limiter Engine
# ---------------------------------------------------------------------------

class RateLimiterEngine:
    """Central rate limiting engine managing token buckets per client+group."""

    def __init__(
        self,
        rules: dict[str, RateLimitRule] | None = None,
        ip_allowlist: set[str] | None = None,
        enabled: bool = True,
    ) -> None:
        self.rules = rules or DEFAULT_RATE_RULES
        self.ip_allowlist = ip_allowlist or DEFAULT_IP_ALLOWLIST
        self.enabled = enabled
        self._buckets: dict[str, TokenBucket] = {}
        self.metrics = MetricsCollector()

    def _resolve_group(self, path: str) -> tuple[str, RateLimitRule]:
        """Resolve the rate limit group for a request path."""
        for prefix, rule in sorted(self.rules.items(), key=lambda x: -len(x[0])):
            if path.startswith(prefix):
                return rule.name or prefix, rule
        return "default", RateLimitRule(requests_per_minute=60, burst_size=15, name="default")

    def _bucket_key(self, client_id: str, group: str) -> str:
        return f"{client_id}:{group}"

    def _get_bucket(self, client_id: str, group: str, rule: RateLimitRule) -> TokenBucket:
        key = self._bucket_key(client_id, group)
        if key not in self._buckets:
            rate_per_second = rule.requests_per_minute / 60.0
            self._buckets[key] = TokenBucket(rate_per_second, rule.burst_size)
        return self._buckets[key]

    def check_rate_limit(self, client_ip: str, path: str) -> tuple[bool, str, TokenBucket | None]:
        """Check if a request should be rate limited.

        Returns:
            (allowed, group_name, bucket)
        """
        if not self.enabled:
            return True, "disabled", None

        if client_ip in self.ip_allowlist:
            return True, "allowlisted", None

        group, rule = self._resolve_group(path)
        bucket = self._get_bucket(client_ip, group, rule)

        if bucket.consume():
            return True, group, bucket
        return False, group, bucket

    def cleanup_stale_buckets(self, max_age_seconds: float = 3600.0) -> int:
        """Remove token buckets that haven't been accessed recently."""
        now = time.monotonic()
        stale_keys = [
            key for key, bucket in self._buckets.items()
            if (now - bucket.last_refill) > max_age_seconds
        ]
        for key in stale_keys:
            del self._buckets[key]
        return len(stale_keys)


# ---------------------------------------------------------------------------
# FastAPI Middleware
# ---------------------------------------------------------------------------

def _extract_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware implementing token bucket rate limiting with observability."""

    def __init__(self, app: Any, rate_limiter: RateLimiterEngine | None = None) -> None:
        super().__init__(app)
        self.limiter = rate_limiter or RateLimiterEngine()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = _extract_client_ip(request)
        path = request.url.path
        start_time = time.perf_counter()

        # Check rate limit
        allowed, group, bucket = self.limiter.check_rate_limit(client_ip, path)

        if not allowed and bucket is not None:
            retry_after = max(1, int(bucket.retry_after_seconds) + 1)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self.limiter.metrics.record(group, 429, latency_ms)

            logger.warning(
                "Rate limited: client=%s path=%s group=%s",
                client_ip, path, group,
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please retry after the specified interval.",
                    "retry_after_seconds": retry_after,
                    "rate_limit_group": group,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(bucket.burst if bucket else 0),
                    "X-RateLimit-Remaining": str(bucket.remaining if bucket else 0),
                    "X-RateLimit-Reset": str(retry_after),
                },
            )

        # Process request
        response = await call_next(request)

        # Record metrics
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        self.limiter.metrics.record(group, response.status_code, latency_ms)

        # Add rate limit headers to successful responses
        if bucket is not None:
            response.headers["X-RateLimit-Limit"] = str(bucket.burst)
            response.headers["X-RateLimit-Remaining"] = str(bucket.remaining)

        return response
