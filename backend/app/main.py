import asyncio
import logging
import platform
import time
from uuid import uuid4
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging, correlation_id_context, set_correlation_id
from app.core.rate_limiter import RateLimiterEngine, RateLimitMiddleware
from app.core.security import hash_password
from app.models import User


# Windows subprocess support for asyncio
if platform.system() == "Windows":
	asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
configure_logging()
logger = logging.getLogger("ai-qa-engine.api")


def ensure_initial_admin() -> None:
	from app.core.database import Base, engine
	Base.metadata.create_all(bind=engine)
	with SessionLocal() as db:
		admin_email = settings.INITIAL_ADMIN_EMAIL
		admin_password = settings.INITIAL_ADMIN_PASSWORD
		admin_user = db.query(User).filter(User.email == admin_email).first()
		if admin_user is None:
			admin_user = User(email=admin_email, password_hash=hash_password(admin_password), role="admin")
			db.add(admin_user)
			db.commit()
			db.refresh(admin_user)
		elif (admin_user.role or "").strip().lower() != "admin":
			admin_user.role = "admin"
			db.add(admin_user)
			db.commit()

		from app.models.application import Application
		if db.query(Application).filter(Application.created_by == admin_user.id).first() is None:
			default_app = Application(
				name="SkyWatch Default App",
				platform="web",
				target="https://example.com",
				created_by=admin_user.id,
			)
			db.add(default_app)
			db.commit()


openapi_tags = [
	{"name": "Auth", "description": "Authentication, token verification, and user management"},
	{"name": "Applications", "description": "Target applications and platform configurations"},
	{"name": "Test Cases", "description": "Test case authoring, retrieval, updates, and smart data generation"},
	{"name": "AI Generation", "description": "Multi-provider AI test generation, vision discovery, and synthesis"},
	{"name": "Execution", "description": "Playwright test execution, step runner, and Allure exports"},
	{"name": "Defects", "description": "Defect tracking, automatic root cause analysis, and Jira/Linear sync"},
	{"name": "Healing & Agents", "description": "Autonomous self-healing, heuristic repairs, and DOM resolution"},
	{"name": "Observability", "description": "System health, live telemetry, execution metrics, and rate limiting"},
	{"name": "Settings", "description": "AI provider configuration, connection testing, and runtime settings"},
]

from starlette.middleware.gzip import GZipMiddleware

app = FastAPI(
	title=settings.APP_NAME,
	version=settings.APP_VERSION,
	description="SkyWatch Autonomous Enterprise QA Platform — AI-Driven Test Generation, Self-Healing Execution & Observability Engine",
	openapi_tags=openapi_tags,
	docs_url="/docs",
	redoc_url="/redoc",
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
	CORSMiddleware,
	allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?",
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
	expose_headers=[
		"X-SkyWatch-AI-Generation-Mode",
		"X-SkyWatch-AI-Provider",
		"X-SkyWatch-AI-Provider-Configured",
		"X-SkyWatch-AI-Generation-Note",
		"X-AI-QA-Engine-AI-Generation-Mode",
		"X-AI-QA-Engine-AI-Provider",
		"X-AI-QA-Engine-AI-Provider-Configured",
		"X-AI-QA-Engine-AI-Generation-Note",
	],
)
app.include_router(api_router)

# Rate Limiting Middleware
_rate_limiter = RateLimiterEngine(enabled=settings.RATE_LIMIT_ENABLED)
app.add_middleware(RateLimitMiddleware, rate_limiter=_rate_limiter)

# Wire rate limiter to observability endpoint
from app.api.v1.observability import set_rate_limiter_engine
set_rate_limiter_engine(_rate_limiter)

ensure_initial_admin()


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
	response = await call_next(request)
	response.headers["X-Content-Type-Options"] = "nosniff"
	response.headers["X-Frame-Options"] = "DENY"
	response.headers["X-XSS-Protection"] = "1; mode=block"
	response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
	if request.headers.get("access-control-request-private-network") == "true":
		response.headers["Access-Control-Allow-Private-Network"] = "true"
	return response


@app.middleware("http")
async def request_metrics_middleware(request: Request, call_next):
	correlation_id = request.headers.get("X-Correlation-ID", "").strip() or str(uuid4())
	token = set_correlation_id(correlation_id)
	start = time.perf_counter()
	request.state.correlation_id = correlation_id
	try:
		response = await call_next(request)
		duration_ms = round((time.perf_counter() - start) * 1000, 2)
		logger.info(
			"request_completed method=%s path=%s status=%s duration_ms=%.2f",
			request.method,
			request.url.path,
			response.status_code,
			duration_ms,
		)
		response.headers["X-Correlation-ID"] = correlation_id
		response.headers["X-Request-Duration-Ms"] = str(duration_ms)
		return response
	finally:
		correlation_id_context.reset(token)


@app.get("/health")
@app.head("/health", include_in_schema=False)
async def health() -> dict:
	db_status = "healthy"
	try:
		from sqlalchemy import text
		with SessionLocal() as db:
			db.execute(text("SELECT 1"))
	except Exception as error:
		logger.warning("Health check DB probe failed: %s", error)
		db_status = f"unhealthy: {error}"

	return {
		"status": "ok" if db_status == "healthy" else "degraded",
		"database": db_status,
		"version": settings.APP_VERSION,
		"environment": settings.ENVIRONMENT,
	}
