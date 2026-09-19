from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_audit_event(
    db: Session,
    *,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: str | int | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action[:120],
            resource_type=resource_type[:80],
            resource_id=None if resource_id is None else str(resource_id)[:120],
            metadata_json=(metadata or {}),
        )
    )
