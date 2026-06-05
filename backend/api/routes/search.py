"""Search routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.search_service import SearchService


router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search_reports(
    q: str,
    week: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    project: str | None = None,
    tag: list[str] | None = None,
    limit: int = 10,
    current_user=Depends(get_current_user),
) -> list[dict]:
    """Search optimized reports by keyword."""

    results = SearchService(
        user_context=UserContext(
            user_id=current_user.id,
            username=current_user.username,
            storage_mode="database",
        )
    ).search_reports(
        query=q,
        week=week,
        from_date=from_date,
        to_date=to_date,
        project=project,
        tags=tag,
        limit=limit,
    )
    return [item.model_dump() for item in results]
