"""Observability API Endpoints for SkyWatch.

Exposes system-level metrics and deep health checks:
- GET /api/v1/observability/metrics — aggregated request counts, latencies, rate-limit triggers
- GET /api/v1/observability/health — deep health check with DB, LLM provider, and rate limiter status
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.dependencies import DbSession, current_user
from app.core.config import settings
from app.models.user import User

logger = logging.getLogger("skywatch.api.observability")

router = APIRouter(prefix="/observability", tags=["observability"])

# Reference to the global rate limiter — set at app startup
_rate_limiter_engine = None


def set_rate_limiter_engine(engine: Any) -> None:
    """Register the rate limiter engine for metrics access. Called from main.py."""
    global _rate_limiter_engine
    _rate_limiter_engine = engine


@router.get("/metrics")
async def get_observability_metrics(
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Return aggregated observability metrics across all endpoint groups.

    Includes total request counts, error rates, latency distributions,
    and rate-limiting trigger counts per endpoint group.
    """
    if _rate_limiter_engine is None:
        return {
            "status": "unavailable",
            "message": "Rate limiter engine not initialized.",
        }

    metrics = _rate_limiter_engine.metrics.snapshot()
    metrics["rate_limiter_enabled"] = _rate_limiter_engine.enabled
    metrics["active_buckets"] = len(_rate_limiter_engine._buckets)
    return metrics


@router.get("/health")
async def deep_health_check(
    db: DbSession,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Deep health check probing database, LLM provider availability, and rate limiter status."""
    checks: dict[str, Any] = {}

    # 1. Database health
    db_start = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_ms = round((time.perf_counter() - db_start) * 1000, 2)
        checks["database"] = {"status": "healthy", "latency_ms": db_ms}
    except Exception as ex:
        db_ms = round((time.perf_counter() - db_start) * 1000, 2)
        checks["database"] = {"status": "unhealthy", "error": str(ex), "latency_ms": db_ms}

    # 2. LLM provider availability
    try:
        from app.services.llm_client import get_all_provider_statuses
        providers = get_all_provider_statuses()
        configured = [p for p in providers if p.get("configured")]
        checks["llm_providers"] = {
            "status": "healthy" if configured else "degraded",
            "total_providers": len(providers),
            "configured_count": len(configured),
            "active_provider": settings.AI_PROVIDER,
            "configured_names": [p["name"] for p in configured],
        }
    except Exception as ex:
        checks["llm_providers"] = {"status": "error", "error": str(ex)}

    # 3. Rate limiter status
    if _rate_limiter_engine is not None:
        checks["rate_limiter"] = {
            "status": "enabled" if _rate_limiter_engine.enabled else "disabled",
            "active_buckets": len(_rate_limiter_engine._buckets),
            "groups_configured": len(_rate_limiter_engine.rules),
        }
    else:
        checks["rate_limiter"] = {"status": "not_initialized"}

    # Overall status
    unhealthy = any(
        v.get("status") in {"unhealthy", "error"} for v in checks.values() if isinstance(v, dict)
    )
    overall = "degraded" if unhealthy else "healthy"

    return {
        "status": overall,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "checks": checks,
    }
