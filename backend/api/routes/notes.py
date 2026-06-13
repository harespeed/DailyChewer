"""Daily note routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from backend.api.schemas import DailyNoteCreateRequest, DailyNoteRangeWeeklyRequest, DailyNoteRangeWeeklyTaskResponse, DailyNoteUpdateRequest
from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.config import load_settings
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.note_service import DailyNoteService
from dailychewer_backend.services.note_task_service import (
    create_note_weekly_range_task,
    get_note_weekly_range_task,
    run_note_weekly_range_task,
    serialize_note_weekly_range_task,
)


router = APIRouter(prefix="/api/notes", tags=["notes"])


def _service(current_user) -> DailyNoteService:
    return DailyNoteService(
        user_context=UserContext(
            user_id=current_user.id,
            username=current_user.username,
            storage_mode="database",
        )
    )


@router.get("")
def list_notes(month: str, current_user=Depends(get_current_user)) -> dict:
    """List notes and calendar summaries for one month."""

    try:
        return _service(current_user).list_month(month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("")
def create_note(payload: DailyNoteCreateRequest, current_user=Depends(get_current_user)) -> dict:
    """Create one note for the current or provided period."""

    try:
        record = _service(current_user).create_note(
            content=payload.content,
            note_date=payload.date,
            period=payload.period,
        )
        return DailyNoteService.serialize_note(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/generate-weekly-range")
def generate_weekly_from_note_range(payload: DailyNoteRangeWeeklyRequest, current_user=Depends(get_current_user)) -> dict:
    """Generate and save a weekly/stage report for an explicit note date range."""

    try:
        return _service(current_user).generate_weekly_range(
            from_date=payload.from_date,
            to_date=payload.to_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/generate-weekly-range-tasks")
def create_weekly_range_task(
    payload: DailyNoteRangeWeeklyRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
) -> DailyNoteRangeWeeklyTaskResponse:
    """Queue a long-running weekly/stage report generation task."""

    task = create_note_weekly_range_task(
        user_id=current_user.id,
        username=current_user.username,
        from_date=payload.from_date,
        to_date=payload.to_date,
    )
    settings = load_settings()
    background_tasks.add_task(run_note_weekly_range_task, task.id, settings.project_root)
    return DailyNoteRangeWeeklyTaskResponse(**serialize_note_weekly_range_task(task))


@router.get("/generate-weekly-range-tasks/{task_id}")
def get_weekly_range_task(task_id: str, current_user=Depends(get_current_user)) -> DailyNoteRangeWeeklyTaskResponse:
    """Return the current status and result for one note stage-report task."""

    task = get_note_weekly_range_task(user_id=current_user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Stage report task not found.")
    return DailyNoteRangeWeeklyTaskResponse(**serialize_note_weekly_range_task(task))


@router.get("/{note_date}")
def list_notes_for_date(note_date: str, current_user=Depends(get_current_user)) -> dict:
    """List all notes for one date."""

    try:
        return _service(current_user).list_date(note_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{note_id}")
def update_note(note_id: str, payload: DailyNoteUpdateRequest, current_user=Depends(get_current_user)) -> dict:
    """Update one note."""

    try:
        record = _service(current_user).update_note(
            note_id=note_id,
            content=payload.content,
            period=payload.period,
        )
        return DailyNoteService.serialize_note(record)
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "便条不存在。" else 400, detail=str(exc)) from exc


@router.delete("/{note_id}")
def delete_note(note_id: str, current_user=Depends(get_current_user)) -> dict:
    """Delete one note."""

    try:
        _service(current_user).delete_note(note_id)
        return {"deleted": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{note_date}/generate-daily")
def generate_daily_from_notes(note_date: str, current_user=Depends(get_current_user)) -> dict:
    """Generate and save an optimized daily report from notes for one date."""

    try:
        return _service(current_user).generate_daily(note_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{note_date}/generate-weekly")
def generate_weekly_from_notes(note_date: str, current_user=Depends(get_current_user)) -> dict:
    """Generate and save a weekly report for the date's week."""

    try:
        return _service(current_user).generate_weekly(note_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
