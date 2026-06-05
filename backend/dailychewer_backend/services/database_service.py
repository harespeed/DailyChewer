"""Database initialization and health-check helpers."""

from __future__ import annotations

from pathlib import Path
import subprocess
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from dailychewer_backend.auth.security import hash_password
from dailychewer_backend.db.models import Base
from dailychewer_backend.db.repositories import UserRepository
from dailychewer_backend.db.session import get_engine, get_session_maker
from dailychewer_backend.models import DatabaseCheckResult, DatabaseInitResult
from dailychewer_backend.services import build_runtime

try:  # pragma: no cover - optional in current local env
    from alembic import command
    from alembic.config import Config
except Exception:  # pragma: no cover - fallback path
    command = None
    Config = None


def mask_database_url(database_url: str | None) -> str:
    """Hide database passwords while keeping host and db name visible."""

    if not database_url:
        return "not configured"
    parsed = urlsplit(database_url)
    if "@" not in parsed.netloc:
        return database_url
    credentials, host_part = parsed.netloc.rsplit("@", maxsplit=1)
    if ":" in credentials:
        username, _ = credentials.split(":", maxsplit=1)
        safe_netloc = f"{username}:****@{host_part}"
    else:
        safe_netloc = f"{credentials}@{host_part}"
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path, parsed.query, parsed.fragment))


class DatabaseService:
    """Inspect and initialize the configured database backend."""

    def __init__(self, project_root: Path | None = None):
        self.settings, _, _, _, self.logger = build_runtime(project_root=project_root)

    def check(self) -> DatabaseCheckResult:
        """Return a structured database status summary."""

        database_url = self.settings.database_url
        result = DatabaseCheckResult(
            database_url_configured=bool(database_url),
            database_url_masked=mask_database_url(database_url),
        )
        if not database_url:
            result.details.append("DATABASE_URL is not configured. CLI local mode can still use data/index.json.")
            return result

        try:
            engine = get_engine(database_url)
            with engine.begin() as connection:
                connection.execute(text("SELECT 1"))
            result.database_reachable = True
        except Exception as exc:
            result.details.append(str(exc))
            return result

        try:
            inspector = inspect(engine)
            result.users_table_exists = inspector.has_table("users")
            if inspector.has_table("alembic_version"):
                with engine.begin() as connection:
                    result.alembic_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            else:
                result.alembic_revision = None
                result.details.append("alembic_version table not found.")
            if result.users_table_exists:
                with engine.begin() as connection:
                    count = connection.execute(
                        text("SELECT COUNT(*) FROM users WHERE is_active = true AND is_admin = true")
                    ).scalar_one()
                result.active_admin_exists = bool(count)
        except Exception as exc:
            result.details.append(str(exc))
        return result

    def init(self) -> DatabaseInitResult:
        """Initialize database schema and default admin user."""

        status = self.check()
        if not status.database_url_configured:
            raise ValueError("DATABASE_URL is required for db init.")
        if not status.database_reachable:
            raise ValueError("Database is not reachable. Check DATABASE_URL and PostgreSQL status.")

        migration_applied = False
        migration_mode = "alembic"
        details: list[str] = []
        try:
            self._upgrade_schema()
            migration_applied = True
        except Exception as exc:
            migration_mode = "metadata-create-all"
            details.append(f"Alembic unavailable or failed: {exc}")
            engine = get_engine(self.settings.database_url)
            Base.metadata.create_all(engine)
            migration_applied = True
            details.append("Fallback schema creation completed with SQLAlchemy metadata.")

        default_user_created = False
        default_username = None
        if self.settings.database.create_default_user:
            session_factory = get_session_maker(self.settings)
            with session_factory() as session:
                repo = UserRepository(session)
                existing = repo.get_by_username(self.settings.database.default_username)
                if existing is None:
                    repo.create_user(
                        username=self.settings.database.default_username,
                        password_hash=hash_password(self.settings.database.default_password),
                        display_name=self.settings.database.default_display_name,
                        is_admin=True,
                    )
                    default_user_created = True
                    default_username = self.settings.database.default_username
                    self.logger.info("Default admin user created: %s", default_username)
        return DatabaseInitResult(
            database_reachable=True,
            migration_applied=migration_applied,
            migration_mode=migration_mode,
            default_user_created=default_user_created,
            default_username=default_username,
            details=details,
        )

    def _upgrade_schema(self) -> None:
        """Run `alembic upgrade head` via Python API or subprocess."""

        if command is not None and Config is not None:
            alembic_config = Config(str(self.settings.project_root / "alembic.ini"))
            command.upgrade(alembic_config, "head")
            return
        subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=self.settings.project_root,
            check=True,
        )
