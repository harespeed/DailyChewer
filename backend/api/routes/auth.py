"""Authentication API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dailychewer_backend.auth.dependencies import get_current_user
from dailychewer_backend.auth.schemas import PasswordChangeRequest, TokenResponse, UserCreate, UserLogin, UserRead
from dailychewer_backend.auth.security import create_access_token, hash_password, verify_password
from dailychewer_backend.db.repositories import UserRepository
from dailychewer_backend.db.session import get_db
from dailychewer_backend.services.user_service import UserService


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserRead)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    """Register one new user."""

    repo = UserRepository(db)
    if repo.get_by_username(payload.username):
        raise HTTPException(status_code=400, detail="Username already exists.")
    try:
        user = repo.create_user(
            username=payload.username,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail="Username already exists.") from exc
    return UserRead.from_orm_user(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate one user and return a bearer token."""

    repo = UserRepository(db)
    user = repo.get_by_username(payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive.")
    token = create_access_token(user_id=user.id, username=user.username)
    return TokenResponse(access_token=token, user=UserRead.from_orm_user(user))


@router.get("/me", response_model=UserRead)
def me(current_user=Depends(get_current_user)) -> UserRead:
    """Return the current authenticated user."""

    return UserRead.from_orm_user(current_user)


@router.post("/change-password")
def change_password(payload: PasswordChangeRequest, current_user=Depends(get_current_user)) -> dict[str, str]:
    """Change the current user's password."""

    try:
        UserService().change_password(
            user_id=current_user.id,
            old_password=payload.old_password,
            new_password=payload.new_password,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}
