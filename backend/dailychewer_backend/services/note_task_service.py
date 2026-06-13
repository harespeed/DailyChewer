"""Background task helpers for long-running note report generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from dailychewer_backend.models import UserContext
from dailychewer_backend.services.note_service import DailyNoteService


@dataclass
class NoteWeeklyRangeTask:
    """In-memory task state for one note range report generation."""

    id: str
    user_id: str
    username: str | None
    from_date: str
    to_date: str
    status: str = "pending"
    result: dict | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().replace(microsecond=0).isoformat())
    started_at: str | None = None
    completed_at: str | None = None


_TASKS: dict[str, NoteWeeklyRangeTask] = {}
_TASK_LOCK = Lock()


def create_note_weekly_range_task(
    user_id: str,
    username: str | None,
    from_date: str,
    to_date: str,
) -> NoteWeeklyRangeTask:
    """Create one queued stage-report task."""

    task = NoteWeeklyRangeTask(
        id=str(uuid4()),
        user_id=user_id,
        username=username,
        from_date=from_date,
        to_date=to_date,
    )
    with _TASK_LOCK:
        _TASKS[task.id] = task
    return task


def get_note_weekly_range_task(user_id: str, task_id: str) -> NoteWeeklyRangeTask | None:
    """Return one task only when it belongs to the current user."""

    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None or task.user_id != user_id:
            return None
        return task


def run_note_weekly_range_task(task_id: str, project_root: Path | None = None) -> None:
    """Generate a stage report for one queued note range task."""

    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None or task.status not in {"pending", "failed"}:
            return
        task.status = "running"
        task.started_at = datetime.utcnow().replace(microsecond=0).isoformat()
        task.error_message = None

    try:
        result = DailyNoteService(
            project_root=project_root,
            user_context=UserContext(
                user_id=task.user_id,
                username=task.username,
                storage_mode="database",
            ),
        ).generate_weekly_range(from_date=task.from_date, to_date=task.to_date)
        with _TASK_LOCK:
            task.status = "completed"
            task.result = result
            task.completed_at = datetime.utcnow().replace(microsecond=0).isoformat()
    except (ValueError, RuntimeError) as exc:
        with _TASK_LOCK:
            task.status = "failed"
            task.error_message = str(exc)
            task.completed_at = datetime.utcnow().replace(microsecond=0).isoformat()
    except Exception as exc:
        with _TASK_LOCK:
            task.status = "failed"
            task.error_message = f"Unexpected stage report task failure: {exc}"
            task.completed_at = datetime.utcnow().replace(microsecond=0).isoformat()


def serialize_note_weekly_range_task(task: NoteWeeklyRangeTask) -> dict:
    """Serialize task state for API responses."""

    return {
        "task_id": task.id,
        "from_date": task.from_date,
        "to_date": task.to_date,
        "status": task.status,
        "result": task.result,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
    }
