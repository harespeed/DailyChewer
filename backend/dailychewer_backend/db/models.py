"""SQLAlchemy ORM models for multi-user DailyChewer."""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _uuid_str() -> str:
    """Return a random UUID string for primary keys."""

    return str(uuid4())


JSONType = JSON().with_variant(JSONB, "postgresql")
UUIDType = String(36).with_variant(PGUUID(as_uuid=False), "postgresql")


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class TimestampMixin:
    """Reusable timestamp fields."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class User(Base, TimestampMixin):
    """Application user."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    projects: Mapped[list["Project"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    """User-scoped project catalog."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_projects_user_name"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="projects")
    daily_reports: Mapped[list["DailyReportRecord"]] = relationship(back_populates="project")
    weekly_reports: Mapped[list["WeeklyReportRecord"]] = relationship(back_populates="project")
    monthly_reports: Mapped[list["MonthlyReportRecord"]] = relationship(back_populates="project")


class Tag(Base):
    """User-scoped tag catalog."""

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tags_user_name"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="tags")


class DailyReportTag(Base):
    """Many-to-many relation between daily reports and tags."""

    __tablename__ = "daily_report_tags"

    daily_report_id: Mapped[str] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class WeeklyReportTag(Base):
    """Many-to-many relation between weekly reports and tags."""

    __tablename__ = "weekly_report_tags"

    weekly_report_id: Mapped[str] = mapped_column(
        ForeignKey("weekly_reports.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class MonthlyReportTag(Base):
    """Many-to-many relation between monthly reports and tags."""

    __tablename__ = "monthly_report_tags"

    monthly_report_id: Mapped[str] = mapped_column(
        ForeignKey("monthly_reports.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class DailyReportRecord(Base, TimestampMixin):
    """Persisted optimized daily report plus file metadata."""

    __tablename__ = "daily_reports"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    weekday: Mapped[str] = mapped_column(String(30))
    iso_week: Mapped[str] = mapped_column(String(20), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    source_format: Mapped[str] = mapped_column(String(30))
    raw_file_path: Mapped[str] = mapped_column(Text)
    optimized_file_path: Mapped[str] = mapped_column(Text)
    quality_score_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_report_json: Mapped[dict] = mapped_column(JSONType)

    tags: Mapped[list[Tag]] = relationship(secondary="daily_report_tags")
    project: Mapped[Project | None] = relationship(back_populates="daily_reports")


class DailyNoteRecord(Base, TimestampMixin):
    """User-written raw daily note anchored to one date and day period."""

    __tablename__ = "daily_notes"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    note_date: Mapped[date] = mapped_column(Date, index=True)
    weekday: Mapped[str] = mapped_column(String(30))
    period: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    detail_level: Mapped[int] = mapped_column(Integer, default=1)


class WeeklyReportRecord(Base):
    """Persisted weekly report metadata."""

    __tablename__ = "weekly_reports"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    iso_week: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    from_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    to_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    format: Mapped[str] = mapped_column(String(30))
    style: Mapped[str] = mapped_column(String(30))
    file_path: Mapped[str] = mapped_column(Text)
    report_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    preview_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tags: Mapped[list[Tag]] = relationship(secondary="weekly_report_tags")
    project: Mapped[Project | None] = relationship(back_populates="weekly_reports")


class MonthlyReportRecord(Base):
    """Persisted monthly report metadata."""

    __tablename__ = "monthly_reports"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(20), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    format: Mapped[str] = mapped_column(String(30))
    style: Mapped[str] = mapped_column(String(30))
    file_path: Mapped[str] = mapped_column(Text)
    report_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    preview_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tags: Mapped[list[Tag]] = relationship(secondary="monthly_report_tags")
    project: Mapped[Project | None] = relationship(back_populates="monthly_reports")


class UploadedFileRecord(Base):
    """Persisted uploaded/generated file metadata."""

    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_file_path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purpose: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IngestOptimizeTaskRecord(Base, TimestampMixin):
    """Queued optimize-preview task for one uploaded report."""

    __tablename__ = "ingest_optimize_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "upload_id", "request_sequence", name="uq_ingest_optimize_tasks_sequence"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[str] = mapped_column(String(255), index=True)
    request_sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    request_payload: Mapped[dict] = mapped_column(JSONType)
    result_payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
