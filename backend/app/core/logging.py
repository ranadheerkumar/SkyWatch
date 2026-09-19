"""Logging configuration and observability for SkyWatch.

Features:
- Correlation ID tracking across async request boundaries.
- Secret masking filter (API keys, bearer tokens, passwords).
- Rotating file handlers for application, AI generation, and error logs.
- In-memory thread-safe RingBuffer handler for live dashboard viewing.
"""

from __future__ import annotations

import collections
import contextvars
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import threading
from typing import Any


correlation_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id",
    default="",
)

# Common sensitive token patterns to redact
_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z-_]{20,}"),                                  # Google AI Studio / Gemini API Key
    re.compile(r"AQ\.[0-9A-Za-z-_]{20,}"),                                  # Google Gemini Alternate Key prefix
    re.compile(r"sk-[0-9A-Za-z-_]{16,}"),                                  # OpenAI / Anthropic secret key
    re.compile(r"ghp_[0-9A-Za-z-_]{20,}"),                                  # GitHub Personal Access Token
    re.compile(r"(Bearer\s+)[A-Za-z0-9\._\-]{20,}", re.IGNORECASE),         # Bearer tokens
    re.compile(r'("password"\s*:\s*")[^"]+(")', re.IGNORECASE),             # JSON password fields
    re.compile(r"(password=)[^&\s]+", re.IGNORECASE),                       # Query param or key=val password
]


class SecretMaskingFilter(logging.Filter):
    """Redacts sensitive credentials and tokens before they are emitted to logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.mask_secrets(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    self.mask_secrets(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: self.mask_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
        return True

    @classmethod
    def mask_secrets(cls, text: str) -> str:
        masked = text
        for pattern in _SECRET_PATTERNS:
            if pattern.pattern.startswith("(Bearer"):
                masked = pattern.sub(r"\g<1>***REDACTED***", masked)
            elif pattern.pattern.startswith('("password"'):
                masked = pattern.sub(r"\g<1>***REDACTED***\g<2>", masked)
            elif pattern.pattern.startswith("(password="):
                masked = pattern.sub(r"\g<1>***REDACTED***", masked)
            else:
                masked = pattern.sub("***REDACTED***", masked)
        return masked


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_context.get()
        return True


class RingBufferLogHandler(logging.Handler):
    """Thread-safe circular in-memory buffer holding recent log entries."""

    def __init__(self, capacity: int = 1000):
        super().__init__()
        self.capacity = capacity
        self._buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            iso_time = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
            entry = {
                "timestamp": record.created,
                "iso_time": iso_time,
                "level": record.levelname,
                "logger": record.name,
                "correlation_id": getattr(record, "correlation_id", "") or "",
                "message": msg,
            }
            with self._lock:
                self._buffer.append(entry)
        except Exception:
            self.handleError(record)

    def get_logs(
        self,
        limit: int = 100,
        level: str | None = None,
        search: str | None = None,
        since_timestamp: float | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._buffer)

        # Filter
        if since_timestamp is not None:
            entries = [e for e in entries if e["timestamp"] > since_timestamp]
        if level:
            target_level = level.upper()
            entries = [e for e in entries if e["level"] == target_level]
        if search:
            query = search.casefold()
            entries = [
                e for e in entries
                if query in e["message"].casefold() or query in e["logger"].casefold()
            ]

        # Return latest entries up to limit
        return entries[-limit:]


_global_ring_buffer: RingBufferLogHandler | None = None


def get_ring_buffer_handler() -> RingBufferLogHandler | None:
    return _global_ring_buffer


def get_recent_system_logs(
    limit: int = 100,
    level: str | None = None,
    search: str | None = None,
    since_timestamp: float | None = None,
) -> list[dict[str, Any]]:
    if _global_ring_buffer is not None:
        return _global_ring_buffer.get_logs(
            limit=limit,
            level=level,
            search=search,
            since_timestamp=since_timestamp,
        )
    return []


def configure_logging(log_dir: str | Path | None = None) -> None:
    """Configures console, rotating file, and in-memory ring buffer logging."""
    global _global_ring_buffer

    # Determine logs directory
    if log_dir is None:
        backend_dir = Path(__file__).resolve().parents[2]
        logs_path = backend_dir / "logs"
    else:
        logs_path = Path(log_dir)

    logs_path.mkdir(parents=True, exist_ok=True)

    log_format = "%(asctime)s %(levelname)s correlation_id=%(correlation_id)s %(name)s %(message)s"
    formatter = logging.Formatter(log_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    correlation_filter = CorrelationIdFilter()
    masking_filter = SecretMaskingFilter()

    # 1. Console Handler (stdout)
    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root_logger.handlers
    )
    if not has_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(correlation_filter)
        console_handler.addFilter(masking_filter)
        root_logger.addHandler(console_handler)

    # 2. Main Rotating File Handler (skywatch.log - 5MB, 5 backups)
    has_main_file = any(
        isinstance(h, RotatingFileHandler) and "skywatch.log" in getattr(h, "baseFilename", "")
        for h in root_logger.handlers
    )
    if not has_main_file:
        file_handler = RotatingFileHandler(
            str(logs_path / "skywatch.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(correlation_filter)
        file_handler.addFilter(masking_filter)
        root_logger.addHandler(file_handler)

    # 3. Error Log File Handler (errors.log - ERROR & CRITICAL only)
    has_error_file = any(
        isinstance(h, RotatingFileHandler) and "errors.log" in getattr(h, "baseFilename", "")
        for h in root_logger.handlers
    )
    if not has_error_file:
        error_file_handler = RotatingFileHandler(
            str(logs_path / "errors.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(formatter)
        error_file_handler.addFilter(correlation_filter)
        error_file_handler.addFilter(masking_filter)
        root_logger.addHandler(error_file_handler)

    # 4. Ring Buffer In-Memory Handler (capacity=1000)
    if _global_ring_buffer is None:
        _global_ring_buffer = RingBufferLogHandler(capacity=1000)
        _global_ring_buffer.setLevel(logging.INFO)
        _global_ring_buffer.setFormatter(formatter)
        _global_ring_buffer.addFilter(correlation_filter)
        _global_ring_buffer.addFilter(masking_filter)
        root_logger.addHandler(_global_ring_buffer)

    # 5. Dedicated AI Generation Logger & File Handler (ai_generation.log)
    ai_logger = logging.getLogger("skywatch.ai_generation")
    ai_logger.setLevel(logging.INFO)
    has_ai_file = any(
        isinstance(h, RotatingFileHandler) and "ai_generation.log" in getattr(h, "baseFilename", "")
        for h in ai_logger.handlers
    )
    if not has_ai_file:
        ai_file_handler = RotatingFileHandler(
            str(logs_path / "ai_generation.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        ai_file_handler.setLevel(logging.INFO)
        ai_file_handler.setFormatter(formatter)
        ai_file_handler.addFilter(correlation_filter)
        ai_file_handler.addFilter(masking_filter)
        ai_logger.addHandler(ai_file_handler)

    # Ensure existing handlers have filters
    for handler in root_logger.handlers:
        if not any(isinstance(f, CorrelationIdFilter) for f in handler.filters):
            handler.addFilter(correlation_filter)
        if not any(isinstance(f, SecretMaskingFilter) for f in handler.filters):
            handler.addFilter(masking_filter)


def set_correlation_id(value: str) -> contextvars.Token[str]:
    return correlation_id_context.set(value)


def get_correlation_id() -> str:
    return correlation_id_context.get()


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload = {"event": event, "correlation_id": get_correlation_id(), **fields}
    logger.info(json.dumps(payload, default=str, sort_keys=True))
