"""Template generation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.schemas import TemplateRequest
from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.template_service import TemplateService


router = APIRouter(prefix="/api/template", tags=["template"])


@router.post("")
def generate_template(payload: TemplateRequest, current_user=Depends(get_current_user)) -> dict:
    """Generate a daily template under the configured input directory."""

    result = TemplateService(
        user_context=UserContext(
            user_id=current_user.id,
            username=current_user.username,
            storage_mode="database",
        )
    ).generate_template(date=payload.date, fmt=payload.format)
    return {
        "file": result.file,
        "file_id": result.file_id,
        "download_url": f"/api/files/{result.file_id}/download" if result.file_id else None,
    }
