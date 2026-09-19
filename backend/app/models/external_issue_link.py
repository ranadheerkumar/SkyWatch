from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExternalIssueLink(Base):
    __tablename__ = "external_issue_links"
    __table_args__ = (
        UniqueConstraint("connection_id", "idempotency_key", name="uq_external_issue_link_connection_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("integration_connections.id"), index=True)
    defect_id: Mapped[int | None] = mapped_column(ForeignKey("defects.id"), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("test_runs.id"), nullable=True, index=True)
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id"), nullable=True, index=True)
    system: Mapped[str] = mapped_column(String(20), index=True)
    external_key: Mapped[str] = mapped_column(String(120))
    external_url: Mapped[str] = mapped_column(String(2048))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
