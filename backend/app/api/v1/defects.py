from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.defect import Defect
from app.models.application import Application
from app.models.external_issue_link import ExternalIssueLink
from app.models.user import User
from app.schemas.defect import (
    DefectCreate,
    DefectExportRequest,
    DefectExportResponse,
    DefectResponse,
    DefectUpdate,
    ExternalLinkItem,
)
from app.services.audit import log_audit_event
from app.services.integration_service import (
    IntegrationServiceError,
    export_defect_to_jira,
    export_defect_to_qtest,
)

router = APIRouter(prefix="/defects", tags=["defects"])


def _populate_defect_links(db: DbSession, defects: list[Defect]) -> list[DefectResponse]:
    if not defects:
        return []
    defect_ids = [d.id for d in defects]
    links = db.query(ExternalIssueLink).filter(ExternalIssueLink.defect_id.in_(defect_ids)).all()
    links_by_defect: dict[int, list[ExternalLinkItem]] = {}
    for link in links:
        if link.defect_id:
            links_by_defect.setdefault(link.defect_id, []).append(
                ExternalLinkItem(
                    id=link.id,
                    system=link.system,
                    external_key=link.external_key,
                    external_url=link.external_url,
                )
            )

    results: list[DefectResponse] = []
    for d in defects:
        resp = DefectResponse(
            id=d.id,
            title=d.title,
            description=d.description,
            priority=d.priority,
            severity=d.severity,
            status=d.status,
            application_id=d.application_id,
            created_by=d.created_by,
            external_links=links_by_defect.get(d.id, []),
        )
        results.append(resp)
    return results


@router.get("", response_model=list[DefectResponse])
def list_defects(db: DbSession, user: User = Depends(current_user)) -> list[DefectResponse]:
    defects = db.query(Defect).filter(Defect.created_by == user.id).order_by(Defect.id.desc()).all()
    return _populate_defect_links(db, defects)


@router.post("", response_model=DefectResponse, status_code=201)
def create_defect(
    request: DefectCreate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> DefectResponse:
    if request.application_id is not None:
        application = db.query(Application).filter(
            Application.id == request.application_id,
            Application.created_by == user.id,
        ).first()
        if not application:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    defect = Defect(**request.model_dump(), created_by=user.id)
    db.add(defect)
    db.flush()
    log_audit_event(
        db,
        user_id=user.id,
        action="defect.create",
        resource_type="defect",
        resource_id=defect.id,
        metadata={"application_id": request.application_id},
    )
    db.commit()
    db.refresh(defect)
    return _populate_defect_links(db, [defect])[0]


@router.put("/{defect_id}", response_model=DefectResponse)
def update_defect(
    defect_id: int,
    request: DefectUpdate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> DefectResponse:
    defect = db.query(Defect).filter(Defect.id == defect_id, Defect.created_by == user.id).first()
    if not defect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Defect not found")
    updates = request.model_dump(exclude_unset=True)
    if "application_id" in updates and updates["application_id"] is not None:
        application = db.query(Application).filter(
            Application.id == updates["application_id"],
            Application.created_by == user.id,
        ).first()
        if not application:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    for field, value in updates.items():
        setattr(defect, field, value.strip() if isinstance(value, str) else value)
    defect.updated_at = datetime.now(timezone.utc)
    db.add(defect)
    log_audit_event(
        db,
        user_id=user.id,
        action="defect.update",
        resource_type="defect",
        resource_id=defect.id,
        metadata={"fields": sorted(updates)},
    )
    db.commit()
    db.refresh(defect)
    return _populate_defect_links(db, [defect])[0]


@router.post("/{defect_id}/export-jira", response_model=DefectExportResponse)
async def export_jira_defect(
    defect_id: int,
    request: DefectExportRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> DefectExportResponse:
    try:
        res = await export_defect_to_jira(
            db,
            defect_id=defect_id,
            user_id=user.id,
            connection_id=request.connection_id,
            project_key=request.project_key,
            issue_type=request.issue_type,
            priority=request.priority,
            labels=request.labels,
        )
        log_audit_event(
            db,
            user_id=user.id,
            action="defect.export_jira",
            resource_type="defect",
            resource_id=defect_id,
            metadata={"jira_key": res["external_key"]},
        )
        return DefectExportResponse(**res)
    except IntegrationServiceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/{defect_id}/export-qtest", response_model=DefectExportResponse)
async def export_qtest_defect(
    defect_id: int,
    request: DefectExportRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> DefectExportResponse:
    try:
        res = await export_defect_to_qtest(
            db,
            defect_id=defect_id,
            user_id=user.id,
            connection_id=request.connection_id,
        )
        log_audit_event(
            db,
            user_id=user.id,
            action="defect.export_qtest",
            resource_type="defect",
            resource_id=defect_id,
            metadata={"qtest_key": res["external_key"]},
        )
        return DefectExportResponse(**res)
    except IntegrationServiceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.delete("/{defect_id}", status_code=204)
def delete_defect(defect_id: int, db: DbSession, user: User = Depends(require_roles("qa_lead", "admin"))) -> None:
    defect = db.query(Defect).filter(Defect.id == defect_id, Defect.created_by == user.id).first()
    if not defect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Defect not found")
    log_audit_event(
        db,
        user_id=user.id,
        action="defect.delete",
        resource_type="defect",
        resource_id=defect_id,
    )
    db.delete(defect)
    db.commit()
