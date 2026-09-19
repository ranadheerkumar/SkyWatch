from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_roles
from app.models.user import User
from app.schemas.execution import MobileExecutionRequest
from app.services.mobile_execution import MobileRunnerNotConfigured, execute_mobile_target


router = APIRouter(prefix="/mobile", tags=["mobile"])


@router.post("/run")
async def run_mobile(request: MobileExecutionRequest, user: User = Depends(require_roles("tester", "qa_lead", "admin"))) -> dict[str, str]:
	try:
		return await execute_mobile_target(request)
	except (ValueError, FileNotFoundError, MobileRunnerNotConfigured) as error:
		raise HTTPException(status_code=422, detail=str(error)) from error