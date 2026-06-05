"""Weekly report routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.schemas import WeeklyRequest
from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.weekly_service import WeeklyService


router = APIRouter(prefix="/api/weekly", tags=["weekly"])


@router.post("")
def generate_weekly(payload: WeeklyRequest, current_user=Depends(get_current_user)) -> dict:
    """Generate a weekly report preview and optional export."""

    result = WeeklyService(
        user_context=UserContext(
            user_id=current_user.id,
            username=current_user.username,
            storage_mode="database",
        )
    ).build_weekly_report(
        week=payload.week,
        from_date=payload.from_date,
        to_date=payload.to_date,
        fmt=payload.format,
        style=payload.style,
        project=payload.project,
        tags=payload.tags,
        preview=not payload.save,
        save=payload.save,
    )
    return {
        "file": result.file,
        "file_id": result.file_id,
        "preview": result.preview,
        "download_url": result.download_path,
    }
