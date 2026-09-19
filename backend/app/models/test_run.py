from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TestRun(Base):
	__tablename__ = "test_runs"

	id: Mapped[str] = mapped_column(String(32), primary_key=True)
	application_id: Mapped[int] = mapped_column(index=True)
	created_by: Mapped[int] = mapped_column(index=True)
	status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
	steps: Mapped[list] = mapped_column(JSON, default=list)
	result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
	log: Mapped[str] = mapped_column(Text, default="")
	batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
	build_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
	trigger_source: Mapped[str | None] = mapped_column(String(50), nullable=True, default="manual")
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
