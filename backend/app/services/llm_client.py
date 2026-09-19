"""Unified LLM client with provider abstraction, token tracking, and structured output.

Wraps the existing multi-provider httpx-based integration from ai_service.py into
a clean, reusable client that supports function calling for the agent runtime.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import log_event

logger = logging.getLogger("ai-qa-engine.llm_client")


class LLMClientError(RuntimeError):
    """Raised when an LLM request fails after retries."""
    pass


@dataclass(frozen=True)
class LLMProviderConfig:
    """Configuration for a single LLM provider."""
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: int = 60
    max_tokens: int = 4096
    temperature: float = 0.2


@dataclass
class LLMUsage:
    """Token usage tracking for a single request."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    content: str = ""
    parsed_json: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    provider: str = ""
    model: str = ""
    duration_ms: float = 0.0
    finish_reason: str = ""


def get_all_provider_statuses() -> list[dict[str, Any]]:
    """Inspect and return the availability and configuration status of all supported LLM providers."""
    copilot_token = os.getenv("GITHUB_TOKEN") or os.getenv("COPILOT_API_KEY") or os.getenv("GH_TOKEN") or ""
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or getattr(settings, "GEMINI_API_KEY", "") or ""
    openai_key = os.getenv("OPENAI_API_KEY") or ""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or ""
    azure_key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_API_KEY") or ""

    return [
        {
            "provider": "gemini",
            "name": "Google Gemini",
            "configured": bool(gemini_key),
            "default_model": os.getenv("GEMINI_MODEL", getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")),
            "models": ["gemini-2.0-flash", "gemini-2.5-pro", "gemini-1.5-pro", "gemini-1.5-flash"],
            "endpoint": os.getenv("GEMINI_BASE_URL", getattr(settings, "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")),
        },
        {
            "provider": "github_copilot",
            "name": "GitHub Copilot",
            "configured": bool(copilot_token),
            "default_model": os.getenv("COPILOT_MODEL", "gpt-4o"),
            "models": ["gpt-4o", "gpt-4o-mini", "claude-3.5-sonnet", "o3-mini"],
            "endpoint": "https://api.githubcopilot.com",
        },
        {
            "provider": "openai",
            "name": "OpenAI",
            "configured": bool(openai_key),
            "default_model": os.getenv("OPENAI_MODEL", "gpt-4o"),
            "models": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
            "endpoint": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        },
        {
            "provider": "anthropic",
            "name": "Anthropic Claude",
            "configured": bool(anthropic_key),
            "default_model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
            "endpoint": "https://api.anthropic.com/v1",
        },
        {
            "provider": "azure_openai",
            "name": "Azure OpenAI",
            "configured": bool(azure_key),
            "default_model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            "models": ["gpt-4o", "gpt-4o-mini"],
            "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        },
        {
            "provider": "local",
            "name": "Local / Ollama",
            "configured": True,
            "default_model": os.getenv("LOCAL_MODEL", "llama3.2"),
            "models": ["llama3.2", "mistral", "deepseek-coder"],
            "endpoint": os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"),
        },
    ]


def _resolve_provider_config(
    override_provider: str | None = None,
    override_model: str | None = None,
) -> LLMProviderConfig:
    """Resolve LLM provider configuration from settings, availability, and optional overrides."""
    provider = (override_provider or settings.AI_PROVIDER).strip().lower()
    model = (override_model or settings.AI_MODEL).strip()
    api_key = settings.AI_API_KEY
    base_url = settings.AI_ENDPOINT

    copilot_token = os.getenv("GITHUB_TOKEN") or os.getenv("COPILOT_API_KEY") or os.getenv("GH_TOKEN") or ""
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or getattr(settings, "GEMINI_API_KEY", "") or ""
    openai_key = os.getenv("OPENAI_API_KEY") or ""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or ""

    # Dynamic auto-detection if "auto" or if primary configured provider has no credentials
    if provider in {"auto", "dynamic", "all"}:
        if gemini_key:
            provider = "gemini"
        elif copilot_token:
            provider = "github_copilot"
        elif openai_key:
            provider = "openai"
        elif anthropic_key:
            provider = "anthropic"
        else:
            provider = "local"

    # Specific Provider Defaults
    if provider in {"gemini", "google"}:
        base_url = os.getenv(
            "GEMINI_BASE_URL",
            getattr(settings, "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        )
        api_key = gemini_key or api_key
        if not model or model in {"gpt-4o", "gpt-4.1"}:
            model = os.getenv("GEMINI_MODEL", getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"))

    elif provider in {"github_copilot", "copilot", "github", "github_models"}:
        if not base_url or "openai.com" in base_url or "googleapis.com" in base_url:
            base_url = os.getenv(
                "GITHUB_COPILOT_BASE_URL",
                os.getenv("COPILOT_BASE_URL", "https://api.githubcopilot.com"),
            )
        if not model or model == "gpt-4.1":
            model = os.getenv("GITHUB_COPILOT_MODEL", os.getenv("COPILOT_MODEL", "gpt-4o"))
        api_key = copilot_token or api_key

    elif provider == "openai":
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        api_key = openai_key or api_key
        if not model:
            model = "gpt-4o"

    elif provider in {"anthropic", "claude"}:
        base_url = "https://api.anthropic.com/v1"
        api_key = anthropic_key or api_key
        if not model:
            model = "claude-3-5-sonnet-20241022"

    elif provider in {"local", "ollama", "vllm", "custom"}:
        provider = "local"
        base_url = os.getenv(
            "LOCAL_LLM_URL",
            os.getenv("OLLAMA_BASE_URL", getattr(settings, "AI_ENDPOINT", "http://127.0.0.1:11434/v1")),
        )
        if not model or model in {"gpt-4o", "gpt-4.1"}:
            model = os.getenv("LOCAL_MODEL", "llama3.2")
        api_key = api_key or "local-key"

    return LLMProviderConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        timeout_seconds=settings.AI_TIMEOUT_SECONDS,
        max_tokens=settings.AI_MAX_TOKENS,
        temperature=settings.AI_TEMPERATURE,
    )


def _build_headers(config: LLMProviderConfig) -> dict[str, str]:
    """Build HTTP headers for the configured provider."""
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        if config.provider == "anthropic":
            headers["x-api-key"] = config.api_key
            headers["anthropic-version"] = "2023-06-01"
        elif config.provider in {"azure_openai", "azure"}:
            headers["api-key"] = config.api_key
            headers["Authorization"] = f"Bearer {config.api_key}"
        elif config.provider in {"github_copilot", "copilot", "github", "github_models"}:
            headers["Authorization"] = f"Bearer {config.api_key}"
            headers["Editor-Version"] = "vscode/1.95.0"
            headers["User-Agent"] = "GitHubCopilot/1.0"
            headers["Copilot-Integration-Id"] = "vscode-chat"
        elif config.provider in {"gemini", "google"}:
            headers["Authorization"] = f"Bearer {config.api_key}"
            headers["User-Agent"] = "SkyWatch-Gemini/2.0"
        else:
            headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def _extract_json_from_text(text: str) -> str:
    """Extract JSON from LLM response text, handling markdown code fences."""
    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", stripped, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped
    brace_start = stripped.find("{")
    bracket_start = stripped.find("[")
    if brace_start >= 0 and (bracket_start < 0 or brace_start < bracket_start):
        return stripped[brace_start:]
    if bracket_start >= 0:
        return stripped[bracket_start:]
    return stripped


class LLMClient:
    """Unified LLM client supporting chat completions and function calling.

    Wraps the existing multi-provider httpx-based integration with:
    - Token tracking per request and cumulative
    - Function calling / tool use support
    - Retry with exponential backoff
    - Structured JSON response parsing
    - Provider abstraction
    """

    def __init__(self, config: LLMProviderConfig | None = None) -> None:
        self.config = config or _resolve_provider_config()
        self._cumulative_usage = LLMUsage()
        self._client: httpx.AsyncClient | None = None

    @property
    def cumulative_usage(self) -> LLMUsage:
        return self._cumulative_usage

    async def get_http_client(self, timeout_seconds: int | None = None) -> httpx.AsyncClient:
        """Get or initialize a pooled reusable HTTP client with connection pooling."""
        effective_timeout = float(timeout_seconds or self.config.timeout_seconds)
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=effective_timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def aclose(self) -> None:
        """Close the reusable HTTP client session."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_seconds: int | None = None,
        max_retries: int = 2,
    ) -> LLMResponse:
        """Send a chat completion request to the LLM provider.

        Args:
            messages: Chat messages (system, user, assistant, tool roles).
            tools: Optional OpenAI function-calling tool schemas.
            response_format: Optional response format (e.g., {"type": "json_object"}).
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            timeout_seconds: Override default timeout.
            max_retries: Number of retries on transient failures.

        Returns:
            LLMResponse with content, parsed JSON, tool calls, and usage metrics.
        """
        payload: dict[str, Any] = {
            "model": self.config.model,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if response_format and self.config.provider in {"openai", "azure_openai", "github_copilot", "github_models", "local"}:
            payload["response_format"] = response_format

        headers = _build_headers(self.config)
        endpoint = f"{self.config.base_url}/chat/completions"
        effective_timeout = timeout_seconds or self.config.timeout_seconds

        start_time = time.perf_counter()
        log_event(
            logger,
            "llm_request_started",
            provider=self.config.provider,
            model=self.config.model,
            message_count=len(messages),
            has_tools=bool(tools),
        )

        response = await self._post_with_retry(
            endpoint, headers, payload, effective_timeout, max_retries
        )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        parsed = self._parse_response(response, duration_ms)
        log_event(
            logger,
            "llm_request_completed",
            provider=self.config.provider,
            model=self.config.model,
            duration_ms=duration_ms,
            prompt_tokens=parsed.usage.prompt_tokens,
            completion_tokens=parsed.usage.completion_tokens,
            total_tokens=parsed.usage.total_tokens,
        )
        return parsed

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Convenience method: send a prompt and get parsed JSON back."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await self.complete(
            messages,
            response_format={"type": "json_object"},
            **kwargs,
        )
        if response.parsed_json is not None:
            return response.parsed_json
        # Attempt to parse content as JSON
        try:
            return json.loads(_extract_json_from_text(response.content))
        except (json.JSONDecodeError, ValueError) as error:
            raise LLMClientError(f"LLM response is not valid JSON: {error}") from error

    async def complete_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a completion request with tool schemas for function calling."""
        return await self.complete(messages, tools=tools, **kwargs)

    async def _post_with_retry(
        self,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: int,
        max_retries: int,
    ) -> httpx.Response:
        """POST with retry on transient failures and rate limits."""
        is_gemini = self.config.provider in {"gemini", "google"}
        effective_retries = max(max_retries, 4) if is_gemini else max_retries

        current_payload = payload
        for attempt in range(effective_retries + 1):
            try:
                client = await self.get_http_client(timeout_seconds)
                response = await client.post(endpoint, headers=headers, json=current_payload)
            except httpx.HTTPError as error:
                if attempt < effective_retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise LLMClientError(
                    f"LLM provider {self.config.provider} request failed: {error}"
                ) from error

            # Handle response_format incompatibility
            if response.status_code == 400 and "response_format" in response.text:
                if "response_format" in current_payload:
                    current_payload = {k: v for k, v in current_payload.items() if k != "response_format"}
                    continue

            # Rate limiting with Gemini-aware progressive backoff
            if response.status_code == 429:
                if attempt < effective_retries:
                    if is_gemini:
                        retry_after = min(5.0 * (attempt + 1), 30.0)
                    else:
                        retry_after = min(float(response.headers.get("retry-after", "2")), 10.0)
                    logger.warning("LLM rate limited (%s:%s), retrying in %.1fs (attempt %d/%d)",
                                   self.config.provider, self.config.model, retry_after, attempt + 1, effective_retries)
                    await asyncio.sleep(retry_after)
                    continue
                if is_gemini:
                    raise LLMClientError(
                        f"Gemini API rate limit exceeded for model '{self.config.model}'. "
                        "The free tier allows ~20 requests/minute. "
                        "Wait 60 seconds and retry, upgrade at https://ai.google.dev/pricing, "
                        "or switch to 'Local / Ollama' for unlimited generation."
                    )
                raise LLMClientError(f"LLM provider rate limited after {effective_retries} retries")

            # Server errors
            if response.status_code in {500, 502, 503, 504} and attempt < effective_retries:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue

            if response.status_code >= 400:
                error_body = response.text[:500]
                raise LLMClientError(
                    f"LLM provider {self.config.provider}:{self.config.model} "
                    f"returned HTTP {response.status_code}: {error_body}"
                )

            return response

        raise LLMClientError("LLM provider exceeded retry attempts")


    def _parse_response(self, response: httpx.Response, duration_ms: float) -> LLMResponse:
        """Parse the HTTP response into a structured LLMResponse."""
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as error:
            raise LLMClientError(f"Invalid JSON response from LLM: {error}") from error

        # Extract usage
        usage_data = data.get("usage") or {}
        usage = LLMUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        self._cumulative_usage.prompt_tokens += usage.prompt_tokens
        self._cumulative_usage.completion_tokens += usage.completion_tokens
        self._cumulative_usage.total_tokens += usage.total_tokens

        # Extract choice
        choices = data.get("choices", [])
        if not choices:
            raise LLMClientError("LLM response contains no choices")

        choice = choices[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        # Extract content
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))

        # Extract tool calls
        tool_calls = []
        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            try:
                args = json.loads(func.get("arguments", "{}"))
            except (json.JSONDecodeError, ValueError):
                args = {}
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "arguments": args,
            })

        # Try to parse content as JSON
        parsed_json = None
        if content and not tool_calls:
            try:
                parsed_json = json.loads(_extract_json_from_text(content))
                if not isinstance(parsed_json, dict):
                    parsed_json = None
            except (json.JSONDecodeError, ValueError):
                pass

        log_event(
            logger,
            "llm_response_received",
            provider=self.config.provider,
            model=self.config.model,
            duration_ms=duration_ms,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            tool_call_count=len(tool_calls),
            finish_reason=finish_reason,
        )

        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            tool_calls=tool_calls,
            usage=usage,
            provider=self.config.provider,
            model=self.config.model,
            duration_ms=duration_ms,
            finish_reason=finish_reason,
        )


def create_llm_client(
    override_provider: str | None = None,
    override_model: str | None = None,
) -> LLMClient:
    """Factory to create an LLM client with the current configuration."""
    config = _resolve_provider_config(
        override_provider=override_provider,
        override_model=override_model,
    )
    return LLMClient(config)
