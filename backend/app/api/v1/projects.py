from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.audit import log_audit_event


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(db: DbSession, user: User = Depends(current_user)) -> list[Project]:
    return db.query(Project).filter(Project.created_by == user.id).order_by(Project.updated_at.desc(), Project.id).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: DbSession, user: User = Depends(current_user)) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.created_by == user.id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    request: ProjectCreate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> Project:
    project = Project(
        id=f"{request.name.strip().lower().replace(' ', '-')[:54]}-{uuid4().hex[:12]}",
        name=request.name.strip(),
        description=request.description.strip(),
        lifecycle=request.lifecycle,
        owner=request.owner.strip(),
        created_by=user.id,
    )
    db.add(project)
    db.flush()
    log_audit_event(
        db,
        user_id=user.id,
        action="project.create",
        resource_type="project",
        resource_id=project.id,
        metadata={"name": project.name, "lifecycle": project.lifecycle},
    )
    db.commit()
    db.refresh(project)
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    request: ProjectUpdate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.created_by == user.id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(project, field, value)
    project.updated_at = datetime.now(timezone.utc)
    db.add(project)
    log_audit_event(
        db,
        user_id=user.id,
        action="project.update",
        resource_type="project",
        resource_id=project.id,
        metadata={"fields": sorted(updates)},
    )
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: DbSession,
    user: User = Depends(require_roles("qa_lead", "admin")),
) -> None:
    project = db.query(Project).filter(Project.id == project_id, Project.created_by == user.id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    log_audit_event(
        db,
        user_id=user.id,
        action="project.delete",
        resource_type="project",
        resource_id=project.id,
        metadata={"name": project.name},
    )
    db.delete(project)
    db.commit()
