"""Admin-oriented user management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.auth.schemas import UserRead
from dailychewer_backend.services.user_service import UserService


router = APIRouter(prefix="/api/users", tags=["users"])


class UserStatusUpdateRequest(BaseModel):
    """User status toggle payload."""

    is_active: bool


def _require_admin(current_user) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


@router.get("/me", response_model=UserRead)
def read_current_user(current_user=Depends(get_current_user)) -> UserRead:
    """Return the authenticated user profile."""

    return UserRead.from_orm_user(current_user)


@router.get("", response_model=list[UserRead])
def list_users(current_user=Depends(get_current_user)) -> list[UserRead]:
    """Return all users for administrators."""

    _require_admin(current_user)
    return [
        UserRead(
            id=item.id,
            username=item.username,
            display_name=item.display_name,
            is_active=item.is_active,
            is_admin=item.is_admin,
            created_at=item.created_at,
        )
        for item in UserService().list_users()
    ]


@router.patch("/{user_id}/status", response_model=UserRead)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    current_user=Depends(get_current_user),
) -> UserRead:
    """Enable or disable one user as an administrator."""

    _require_admin(current_user)
    if current_user.id == user_id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account.")

    service = UserService()
    for item in service.list_users():
        if item.id == user_id:
            updated = service.set_user_active(item.username, is_active=payload.is_active)
            return UserRead(
                id=updated.id,
                username=updated.username,
                display_name=updated.display_name,
                is_active=updated.is_active,
                is_admin=updated.is_admin,
                created_at=updated.created_at,
            )
    raise HTTPException(status_code=404, detail="User not found.")
