import os

import httpx


class SecretResolutionError(RuntimeError):
    pass


def _provider() -> str:
    return (os.getenv("AI_QA_ENGINE_SECRET_PROVIDER", "env").strip().lower() or "env")


def _read_from_env(secret_name: str) -> str | None:
    value = os.getenv(secret_name)
    return value.strip() if value is not None and value.strip() else None


def _read_from_vault(secret_name: str) -> str | None:
    vault_addr = os.getenv("AI_QA_ENGINE_VAULT_ADDR", "").strip()
    vault_token = os.getenv("AI_QA_ENGINE_VAULT_TOKEN", "").strip()
    vault_path = os.getenv("AI_QA_ENGINE_VAULT_PATH", "secret/data/ai-qa-engine").strip()
    if not vault_addr or not vault_token:
        raise SecretResolutionError("Vault provider is configured but AI_QA_ENGINE_VAULT_ADDR/TOKEN is missing")

    url = f"{vault_addr.rstrip('/')}/v1/{vault_path.lstrip('/')}"
    headers = {"X-Vault-Token": vault_token}
    try:
        response = httpx.get(url, headers=headers, timeout=8.0)
    except httpx.HTTPError as error:
        raise SecretResolutionError(f"Vault read failed: {error}") from error
    if response.status_code >= 400:
        raise SecretResolutionError(f"Vault returned HTTP {response.status_code}")
    payload = response.json()
    data = payload.get("data", {})
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    if not isinstance(data, dict):
        raise SecretResolutionError("Vault response payload is invalid")
    value = data.get(secret_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SecretResolutionError(f"Vault secret {secret_name} must be a string")
    return value.strip()


def resolve_secret_value(secret_name: str) -> str | None:
    provider = _provider()
    if provider == "env":
        return _read_from_env(secret_name)
    if provider == "vault":
        return _read_from_vault(secret_name)
    raise SecretResolutionError(f"Unsupported secret provider '{provider}'")
