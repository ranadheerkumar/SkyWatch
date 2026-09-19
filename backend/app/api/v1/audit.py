from fastapi import APIRouter, Depends, Query

from app.api.dependencies import DbSession, require_roles
from app.models.audit_log import AuditLog
from app.models.user import User


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_events(
    db: DbSession,
    _: User = Depends(require_roles("qa_lead", "admin")),
    user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict]:
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action.strip())
    rows = query.limit(limit).all()
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
