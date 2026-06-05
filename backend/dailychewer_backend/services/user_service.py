"""Shared user administration and account management logic."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.auth.security import hash_password, verify_password
from dailychewer_backend.db.repositories import UserRepository
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import UserReadModel
from dailychewer_backend.services import build_runtime


class UserService:
    """Create, list, enable, disable, and update user credentials."""

    def __init__(self, project_root: Path | None = None):
        self.settings, _, _, _, self.logger = build_runtime(project_root=project_root)
        if not self.settings.database_url:
            raise ValueError("DATABASE_URL is required for user management commands.")
        self.session_factory = get_session_maker(self.settings)

    def create_user(
        self,
        username: str,
        password: str,
        display_name: str | None = None,
        is_admin: bool = False,
    ) -> UserReadModel:
        """Create one user and return a safe representation."""

        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        with self.session_factory() as session:
            repo = UserRepository(session)
            if repo.get_by_username(username):
                raise ValueError("User already exists.")
            user = repo.create_user(
                username=username,
                password_hash=hash_password(password),
                display_name=display_name,
                is_admin=is_admin,
            )
        self.logger.info("user_created username=%s is_admin=%s", username, is_admin)
        return self._to_model(user)

    def list_users(self) -> list[UserReadModel]:
        """Return all users for local admin usage."""

        with self.session_factory() as session:
            users = UserRepository(session).list_users()
        return [self._to_model(user) for user in users]

    def set_user_active(self, username: str, is_active: bool) -> UserReadModel:
        """Enable or disable one existing user."""

        with self.session_factory() as session:
            repo = UserRepository(session)
            user = repo.get_by_username(username)
            if user is None:
                raise ValueError("User not found.")
            updated = repo.set_active(user, is_active=is_active)
        self.logger.info("user_status_updated username=%s is_active=%s", username, is_active)
        return self._to_model(updated)

    def reset_password(self, username: str, password: str) -> UserReadModel:
        """Reset one user's password without returning sensitive data."""

        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        with self.session_factory() as session:
            repo = UserRepository(session)
            user = repo.get_by_username(username)
            if user is None:
                raise ValueError("User not found.")
            updated = repo.update_password_hash(user, hash_password(password))
        self.logger.info("user_password_reset username=%s", username)
        return self._to_model(updated)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> None:
        """Change the current user's password after verifying the old password."""

        if len(new_password) < 6:
            raise ValueError("New password must be at least 6 characters long.")
        with self.session_factory() as session:
            repo = UserRepository(session)
            user = repo.get_by_id(user_id)
            if user is None:
                raise ValueError("User not found.")
            if not verify_password(old_password, user.password_hash):
                raise PermissionError("Old password is incorrect.")
            repo.update_password_hash(user, hash_password(new_password))
        self.logger.info("user_password_changed user_id=%s", user_id)

    def _to_model(self, user) -> UserReadModel:
        """Map one ORM user into a CLI/API-safe model."""

        return UserReadModel(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at.replace(microsecond=0).isoformat(),
        )
