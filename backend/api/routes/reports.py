"""Report listing routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.search_service import SearchService


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(
    week: str | None = None,
    project: str | None = None,
    tag: str | None = None,
    current_user=Depends(get_current_user),
) -> list[dict]:
    """Return indexed daily reports."""

    reports = SearchService(
        user_context=UserContext(
            user_id=current_user.id,
            username=current_user.username,
            storage_mode="database",
        )
    ).list_reports(week=week, project=project, tag=tag)
    return [item.model_dump(by_alias=True) for item in reports]
