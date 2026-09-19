from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DbSession, current_user, require_roles
from app.core.config import settings
from app.models.external_issue_link import ExternalIssueLink
from app.models.integration_connection import IntegrationConnection
from app.models.user import User
from app.schemas.integration import (
    ConnectionStatus,
    IntegrationAssetResponse,
    IntegrationAssetType,
    IntegrationConnectionCreate,
    IntegrationConnectionResponse,
    IntegrationConnectionTestResponse,
    IntegrationConnectionUpdate,
    IntegrationEnvironmentProfile,
    IntegrationEnvironmentResponse,
    IntegrationEnvironmentUpdate,
    IntegrationSystem,
    JiraCommentRequest,
    JiraFetchIssueRequest,
    JiraIssueResponse,
    JiraLinkRequest,
    JiraTransitionRequest,
    QTestBuildCreateRequest,
    QTestExportTestCaseRequest,
    QTestSubmitTestLogRequest,
)
from app.services.audit import log_audit_event
from app.services.integration_service import (
    IntegrationServiceError,
    _client_for,
    attach_artifact_to_jira_defect,
    connection_response,
    create_connection,
    environment_credential,
    environment_connection,
    export_test_case_to_qtest,
    fetch_jira_issue,
    get_jira_issue_transitions,
    get_qtest_builds,
    integration_environment_value,
    is_environment_connection,
    link_jira_defect_to_requirement,
    list_jira_requirements,
    list_qtest_assets,
    register_qtest_build,
    submit_qtest_test_run_log,
    test_connection,
    transition_jira_issue,
    update_environment_configuration,
    update_connection,
)
from app.services.integrations import IntegrationClientError, JiraClient, QTestClient



router = APIRouter(prefix="/integrations", tags=["integrations"])


def _load_owned_connection(db: DbSession, connection_id: int, user: User) -> IntegrationConnection:
    for system, environment_id in (("jira", -1), ("qtest", -2)):
        if connection_id == environment_id:
            connection = environment_connection(system)
            if connection:
                return connection
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment integration is not configured")
    connection = (
        db.query(IntegrationConnection)
        .filter(IntegrationConnection.id == connection_id, IntegrationConnection.created_by == user.id)
        .first()
    )
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration connection not found")
    return connection


def _integration_error_message(error: Exception) -> str:
    if isinstance(error, IntegrationClientError):
        return str(error)
    if isinstance(error, IntegrationServiceError):
        return str(error)
    return "Integration operation failed"


def _require_active_connection(connection: IntegrationConnection) -> None:
    if connection.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test and activate the integration connection before reading external data")


def _require_successful_connection_test(connection: IntegrationConnection) -> None:
    if connection.last_test_status != "success":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test the integration connection successfully before activating it")


@router.get("/environment", response_model=IntegrationEnvironmentResponse)
def get_environment_configuration(user: User = Depends(current_user)) -> IntegrationEnvironmentResponse:
    del user
    jira_environment = environment_connection("jira")
    qtest_environment = environment_connection("qtest")
    return IntegrationEnvironmentResponse(
        read_only=True,
        jira=IntegrationEnvironmentProfile(
            configured=jira_environment is not None,
            profile_name=integration_environment_value("JIRA_PROFILE_NAME", settings.JIRA_PROFILE_NAME) or None,
            base_url=integration_environment_value("JIRA_BASE_URL", settings.JIRA_BASE_URL) or None,
            username=integration_environment_value("JIRA_EMAIL", settings.JIRA_EMAIL) or None,
            project_key=integration_environment_value("JIRA_PROJECT_KEY", settings.JIRA_PROJECT_KEY) or None,
            filter_id=integration_environment_value("JIRA_FILTER_ID", settings.JIRA_FILTER_ID) or None,
            credential_env_name=integration_environment_value("JIRA_CREDENTIAL_ENV_NAME", settings.JIRA_CREDENTIAL_ENV_NAME) or None,
            credential_configured=bool(environment_credential("jira")),
        ),
        qtest=IntegrationEnvironmentProfile(
            configured=qtest_environment is not None,
            profile_name=integration_environment_value("QTEST_PROFILE_NAME", settings.QTEST_PROFILE_NAME) or None,
            base_url=integration_environment_value("QTEST_BASE_URL", settings.QTEST_BASE_URL) or None,
            project_id=integration_environment_value("QTEST_PROJECT_ID", settings.QTEST_PROJECT_ID) or None,
            project_name=integration_environment_value("QTEST_PROJECT_NAME", settings.QTEST_PROJECT_NAME) or None,
            credential_env_name=integration_environment_value("QTEST_CREDENTIAL_ENV_NAME", settings.QTEST_CREDENTIAL_ENV_NAME) or None,
            credential_configured=bool(environment_credential("qtest")),
        ),
    )


@router.put("/environment", response_model=IntegrationEnvironmentResponse)
def update_environment_configuration_profile(
    request: IntegrationEnvironmentUpdate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> IntegrationEnvironmentResponse:
    try:
        update_environment_configuration(request)
    except IntegrationServiceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    changed_systems = [system for system, values in (("jira", request.jira), ("qtest", request.qtest)) if values is not None]
    log_audit_event(
        db,
        user_id=user.id,
        action="integration.environment.update",
        resource_type="integration_environment",
        resource_id="environment",
        metadata={
            "systems": changed_systems,
            "read_only_external": True,
            "external_mutation": False,
        },
    )
    db.commit()
    return get_environment_configuration(user=user)


@router.get("/connections", response_model=list[IntegrationConnectionResponse])
def list_connections(
    db: DbSession,
    system: IntegrationSystem | None = None,
    status_filter: ConnectionStatus | None = Query(default=None, alias="status"),
    user: User = Depends(current_user),
) -> list[IntegrationConnectionResponse]:
    query = db.query(IntegrationConnection).filter(IntegrationConnection.created_by == user.id)
    if system:
        query = query.filter(IntegrationConnection.system == system)
    if status_filter:
        query = query.filter(IntegrationConnection.status == status_filter)
    environment_profiles = []
    systems = [system] if system else ["jira", "qtest"]
    for configured_system in systems:
        profile = environment_connection(configured_system)
        if profile:
            environment_profiles.append(connection_response(profile))
    if status_filter and status_filter != "active":
        environment_profiles = []
    return environment_profiles + [connection_response(item) for item in query.order_by(IntegrationConnection.id.desc()).all()]


@router.post("/connections", response_model=IntegrationConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection_profile(
    request: IntegrationConnectionCreate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> IntegrationConnectionResponse:
    try:
        connection = create_connection(db, request, user.id)
        log_audit_event(
            db,
            user_id=user.id,
            action="integration.connection.create",
            resource_type="integration_connection",
            resource_id=connection.id,
            metadata={"system": connection.system, "name": connection.name},
        )
        db.commit()
        db.refresh(connection)
        return connection_response(connection)
    except IntegrationServiceError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A connection with this name already exists") from error


@router.get("/connections/{connection_id}", response_model=IntegrationConnectionResponse)
def get_connection_profile(
    connection_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> IntegrationConnectionResponse:
    return connection_response(_load_owned_connection(db, connection_id, user))


@router.put("/connections/{connection_id}", response_model=IntegrationConnectionResponse)
def update_connection_profile(
    connection_id: int,
    request: IntegrationConnectionUpdate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> IntegrationConnectionResponse:
    connection = _load_owned_connection(db, connection_id, user)
    if is_environment_connection(connection):
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Environment-backed integration profiles are controlled by backend environment variables", headers={"Allow": "GET"})
    try:
        update_connection(db, connection, request)
        log_audit_event(
            db,
            user_id=user.id,
            action="integration.connection.update",
            resource_type="integration_connection",
            resource_id=connection.id,
            metadata={"system": connection.system, "name": connection.name},
        )
        db.commit()
        db.refresh(connection)
        return connection_response(connection)
    except IntegrationServiceError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A connection with this name already exists") from error


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection_profile(
    connection_id: int,
    db: DbSession,
    user: User = Depends(require_roles("qa_lead", "admin")),
) -> None:
    connection = _load_owned_connection(db, connection_id, user)
    if is_environment_connection(connection):
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Environment-backed integration profiles are controlled by backend environment variables", headers={"Allow": "GET"})
    if db.query(ExternalIssueLink.id).filter(ExternalIssueLink.connection_id == connection.id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deactivate this profile instead; local external issue links still reference it")
    log_audit_event(
        db,
        user_id=user.id,
        action="integration.connection.delete",
        resource_type="integration_connection",
        resource_id=connection.id,
        metadata={"system": connection.system, "name": connection.name},
    )
    db.delete(connection)
    db.commit()


@router.post("/connections/{connection_id}/activate", response_model=IntegrationConnectionResponse)
def activate_connection_profile(
    connection_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> IntegrationConnectionResponse:
    connection = _load_owned_connection(db, connection_id, user)
    if is_environment_connection(connection):
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Environment-backed integration profiles are controlled by backend environment variables", headers={"Allow": "GET"})
    _require_successful_connection_test(connection)
    connection.status = "active"
    connection.updated_at = datetime.now(timezone.utc)
    log_audit_event(db, user_id=user.id, action="integration.connection.activate", resource_type="integration_connection", resource_id=connection.id, metadata={"system": connection.system})
    db.commit()
    db.refresh(connection)
    return connection_response(connection)


@router.post("/connections/{connection_id}/deactivate", response_model=IntegrationConnectionResponse)
def deactivate_connection_profile(
    connection_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> IntegrationConnectionResponse:
    connection = _load_owned_connection(db, connection_id, user)
    if is_environment_connection(connection):
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Environment-backed integration profiles are controlled by backend environment variables", headers={"Allow": "GET"})
    connection.status = "inactive"
    connection.updated_at = datetime.now(timezone.utc)
    log_audit_event(db, user_id=user.id, action="integration.connection.deactivate", resource_type="integration_connection", resource_id=connection.id, metadata={"system": connection.system})
    db.commit()
    db.refresh(connection)
    return connection_response(connection)


@router.post("/connections/{connection_id}/test", response_model=IntegrationConnectionTestResponse)
async def test_connection_profile(
    connection_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> IntegrationConnectionTestResponse:
    connection = _load_owned_connection(db, connection_id, user)
    started = datetime.now(timezone.utc)
    try:
        result, latency_ms = await test_connection(connection)
        connection.status = "active"
        connection.last_test_status = "success"
        connection.last_test_message = result.message[:500]
        connection.last_test_latency_ms = latency_ms
        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_metadata = result.metadata
        log_audit_event(
            db,
            user_id=user.id,
            action="integration.connection.test",
            resource_type="integration_connection",
            resource_id=connection.id,
            metadata={"system": connection.system, "status": "success", "latency_ms": latency_ms, "read_only": True},
        )
        db.commit()
        return IntegrationConnectionTestResponse(
            connection_id=connection.id,
            system=connection.system,
            status="success",
            message=result.message,
            latency_ms=latency_ms,
            metadata=result.metadata,
        )
    except (IntegrationServiceError, IntegrationClientError) as error:
        latency_ms = max(0, round((datetime.now(timezone.utc) - started).total_seconds() * 1000))
        connection.status = "error"
        connection.last_test_status = "error"
        connection.last_test_message = _integration_error_message(error)[:500]
        connection.last_test_latency_ms = latency_ms
        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_metadata = None
        log_audit_event(
            db,
            user_id=user.id,
            action="integration.connection.test",
            resource_type="integration_connection",
            resource_id=connection.id,
            metadata={"system": connection.system, "status": "error", "latency_ms": latency_ms, "read_only": True},
        )
        db.commit()
        return IntegrationConnectionTestResponse(
            connection_id=connection.id,
            system=connection.system,
            status="error",
            message=_integration_error_message(error)[:500],
            latency_ms=latency_ms,
            metadata={},
        )


@router.get("/jira/{connection_id}/requirements", response_model=IntegrationAssetResponse)
async def get_jira_requirements(
    connection_id: int,
    db: DbSession,
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=25, ge=1, le=50),
    user: User = Depends(current_user),
) -> IntegrationAssetResponse:
    connection = _load_owned_connection(db, connection_id, user)
    _require_active_connection(connection)
    if connection.system != "jira":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Jira profile")
    started = perf_counter()
    try:
        items, next_page = await list_jira_requirements(connection, page=page, page_size=page_size)
    except (IntegrationServiceError, IntegrationClientError) as error:
        latency_ms = round((perf_counter() - started) * 1000)
        log_audit_event(db, user_id=user.id, action="integration.jira.requirements.read", resource_type="integration_connection", resource_id=connection.id, metadata={"page": page, "page_size": page_size, "status": "error", "latency_ms": latency_ms, "read_only": True})
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_integration_error_message(error)) from error
    log_audit_event(db, user_id=user.id, action="integration.jira.requirements.read", resource_type="integration_connection", resource_id=connection.id, metadata={"page": page, "page_size": page_size, "item_count": len(items), "status": "success", "latency_ms": round((perf_counter() - started) * 1000), "read_only": True})
    db.commit()
    return IntegrationAssetResponse(connection_id=connection.id, system="jira", asset_type="requirements", items=items, next_page=next_page)


@router.post("/jira/fetch-issue", response_model=JiraIssueResponse)
async def fetch_jira_issue_context(
    request: JiraFetchIssueRequest,
    db: DbSession,
    user: User = Depends(current_user),
) -> JiraIssueResponse:
    connection: IntegrationConnection | None = None
    if request.connection_id is not None:
        connection = _load_owned_connection(db, request.connection_id, user)
        if connection.system != "jira":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Jira profile")
        if connection.status == "inactive":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The selected Jira profile is inactive")
    else:
        owned_connection = (
            db.query(IntegrationConnection)
            .filter(
                IntegrationConnection.created_by == user.id,
                IntegrationConnection.system == "jira",
                IntegrationConnection.status.in_(["active", "untested"]),
            )
            .order_by(IntegrationConnection.status.asc(), IntegrationConnection.id.desc())
            .first()
        )
        connection = owned_connection or environment_connection("jira")

    started = perf_counter()
    try:
        issue_dict = await fetch_jira_issue(connection, request.issue_key_or_url)
    except (IntegrationServiceError, IntegrationClientError) as error:
        latency_ms = round((perf_counter() - started) * 1000)
        log_audit_event(
            db,
            user_id=user.id,
            action="integration.jira.issue.read",
            resource_type="integration_connection",
            resource_id=str(connection.id) if connection else "environment",
            metadata={"issue_input": request.issue_key_or_url[:120], "status": "error", "latency_ms": latency_ms, "read_only": True},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_integration_error_message(error)) from error

    latency_ms = round((perf_counter() - started) * 1000)
    log_audit_event(
        db,
        user_id=user.id,
        action="integration.jira.issue.read",
        resource_type="integration_connection",
        resource_id=str(connection.id) if connection else "environment",
        metadata={"issue_key": issue_dict.get("key"), "status": "success", "latency_ms": latency_ms, "read_only": True},
    )
    db.commit()
    return JiraIssueResponse(**issue_dict)


@router.get("/jira/issue/{issue_key}", response_model=JiraIssueResponse)
async def get_jira_issue_by_key(
    issue_key: str,
    db: DbSession,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> JiraIssueResponse:
    return await fetch_jira_issue_context(
        JiraFetchIssueRequest(issue_key_or_url=issue_key, connection_id=connection_id),
        db=db,
        user=user,
    )


@router.get("/qtest/{connection_id}/assets", response_model=IntegrationAssetResponse)
async def get_qtest_assets(
    connection_id: int,
    db: DbSession,
    asset_type: IntegrationAssetType = Query(default="metadata"),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=25, ge=1, le=50),
    user: User = Depends(current_user),
) -> IntegrationAssetResponse:
    connection = _load_owned_connection(db, connection_id, user)
    _require_active_connection(connection)
    if connection.system != "qtest":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a qTest profile")
    started = perf_counter()
    try:
        items, next_page = await list_qtest_assets(connection, asset_type, page=page, page_size=page_size)
    except (IntegrationServiceError, IntegrationClientError) as error:
        latency_ms = round((perf_counter() - started) * 1000)
        log_audit_event(db, user_id=user.id, action="integration.qtest.assets.read", resource_type="integration_connection", resource_id=connection.id, metadata={"asset_type": asset_type, "page": page, "page_size": page_size, "status": "error", "latency_ms": latency_ms, "read_only": True})
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_integration_error_message(error)) from error
    log_audit_event(db, user_id=user.id, action="integration.qtest.assets.read", resource_type="integration_connection", resource_id=connection.id, metadata={"asset_type": asset_type, "page": page, "page_size": page_size, "item_count": len(items), "status": "success", "latency_ms": round((perf_counter() - started) * 1000), "read_only": True})
    db.commit()
    return IntegrationAssetResponse(connection_id=connection.id, system="qtest", asset_type=asset_type, items=items, next_page=next_page)


@router.api_route(
    "/jira/{connection_id}/defects",
    methods=["POST", "PUT", "PATCH", "DELETE"],
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    include_in_schema=False,
)
def block_jira_mutations(connection_id: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Jira write operations are disabled. This integration is read-only.",
        headers={"Allow": "GET"},
    )


@router.post("/jira/issues/{issue_key}/attachments")
async def upload_jira_attachment_endpoint(
    issue_key: str,
    db: DbSession,
    file: UploadFile = File(...),
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    target_conn = None
    if connection_id is not None:
        target_conn = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_conn is None:
        target_conn = environment_connection("jira")
    if target_conn is None:
        target_conn = db.query(IntegrationConnection).filter(IntegrationConnection.system == "jira", IntegrationConnection.status == "active").first()
    if target_conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active Jira connection configured")

    client = _client_for(target_conn)
    if not isinstance(client, JiraClient):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Jira profile")

    file_bytes = await file.read()
    try:
        result = await client.upload_attachment(
            issue_key=issue_key,
            filename=file.filename or "attachment.png",
            content=file_bytes,
            content_type=file.content_type or "application/octet-stream",
        )
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    log_audit_event(
        db,
        user_id=user.id,
        action="integration.jira.attachment.upload",
        resource_type="jira_issue",
        resource_id=issue_key,
        metadata={"filename": file.filename},
    )
    db.commit()
    return result


@router.post("/jira/issues/{issue_key}/links")
async def create_jira_issue_link_endpoint(
    issue_key: str,
    request: JiraLinkRequest,
    db: DbSession,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    target_conn = None
    if connection_id is not None:
        target_conn = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_conn is None:
        target_conn = environment_connection("jira")
    if target_conn is None:
        target_conn = db.query(IntegrationConnection).filter(IntegrationConnection.system == "jira", IntegrationConnection.status == "active").first()
    if target_conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active Jira connection configured")

    client = _client_for(target_conn)
    if not isinstance(client, JiraClient):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Jira profile")

    try:
        result = await client.link_issues(
            inward_key=issue_key,
            outward_key=request.outward_key,
            link_type=request.link_type,
            comment=request.comment,
        )
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    log_audit_event(
        db,
        user_id=user.id,
        action="integration.jira.issue.link",
        resource_type="jira_issue",
        resource_id=issue_key,
        metadata={"outward": request.outward_key, "type": request.link_type},
    )
    db.commit()
    return result


@router.get("/jira/issues/{issue_key}/transitions")
async def get_jira_transitions_endpoint(
    issue_key: str,
    db: DbSession,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    try:
        return await get_jira_issue_transitions(db, issue_key, connection_id=connection_id)
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


@router.post("/jira/issues/{issue_key}/transitions")
async def apply_jira_transition_endpoint(
    issue_key: str,
    request: JiraTransitionRequest,
    db: DbSession,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    try:
        result = await transition_jira_issue(
            db,
            issue_key=issue_key,
            transition_id=request.transition_id,
            comment=request.comment,
            connection_id=connection_id,
        )
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    log_audit_event(
        db,
        user_id=user.id,
        action="integration.jira.issue.transition",
        resource_type="jira_issue",
        resource_id=issue_key,
        metadata={"transition_id": request.transition_id},
    )
    db.commit()
    return result


@router.post("/jira/issues/{issue_key}/comments")
async def post_jira_comment_endpoint(
    issue_key: str,
    request: JiraCommentRequest,
    db: DbSession,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    target_conn = None
    if connection_id is not None:
        target_conn = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if target_conn is None:
        target_conn = environment_connection("jira")
    if target_conn is None:
        target_conn = db.query(IntegrationConnection).filter(IntegrationConnection.system == "jira", IntegrationConnection.status == "active").first()
    if target_conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active Jira connection configured")

    client = _client_for(target_conn)
    if not isinstance(client, JiraClient):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Jira profile")

    try:
        result = await client.add_comment(issue_key, request.comment)
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    log_audit_event(db, user_id=user.id, action="integration.jira.issue.comment", resource_type="jira_issue", resource_id=issue_key)
    db.commit()
    return result


@router.get("/qtest/builds")
async def list_qtest_builds_endpoint(
    release_id: str = Query(...),
    db: DbSession = None,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    try:
        return await get_qtest_builds(db, release_id=release_id, connection_id=connection_id)
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


@router.post("/qtest/builds")
async def create_qtest_build_endpoint(
    request: QTestBuildCreateRequest,
    db: DbSession,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    try:
        result = await register_qtest_build(
            db,
            release_id=request.release_id,
            build_name=request.build_name,
            build_note=request.build_note,
            connection_id=connection_id,
        )
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    log_audit_event(
        db,
        user_id=user.id,
        action="integration.qtest.build.create",
        resource_type="qtest_build",
        resource_id=str(result.get("id")),
        metadata={"release_id": str(request.release_id), "name": request.build_name},
    )
    db.commit()
    return result


@router.post("/qtest/test-runs/{test_run_id}/logs")
async def submit_qtest_log_endpoint(
    test_run_id: str,
    request: QTestSubmitTestLogRequest,
    db: DbSession,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    try:
        result = await submit_qtest_test_run_log(
            db,
            test_run_id=test_run_id,
            status=request.status,
            start_time=request.start_time,
            end_time=request.end_time,
            name=request.name,
            note=request.note,
            steps=request.steps,
            defect_ids=request.defect_ids,
            connection_id=connection_id,
        )
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    log_audit_event(
        db,
        user_id=user.id,
        action="integration.qtest.test_log.submit",
        resource_type="qtest_test_run",
        resource_id=test_run_id,
        metadata={"status": request.status},
    )
    db.commit()
    return result


@router.post("/qtest/test-cases/export")
async def export_qtest_test_case_endpoint(
    request: QTestExportTestCaseRequest,
    db: DbSession,
    connection_id: int | None = Query(default=None),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    try:
        result = await export_test_case_to_qtest(
            db,
            name=request.name,
            description=request.description,
            steps=request.steps,
            parent_id=request.parent_id,
            connection_id=connection_id,
        )
    except (IntegrationClientError, IntegrationServiceError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    log_audit_event(
        db,
        user_id=user.id,
        action="integration.qtest.test_case.export",
        resource_type="qtest_test_case",
        resource_id=str(result.get("id")),
        metadata={"name": request.name},
    )
    db.commit()
    return result


@router.post("/webhooks/jira")
async def receive_jira_webhook(
    payload: dict[str, Any],
    db: DbSession,
) -> dict[str, Any]:
    webhook_event = payload.get("webhookEvent") or payload.get("event") or "unknown"
    issue = payload.get("issue") or {}
    issue_key = issue.get("key")
    return {
        "status": "received",
        "system": "jira",
        "webhook_event": webhook_event,
        "issue_key": issue_key,
    }


@router.post("/webhooks/qtest")
async def receive_qtest_webhook(
    payload: dict[str, Any],
    db: DbSession,
) -> dict[str, Any]:
    event_type = payload.get("event") or payload.get("action") or "unknown"
    return {
        "status": "received",
        "system": "qtest",
        "event_type": event_type,
    }
