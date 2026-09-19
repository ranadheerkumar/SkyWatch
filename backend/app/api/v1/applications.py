import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.application import Application
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate
from app.services.audit import log_audit_event
from app.services.test_execution import validate_target


router = APIRouter(prefix="/applications", tags=["applications"])
UPLOAD_DIRECTORY = Path(__file__).resolve().parents[3] / "uploads"


@router.get("", response_model=list[ApplicationResponse])
def list_applications(db: DbSession, user: User = Depends(current_user)) -> list[Application]:
	return db.query(Application).filter(Application.created_by == user.id).order_by(Application.id.desc()).all()


@router.post("", response_model=ApplicationResponse, status_code=201)
def create_application(request: ApplicationCreate, db: DbSession, user: User = Depends(require_roles("tester", "qa_lead", "admin"))) -> Application:
	if request.platform == "web":
		try:
			validate_target(request.target)
		except ValueError as error:
			raise HTTPException(status_code=400, detail=str(error)) from error
	elif request.target.startswith(("http://", "https://")):
		raise HTTPException(status_code=400, detail="Mobile applications require an uploaded package")
	application = Application(name=request.name, platform=request.platform, target=request.target, created_by=user.id)
	db.add(application)
	db.flush()
	log_audit_event(
		db,
		user_id=user.id,
		action="application.create",
		resource_type="application",
		resource_id=application.id,
		metadata={"platform": request.platform},
	)
	db.commit()
	db.refresh(application)
	return application


@router.post("/mobile", response_model=ApplicationResponse, status_code=201)
async def create_mobile_application(
	db: DbSession,
	user: User = Depends(require_roles("tester", "qa_lead", "admin")),
	name: str = Form(...),
	platform: str = Form(...),
	file: UploadFile = File(...),
) -> Application:
	if platform not in {"android", "ios"}:
		raise HTTPException(status_code=400, detail="Mobile platform must be android or ios")
	filename = file.filename or ""
	expected_extension = ".apk" if platform == "android" else ".ipa"
	if not filename.lower().endswith(expected_extension):
		raise HTTPException(status_code=400, detail=f"Choose a {expected_extension} file")
	if not name.strip():
		raise HTTPException(status_code=400, detail="Application name is required")
	max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
	content = await file.read(max_upload_bytes + 1)
	if len(content) > max_upload_bytes:
		raise HTTPException(status_code=413, detail="Mobile package exceeds the configured upload limit")
	UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
	stored_name = f"{uuid4().hex}{expected_extension}"
	(UPLOAD_DIRECTORY / stored_name).write_bytes(content)
	application = Application(name=name.strip(), platform=platform, target=f"uploads/{stored_name}", created_by=user.id)
	db.add(application)
	db.flush()
	log_audit_event(
		db,
		user_id=user.id,
		action="application.create.mobile",
		resource_type="application",
		resource_id=application.id,
		metadata={"platform": platform, "artifact": stored_name},
	)
	db.commit()
	db.refresh(application)
	return application


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: int, db: DbSession, user: User = Depends(require_roles("qa_lead", "admin"))) -> None:
	application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
	if not application:
		raise HTTPException(status_code=404, detail="Application not found")
	log_audit_event(
		db,
		user_id=user.id,
		action="application.delete",
		resource_type="application",
		resource_id=application.id,
		metadata={"name": application.name},
	)
	db.delete(application)
	db.commit()


@router.put("/{application_id}", response_model=ApplicationResponse)
def update_application(
	application_id: int,
	request: ApplicationUpdate,
	db: DbSession,
	user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> Application:
	application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
	if not application:
		raise HTTPException(status_code=404, detail="Application not found")
	if application.platform == "web":
		try:
			validate_target(request.target)
		except ValueError as error:
			raise HTTPException(status_code=400, detail=str(error)) from error
	elif request.target.startswith(("http://", "https://")):
		raise HTTPException(status_code=400, detail="Mobile applications require an uploaded package")
	application.name = request.name.strip()
	application.target = request.target.strip()
	db.add(application)
	log_audit_event(
		db,
		user_id=user.id,
		action="application.update",
		resource_type="application",
		resource_id=application.id,
		metadata={"name": application.name, "platform": application.platform},
	)
	db.commit()
	db.refresh(application)
	return application
