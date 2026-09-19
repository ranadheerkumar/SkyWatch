import os
import re
import time
from pathlib import Path
from typing import Any, Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import current_user, require_roles
from app.models.user import User
from app.services.ai_service import AIServiceError, get_ai_provider_metadata, test_ai_provider_connection

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_FILE_PATH = Path(__file__).resolve().parents[3] / ".env"

PROVIDER_KEY_NAMES: dict[str, tuple[str, ...]] = {
    "github_copilot": ("GITHUB_TOKEN", "COPILOT_API_KEY", "GITHUB_COPILOT_API_KEY", "GH_TOKEN"),
    "openai": ("OPENAI_API_KEY", "AI_OPENAI_API_KEY", "AI_QA_ENGINE_OPENAI_API_KEY", "AI_QA_ENGINE_API_KEY", "AI_API_KEY"),
    "azure_openai": ("AZURE_OPENAI_API_KEY", "AZURE_API_KEY", "OPENAI_API_KEY", "AI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "AI_API_KEY"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "AI_API_KEY"),
    "local": ("AI_API_KEY",),
}


def _provider_key(provider: str, explicit_key: str | None = None) -> str:
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    normalized_provider = provider.strip().lower()
    for key_name in PROVIDER_KEY_NAMES.get(normalized_provider, ()):
        value = os.getenv(key_name, "").strip()
        if value:
            return value
    return ""


def _provider_endpoint(provider: str) -> str:
    normalized_provider = provider.strip().lower()
    if normalized_provider in {"github_copilot", "copilot", "github", "github_models"}:
        return "https://api.githubcopilot.com"
    if normalized_provider == "gemini":
        return "https://generativelanguage.googleapis.com/v1beta/openai"
    if normalized_provider == "anthropic":
        return "https://api.anthropic.com/v1"
    if normalized_provider == "local":
        return "http://127.0.0.1:8080/v1"
    return "https://api.openai.com/v1"


def _update_env_file(key_values: dict[str, str]) -> None:
    """Safely updates or appends environment variables to backend/.env file."""
    if not ENV_FILE_PATH.exists():
        lines = []
    else:
        lines = ENV_FILE_PATH.read_text(encoding="utf-8").splitlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in key_values:
            val = key_values[key]
            new_lines.append(f"{key}={val}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    for key, val in key_values.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    ENV_FILE_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


class AIConfigModel(BaseModel):
    provider: Literal[
        "github_copilot",
        "openai",
        "azure_openai",
        "anthropic",
        "gemini",
        "local",
    ] = "github_copilot"
    model: str = "gpt-4o"
    api_key: str | None = None
    endpoint: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=100, le=16384)
    timeout_seconds: int = Field(default=45, ge=10, le=300)


class AIModelDiscoverRequest(BaseModel):
    provider: str = "github_copilot"
    endpoint: str | None = None
    api_key: str | None = None


DEFAULT_MODELS_BY_PROVIDER: dict[str, list[dict[str, str]]] = {
    "github_copilot": [
        {"id": "gpt-4o", "name": "GPT-4o (Recommended)", "family": "OpenAI", "description": "High-intelligence multimodal flagship model"},
        {"id": "gpt-4.1", "name": "GPT-4.1", "family": "OpenAI", "description": "Latest generation high-precision reasoning model"},
        {"id": "claude-haiku-4.5", "name": "Claude Haiku 4.5", "family": "Anthropic", "description": "Fast, high-efficiency lightweight Claude model"},
        {"id": "gpt-4o-mini", "name": "GPT-4o mini", "family": "OpenAI", "description": "Fast and lightweight flagship variant"},
        {"id": "gemini-3.7-flash", "name": "Gemini 3.7 Flash", "family": "Google", "description": "High-speed multimodal flash reasoning"},
        {"id": "kimi-k2.7-code", "name": "Kimi K2.7 Code", "family": "Moonshot AI", "description": "Code and automation test reasoning"},
        {"id": "gpt-4", "name": "GPT-4", "family": "OpenAI", "description": "Standard robust GPT-4 model"},
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "family": "OpenAI", "description": "Standard fast conversational model"},
    ],
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o", "family": "OpenAI", "description": "Flagship multimodal OpenAI model"},
        {"id": "gpt-4o-mini", "name": "GPT-4o mini", "family": "OpenAI", "description": "Affordable and fast multimodal model"},
        {"id": "gpt-4.1", "name": "GPT-4.1", "family": "OpenAI", "description": "High-reasoning GPT-4.1 model"},
        {"id": "o3-mini", "name": "o3-mini", "family": "OpenAI", "description": "High-depth reasoning & planning model"},
        {"id": "o1", "name": "o1", "family": "OpenAI", "description": "Deep reasoning model for complex workflows"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "family": "OpenAI", "description": "High-throughput GPT-4 Turbo model"},
    ],
    "azure_openai": [
        {"id": "gpt-4o", "name": "gpt-4o (Deployment)", "family": "Azure OpenAI", "description": "Azure-hosted GPT-4o instance"},
        {"id": "gpt-4o-mini", "name": "gpt-4o-mini (Deployment)", "family": "Azure OpenAI", "description": "Azure-hosted GPT-4o-mini instance"},
        {"id": "gpt-4", "name": "gpt-4 (Deployment)", "family": "Azure OpenAI", "description": "Azure-hosted GPT-4 instance"},
    ],
    "anthropic": [
        {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "family": "Anthropic", "description": "State-of-the-art coding and QA reasoning"},
        {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "family": "Anthropic", "description": "Fast and responsive test architect"},
        {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "family": "Anthropic", "description": "Maximum reasoning capability"},
    ],
    "gemini": [
        {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "family": "Google", "description": "2M token context reasoning engine"},
        {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "family": "Google", "description": "High-speed multimodal model"},
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "family": "Google", "description": "Next-gen real-time reasoning model"},
    ],
    "local": [
        {"id": "local-model", "name": "Default Local Model", "family": "Custom", "description": "Custom inference server model"},
    ],
}


@router.get("/ai-configuration")
def get_ai_configuration(user: User = Depends(current_user)) -> dict[str, Any]:
    provider = os.getenv("AI_PROVIDER") or os.getenv("AI_QA_ENGINE_AI_PROVIDER") or os.getenv("AI_QA_ENGINE_AI_PROVIDER") or "github_copilot"
    model = os.getenv("AI_MODEL") or os.getenv("AI_QA_ENGINE_AI_MODEL") or os.getenv("AI_QA_ENGINE_AI_OPENAI_MODEL") or "gpt-4o"

    endpoint = os.getenv("AI_ENDPOINT") or os.getenv("AI_BASE_URL") or os.getenv("AI_QA_ENGINE_AI_BASE_URL") or _provider_endpoint(provider)
    raw_api_key = _provider_key(provider)
    masked_key = f"{raw_api_key[:4]}...{raw_api_key[-4:]}" if len(raw_api_key) > 8 else ("configured" if raw_api_key else "not_configured")
    temp = float(os.getenv("AI_TEMPERATURE", "0.2"))
    tokens = int(os.getenv("AI_MAX_TOKENS", "4096"))
    timeout = int(os.getenv("AI_TIMEOUT_SECONDS", "45"))

    meta = get_ai_provider_metadata()

    return {
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "api_key_status": masked_key,
        "temperature": temp,
        "max_tokens": tokens,
        "timeout_seconds": timeout,
        "status": meta,
        "supported_providers": [
            {"id": "github_copilot", "name": "GitHub Copilot / GitHub Models", "description": "Direct GitHub Copilot API (GPT-4o, GPT-4.1, Claude Haiku 4.5, etc.)"},
            {"id": "openai", "name": "OpenAI API", "description": "Direct OpenAI GPT-4o / GPT-4.1 endpoints"},
            {"id": "azure_openai", "name": "Azure OpenAI Service", "description": "Enterprise Azure-hosted GPT models"},
            {"id": "anthropic", "name": "Anthropic Claude", "description": "Claude 3.5 Sonnet / Haiku"},
            {"id": "gemini", "name": "Google Gemini", "description": "Gemini 1.5 Pro / Flash"},
            {"id": "local", "name": "Local LLM / vLLM", "description": "Custom OpenAI-compatible inference servers"},
        ],
    }


@router.post("/ai-configuration")
@router.put("/ai-configuration")
def update_ai_configuration(
    config: AIConfigModel,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> dict[str, Any]:
    env_updates: dict[str, str] = {
        "AI_PROVIDER": config.provider,
        "AI_MODEL": config.model.strip(),
        "AI_ENDPOINT": (config.endpoint or "").strip() or _provider_endpoint(config.provider),
        "AI_TEMPERATURE": str(config.temperature),
        "AI_MAX_TOKENS": str(config.max_tokens),
        "AI_TIMEOUT_SECONDS": str(config.timeout_seconds),
    }

    if config.api_key and config.api_key.strip():
        clean_key = config.api_key.strip()
        if config.provider in {"github_copilot", "copilot", "github", "github_models"}:
            env_updates["GITHUB_TOKEN"] = clean_key
            env_updates["COPILOT_API_KEY"] = clean_key
        elif config.provider == "openai":
            env_updates["OPENAI_API_KEY"] = clean_key
        elif config.provider in {"azure_openai", "azure"}:
            env_updates["AZURE_OPENAI_API_KEY"] = clean_key
        elif config.provider in {"anthropic", "claude"}:
            env_updates["ANTHROPIC_API_KEY"] = clean_key
        elif config.provider in {"gemini", "google"}:
            env_updates["GEMINI_API_KEY"] = clean_key
        else:
            env_updates["AI_API_KEY"] = clean_key

    for k, v in env_updates.items():
        os.environ[k] = v

    try:
        _update_env_file(env_updates)
    except Exception as e:
        print("Warning: could not persist to .env file:", e)

    return get_ai_configuration(user=user)


@router.post("/ai-models")
async def discover_ai_models(
    request: AIModelDiscoverRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    provider = request.provider.lower()
    api_key = _provider_key(provider, request.api_key)

    if provider in {"github_copilot", "copilot", "github", "github_models"}:
        endpoint = request.endpoint or "https://api.githubcopilot.com"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Editor-Version": "vscode/1.95.0",
            "User-Agent": "GitHubCopilot/1.0",
            "Copilot-Integration-Id": "vscode-chat",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(f"{endpoint.rstrip('/')}/models", headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    live_models = []
                    seen_ids = set()
                    for item in data:
                        m_id = str(item.get("id") or "").strip()
                        if not m_id or "embedding" in m_id.lower() or "trajectory" in m_id.lower():
                            continue
                        supported = item.get("supported_endpoints", [])
                        # Exclude models that only support /responses or do not support /chat/completions
                        if supported and "/chat/completions" not in supported:
                            continue
                        if m_id.startswith(("gpt-5.", "mai-")):
                            continue

                        name = item.get("name") or m_id
                        vendor = item.get("vendor") or ("Anthropic" if "claude" in m_id.lower() else ("Google" if "gemini" in m_id.lower() else ("Moonshot AI" if "kimi" in m_id.lower() else "OpenAI")))

                        # Collapse dated snapshot suffix if primary is available
                        base_id = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", m_id)
                        chosen_id = base_id if base_id in {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "claude-haiku-4.5", "gpt-4", "gpt-3.5-turbo"} else m_id
                        if chosen_id in seen_ids:
                            continue
                        seen_ids.add(chosen_id)

                        live_models.append({
                            "id": chosen_id,
                            "name": name if name != m_id else chosen_id,
                            "family": vendor,
                            "description": f"Copilot native chat model ({vendor})",
                        })
                    if live_models:
                        return {"provider": provider, "source": "live_api", "models": live_models}
        except Exception as e:
            print("Failed to query live Copilot models:", e)

    elif provider == "openai" and api_key:
        endpoint = request.endpoint or "https://api.openai.com/v1"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(f"{endpoint.rstrip('/')}/models", headers=headers)
                if resp.status_code == 200:
                    models = [
                        {
                            "id": m.get("id"),
                            "name": m.get("id"),
                            "family": "OpenAI",
                            "description": "OpenAI hosted model",
                        }
                        for m in resp.json().get("data", [])
                        if m.get("id") and ("gpt" in m.get("id").lower() or "o1" in m.get("id").lower() or "o3" in m.get("id").lower())
                    ]
                    if models:
                        return {"provider": provider, "source": "live_api", "models": models}
        except Exception:
            pass

    curated = DEFAULT_MODELS_BY_PROVIDER.get(provider)
    if curated is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported AI provider '{provider}'. Select an explicit configured provider.")
    return {"provider": provider, "source": "catalog", "models": curated}


@router.post("/ai-configuration/test")
async def test_ai_configuration(
    config: AIConfigModel,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        probe = await test_ai_provider_connection(
            provider=config.provider,
            model=config.model,
            api_key=config.api_key or _provider_key(config.provider),
            endpoint=config.endpoint,
        )
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {
            "status": "success",
            "message": f"Successfully connected to {probe['provider']} ({probe['model']}). Response: {probe['response']}",
            "provider": probe["provider"],
            "model": probe["model"],
            "latency_ms": latency_ms,
        }
    except AIServiceError as error:
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {
            "status": "error",
            "message": str(error)[:500],
            "provider": config.provider,
            "model": config.model,
            "latency_ms": latency_ms,
        }
