import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.integration_connection import IntegrationConnection
from app.schemas.integration import (
    IntegrationConnectionCreate,
    IntegrationConnectionResponse,
    IntegrationConnectionUpdate,
    IntegrationEnvironmentUpdate,
)
from app.services.integration_secrets import (
    IntegrationSecretError,
    decrypt_integration_secret,
    encrypt_integration_secret,
)
from app.services.integrations import (
    IntegrationClientError,
    IntegrationTestResult,
    JiraClient,
    QTestClient,
)
from app.services.secrets import SecretResolutionError, resolve_secret_value


class IntegrationServiceError(RuntimeError):
    pass


ENVIRONMENT_CONNECTION_IDS = {"jira": -1, "qtest": -2, "xray": -3}
INTEGRATION_ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"


def integration_environment_value(name: str, fallback: str = "") -> str:
    value = os.environ.get(name)
    return fallback if value is None else value.strip()


def environment_credential(system: str) -> str:
    if system == "jira":
        credential_name = integration_environment_value("JIRA_CREDENTIAL_ENV_NAME", settings.JIRA_CREDENTIAL_ENV_NAME)
        fallback = settings.JIRA_API_TOKEN
    elif system == "qtest":
        credential_name = integration_environment_value("QTEST_CREDENTIAL_ENV_NAME", settings.QTEST_CREDENTIAL_ENV_NAME)
        fallback = settings.QTEST_TOKEN
    elif system == "xray":
        credential_name = integration_environment_value("XRAY_CREDENTIAL_ENV_NAME", getattr(settings, "XRAY_CREDENTIAL_ENV_NAME", "XRAY_CLIENT_SECRET"))
        fallback = getattr(settings, "XRAY_CLIENT_SECRET", "")
    else:
        return ""
    configured_value = os.environ.get(credential_name)
    if configured_value is not None and configured_value.strip():
        return configured_value.strip()
    return fallback


def environment_connection(system: str) -> IntegrationConnection | None:
    if system == "jira":
        base_url = integration_environment_value("JIRA_BASE_URL", settings.JIRA_BASE_URL)
        email = integration_environment_value("JIRA_EMAIL", settings.JIRA_EMAIL)
        project_key = integration_environment_value("JIRA_PROJECT_KEY", settings.JIRA_PROJECT_KEY)
        filter_id = integration_environment_value("JIRA_FILTER_ID", settings.JIRA_FILTER_ID)
        profile_name = integration_environment_value("JIRA_PROFILE_NAME", settings.JIRA_PROFILE_NAME)
        credential_env_name = integration_environment_value("JIRA_CREDENTIAL_ENV_NAME", settings.JIRA_CREDENTIAL_ENV_NAME)
        if not base_url or not email or not environment_credential("jira"):
            return None
        return IntegrationConnection(
            id=ENVIRONMENT_CONNECTION_IDS[system],
            system="jira",
            name=profile_name or "Jira environment",
            base_url=base_url,
            project_key=project_key or None,
            username=email or None,
            auth_type="basic_api_token",
            secret_ref=credential_env_name or None,
            status="active",
            created_by=0,
        )
    if system == "qtest":
        base_url = integration_environment_value("QTEST_BASE_URL", settings.QTEST_BASE_URL)
        project_id = integration_environment_value("QTEST_PROJECT_ID", settings.QTEST_PROJECT_ID)
        project_name = integration_environment_value("QTEST_PROJECT_NAME", settings.QTEST_PROJECT_NAME)
        profile_name = integration_environment_value("QTEST_PROFILE_NAME", settings.QTEST_PROFILE_NAME)
        credential_env_name = integration_environment_value("QTEST_CREDENTIAL_ENV_NAME", settings.QTEST_CREDENTIAL_ENV_NAME)
        if not base_url or not environment_credential("qtest"):
            return None
        if not project_id and not project_name:
            return None
        return IntegrationConnection(
            id=ENVIRONMENT_CONNECTION_IDS[system],
            system="qtest",
            name=profile_name or "qTest environment",
            base_url=base_url,
            project_id=project_id or None,
            project_name=project_name or None,
            auth_type="bearer_token",
            secret_ref=credential_env_name or None,
            status="active",
            created_by=0,
        )
    if system == "xray":
        base_url = integration_environment_value("XRAY_BASE_URL", getattr(settings, "XRAY_BASE_URL", "https://xray.cloud.getxray.app"))
        client_id = integration_environment_value("XRAY_CLIENT_ID", getattr(settings, "XRAY_CLIENT_ID", ""))
        project_key = integration_environment_value("XRAY_PROJECT_KEY", getattr(settings, "XRAY_PROJECT_KEY", "XSP"))
        profile_name = integration_environment_value("XRAY_PROFILE_NAME", getattr(settings, "XRAY_PROFILE_NAME", "Xray Cloud Production"))
        credential_env_name = integration_environment_value("XRAY_CREDENTIAL_ENV_NAME", getattr(settings, "XRAY_CREDENTIAL_ENV_NAME", "XRAY_CLIENT_SECRET"))
        cred = environment_credential("xray")
        if not base_url or not client_id or not cred:
            return None
        return IntegrationConnection(
            id=ENVIRONMENT_CONNECTION_IDS[system],
            system="xray",
            name=profile_name or "Xray environment",
            base_url=base_url,
            project_key=project_key or "XSP",
            username=client_id or None,
            auth_type="oauth2_client_credentials",
            secret_ref=credential_env_name or None,
            status="active",
            last_test_status="success",
            created_by=0,
        )
    return None


def is_environment_connection(connection: IntegrationConnection) -> bool:
    return connection.created_by == 0 and connection.id in ENVIRONMENT_CONNECTION_IDS.values()


def _write_environment_values(values: dict[str, str]) -> None:
    if not values:
        raise IntegrationServiceError("Provide at least one integration setting to update")
    path = INTEGRATION_ENV_FILE_PATH
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated_keys: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            next_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in values:
            next_lines.append(f"{key}={values[key]}")
            updated_keys.add(key)
        else:
            next_lines.append(line)
    next_lines.extend(f"{key}={value}" for key, value in values.items() if key not in updated_keys)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    temporary_path.replace(path)
    for key, value in values.items():
        os.environ[key] = value


def update_environment_configuration(request: IntegrationEnvironmentUpdate) -> None:
    values: dict[str, str] = {}
    if request.jira is not None:
        jira = request.jira
        if jira.base_url is not None:
            values["JIRA_BASE_URL"] = str(jira.base_url).rstrip("/")
        for field_name, environment_name in (
            ("email", "JIRA_EMAIL"),
            ("project_key", "JIRA_PROJECT_KEY"),
            ("filter_id", "JIRA_FILTER_ID"),
            ("profile_name", "JIRA_PROFILE_NAME"),
            ("credential_env_name", "JIRA_CREDENTIAL_ENV_NAME"),
        ):
            value = getattr(jira, field_name)
            if value is not None:
                values[environment_name] = value
        credential_name = jira.credential_env_name or integration_environment_value("JIRA_CREDENTIAL_ENV_NAME", settings.JIRA_CREDENTIAL_ENV_NAME)
        current_credential_name = integration_environment_value("JIRA_CREDENTIAL_ENV_NAME", settings.JIRA_CREDENTIAL_ENV_NAME)
        if jira.credential_env_name and jira.credential_env_name != current_credential_name and jira.api_token is None:
            raise IntegrationServiceError("Provide a new Jira token when changing its credential environment variable name")
        if jira.api_token is not None:
            values[credential_name] = jira.api_token
    if request.qtest is not None:
        qtest = request.qtest
        if qtest.base_url is not None:
            values["QTEST_BASE_URL"] = str(qtest.base_url).rstrip("/")
        for field_name, environment_name in (
            ("project_id", "QTEST_PROJECT_ID"),
            ("project_name", "QTEST_PROJECT_NAME"),
            ("profile_name", "QTEST_PROFILE_NAME"),
            ("credential_env_name", "QTEST_CREDENTIAL_ENV_NAME"),
        ):
            value = getattr(qtest, field_name)
            if value is not None:
                values[environment_name] = value
        credential_name = qtest.credential_env_name or integration_environment_value("QTEST_CREDENTIAL_ENV_NAME", settings.QTEST_CREDENTIAL_ENV_NAME)
        current_credential_name = integration_environment_value("QTEST_CREDENTIAL_ENV_NAME", settings.QTEST_CREDENTIAL_ENV_NAME)
        if qtest.credential_env_name and qtest.credential_env_name != current_credential_name and qtest.token is None:
            raise IntegrationServiceError("Provide a new qTest token when changing its credential environment variable name")
        if qtest.token is not None:
            values[credential_name] = qtest.token
    _write_environment_values(values)


def _credential_for(connection: IntegrationConnection) -> str:
    if connection.encrypted_secret:
        try:
            credential = decrypt_integration_secret(connection.encrypted_secret)
        except IntegrationSecretError as error:
            raise IntegrationServiceError(str(error)) from error
        if credential:
            return credential
    if connection.secret_ref:
        try:
            credential = resolve_secret_value(connection.secret_ref)
        except SecretResolutionError as error:
            raise IntegrationServiceError(str(error)) from error
        if credential:
            return credential
    configured_credential = environment_credential(connection.system)
    if configured_credential:
        return configured_credential
    raise IntegrationServiceError("Integration credential is not configured")


def _client_for(connection: IntegrationConnection) -> Any:
    credential = _credential_for(connection)
    if connection.system == "jira":
        return JiraClient(connection, credential)
    if connection.system == "qtest":
        return QTestClient(connection, credential)
    if connection.system == "xray":
        from app.services.test_management.xray_provider import XrayClient
        return XrayClient(connection, credential)
    raise IntegrationServiceError(f"Unsupported integration system '{connection.system}'")


def connection_response(connection: IntegrationConnection) -> IntegrationConnectionResponse:
    return IntegrationConnectionResponse(
        id=connection.id,
        system=connection.system,
        name=connection.name,
        base_url=connection.base_url,
        project_key=connection.project_key,
        project_name=connection.project_name,
        project_id=connection.project_id,
        username=connection.username,
        auth_type=connection.auth_type,
        environment=connection.environment,
        status=connection.status,
        credential_configured=bool(connection.encrypted_secret or connection.secret_ref or environment_credential(connection.system)),
        environment_backed=is_environment_connection(connection),
        secret_ref=connection.secret_ref,
        last_test_status=connection.last_test_status,
        last_test_message=connection.last_test_message,
        last_test_latency_ms=connection.last_test_latency_ms,
        last_tested_at=connection.last_tested_at,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def _apply_credential(
    connection: IntegrationConnection,
    *,
    credential: str | None,
    secret_ref: str | None,
    is_update: bool,
) -> None:
    if credential and secret_ref:
        raise IntegrationServiceError("Provide an encrypted credential or a secret reference, not both")
    if credential:
        try:
            connection.encrypted_secret = encrypt_integration_secret(credential)
        except IntegrationSecretError as error:
            raise IntegrationServiceError(str(error)) from error
        connection.secret_ref = None
    elif secret_ref is not None:
        connection.secret_ref = secret_ref or None
        connection.encrypted_secret = None
    elif not is_update:
        raise IntegrationServiceError("Provide an encrypted credential or a secret reference")


def create_connection(db: Session, request: IntegrationConnectionCreate, user_id: int) -> IntegrationConnection:
    connection = IntegrationConnection(
        system=request.system,
        name=request.name,
        base_url=str(request.base_url).rstrip("/"),
        project_key=request.project_key,
        project_name=request.project_name,
        project_id=request.project_id,
        username=request.username,
        auth_type=request.auth_type,
        environment=request.environment,
        status="untested",
        created_by=user_id,
    )
    _apply_credential(connection, credential=request.credential, secret_ref=request.secret_ref, is_update=False)
    db.add(connection)
    db.flush()
    return connection


def update_connection(db: Session, connection: IntegrationConnection, request: IntegrationConnectionUpdate) -> IntegrationConnection:
    updates = request.model_dump(exclude_unset=True, exclude={"credential"})
    if request.name is not None:
        connection.name = request.name
    if request.base_url is not None:
        connection.base_url = str(request.base_url).rstrip("/")
    for field in ("project_key", "project_name", "project_id", "username", "auth_type", "environment"):
        if field in updates:
            setattr(connection, field, updates[field])
    _apply_credential(
        connection,
        credential=request.credential,
        secret_ref=request.secret_ref if "secret_ref" in updates else None,
        is_update=True,
    )
    connection.status = "untested"
    connection.last_test_status = None
    connection.last_test_message = None
    connection.last_metadata = None
    connection.updated_at = datetime.now(timezone.utc)
    db.add(connection)
    return connection


async def test_connection(connection: IntegrationConnection) -> tuple[IntegrationTestResult, int]:
    started = perf_counter()
    client = _client_for(connection)
    try:
        result = await client.test_connection()
    except (IntegrationClientError, IntegrationServiceError):
        raise
    return result, round((perf_counter() - started) * 1000)


async def list_jira_requirements(connection: IntegrationConnection, *, page: int, page_size: int) -> tuple[list[dict[str, Any]], int | None]:
    client = _client_for(connection)
    if not isinstance(client, JiraClient):
        raise IntegrationServiceError("Connection is not a Jira profile")
    return await client.list_requirements(page=page, page_size=page_size)


async def fetch_jira_issue(connection: IntegrationConnection | None, issue_key_or_url: str) -> dict[str, Any]:
    target_connection = connection or environment_connection("jira")
    if target_connection is None:
        raise IntegrationServiceError("No Jira connection is configured. Configure Jira under Settings -> Integrations or in backend environment variables.")
    client = _client_for(target_connection)
    if not isinstance(client, JiraClient):
        raise IntegrationServiceError("Configured connection is not a Jira profile")
    return await client.get_issue(issue_key_or_url)


async def list_qtest_assets(connection: IntegrationConnection, asset_type: str, *, page: int, page_size: int) -> tuple[list[dict[str, Any]], int | None]:
    client = _client_for(connection)
    if not isinstance(client, QTestClient):
        raise IntegrationServiceError("Connection is not a qTest profile")
    return await client.list_assets(asset_type, page=page, page_size=page_size)


async def export_defect_to_jira(
    db: Session,
    defect_id: int,
    user_id: int,
    *,
    connection_id: int | None = None,
    project_key: str | None = None,
    issue_type: str = "Bug",
    priority: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    from app.models.defect import Defect
    from app.models.external_issue_link import ExternalIssueLink

    defect = db.query(Defect).filter(Defect.id == defect_id, Defect.created_by == user_id).first()
    if not defect:
        raise IntegrationServiceError(f"Defect #{defect_id} was not found")

    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("jira")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "jira", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active Jira connection is configured. Please configure Jira in AI & Settings > Integrations.")

    client = _client_for(target_connection)
    if not isinstance(client, JiraClient):
        raise IntegrationServiceError("Configured connection is not a Jira profile")

    jira_priority = priority or ("High" if defect.priority in {"high", "critical"} else "Medium" if defect.priority == "medium" else "Low")
    jira_labels = ["ai-qa-engine", "auto-logged-defect"]
    if labels:
        jira_labels.extend(labels)

    created = await client.create_defect(
        summary=f"[AI-QA-Engine] {defect.title}",
        description=defect.description or f"Defect #{defect.id} identified during automated test execution.\nSeverity: {defect.severity}\nPriority: {defect.priority}",
        project_key=project_key or target_connection.project_key,
        issue_type=issue_type or "Bug",
        priority=jira_priority,
        labels=list(dict.fromkeys(jira_labels)),
    )

    idempotency_key = f"defect-{defect.id}-{created['key']}"
    link = db.query(ExternalIssueLink).filter(
        ExternalIssueLink.connection_id == target_connection.id,
        ExternalIssueLink.idempotency_key == idempotency_key,
    ).first()
    if not link:
        link = ExternalIssueLink(
            connection_id=target_connection.id,
            defect_id=defect.id,
            system="jira",
            external_key=created["key"],
            external_url=created["url"],
            idempotency_key=idempotency_key,
            created_by=user_id,
        )
        db.add(link)
        db.commit()

    return {
        "defect_id": defect.id,
        "system": "jira",
        "external_key": created["key"],
        "external_url": created["url"],
    }


async def export_defect_to_qtest(
    db: Session,
    defect_id: int,
    user_id: int,
    *,
    connection_id: int | None = None,
) -> dict[str, Any]:
    from app.models.defect import Defect
    from app.models.external_issue_link import ExternalIssueLink

    defect = db.query(Defect).filter(Defect.id == defect_id, Defect.created_by == user_id).first()
    if not defect:
        raise IntegrationServiceError(f"Defect #{defect_id} was not found")

    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("qtest")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "qtest", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active qTest connection is configured. Please configure qTest in AI & Settings > Integrations.")

    client = _client_for(target_connection)
    if not isinstance(client, QTestClient):
        raise IntegrationServiceError("Configured connection is not a qTest profile")

    created = await client.create_defect(
        summary=f"[AI-QA-Engine] {defect.title}",
        description=defect.description or f"Defect #{defect.id} identified during automated test execution.\nSeverity: {defect.severity}\nPriority: {defect.priority}",
        severity=defect.severity,
    )

    idempotency_key = f"defect-{defect.id}-{created['key']}"
    link = db.query(ExternalIssueLink).filter(
        ExternalIssueLink.connection_id == target_connection.id,
        ExternalIssueLink.idempotency_key == idempotency_key,
    ).first()
    if not link:
        link = ExternalIssueLink(
            connection_id=target_connection.id,
            defect_id=defect.id,
            system="qtest",
            external_key=created["key"],
            external_url=created["url"],
            idempotency_key=idempotency_key,
            created_by=user_id,
        )
        db.add(link)
        db.commit()

    return {
        "defect_id": defect.id,
        "system": "qtest",
        "external_key": created["key"],
        "external_url": created["url"],
    }


async def attach_artifact_to_jira_defect(
    db: Session,
    defect_id: int,
    user_id: int,
    *,
    filename: str,
    content: bytes,
    mime_type: str = "application/octet-stream",
    connection_id: int | None = None,
) -> dict[str, Any]:
    from app.models.defect import Defect
    from app.models.external_issue_link import ExternalIssueLink

    defect = db.query(Defect).filter(Defect.id == defect_id).first()
    if not defect:
        raise IntegrationServiceError(f"Defect #{defect_id} was not found")

    link = db.query(ExternalIssueLink).filter(
        ExternalIssueLink.defect_id == defect_id,
        ExternalIssueLink.system == "jira",
    ).first()
    if not link or not link.external_key:
        raise IntegrationServiceError(f"No Jira issue is linked to Defect #{defect_id}")

    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("jira")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "jira", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active Jira connection configured")

    client = _client_for(target_connection)
    if not isinstance(client, JiraClient):
        raise IntegrationServiceError("Configured connection is not a Jira profile")

    return await client.upload_attachment(
        issue_key=link.external_key,
        filename=filename,
        content=content,
        content_type=mime_type,
    )


async def link_jira_defect_to_requirement(
    db: Session,
    defect_id: int,
    requirement_key: str,
    *,
    link_type: str = "Relates",
    connection_id: int | None = None,
) -> dict[str, Any]:
    from app.models.external_issue_link import ExternalIssueLink

    link = db.query(ExternalIssueLink).filter(
        ExternalIssueLink.defect_id == defect_id,
        ExternalIssueLink.system == "jira",
    ).first()
    if not link or not link.external_key:
        raise IntegrationServiceError(f"No Jira issue is linked to Defect #{defect_id}")

    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("jira")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "jira", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active Jira connection configured")

    client = _client_for(target_connection)
    if not isinstance(client, JiraClient):
        raise IntegrationServiceError("Configured connection is not a Jira profile")

    return await client.link_issues(
        inward_key=link.external_key,
        outward_key=requirement_key,
        link_type=link_type,
    )


async def get_jira_issue_transitions(
    db: Session,
    issue_key: str,
    *,
    connection_id: int | None = None,
) -> list[dict[str, Any]]:
    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("jira")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "jira", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active Jira connection configured")

    client = _client_for(target_connection)
    if not isinstance(client, JiraClient):
        raise IntegrationServiceError("Configured connection is not a Jira profile")

    return await client.get_transitions(issue_key)


async def transition_jira_issue(
    db: Session,
    issue_key: str,
    transition_id: str,
    *,
    comment: str | None = None,
    connection_id: int | None = None,
) -> dict[str, Any]:
    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("jira")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "jira", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active Jira connection configured")

    client = _client_for(target_connection)
    if not isinstance(client, JiraClient):
        raise IntegrationServiceError("Configured connection is not a Jira profile")

    return await client.transition_issue(issue_key, transition_id, comment=comment)


async def register_qtest_build(
    db: Session,
    *,
    release_id: int | str,
    build_name: str,
    build_note: str = "",
    connection_id: int | None = None,
) -> dict[str, Any]:
    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("qtest")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "qtest", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active qTest connection configured")

    client = _client_for(target_connection)
    if not isinstance(client, QTestClient):
        raise IntegrationServiceError("Configured connection is not a qTest profile")

    return await client.create_build(release_id=release_id, build_name=build_name, build_note=build_note)


async def get_qtest_builds(
    db: Session,
    release_id: int | str,
    *,
    connection_id: int | None = None,
) -> list[dict[str, Any]]:
    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("qtest")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "qtest", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active qTest connection configured")

    client = _client_for(target_connection)
    if not isinstance(client, QTestClient):
        raise IntegrationServiceError("Configured connection is not a qTest profile")

    return await client.get_builds(release_id=release_id)


async def submit_qtest_test_run_log(
    db: Session,
    test_run_id: int | str,
    *,
    status: str = "PASSED",
    start_time: str | None = None,
    end_time: str | None = None,
    name: str = "SkyWatch Test Run",
    note: str = "",
    steps: list[dict[str, Any]] | None = None,
    defect_ids: list[str | int] | None = None,
    connection_id: int | None = None,
) -> dict[str, Any]:
    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("qtest")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "qtest", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active qTest connection configured")

    client = _client_for(target_connection)
    if not isinstance(client, QTestClient):
        raise IntegrationServiceError("Configured connection is not a qTest profile")

    return await client.submit_auto_test_log(
        test_run_id=test_run_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        name=name,
        note=note,
        steps=steps,
        defect_ids=defect_ids,
    )


async def export_test_case_to_qtest(
    db: Session,
    *,
    name: str,
    description: str = "",
    steps: list[dict[str, str]] | None = None,
    parent_id: int | str | None = None,
    connection_id: int | None = None,
) -> dict[str, Any]:
    target_connection = None
    if connection_id is not None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_connection is None:
        target_connection = environment_connection("qtest")
    if target_connection is None:
        target_connection = db.query(IntegrationConnection).filter(IntegrationConnection.system == "qtest", IntegrationConnection.status == "active").first()
    if target_connection is None:
        raise IntegrationServiceError("No active qTest connection configured")

    client = _client_for(target_connection)
    if not isinstance(client, QTestClient):
        raise IntegrationServiceError("Configured connection is not a qTest profile")

    return await client.export_test_case(name=name, description=description, steps=steps, parent_id=parent_id)
