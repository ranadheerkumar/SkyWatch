import os
from pathlib import Path
from tempfile import gettempdir
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.dependencies import DbSession, current_user
from app.models.case_execution import CaseExecution
from app.models.test_run import TestRun
from app.models.user import User

router = APIRouter(prefix="/evidence", tags=["evidence"])

SCREENSHOT_DIR = Path(gettempdir()) / "ai-qa-engine-runs"


def _artifact_filename(path: str | None) -> str:
    return os.path.basename(path) if path else ""


def _run_references_artifact(run: TestRun, filename: str) -> bool:
    result = run.result or {}
    paths = [_artifact_filename(result.get("screenshot_path"))]
    for key in ("artifacts", "step_artifacts"):
        paths.extend(
            _artifact_filename(artifact.get("path"))
            for artifact in result.get(key) or []
            if isinstance(artifact, dict)
        )
    return filename in {path for path in paths if path}


def _artifact_url(run_id: str, filename: str) -> str:
    return f"/api/v1/evidence/file/{quote(filename, safe='')}?run_id={quote(run_id, safe='')}"


@router.get("/gallery")
def get_evidence_gallery(
    db: DbSession,
    application_id: int | None = None,
    user: User = Depends(current_user),
) -> dict:
    query = (
        db.query(TestRun)
        .filter(TestRun.created_by == user.id)
        .order_by(TestRun.created_at.desc())
    )
    if application_id:
        query = query.filter(TestRun.application_id == application_id)
    runs = query.limit(50).all()

    screenshots = []
    videos = []

    for run in runs:
        res = run.result or {}
        artifacts = res.get("artifacts") or []
        for art in artifacts:
            art_type = art.get("type")
            art_path = art.get("path", "")
            art_label = art.get("label", "")
            filename = os.path.basename(art_path) if art_path else f"{run.id}.png"
            if art_type == "screenshot":
                screenshots.append({
                    "run_id": run.id,
                    "application_id": run.application_id,
                    "label": art_label or "Execution Screenshot",
                    "file_url": _artifact_url(run.id, filename),
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "status": run.status,
                })
            elif art_type == "video":
                videos.append({
                    "run_id": run.id,
                    "application_id": run.application_id,
                    "label": art_label or "Execution Recording",
                    "file_url": _artifact_url(run.id, filename),
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "status": run.status,
                })

        # Also inspect direct screenshot_path
        if res.get("screenshot_path") and not any(s["run_id"] == run.id for s in screenshots):
            filename = os.path.basename(res["screenshot_path"])
            screenshots.append({
                "run_id": run.id,
                "application_id": run.application_id,
                "label": "End-of-run Screenshot",
                "file_url": _artifact_url(run.id, filename),
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "status": run.status,
            })

    return {
        "total_screenshots": len(screenshots),
        "total_videos": len(videos),
        "screenshots": screenshots,
        "videos": videos,
    }


@router.get("/file/{filename}")
def stream_evidence_file(
    filename: str,
    db: DbSession,
    run_id: str = Query(min_length=1, max_length=64),
    user: User = Depends(current_user),
):
    safe_filename = os.path.basename(filename)
    if safe_filename != filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence artifact file not found")

    run = (
        db.query(TestRun)
        .filter(TestRun.id == run_id, TestRun.created_by == user.id)
        .first()
    )
    if not run or not _run_references_artifact(run, safe_filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence artifact file not found")

    candidate_paths = (
        SCREENSHOT_DIR / safe_filename,
        SCREENSHOT_DIR / "videos" / safe_filename,
        SCREENSHOT_DIR / "traces" / safe_filename,
    )
    target_file = next(
        (candidate for candidate in candidate_paths if candidate.exists() and candidate.is_file()),
        None,
    )

    if not target_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence artifact file not found")

    media_type = "image/png"
    if safe_filename.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif safe_filename.endswith(".webm"):
        media_type = "video/webm"
    elif safe_filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif safe_filename.endswith(".zip"):
        media_type = "application/zip"

    return FileResponse(path=str(target_file), media_type=media_type, filename=safe_filename)
