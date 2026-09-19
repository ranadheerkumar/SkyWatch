from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.api.dependencies import DbSession, require_roles
from app.models.ai_generation_job import AIGenerationJob
from app.models.application import Application
from app.models.user import User
from app.schemas.test_case import (
    AIDocumentAnalysisResponse,
    AIDocumentFileAnalysis,
    AIGenerationJobResponse,
    AITestCaseGenerateRequest,
)
from app.services.ai_generation_jobs import AIQueueUnavailableError, enqueue_ai_generation
from app.services.document_analysis import (
    DocumentAnalysisError,
    MAX_DOCUMENT_BYTES,
    MAX_UPLOAD_DOCUMENTS,
    analyze_document,
    build_document_context,
    unpack_archive_documents,
)
from app.services.ai_generation_pipeline import initial_workflow_result
from app.services.guardrails import GuardrailViolationError, sanitize_and_validate_prompt, validate_target_url
from app.services.self_learning import SelfLearningEngine

router = APIRouter(prefix="/ai-generation", tags=["ai-generation"])


@router.post("/documents/analyze", response_model=AIDocumentAnalysisResponse)
async def analyze_generation_documents(
    files: list[UploadFile] = File(...),
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> AIDocumentAnalysisResponse:
    del user
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one requirement document")
    if len(files) > MAX_UPLOAD_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"Upload no more than {MAX_UPLOAD_DOCUMENTS} documents at a time")

    unpacked_items: list[tuple[str, bytes]] = []
    for upload in files:
        filename = upload.filename or "uploaded-document"
        content = await upload.read(MAX_DOCUMENT_BYTES + 1)
        try:
            if filename.lower().endswith(".zip"):
                unpacked = unpack_archive_documents(filename, content)
                unpacked_items.extend(unpacked)
            else:
                unpacked_items.append((filename, content))
        finally:
            await upload.close()

    if not unpacked_items:
        raise HTTPException(status_code=400, detail="No readable documents found in the uploaded files")

    analyses = []
    for doc_name, doc_bytes in unpacked_items[:MAX_UPLOAD_DOCUMENTS * 3]:
        try:
            analyses.append(analyze_document(doc_name, doc_bytes))
        except DocumentAnalysisError as error:
            if len(unpacked_items) == 1:
                raise HTTPException(status_code=400, detail=f"{doc_name}: {error}") from error
            continue

    if not analyses:
        raise HTTPException(status_code=400, detail="None of the uploaded documents could be analyzed.")

    modules: list[str] = []
    seen_modules: set[str] = set()
    warnings: list[str] = []
    for analysis in analyses:
        for module in analysis.modules_identified:
            key = module.casefold()
            if key not in seen_modules:
                seen_modules.add(key)
                modules.append(module)
        warnings.extend(f"{analysis.filename}: {warning}" for warning in analysis.warnings)

    return AIDocumentAnalysisResponse(
        files=[AIDocumentFileAnalysis(**analysis.response_dict()) for analysis in analyses],
        total_files=len(analyses),
        total_pages=sum(analysis.pages_parsed for analysis in analyses),
        requirements_found=sum(analysis.requirements_found for analysis in analyses),
        features_identified=sum(analysis.features_identified for analysis in analyses),
        modules_identified=modules,
        business_rules_found=sum(analysis.business_rules_found for analysis in analyses),
        workflows_discovered=sum(analysis.workflows_discovered for analysis in analyses),
        extracted_characters=sum(analysis.extracted_characters for analysis in analyses),
        context_text=build_document_context(analyses),
        warnings=warnings[:40],
    )


@router.post("/jobs", response_model=AIGenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_generation_job(
    request: AITestCaseGenerateRequest,
    http_request: Request,
    db: DbSession,
    application_id: int,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> AIGenerationJob:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if request.min_steps_per_case > request.max_steps_per_case:
        raise HTTPException(status_code=400, detail="min_steps_per_case cannot be greater than max_steps_per_case")

    # Safety and Injection Guardrails
    try:
        sanitize_and_validate_prompt(request.prompt)
        if request.target_url:
            validate_target_url(request.target_url)
    except GuardrailViolationError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    job = AIGenerationJob(
        id=str(uuid4()),
        application_id=application_id,
        created_by=user.id,
        request_payload=request.model_dump(mode="json"),
        provider=request.provider,
        model=request.model,
        correlation_id=getattr(http_request.state, "correlation_id", None),
        result=initial_workflow_result(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        enqueue_ai_generation(job.id)
    except AIQueueUnavailableError as error:
        job.status = "failed"
        job.phase = "failed"
        job.error = f"Queue unavailable: {type(error).__name__}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI generation queue is unavailable. Start Redis or select the local queue explicitly.",
        ) from error
    return job


@router.get("/jobs/{job_id}", response_model=AIGenerationJobResponse)
def get_generation_job(
    job_id: str,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> AIGenerationJob:
    job = db.query(AIGenerationJob).filter(AIGenerationJob.id == job_id, AIGenerationJob.created_by == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


@router.get("/self-learning/{application_id}")
def get_self_learning_metrics(
    application_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> dict:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    metrics = SelfLearningEngine.get_telemetry_metrics(application_id)
    return metrics
