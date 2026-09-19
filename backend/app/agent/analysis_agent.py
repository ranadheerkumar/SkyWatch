"""Autonomous Failure Analysis Agent for SkyWatch.

Autonomously classifies test execution failures into actionable root causes:
- Selector Drift (element moved, altered, or renamed)
- Regression Bug (application 500 error, crash, unhandled exception, visual bug)
- Environment Flake (network disconnect, gateway 504, timeout spike)
- Auth Failure (session expired, token revoked, 401/403 redirection)
- Timing / Race Condition (DOM element rendered after standard settle time)
- Assertion Failure (business rule expectation not met)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.types import FailureCategory, FailureDiagnosis
from app.services.llm_client import LLMClient

logger = logging.getLogger("skywatch.agent.analysis")


class AutonomousAnalysisAgent:
    """Intelligent failure classifier and root cause analyzer."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client

    async def diagnose_failure(
        self,
        action: str,
        selector: str | None,
        error_message: str,
        page_url: str | None = None,
        dom_snippet: str | None = None,
        status_code: int | None = None,
        duration_ms: float = 0.0,
    ) -> FailureDiagnosis:
        """Diagnose a test failure and produce a structured root-cause classification."""
        err_lower = (error_message or "").lower()
        url_lower = (page_url or "").lower()
        dom_lower = (dom_snippet or "").lower()

        # 1. Check for Authentication / Session Expiry
        if (
            status_code in {401, 403}
            or "unauthorized" in err_lower
            or "forbidden" in err_lower
            or any(auth_path in url_lower for auth_path in ["/login", "/signin", "/auth/login", "auth_required"])
            and not (selector and ("login" in selector.lower() or "signin" in selector.lower()))
        ):
            return FailureDiagnosis(
                category=FailureCategory.AUTH_FAILURE,
                confidence=0.92,
                root_cause="User session expired or unauthorized redirect occurred during execution.",
                suggested_fix="Re-authenticate session before executing downstream steps, or refresh authentication token.",
                evidence={"status_code": status_code, "current_url": page_url, "error": error_message},
            )

        # 2. Check for Infrastructure / Network Environment Flake
        if (
            status_code in {502, 503, 504}
            or "net::err_" in err_lower
            or "econnrefused" in err_lower
            or "gateway timeout" in err_lower
            or "connection reset" in err_lower
            or "dns_probe_finished" in err_lower
        ):
            return FailureDiagnosis(
                category=FailureCategory.ENVIRONMENT_FLAKE,
                confidence=0.95,
                root_cause="Network connection reset, gateway timeout, or backend service unavailable.",
                suggested_fix="Retry execution with exponential backoff; check target staging environment availability.",
                evidence={"status_code": status_code, "network_error": error_message},
            )

        # 3. Check for Application Crash / Regression Bug
        if (
            status_code == 500
            or "internal server error" in dom_lower
            or "something went wrong" in dom_lower
            or "uncaught exception" in err_lower
            or "crash" in err_lower
            or "stack trace" in dom_lower
            or "application error" in dom_lower
        ):
            return FailureDiagnosis(
                category=FailureCategory.REGRESSION_BUG,
                confidence=0.88,
                root_cause="Target application produced an unhandled 500 exception or crash banner in the UI.",
                suggested_fix="Log a defect in Jira/qTest with server stack trace and reproduction steps.",
                evidence={"status_code": status_code, "dom_signals": "Crash/error keywords found in DOM"},
            )

        # 4. Check for Assertion Failure
        if "assert" in action.lower() or "assertionerror" in err_lower or "expected text" in err_lower:
            return FailureDiagnosis(
                category=FailureCategory.ASSERTION_FAILURE,
                confidence=0.90,
                root_cause=f"Assertion condition failed on {selector}: {error_message[:200]}",
                suggested_fix="Verify business expectation or update test baseline if requirement changed.",
                evidence={"action": action, "selector": selector, "error": error_message},
            )

        # 5. Check for Timing / Rendering Latency
        if "timeout" in err_lower and duration_ms > 25000:
            return FailureDiagnosis(
                category=FailureCategory.TIMING_ISSUE,
                confidence=0.82,
                root_cause="Step timed out waiting for DOM element or network idle state.",
                suggested_fix="Increase step wait settle time or add explicit wait_for_selector before interacting.",
                evidence={"duration_ms": duration_ms, "error": error_message},
            )

        # 6. Check for Selector Drift (Locator not found or detached)
        if (
            "waiting for locator" in err_lower
            or "no element found" in err_lower
            or "not attached to the dom" in err_lower
            or "strict mode violation" in err_lower
            or (selector and "timeout" in err_lower)
        ):
            candidates = self._extract_candidate_selectors(selector, dom_snippet)
            return FailureDiagnosis(
                category=FailureCategory.SELECTOR_DRIFT,
                confidence=0.85,
                root_cause=f"Original selector '{selector}' failed to resolve or element structure drifted in DOM.",
                suggested_fix="Trigger autonomous self-healing to bind to alternative semantic locator.",
                evidence={"failed_selector": selector, "error": error_message},
                candidate_selectors=candidates,
            )

        # Default fallback
        return FailureDiagnosis(
            category=FailureCategory.UNKNOWN,
            confidence=0.50,
            root_cause=f"Unclassified failure: {error_message[:200]}",
            suggested_fix="Inspect full execution video and DOM trace.",
            evidence={"action": action, "selector": selector, "error": error_message},
        )

    def _extract_candidate_selectors(self, selector: str | None, dom_snippet: str | None) -> list[str]:
        """Heuristically derive candidate repair selectors from the failed selector and DOM."""
        candidates: list[str] = []
        if not selector:
            return candidates

        # If original was an ID with hash or prefix, try attribute contains
        id_match = re.search(r"#([a-zA-Z0-9_-]+)", selector)
        if id_match:
            raw_id = id_match.group(1)
            # Remove trailing numbers/hashes
            clean_stem = re.sub(r"[-_][0-9a-f]+$", "", raw_id)
            if clean_stem and clean_stem != raw_id:
                candidates.append(f"[id*='{clean_stem}']")
            candidates.append(f"[name='{raw_id}']")

        # If selector has text= or has-text
        text_match = re.search(r"text=['\"]?([^'\"]+)['\"]?", selector)
        if text_match:
            text_val = text_match.group(1)
            candidates.append(f"button:has-text('{text_val}')")
            candidates.append(f"a:has-text('{text_val}')")
            candidates.append(f"[aria-label='{text_val}']")

        # Extract potential testids or buttons from DOM snippet if present
        if dom_snippet:
            testids = re.findall(r'data-testid=["\']([^"\']+)["\']', dom_snippet)
            for tid in testids[:3]:
                candidates.append(f"[data-testid='{tid}']")

        return list(dict.fromkeys(candidates))
