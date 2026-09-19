import pytest

from app.schemas.execution import Step
from app.services import test_execution


def test_step_value_takes_precedence_for_credentials() -> None:
    step = Step(action="type", selector="#user_email", value="step@example.com")

    assert test_execution._resolve_step_value(step, {"username": "parameter@example.com"}) == "step@example.com"


def test_parameterized_credentials_fill_missing_secret(monkeypatch) -> None:
    email_step = Step(action="type", selector="#user_email", secret_name="AI_QA_ENGINE_LOGIN_EMAIL")
    password_step = Step(action="type", selector="#user_password", secret_name="AI_QA_ENGINE_LOGIN_PASSWORD")

    parameters = {"username": "parameter@example.com", "password": "parameter-secret"}
    monkeypatch.setattr(test_execution, "resolve_secret_value", lambda name: None)

    assert test_execution._resolve_step_value(email_step, parameters) == "parameter@example.com"
    assert test_execution._resolve_step_value(password_step, parameters) == "parameter-secret"


def test_login_secret_requires_runtime_parameter(monkeypatch) -> None:
    step = Step(action="type", selector="#user_password", secret_name="AI_QA_ENGINE_LOGIN_PASSWORD")
    monkeypatch.setattr(test_execution, "resolve_secret_value", lambda name: "configured-secret")

    with pytest.raises(ValueError, match="runtime parameters"):
        test_execution._resolve_step_value(step, {})


def test_runtime_parameter_takes_precedence_over_login_secret(monkeypatch) -> None:
    step = Step(action="type", selector="#user_password", secret_name="AI_QA_ENGINE_LOGIN_PASSWORD")
    monkeypatch.setattr(test_execution, "resolve_secret_value", lambda name: "configured-secret")

    assert test_execution._resolve_step_value(step, {"password": "parameter-secret"}) == "parameter-secret"


def test_unresolved_runtime_placeholder_is_rejected() -> None:
    step = Step(action="type", selector="#user_email", value="{{login_email}}")

    with pytest.raises(ValueError, match="login_email"):
        test_execution._resolve_step_value(step, {})


def test_login_email_placeholder_resolves_with_email_parameter() -> None:
    step = Step(action="type", selector="#user_email", value="{{login_email}}")
    assert test_execution._resolve_step_value(step, {"email": "user@test.org"}) == "user@test.org"


def test_login_password_placeholder_resolves_with_password_parameter() -> None:
    step = Step(action="type", selector="#user_password", value="{{login_password}}")
    assert test_execution._resolve_step_value(step, {"password": "MySecret123!"}) == "MySecret123!"


def test_case_insensitive_and_normalized_parameter_lookup() -> None:
    step1 = Step(action="type", selector="#user_email", value="{{email}}")
    assert test_execution._resolve_step_value(step1, {"Login_Email": "admin@site.com"}) == "admin@site.com"

    step2 = Step(action="type", selector="#user_password", value="{{password}}")
    assert test_execution._resolve_step_value(step2, {"LOGIN_PASSWORD": "AdminPassword!"}) == "AdminPassword!"


def test_redacted_or_empty_credential_field_auto_resolves_from_parameters() -> None:
    email_step = Step(action="type", selector="#user_email", value="[redacted]")
    assert test_execution._resolve_step_value(email_step, {"email": "auto@example.com"}) == "auto@example.com"

    pass_step = Step(action="type", selector="#user_password", value="[redacted]")
    assert test_execution._resolve_step_value(pass_step, {"password": "AutoSecret!"}) == "AutoSecret!"


def test_literal_variable_name_resolves_from_parameters() -> None:
    step1 = Step(action="type", selector="label=Username", value="username")
    assert test_execution._resolve_step_value(step1, {"username": "standard_user"}) == "standard_user"

    step2 = Step(action="type", selector="label=Password", value="password")
    assert test_execution._resolve_step_value(step2, {"password": "secret_sauce"}) == "secret_sauce"


def test_check_run_cancelled_returns_false_for_empty_id() -> None:
    assert test_execution._check_run_cancelled(None) is False
    assert test_execution._check_run_cancelled("") is False


def test_credential_resolution_with_password_first_in_parameters() -> None:
    # When login_password appears first in the dictionary, username/email steps must resolve to the email
    params = {"login_password": "MySecretPassword123!", "login_email": "user@example.com"}

    email_step = Step(action="type", selector="label=Email", value="{{username}}")
    pass_step = Step(action="type", selector="label=Password", value="{{password}}")

    assert test_execution._resolve_step_value(email_step, params) == "user@example.com"
    assert test_execution._resolve_step_value(pass_step, params) == "MySecretPassword123!"

    # Test parameter lookups directly
    assert test_execution._lookup_parameter("username", params) == "user@example.com"
    assert test_execution._lookup_parameter("email", params) == "user@example.com"
    assert test_execution._lookup_parameter("user", params) == "user@example.com"
    assert test_execution._lookup_parameter("password", params) == "MySecretPassword123!"
    assert test_execution._lookup_parameter("pass", params) == "MySecretPassword123!"