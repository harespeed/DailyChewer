"""Monthly report routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.schemas import MonthlyRequest
from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.monthly_service import MonthlyService


router = APIRouter(prefix="/api/monthly", tags=["monthly"])


@router.post("")
def generate_monthly(payload: MonthlyRequest, current_user=Depends(get_current_user)) -> dict:
    """Generate a monthly report preview and optional export."""

    result = MonthlyService(
        user_context=UserContext(
            user_id=current_user.id,
            username=current_user.username,
            storage_mode="database",
        )
    ).build_monthly_report(
        month=payload.month,
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
