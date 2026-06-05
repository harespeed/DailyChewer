"""Doctor API routes."""

from __future__ import annotations

from fastapi import APIRouter

from dailychewer_backend.services.doctor_service import DoctorService


router = APIRouter(prefix="/api/doctor", tags=["doctor"])


@router.get("")
def get_doctor(check_api: bool = False) -> dict:
    """Return structured doctor status."""

    result = DoctorService().get_status(check_api=check_api)
    return result.model_dump()
