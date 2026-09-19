from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("created_by", "system", "name", name="uq_integration_connection_owner_system_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    system: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(2048))
    project_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    username: Mapped[str | None] = mapped_column(String(320), nullable=True)
    auth_type: Mapped[str] = mapped_column(String(40), default="api_token")
    environment: Mapped[str | None] = mapped_column(String(120), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="untested", index=True)
    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_test_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
