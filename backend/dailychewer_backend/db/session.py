"""SQLAlchemy session helpers for DailyChewer."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dailychewer_backend.config import Settings, load_settings


def _sqlite_connect_args(database_url: str) -> dict:
    """Return SQLite-specific engine kwargs."""

    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=8)
def get_engine(database_url: str) -> Engine:
    """Create and cache a SQLAlchemy engine for one database URL."""

    return create_engine(
        database_url,
        future=True,
        connect_args=_sqlite_connect_args(database_url),
    )


def get_session_maker(settings: Settings | None = None) -> sessionmaker[Session]:
    """Return the configured SQLAlchemy session factory."""

    resolved_settings = settings or load_settings()
    if not resolved_settings.database_url:
        raise RuntimeError("DATABASE_URL is required for database mode.")
    return sessionmaker(
        bind=get_engine(resolved_settings.database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def get_db():
    """FastAPI dependency yielding one database session."""

    session_factory = get_session_maker()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
