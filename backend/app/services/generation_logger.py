"""Structured contextual logger for AI generation jobs.

Features:
- Captures granular lifecycle events for AI test case generation.
- Records document intake, target DOM exploration, planner blueprints,
  LLM calls, token usage, progressive backoff retries, and validation.
- Streams to:
  1. Active in-memory buffer for real-time live log polling.
  2. Persistent database records in `AIGenerationJob.result['logs']`.
  3. Persistent rotating file `backend/logs/ai_generation.log`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import threading
from typing import Any


ai_file_logger = logging.getLogger("skywatch.ai_generation")

# Active logger registry for live real-time log polling
_active_loggers: dict[str, GenerationLogger] = {}
_registry_lock = threading.Lock()


def get_active_generation_logger(job_id: str) -> GenerationLogger | None:
    with _registry_lock:
        return _active_loggers.get(job_id)


def register_generation_logger(job_id: str, logger: GenerationLogger) -> None:
    with _registry_lock:
        _active_loggers[job_id] = logger


def unregister_generation_logger(job_id: str) -> None:
    with _registry_lock:
        _active_loggers.pop(job_id, None)


class GenerationLogEntry:
    def __init__(
        self,
        job_id: str,
        stage: str,
        level: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ):
        self.job_id = job_id
        self.stage = stage
        self.level = level.upper()
        self.message = message
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc).timestamp()
        self.iso_time = datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "stage": self.stage,
            "level": self.level,
            "message": self.message,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "iso_time": self.iso_time,
        }


class GenerationLogger:
    """Manages logs for an active or completed AIGenerationJob execution."""

    def __init__(self, job_id: str, db=None, correlation_id: str = ""):
        self.job_id = job_id
        self.db = db
        self.correlation_id = correlation_id
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self.current_stage = "queued"
        register_generation_logger(job_id, self)

    def set_stage(self, stage: str) -> None:
        self.current_stage = stage

    def log(
        self,
        level: str,
        message: str,
        stage: str | None = None,
        **metadata: Any,
    ) -> dict[str, Any]:
        st = stage or self.current_stage
        entry = GenerationLogEntry(
            job_id=self.job_id,
            stage=st,
            level=level,
            message=message,
            metadata=metadata if metadata else None,
        )
        entry_dict = entry.to_dict()

        with self._lock:
            self._entries.append(entry_dict)

        # Emit to backend/logs/ai_generation.log
        log_msg = f"[job={self.job_id}] [{st}] {message}"
        lvl = level.upper()
        if lvl == "ERROR":
            ai_file_logger.error(log_msg, extra={"correlation_id": self.correlation_id})
        elif lvl in ("WARN", "WARNING"):
            ai_file_logger.warning(log_msg, extra={"correlation_id": self.correlation_id})
        else:
            ai_file_logger.info(log_msg, extra={"correlation_id": self.correlation_id})

        return entry_dict

    def info(self, message: str, stage: str | None = None, **metadata: Any) -> dict[str, Any]:
        return self.log("INFO", message, stage=stage, **metadata)

    def warn(self, message: str, stage: str | None = None, **metadata: Any) -> dict[str, Any]:
        return self.log("WARN", message, stage=stage, **metadata)

    def error(self, message: str, stage: str | None = None, **metadata: Any) -> dict[str, Any]:
        return self.log("ERROR", message, stage=stage, **metadata)

    def step(self, message: str, stage: str | None = None, **metadata: Any) -> dict[str, Any]:
        return self.log("STEP", message, stage=stage, **metadata)

    def llm(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        tokens: int | None = None,
        latency_ms: float | None = None,
        stage: str | None = None,
        **metadata: Any,
    ) -> dict[str, Any]:
        meta = {**metadata}
        if provider:
            meta["provider"] = provider
        if model:
            meta["model"] = model
        if tokens is not None:
            meta["tokens"] = tokens
        if latency_ms is not None:
            meta["latency_ms"] = latency_ms
        return self.log("LLM", message, stage=stage, **meta)

    def get_entries(self, level: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._entries)
        if level:
            target = level.upper()
            if target != "ALL":
                entries = [e for e in entries if e["level"] == target]
        return entries

    def to_text(self, level: str | None = None) -> str:
        entries = self.get_entries(level=level)
        lines = []
        for e in entries:
            dt = datetime.fromtimestamp(e["timestamp"], tz=timezone.utc).strftime("%H:%M:%S")
            meta = f" | {e['metadata']}" if e.get("metadata") else ""
            lines.append(f"[{dt}] [{e['level']}] [{e['stage']}] {e['message']}{meta}")
        return "\n".join(lines)

    def flush_to_job(self, job) -> None:
        """Persists in-memory logs into job.result['logs']."""
        if not job:
            return
        with self._lock:
            entries_copy = list(self._entries)
        current_res = job.result or {}
        job.result = {**current_res, "logs": entries_copy}
        if self.db:
            try:
                self.db.commit()
            except Exception as e:
                ai_file_logger.warning("Failed to commit generation logs for job %s: %s", self.job_id, e)

    def close(self, job=None) -> None:
        """Final flush and cleanup from active registry."""
        if job:
            self.flush_to_job(job)
        unregister_generation_logger(self.job_id)
