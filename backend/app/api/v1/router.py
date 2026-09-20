from fastapi import APIRouter

from app.api.v1.agent_tasks import router as agent_tasks_router
from app.api.v1.agents import router as agents_router
from app.api.v1.ai_generation import router as ai_generation_router
from app.api.v1.applications import router as applications_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.capabilities import router as capabilities_router
from app.api.v1.defects import router as defects_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.execution import router as execution_router
from app.api.v1.execution_plans import router as execution_plans_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.mobile import router as mobile_router
from app.api.v1.observability import router as observability_router
from app.api.v1.orchestrator import router as orchestrator_router
from app.api.v1.projects import router as projects_router
from app.api.v1.reports import router as reports_router
from app.api.v1.settings import router as settings_router
from app.api.v1.test_cases import router as test_cases_router
from app.api.v1.test_data import router as test_data_router
from app.api.v1.test_suites import router as test_suites_router


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(capabilities_router)
api_router.include_router(auth_router)
api_router.include_router(orchestrator_router)
api_router.include_router(observability_router)
api_router.include_router(agent_tasks_router)
api_router.include_router(ai_generation_router)
api_router.include_router(audit_router)
api_router.include_router(applications_router)
api_router.include_router(test_cases_router)
api_router.include_router(test_suites_router)
api_router.include_router(execution_plans_router)
api_router.include_router(integrations_router)
api_router.include_router(test_data_router)
api_router.include_router(agents_router)
api_router.include_router(evidence_router)
api_router.include_router(settings_router)
api_router.include_router(execution_router)
api_router.include_router(defects_router)
api_router.include_router(mobile_router)
api_router.include_router(projects_router)
api_router.include_router(reports_router)
