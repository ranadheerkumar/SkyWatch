"""OpenTelemetry distributed tracing and observability instrumentation.

Provides unified trace context, span management, and metadata propagation
for AI provider calls, test execution cycles, and API endpoints.
Gracefully handles environments with or without the OpenTelemetry SDK.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import time
from typing import Any, Callable, Generator
from uuid import uuid4

logger = logging.getLogger("ai-qa-engine.telemetry")

_OTEL_AVAILABLE = False
_tracer = None

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    _tracer = trace.get_tracer("skywatch-qa-platform", "3.0.0")
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


class TraceSpan:
    """Lightweight span representation tracking execution duration and attributes."""

    def __init__(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.name = name
        self.span_id = uuid4().hex[:16]
        self.trace_id = uuid4().hex
        self.attributes: dict[str, Any] = attributes.copy() if attributes else {}
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.duration_ms: float = 0.0
        self.status: str = "unset"
        self.error: Exception | None = None
        self._otel_span: Any = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value
        if self._otel_span is not None:
            try:
                self._otel_span.set_attribute(key, str(value) if isinstance(value, (dict, list)) else value)
            except Exception:
                pass

    def record_exception(self, exception: Exception) -> None:
        self.error = exception
        self.status = "error"
        if self._otel_span is not None:
            try:
                self._otel_span.record_exception(exception)
                self._otel_span.set_status(Status(StatusCode.ERROR, str(exception)))
            except Exception:
                pass

    def set_status_ok(self) -> None:
        if self.status != "error":
            self.status = "ok"
            if self._otel_span is not None:
                try:
                    self._otel_span.set_status(Status(StatusCode.OK))
                except Exception:
                    pass


@contextlib.contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Generator[TraceSpan, None, None]:
    """Context manager for distributed tracing of synchronous or asynchronous operations."""
    span = TraceSpan(name=name, attributes=attributes)
    span.start_time = time.perf_counter()

    if _OTEL_AVAILABLE and _tracer is not None:
        try:
            span._otel_span = _tracer.start_span(name)
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, v)
        except Exception as err:
            logger.debug("OTel span init non-critical error: %s", err)

    try:
        yield span
        span.set_status_ok()
    except Exception as exc:
        span.record_exception(exc)
        raise
    finally:
        span.end_time = time.perf_counter()
        span.duration_ms = round((span.end_time - span.start_time) * 1000, 2)
        if span._otel_span is not None:
            try:
                span._otel_span.end()
            except Exception:
                pass
        logger.debug(
            "trace_span_completed name=%s duration_ms=%.2f status=%s",
            span.name,
            span.duration_ms,
            span.status,
        )


def traced(name: str | None = None, default_attributes: dict[str, Any] | None = None) -> Callable:
    """Decorator to trace async or synchronous functions."""

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__qualname__

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            attrs = (default_attributes or {}).copy()
            attrs["function"] = func.__name__
            with trace_span(span_name, attrs):
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            attrs = (default_attributes or {}).copy()
            attrs["function"] = func.__name__
            with trace_span(span_name, attrs):
                return func(*args, **kwargs)

        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
