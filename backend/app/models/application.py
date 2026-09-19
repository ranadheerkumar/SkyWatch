from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Application(Base):
	__tablename__ = "applications"

	id: Mapped[int] = mapped_column(primary_key=True)
	name: Mapped[str] = mapped_column(String(120), index=True)
	platform: Mapped[str] = mapped_column(String(20))
	target: Mapped[str] = mapped_column(String(2048))
	created_by: Mapped[int] = mapped_column(index=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())