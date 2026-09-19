import pytest
from pydantic import ValidationError

from app.api.v1.settings import AIConfigModel
from app.schemas.integration import IntegrationConnectionCreate
from app.schemas.test_case import AIGeneratedTestCaseSet
from app.services.ai_service import AIServiceError, _load_provider_settings, _provider_settings_for_connection


def test_provider_selection_rejects_automatic_and_retired_modes() -> None:
    with pytest.raises(AIServiceError, match="explicit"):
        _load_provider_settings("auto")
    with pytest.raises(AIServiceError, match="explicit"):
        _load_provider_settings("ollama")
    with pytest.raises(AIServiceError, match="explicit"):
        _provider_settings_for_connection("ollama", "model", None, None)


def test_settings_schema_accepts_only_explicit_providers() -> None:
    with pytest.raises(ValidationError):
        AIConfigModel(provider="auto")
    with pytest.raises(ValidationError):
        AIConfigModel(provider="ollama")


def test_generation_schema_accepts_only_provider_mode() -> None:
    base_case = {
        "title": "Checkout smoke",
        "description": "Verify checkout.",
        "preconditions": "User is signed in.",
        "steps": "1. Open checkout\n2. Verify summary",
        "expected_result": "Checkout summary is visible",
    }
    assert AIGeneratedTestCaseSet(test_cases=[base_case], generation_mode="provider").generation_mode == "provider"
    with pytest.raises(ValidationError):
        AIGeneratedTestCaseSet(test_cases=[base_case], generation_mode="deterministic-fallback")


def test_integration_base_url_rejects_embedded_credentials_and_query_strings() -> None:
    base_payload = {
        "system": "jira",
        "name": "QA Jira",
        "project_key": "QA",
        "auth_type": "basic_api_token",
        "username": "qa@example.test",
        "credential": "token",
    }
    with pytest.raises(ValidationError, match="embedded credentials"):
        IntegrationConnectionCreate(**base_payload, base_url="https://user:password@jira.example.test")
    with pytest.raises(ValidationError, match="query string"):
        IntegrationConnectionCreate(**base_payload, base_url="https://jira.example.test?token=secret")


def test_provider_settings_includes_fallback_models(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-123")
    settings = _load_provider_settings("github_copilot", "gpt-4")
    assert len(settings) > 1
    assert settings[0].model == "gpt-4"
    models = [s.model for s in settings]
    assert "gpt-4o" in models
    assert "gpt-4o-mini" in models


def test_cross_provider_fallbacks_when_keys_present(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token-123")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-456")
    settings = _load_provider_settings("github_copilot", "gpt-4o")
    providers = [s.provider for s in settings]
    assert "github_copilot" in providers
    assert "openai" in providers
