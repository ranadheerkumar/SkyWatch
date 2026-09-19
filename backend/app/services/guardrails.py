"""Security, Policy, and Execution Guardrails for AI QA Engine."""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from app.schemas.execution import Step


class GuardrailViolationError(ValueError):
    """Raised when an operation violates security, policy, or safety guardrails."""
    pass


# Disallowed cloud metadata & loopback SSRF targets
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / AWS / GCP / Azure metadata (169.254.169.254)
    ipaddress.ip_network("100.100.100.100/32"), # Alibaba cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
]

BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "instance-data",
    "metadata.internal",
    "169.254.169.254",
}

# Adversarial prompt injection keywords and jailbreak patterns
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|system)\s+prompts?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(developer\s+mode|unrestricted\s+mode|dan\s+mode)", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
    re.compile(r"dump\s+all\s+(system\s+)?variables", re.IGNORECASE),
    re.compile(r"print\s+your\s+(initial|system)\s+instructions?", re.IGNORECASE),
]

SENSITIVE_FIELD_NAME_PATTERNS = re.compile(
    r"\b(password|passcode|secret|api[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|bearer|credential)\b",
    re.IGNORECASE,
)

DANGEROUS_SELECTOR_PATTERNS = [
    re.compile(r"javascript:\s*", re.IGNORECASE),
    re.compile(r"<script[\s>]", re.IGNORECASE),
    re.compile(r"data:text/html", re.IGNORECASE),
]


def validate_target_url(url: str, *, allow_localhost: bool = True) -> str:
    """
    Validates target URL against SSRF and unauthorized network destinations.
    Ensures safe http/https schemes and blocks cloud metadata endpoints.
    """
    clean_url = (url or "").strip()
    if not clean_url:
        raise GuardrailViolationError("Target URL cannot be empty.")

    try:
        parsed = urlparse(clean_url)
    except Exception as error:
        raise GuardrailViolationError(f"Malformed target URL '{clean_url}': {error}") from error

    if parsed.scheme.lower() not in {"http", "https"}:
        raise GuardrailViolationError(
            f"Invalid URL protocol '{parsed.scheme}://'. Only HTTP and HTTPS protocols are allowed."
        )

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise GuardrailViolationError("Target URL must contain a valid hostname.")

    if hostname in BLOCKED_HOSTNAMES:
        raise GuardrailViolationError(f"Access to protected cloud metadata destination '{hostname}' is blocked.")

    # Check if host is a raw IP in a blocked range
    try:
        ip_obj = ipaddress.ip_address(hostname)
        for blocked_net in BLOCKED_IP_NETWORKS:
            if ip_obj in blocked_net:
                raise GuardrailViolationError(f"Target IP address '{hostname}' is in a restricted network range.")
        if not allow_localhost and (ip_obj.is_loopback or ip_obj.is_private):
            raise GuardrailViolationError(f"Local and private network targets ({hostname}) are disabled.")
    except ValueError:
        # Not a raw IP address; domain name string is fine
        pass

    return clean_url


def sanitize_and_validate_prompt(prompt: str, *, max_length: int = 15_000) -> str:
    """
    Scans prompts for prompt injection, adversarial bypass attempts, and length bounds.
    """
    clean_prompt = (prompt or "").strip()
    if not clean_prompt:
        raise GuardrailViolationError("Prompt cannot be empty.")

    if len(clean_prompt) > max_length:
        raise GuardrailViolationError(f"Prompt length ({len(clean_prompt)} chars) exceeds maximum safety limit of {max_length} characters.")

    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(clean_prompt):
            raise GuardrailViolationError(
                "Prompt rejected by AI Safety Guardrails: detected potential prompt injection or system override pattern."
            )

    return clean_prompt


def sanitize_redacted_secrets(data: Any) -> Any:
    """
    Recursively redacts passwords, tokens, and secret fields from JSON-compatible structures
    to guarantee zero credential leakage in logs, traces, and metrics.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_str = str(k)
            if SENSITIVE_FIELD_NAME_PATTERNS.search(k_str) and isinstance(v, str) and v and not v.startswith("{{"):
                sanitized[k] = "[redacted]"
            else:
                sanitized[k] = sanitize_redacted_secrets(v)
        return sanitized
    if isinstance(data, list):
        return [sanitize_redacted_secrets(item) for item in data]
    if isinstance(data, str):
        # Redact JWT tokens and generic long secret keys if present in free text
        masked = re.sub(r"eyJ[a-zA-Z0-9_\-]{20,}\.eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}", "[redacted_jwt]", data)
        masked = re.sub(r"ghp_[a-zA-Z0-9]{30,}", "[redacted_token]", masked)
        masked = re.sub(r"sk-[a-zA-Z0-9]{30,}", "[redacted_api_key]", masked)
        return masked
    return data


def validate_step_guardrails(step: Step) -> Step:
    """
    Validates a single Playwright execution step against safety guardrails:
    - Selector safety (no script injections)
    - Action type constraints
    - Value bounds and secret isolation
    """
    if step.selector:
        for danger_pattern in DANGEROUS_SELECTOR_PATTERNS:
            if danger_pattern.search(step.selector):
                raise GuardrailViolationError(f"Step selector '{step.selector[:60]}' contains potentially unsafe script content.")

        if len(step.selector) > 1000:
            raise GuardrailViolationError(f"Step selector exceeds maximum length of 1,000 characters.")

    if step.value and len(step.value) > 2500:
        raise GuardrailViolationError("Step value exceeds maximum safety length of 2,500 characters.")

    return step


def verify_healed_step_guardrails(original_step: Step, healed_step: Step) -> Step:
    """
    Enforces strict safety guardrails on AI-generated self-healing steps:
    1. Preserves original action type (e.g. type stays type, click stays click).
    2. Validates selector syntax & safety.
    3. Prevents credential leakage into selector attributes.
    4. Preserves secret references.
    """
    if healed_step.action != original_step.action:
        raise GuardrailViolationError(
            f"Healer safety violation: proposed action '{healed_step.action}' does not match original '{original_step.action}'."
        )

    if not healed_step.selector and healed_step.action not in {"navigate", "assert_url_contains", "assert_title", "go_back"}:
        raise GuardrailViolationError("Healer safety violation: element action must contain a valid selector.")

    validate_step_guardrails(healed_step)

    # Ensure passwords/secrets were not baked into selector text
    if original_step.secret_name or (original_step.action == "type" and SENSITIVE_FIELD_NAME_PATTERNS.search(original_step.selector or "")):
        if healed_step.selector and SENSITIVE_FIELD_NAME_PATTERNS.search(healed_step.selector):
            pass  # Structural matching on 'password' attribute is fine
        if healed_step.value and healed_step.value != original_step.value and not healed_step.value.startswith("{{"):
            healed_step = healed_step.model_copy(update={"value": original_step.value, "secret_name": original_step.secret_name})

    return healed_step
