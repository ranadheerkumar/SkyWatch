"""Parallel Execution Engine for SkyWatch Autonomous Testing.

Manages high-throughput concurrent test execution with:
- Configurable worker pool concurrency (asyncio semaphore)
- Adaptive circuit breaker to prevent cascading environment overload
- Real-time step progress streaming
- Automatic interception of failures for autonomous diagnosis & self-healing
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("skywatch.agent.parallel_executor")


class CircuitBreakerOpenException(Exception):
    """Raised when execution stops because circuit breaker threshold was breached."""
    pass


class CircuitBreaker:
    """Monitors error rates and trips when environmental or auth failures cascade."""

    def __init__(self, failure_threshold: float = 0.60, min_samples: int = 5, max_consecutive_auth_failures: int = 3) -> None:
        self.failure_threshold = failure_threshold
        self.min_samples = min_samples
        self.max_consecutive_auth_failures = max_consecutive_auth_failures
        self.total_runs = 0
        self.total_failures = 0
        self.consecutive_auth_failures = 0
        self.is_open = False
        self.trip_reason = ""

    def record_result(self, success: bool, is_auth_failure: bool = False) -> None:
        self.total_runs += 1
        if not success:
            self.total_failures += 1
            if is_auth_failure:
                self.consecutive_auth_failures += 1
            else:
                self.consecutive_auth_failures = 0
        else:
            self.consecutive_auth_failures = 0

        # Check circuit breaker conditions
        if self.consecutive_auth_failures >= self.max_consecutive_auth_failures:
            self.is_open = True
            self.trip_reason = f"Circuit tripped: {self.consecutive_auth_failures} consecutive authentication failures."
            logger.error(self.trip_reason)

        elif self.total_runs >= self.min_samples:
            rate = self.total_failures / self.total_runs
            if rate >= self.failure_threshold:
                self.is_open = True
                self.trip_reason = f"Circuit tripped: failure rate ({rate:.1%}) exceeded threshold ({self.failure_threshold:.1%})."
                logger.error(self.trip_reason)


class ParallelExecutor:
    """Executes a suite of test cases concurrently with resource throttling and circuit breakers."""

    def __init__(self, max_concurrency: int = 4, progress_callback: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.circuit_breaker = CircuitBreaker()
        self.progress_callback = progress_callback

    async def execute_suite(
        self,
        test_cases: list[dict[str, Any]],
        executor_fn: Callable[[dict[str, Any]], Any],
    ) -> dict[str, Any]:
        """Execute test cases in parallel across the worker pool."""
        start_time = time.perf_counter()
        results: list[dict[str, Any]] = []
        healed_count = 0
        passed_count = 0
        failed_count = 0

        async def _run_worker(test_case: dict[str, Any]) -> dict[str, Any]:
            if self.circuit_breaker.is_open:
                return {
                    "test_id": test_case.get("id"),
                    "title": test_case.get("title", ""),
                    "status": "skipped",
                    "reason": self.circuit_breaker.trip_reason,
                }

            async with self.semaphore:
                try:
                    res = await executor_fn(test_case)
                    success = res.get("status") in {"passed", "healed"}
                    is_auth = res.get("failure_category") == "auth_failure"
                    self.circuit_breaker.record_result(success=success, is_auth_failure=is_auth)

                    if self.progress_callback:
                        self.progress_callback({
                            "type": "test_completed",
                            "test_id": test_case.get("id"),
                            "status": res.get("status"),
                            "healed": res.get("healed", False),
                        })

                    return res
                except Exception as ex:
                    self.circuit_breaker.record_result(success=False)
                    return {
                        "test_id": test_case.get("id"),
                        "title": test_case.get("title", ""),
                        "status": "failed",
                        "error": str(ex),
                    }

        tasks = [_run_worker(tc) for tc in test_cases]
        raw_results = await asyncio.gather(*tasks, return_exceptions=False)

        for r in raw_results:
            results.append(r)
            status = r.get("status")
            if status == "passed":
                passed_count += 1
            elif status == "healed":
                passed_count += 1
                healed_count += 1
            else:
                failed_count += 1

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        total = len(test_cases)
        pass_rate = round((passed_count / total * 100) if total > 0 else 0.0, 1)

        return {
            "total_tests": total,
            "passed": passed_count,
            "failed": failed_count,
            "healed": healed_count,
            "pass_rate_percentage": pass_rate,
            "duration_ms": duration_ms,
            "circuit_breaker_tripped": self.circuit_breaker.is_open,
            "circuit_breaker_reason": self.circuit_breaker.trip_reason,
            "results": results,
        }
