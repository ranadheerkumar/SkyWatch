from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AutomationQualityResult:
    confidence_score: int
    confidence_label: Literal["high", "medium", "low"]
    needs_manual_selector_review: bool
    reasons: list[str]


def evaluate_automation_quality(steps: list[dict] | None, checks: list[dict] | None) -> AutomationQualityResult:
    step_items = steps or []
    check_items = checks or []
    score = 100
    reasons: list[str] = []

    if not step_items:
        score -= 40
        reasons.append("No executable steps configured")

    if not check_items:
        score -= 15
        reasons.append("No validation checks configured")

    unstable_selector_count = 0
    stable_selector_count = 0
    missing_selector_count = 0
    assertion_steps = 0

    for step in step_items:
        action = str(step.get("action") or "").strip().lower()
        selector = str(step.get("selector") or "").strip()
        if action.startswith("assert_"):
            assertion_steps += 1

        if action in {"click", "type", "select", "check", "uncheck", "assert_visible", "assert_text"}:
            if not selector:
                missing_selector_count += 1
                score -= 10
                continue
            lowered_selector = selector.casefold()
            if lowered_selector.startswith("text=") or lowered_selector.startswith("*:has-text") or lowered_selector.startswith("xpath="):
                unstable_selector_count += 1
            if (
                lowered_selector.startswith("#")
                or lowered_selector.startswith("[data-testid")
                or lowered_selector.startswith("label=")
                or lowered_selector.startswith("role=")
                or lowered_selector.startswith("[name=")
            ):
                stable_selector_count += 1

    if missing_selector_count:
        reasons.append(f"{missing_selector_count} step(s) missing selectors")

    if unstable_selector_count:
        score -= min(30, unstable_selector_count * 6)
        reasons.append("Contains brittle text/xpath selectors")

    if not assertion_steps and not any(str(check.get("type") or "") in {"title_contains", "visible", "text_contains"} for check in check_items):
        score -= 15
        reasons.append("Limited assertion coverage")

    if stable_selector_count:
        score += min(8, stable_selector_count * 2)

    score = max(0, min(100, score))
    confidence_label = "high" if score >= 80 else "medium" if score >= 60 else "low"
    needs_manual_selector_review = (
        confidence_label != "high"
        or unstable_selector_count > 0
        or missing_selector_count > 0
    )

    if not reasons:
        reasons.append("Automation structure is stable")

    return AutomationQualityResult(
        confidence_score=score,
        confidence_label=confidence_label,
        needs_manual_selector_review=needs_manual_selector_review,
        reasons=reasons,
    )
