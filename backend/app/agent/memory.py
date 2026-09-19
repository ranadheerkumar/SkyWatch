"""Agent working memory and context management.

Maintains the agent's execution context with sliding window management
to stay within LLM token limits. Provides short-term memory (recent tool
calls/observations) and integration with the existing ChromaDB vector
store for long-term memory.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agent.types import AgentPlan, Observation, ToolCallResult

logger = logging.getLogger("ai-qa-engine.agent.memory")

# Approximate token estimation: ~4 chars per token for English text
CHARS_PER_TOKEN = 4
DEFAULT_MAX_CONTEXT_TOKENS = 24_000  # Conservative limit for most models
SUMMARY_THRESHOLD_TOKENS = 18_000   # Start summarizing when context exceeds this


@dataclass
class WorkingMemory:
    """Short-term working memory for agent execution.

    Maintains a sliding window of recent observations, tool results,
    and decisions. Automatically compresses older entries when approaching
    the token budget.
    """

    objective: str = ""
    plan: AgentPlan | None = None
    observations: list[Observation] = field(default_factory=list)
    tool_results: list[ToolCallResult] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    application_context: dict[str, Any] = field(default_factory=dict)
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS

    # Compressed summaries of older context
    _compressed_history: str = ""

    def add_observation(self, content: str, source: str, **metadata: Any) -> None:
        """Record a new observation."""
        self.observations.append(Observation(content=content, source=source, metadata=metadata))

    def add_tool_result(self, result: ToolCallResult) -> None:
        """Record a tool execution result."""
        self.tool_results.append(result)

    def add_decision(self, decision: str) -> None:
        """Record an agent decision."""
        self.decisions.append(decision)

    def add_artifact(self, artifact: dict[str, Any]) -> None:
        """Record a generated artifact."""
        self.artifacts.append(artifact)

    def estimated_tokens(self) -> int:
        """Estimate the current context size in tokens."""
        total_chars = len(self.objective)
        if self.plan:
            total_chars += len(json.dumps(self.plan.to_dict()))
        total_chars += sum(len(o.content) for o in self.observations)
        total_chars += sum(len(r.summary()) for r in self.tool_results)
        total_chars += sum(len(d) for d in self.decisions)
        total_chars += len(self._compressed_history)
        total_chars += len(json.dumps(self.application_context)) if self.application_context else 0
        return total_chars // CHARS_PER_TOKEN

    def needs_compression(self) -> bool:
        """Check if the context needs to be compressed."""
        return self.estimated_tokens() > SUMMARY_THRESHOLD_TOKENS

    def compress(self) -> None:
        """Compress older observations and tool results into a summary.

        Keeps the most recent items in full detail while summarizing
        older entries into a compact history block.
        """
        if not self.needs_compression():
            return

        # Keep the last 5 observations and tool results in full
        keep_recent = 5

        if len(self.observations) > keep_recent:
            old_observations = self.observations[:-keep_recent]
            self.observations = self.observations[-keep_recent:]
            summary_lines = [f"[Previous observation from {o.source}]: {o.content[:150]}" for o in old_observations[-10:]]
            self._compressed_history += "\n--- Compressed History ---\n" + "\n".join(summary_lines)

        if len(self.tool_results) > keep_recent:
            old_results = self.tool_results[:-keep_recent]
            self.tool_results = self.tool_results[-keep_recent:]
            summary_lines = [r.summary(max_length=150) for r in old_results[-10:]]
            self._compressed_history += "\n" + "\n".join(summary_lines)

        if len(self.decisions) > 10:
            old_decisions = self.decisions[:-10]
            self.decisions = self.decisions[-10:]
            self._compressed_history += "\n[Previous decisions]: " + "; ".join(old_decisions[-5:])

        # Cap compressed history itself
        if len(self._compressed_history) > 8000:
            self._compressed_history = self._compressed_history[-6000:]

        logger.debug(
            "Memory compressed: %d observations, %d tool results, ~%d tokens",
            len(self.observations),
            len(self.tool_results),
            self.estimated_tokens(),
        )

    def build_context_messages(self) -> list[dict[str, str]]:
        """Build the context messages for the LLM, with automatic compression.

        Returns a list of chat messages representing the agent's current
        working memory, suitable for inclusion in an LLM completion request.
        """
        if self.needs_compression():
            self.compress()

        parts: list[str] = []

        # Objective
        parts.append(f"## Objective\n{self.objective}")

        # Plan
        if self.plan:
            plan_text = json.dumps(self.plan.to_dict(), indent=2)
            if len(plan_text) > 3000:
                # Compact plan representation
                step_lines = []
                for s in self.plan.steps:
                    step_lines.append(f"  [{s.status.value}] {s.goal}")
                plan_text = "Plan steps:\n" + "\n".join(step_lines)
            parts.append(f"## Current Plan\n{plan_text}")

        # Application context (compact)
        if self.application_context:
            ctx_text = json.dumps(self.application_context, indent=1)
            if len(ctx_text) > 2000:
                ctx_text = ctx_text[:2000] + "...(truncated)"
            parts.append(f"## Application Context\n{ctx_text}")

        # Compressed history
        if self._compressed_history:
            parts.append(f"## Previous History (compressed)\n{self._compressed_history[-3000:]}")

        # Recent observations
        if self.observations:
            obs_lines = [f"- [{o.source}] {o.content[:300]}" for o in self.observations[-8:]]
            parts.append(f"## Recent Observations\n" + "\n".join(obs_lines))

        # Recent tool results
        if self.tool_results:
            result_lines = [r.summary(max_length=300) for r in self.tool_results[-6:]]
            parts.append(f"## Recent Tool Results\n" + "\n".join(result_lines))

        # Recent decisions
        if self.decisions:
            decision_lines = [f"- {d[:200]}" for d in self.decisions[-6:]]
            parts.append(f"## Recent Decisions\n" + "\n".join(decision_lines))

        # Artifacts summary
        if self.artifacts:
            artifact_lines = [f"- {a.get('type', 'artifact')}: {a.get('description', '')[:100]}" for a in self.artifacts[-10:]]
            parts.append(f"## Generated Artifacts ({len(self.artifacts)} total)\n" + "\n".join(artifact_lines))

        return [{"role": "user", "content": "\n\n".join(parts)}]
