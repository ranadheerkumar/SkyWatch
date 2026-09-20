from collections.abc import Generator

try:
	from sqlalchemy import create_engine, event
	from sqlalchemy.engine import Engine
	from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
	_HAS_SQLALCHEMY = True
except ImportError:
	_HAS_SQLALCHEMY = False
	Engine = object  # type: ignore[assignment,misc]
	class DeclarativeBase:  # type: ignore[no-redef]
		metadata = None
	class Session:  # type: ignore[no-redef]
		pass
	def sessionmaker(*args, **kwargs):  # type: ignore[no-redef]
		return lambda: Session()
	def create_engine(*args, **kwargs):  # type: ignore[no-redef]
		return None
	class _DummyEvent:
		@staticmethod
		def listens_for(*args, **kwargs):
			return lambda fn: fn
	event = _DummyEvent()  # type: ignore[assignment]

from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
if _HAS_SQLALCHEMY:
	if DATABASE_URL.startswith("sqlite"):
		engine = create_engine(
			DATABASE_URL,
			connect_args={"check_same_thread": False, "timeout": 30},
			pool_pre_ping=True,
		)
	else:
		engine = create_engine(
			DATABASE_URL,
			pool_size=settings.DB_POOL_SIZE,
			max_overflow=settings.DB_MAX_OVERFLOW,
			pool_timeout=30,
			pool_recycle=1800,
			pool_pre_ping=True,
		)

	@event.listens_for(Engine, "connect")
	def _set_sqlite_pragmas(dbapi_connection, connection_record):
		if DATABASE_URL.startswith("sqlite"):
			cursor = dbapi_connection.cursor()
			try:
				cursor.execute("PRAGMA journal_mode=WAL")
				cursor.execute("PRAGMA synchronous=NORMAL")
				cursor.execute("PRAGMA busy_timeout=15000")
				cursor.execute("PRAGMA cache_size=-64000")
				cursor.execute("PRAGMA temp_store=MEMORY")
			finally:
				cursor.close()

	SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

	class Base(DeclarativeBase):
		pass
else:
	engine = None
	SessionLocal = sessionmaker()

	class Base(DeclarativeBase):  # type: ignore[no-redef]
		pass


def get_db() -> Generator[Session, None, None]:
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()
