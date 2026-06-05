"""Pydantic schemas for auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """User registration payload."""

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6)
    display_name: str | None = None


class UserLogin(BaseModel):
    """User login payload."""

    username: str
    password: str


class UserRead(BaseModel):
    """Safe user response payload."""

    id: str
    username: str
    display_name: str | None = None
    is_active: bool
    is_admin: bool
    created_at: str | None = None

    @classmethod
    def from_orm_user(cls, user) -> "UserRead":
        return cls(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at.replace(microsecond=0).isoformat() if getattr(user, "created_at", None) else None,
        )


class TokenResponse(BaseModel):
    """JWT login response."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead


class PasswordChangeRequest(BaseModel):
    """Authenticated password change payload."""

    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6)
