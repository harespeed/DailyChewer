"""FastAPI entrypoint for DailyChewer."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from backend.api.routes import auth, doctor, files, ingest, monthly, notes, reports, search, template, users, weekly
from dailychewer_backend.auth.security import hash_password
from dailychewer_backend.config import load_settings
from dailychewer_backend.db.repositories import UserRepository
from dailychewer_backend.db.session import get_engine, get_session_maker
from dailychewer_backend.utils.logger import get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate database configuration and bootstrap default user on startup."""

    settings = load_settings()
    logger = get_logger(settings)
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for web backend mode.")
    get_engine(settings.database_url)
    if settings.database.create_default_user:
        session_factory = get_session_maker(settings)
        try:
            with session_factory() as session:
                repo = UserRepository(session)
                existing = repo.get_by_username(settings.database.default_username)
                if existing is None:
                    repo.create_user(
                        username=settings.database.default_username,
                        password_hash=hash_password(settings.database.default_password),
                        display_name=settings.database.default_display_name,
                        is_admin=True,
                    )
                    logger.info("Default admin user created: %s", settings.database.default_username)
        except OperationalError as exc:
            raise RuntimeError("Database is not initialized. Run `alembic upgrade head` before starting the backend.") from exc
    yield


app = FastAPI(title="DailyChewer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Minimal health check route."""

    return {"status": "ok", "app": "DailyChewer"}


app.include_router(doctor.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(ingest.router)
app.include_router(reports.router)
app.include_router(search.router)
app.include_router(weekly.router)
app.include_router(monthly.router)
app.include_router(template.router)
app.include_router(files.router)
app.include_router(notes.router)
