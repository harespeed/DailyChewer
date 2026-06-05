"""Doctor API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dailychewer_backend.auth.dependencies import get_current_admin_user
from dailychewer_backend.services.doctor_service import DoctorService


router = APIRouter(prefix="/api/doctor", tags=["doctor"])


@router.get("")
def get_doctor(check_api: bool = False, current_user=Depends(get_current_admin_user)) -> dict:
    """Return structured doctor status for administrators."""

    result = DoctorService().get_status(check_api=check_api)
    return result.model_dump()
