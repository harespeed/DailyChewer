"""File download routes with user-scoped safety checks."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.config import load_settings
from dailychewer_backend.db.repositories import UploadedFileRepository
from dailychewer_backend.db.session import get_session_maker


router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{file_id}/download")
def download_file_by_id(file_id: str, current_user=Depends(get_current_user)) -> FileResponse:
    """Download one file by database-owned file id."""

    settings = load_settings()
    if not settings.database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL is required for file downloads.")
    session_factory = get_session_maker(settings)
    with session_factory() as session:
        file_record = UploadedFileRepository(session).get_uploaded_file(current_user.id, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    resolved = Path(file_record.stored_file_path).resolve()
    if resolved.name in {".env", "index.json"}:
        raise HTTPException(status_code=403, detail="Forbidden file path.")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    user_root = (settings.data_dir / "users" / current_user.id).resolve()
    if not resolved.is_relative_to(user_root):
        raise HTTPException(status_code=403, detail="Forbidden file path.")
    return FileResponse(resolved, filename=file_record.original_filename)


@router.get("/download")
def download_file(
    path: str = Query(..., description="Path under the current user's data root."),
    current_user=Depends(get_current_user),
) -> FileResponse:
    """Fallback path-based download restricted to the current user's directory."""

    settings = load_settings()
    requested = Path(path)
    if requested.is_absolute() or ".." in requested.parts:
        raise HTTPException(status_code=403, detail="Forbidden file path.")
    resolved = (settings.project_root / requested).resolve()
    user_root = (settings.data_dir / "users" / current_user.id).resolve()
    forbidden_names = {".env", "index.json"}
    if resolved.name in forbidden_names or not resolved.is_relative_to(user_root):
        raise HTTPException(status_code=403, detail="Forbidden file path.")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(resolved)
