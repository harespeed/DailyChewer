"""Ingest preview and save routes."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from backend.api.schemas import IngestOptimizeRequest, IngestOptimizeTaskResponse, IngestSaveRequest
from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.config import SUPPORTED_INPUT_FORMATS, load_settings
from dailychewer_backend.db.repositories import IngestOptimizeTaskRepository, UploadedFileRepository
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.optimize_task_service import (
    build_optimize_task_result,
    drain_optimize_task_queue,
)
from dailychewer_backend.services.ingest_service import IngestService


router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _uploads_dir(user_id: str) -> Path:
    settings = load_settings()
    target = settings.data_dir / "users" / user_id / "uploads" / "tmp"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _build_preview_response(result) -> dict:
    """Normalize one ingest preview result for API callers."""

    payload = build_optimize_task_result(upload_id="", result=result)
    payload["upload_id"] = None
    return payload


@router.post("/preview")
async def preview_ingest(request: Request, current_user=Depends(get_current_user)) -> dict:
    """Upload one report file and return an optimized preview without saving."""

    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail='File upload support requires "python-multipart" to be installed.',
        ) from exc

    file = form.get("file")
    date = form.get("date")
    project = form.get("project")
    tags = form.getlist("tags")
    no_questions = str(form.get("no_questions", "false")).strip().lower() in {"1", "true", "yes", "y"}
    if file is None or not hasattr(file, "filename"):
        raise HTTPException(status_code=400, detail="Missing upload file.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_INPUT_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    upload_id = f"{uuid4().hex}{suffix}"
    temp_path = _uploads_dir(current_user.id) / upload_id
    content = await file.read()
    temp_path.write_bytes(content)
    settings = load_settings()
    if settings.database_url:
        session_factory = get_session_maker(settings)
        with session_factory() as session:
            UploadedFileRepository(session).create_uploaded_file(
                user_id=current_user.id,
                original_filename=file.filename or upload_id,
                stored_file_path=str(temp_path),
                purpose="upload_tmp",
                content_type=getattr(file, "content_type", None),
                size_bytes=len(content),
            )
    try:
        result = IngestService(
            user_context=UserContext(
                user_id=current_user.id,
                username=current_user.username,
                storage_mode="database",
            )
        ).ingest_report(
            file_path=temp_path,
            date=date,
            project=project,
            tags=tags,
            save=False,
            no_questions=no_questions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return build_optimize_task_result(upload_id=upload_id, result=result)


@router.post("/optimize")
def optimize_preview(
    payload: IngestOptimizeRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
) -> IngestOptimizeTaskResponse:
    """Queue one preview re-optimization task and return task metadata."""

    base_upload_dir = _uploads_dir(current_user.id).resolve()
    temp_path = (base_upload_dir / payload.upload_id).resolve()
    if not temp_path.is_relative_to(base_upload_dir):
        raise HTTPException(status_code=403, detail="Forbidden upload path.")
    if not temp_path.exists():
        raise HTTPException(status_code=404, detail="Upload not found.")
    settings = load_settings()
    session_factory = get_session_maker(settings)
    with session_factory() as session:
        task = IngestOptimizeTaskRepository(session).create_task(
            user_id=current_user.id,
            upload_id=payload.upload_id,
            request_payload=payload.model_dump(),
        )
    background_tasks.add_task(
        drain_optimize_task_queue,
        current_user.id,
        current_user.username,
        payload.upload_id,
        settings.project_root,
    )
    return IngestOptimizeTaskResponse(
        task_id=task.id,
        upload_id=task.upload_id,
        sequence=task.request_sequence,
        status=task.status,
    )


@router.get("/optimize-tasks/{task_id}")
def get_optimize_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
) -> IngestOptimizeTaskResponse:
    """Return the current status and final result for one queued optimize task."""

    settings = load_settings()
    session_factory = get_session_maker(settings)
    with session_factory() as session:
        task = IngestOptimizeTaskRepository(session).get_task(user_id=current_user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Optimize task not found.")
    if task.status == "pending":
        background_tasks.add_task(
            drain_optimize_task_queue,
            current_user.id,
            current_user.username,
            task.upload_id,
            settings.project_root,
        )
    return IngestOptimizeTaskResponse(
        task_id=task.id,
        upload_id=task.upload_id,
        sequence=task.request_sequence,
        status=task.status,
        result=task.result_payload,
        error_message=task.error_message,
    )

@router.post("/save")
def save_ingest(payload: IngestSaveRequest, current_user=Depends(get_current_user)) -> dict:
    """Persist one previously uploaded report and return saved paths."""

    base_upload_dir = _uploads_dir(current_user.id).resolve()
    temp_path = (base_upload_dir / payload.upload_id).resolve()
    if not temp_path.is_relative_to(base_upload_dir):
        raise HTTPException(status_code=403, detail="Forbidden upload path.")
    if not temp_path.exists():
        raise HTTPException(status_code=404, detail="Upload not found.")
    try:
        result = IngestService(
            user_context=UserContext(
                user_id=current_user.id,
                username=current_user.username,
                storage_mode="database",
            )
        ).ingest_report(
            file_path=temp_path,
            date=payload.date,
            project=payload.project,
            tags=payload.tags,
            save=True,
            no_questions=False,
            user_answers=payload.user_answers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "raw_file": result.raw_file,
        "optimized_file": result.optimized_file,
        "index_item": result.index_item.model_dump() if result.index_item else None,
    }
