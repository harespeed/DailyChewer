"""Database-backed optimize-preview task queue."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.config import load_settings
from dailychewer_backend.db.repositories import IngestOptimizeTaskRepository
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.ingest_service import IngestService


def build_optimize_task_result(upload_id: str, result) -> dict:
    """Normalize one optimize task result payload for API polling."""

    return {
        "upload_id": upload_id,
        "daily_report": result.daily_report.model_dump(),
        "questions": result.questions,
        "quality_score": result.quality_score.model_dump() if result.quality_score else None,
    }


def drain_optimize_task_queue(
    user_id: str,
    username: str,
    upload_id: str,
    project_root: Path | None = None,
) -> None:
    """Drain queued optimize tasks for one upload in submission order."""

    settings = load_settings(project_root=project_root)
    session_factory = get_session_maker(settings)

    while True:
        with session_factory() as session:
            repo = IngestOptimizeTaskRepository(session)
            if repo.get_running_task(user_id=user_id, upload_id=upload_id) is not None:
                return
            next_pending = repo.get_next_pending_task(user_id=user_id, upload_id=upload_id)
            if next_pending is None:
                return
            claimed = repo.try_mark_running(next_pending.id)
            if claimed is None:
                continue
            request_payload = claimed.request_payload
            task_id = claimed.id

        try:
            temp_path = (
                settings.data_dir / "users" / user_id / "uploads" / "tmp" / str(request_payload["upload_id"])
            ).resolve()
            result = IngestService(
                project_root=project_root,
                user_context=UserContext(
                    user_id=user_id,
                    username=username,
                    storage_mode="database",
                ),
            ).ingest_report(
                file_path=temp_path,
                date=request_payload.get("date"),
                save=False,
                no_questions=False,
                user_answers=request_payload.get("user_answers") or {},
            )
            with session_factory() as session:
                IngestOptimizeTaskRepository(session).mark_completed(
                    task_id=task_id,
                    result_payload=build_optimize_task_result(upload_id=request_payload["upload_id"], result=result),
                )
        except ValueError as exc:
            with session_factory() as session:
                IngestOptimizeTaskRepository(session).mark_failed(task_id=task_id, error_message=str(exc))
        except RuntimeError as exc:
            with session_factory() as session:
                IngestOptimizeTaskRepository(session).mark_failed(task_id=task_id, error_message=str(exc))
        except Exception as exc:
            with session_factory() as session:
                IngestOptimizeTaskRepository(session).mark_failed(task_id=task_id, error_message=f"Unexpected optimize task failure: {exc}")
