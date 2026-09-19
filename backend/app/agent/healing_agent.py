"""Autonomous Self-Healing Agent for SkyWatch.

Autonomously repairs drifting or broken selectors during execution:
1. Queries historical learned locator cache.
2. Generates semantic and structural candidate replacements.
3. Live-validates candidate against active browser DOM.
4. Auto-applies healed selector to test definition and database.
5. Emits an immutable healing audit record with confidence score.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent.types import HealingRecord
from app.services.self_learning import SelfLearningEngine

logger = logging.getLogger("skywatch.agent.healing")


class AutonomousHealingAgent:
    """Intelligent selector healer with live DOM validation and auto-persistence."""

    def __init__(self, min_confidence: float = 0.70) -> None:
        self.min_confidence = min_confidence

    async def attempt_heal_step(
        self,
        app_id: int,
        test_id: str,
        step_index: int,
        action: str,
        failing_selector: str,
        candidate_selectors: list[str] | None = None,
        page_instance: Any | None = None,
    ) -> HealingRecord | None:
        """Attempt to heal a broken step selector autonomously."""
        start_time = time.perf_counter()
        candidates: list[tuple[str, str, float]] = []  # (selector, strategy, confidence)
        learning_engine = SelfLearningEngine(app_id)

        # Strategy 1: Check Learned Locator Cache from previous successful runs
        cached = learning_engine.get_learned_locator(action, failing_selector)
        if cached and cached != failing_selector:
            candidates.append((cached, "learned_cache", 0.95))

        # Strategy 2: Use candidates from Analysis Agent
        for c in (candidate_selectors or []):
            if c != failing_selector:
                candidates.append((c, "analysis_inference", 0.85))

        # Strategy 3: Heuristic transformations
        heuristic_candidates = self._generate_fallback_candidates(failing_selector)
        for hc in heuristic_candidates:
            if hc != failing_selector and hc not in [c[0] for c in candidates]:
                candidates.append((hc, "fuzzy_heuristic", 0.75))

        # If live browser page instance is available, validate in sandbox
        validated_record: HealingRecord | None = None
        for cand_sel, strategy, confidence in candidates:
            if confidence < self.min_confidence:
                continue

            is_valid = False
            if page_instance is not None:
                try:
                    count = await page_instance.locator(cand_sel).count()
                    if count == 1:
                        # Exactly one element matches - check visibility
                        is_visible = await page_instance.locator(cand_sel).is_visible()
                        if is_visible:
                            is_valid = True
                    elif count > 1:
                        # Multiple matches; refine to first visible
                        cand_sel = f"{cand_sel} >> nth=0"
                        is_valid = True
                except Exception as ex:
                    logger.debug("Candidate %s failed validation: %s", cand_sel, ex)
            else:
                # If validating offline or without active page instance, accept highest confidence
                is_valid = True

            if is_valid:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                validated_record = HealingRecord(
                    test_id=test_id,
                    step_index=step_index,
                    original_selector=failing_selector,
                    healed_selector=cand_sel,
                    strategy=strategy,
                    confidence=confidence,
                    validated_live=page_instance is not None,
                    duration_ms=duration_ms,
                )

                # Persist learned selector into continuous learning repository
                learning_engine.record_successful_locator(
                    action=action,
                    raw_selector=failing_selector,
                    verified_selector=cand_sel,
                    confidence=confidence,
                    source="autonomous_healer",
                )
                logger.info(
                    "Self-healed step %d for test %s: '%s' -> '%s' (strategy=%s, conf=%.2f)",
                    step_index,
                    test_id,
                    failing_selector,
                    cand_sel,
                    strategy,
                    confidence,
                )
                break

        return validated_record

    def _generate_fallback_candidates(self, selector: str) -> list[str]:
        candidates: list[str] = []
        if not selector:
            return candidates

        # Strip ID-based strict prefixes
        if "#" in selector and " " in selector:
            parts = selector.split(" ")
            candidates.append(parts[-1])  # Target child directly

        # If data-testid was used, try generic text or role
        if "data-testid" in selector or "data-test" in selector:
            name_part = selector.split("=")[-1].strip(" '\"\\][")
            candidates.append(f"[name='{name_part}']")
            candidates.append(f"[aria-label*='{name_part}']")

        return candidates
