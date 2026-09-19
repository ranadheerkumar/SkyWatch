from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    preconditions: Mapped[str | None] = mapped_column(Text, default=None)
    steps: Mapped[str] = mapped_column(Text, default="")
    expected_result: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    category: Mapped[str] = mapped_column(String(40), default="positive", index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    automation_status: Mapped[str] = mapped_column(String(40), default="automated", index=True)
    test_data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
