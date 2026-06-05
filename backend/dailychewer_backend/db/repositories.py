"""Repository layer for user-scoped database operations."""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session, joinedload

from dailychewer_backend.db.models import (
    DailyNoteRecord,
    DailyReportRecord,
    IngestOptimizeTaskRecord,
    MonthlyReportRecord,
    Project,
    Tag,
    UploadedFileRecord,
    User,
    WeeklyReportRecord,
)


class UserRepository:
    """User persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_user(
        self,
        username: str,
        password_hash: str,
        display_name: str | None = None,
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        user = User(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            is_admin=is_admin,
            is_active=is_active,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username))

    def get_by_id(self, user_id: str) -> User | None:
        return self.session.scalar(select(User).where(User.id == user_id))

    def list_users(self) -> list[User]:
        return list(self.session.scalars(select(User).order_by(User.created_at, User.username)))

    def set_active(self, user: User, is_active: bool) -> User:
        user.is_active = is_active
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update_password_hash(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user


class ProjectRepository:
    """Project persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create_project(self, user_id: str, name: str | None) -> Project | None:
        if not name:
            return None
        existing = self.session.scalar(
            select(Project).where(Project.user_id == user_id, Project.name == name)
        )
        if existing:
            return existing
        project = Project(user_id=user_id, name=name)
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def list_projects(self, user_id: str) -> list[Project]:
        return list(self.session.scalars(select(Project).where(Project.user_id == user_id).order_by(Project.name)))


class TagRepository:
    """Tag persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create_tags(self, user_id: str, names: Iterable[str]) -> list[Tag]:
        results: list[Tag] = []
        seen: set[str] = set()
        for name in names:
            cleaned = name.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            existing = self.session.scalar(select(Tag).where(Tag.user_id == user_id, Tag.name == cleaned))
            if existing:
                results.append(existing)
                continue
            tag = Tag(user_id=user_id, name=cleaned)
            self.session.add(tag)
            self.session.flush()
            results.append(tag)
        self.session.commit()
        return results

    def list_tags(self, user_id: str) -> list[Tag]:
        return list(self.session.scalars(select(Tag).where(Tag.user_id == user_id).order_by(Tag.name)))


class DailyReportRepository:
    """Daily report persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_daily_report(
        self,
        user_id: str,
        report_date: date,
        weekday: str,
        iso_week: str,
        project_id: str | None,
        source_format: str,
        raw_file_path: str,
        optimized_file_path: str,
        quality_score_total: int | None,
        daily_report_json: dict,
        tags: list[Tag],
    ) -> DailyReportRecord:
        record = self.session.scalar(
            select(DailyReportRecord).where(
                DailyReportRecord.user_id == user_id,
                DailyReportRecord.date == report_date,
                DailyReportRecord.project_id == project_id,
            )
        )
        if record is None:
            record = DailyReportRecord(
                user_id=user_id,
                date=report_date,
                weekday=weekday,
                iso_week=iso_week,
                project_id=project_id,
                source_format=source_format,
                raw_file_path=raw_file_path,
                optimized_file_path=optimized_file_path,
                quality_score_total=quality_score_total,
                daily_report_json=daily_report_json,
                tags=tags,
            )
        else:
            record.weekday = weekday
            record.iso_week = iso_week
            record.source_format = source_format
            record.raw_file_path = raw_file_path
            record.optimized_file_path = optimized_file_path
            record.quality_score_total = quality_score_total
            record.daily_report_json = daily_report_json
            record.tags = tags
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_daily_reports(
        self,
        user_id: str,
        week: str | None = None,
        project: str | None = None,
        tag: str | None = None,
    ) -> list[DailyReportRecord]:
        stmt: Select[tuple[DailyReportRecord]] = (
            select(DailyReportRecord)
            .where(DailyReportRecord.user_id == user_id)
            .options(joinedload(DailyReportRecord.tags), joinedload(DailyReportRecord.project))
            .order_by(DailyReportRecord.date)
        )
        if week:
            stmt = stmt.where(DailyReportRecord.iso_week == week)
        if project:
            stmt = stmt.join(Project, isouter=True).where(Project.name == project)
        if tag:
            stmt = stmt.join(DailyReportRecord.tags).where(Tag.name == tag)
        return list(self.session.scalars(stmt).unique())

    def list_daily_reports_by_date_range(
        self,
        user_id: str,
        from_date: date,
        to_date: date,
        project: str | None = None,
        tag: str | None = None,
    ) -> list[DailyReportRecord]:
        stmt: Select[tuple[DailyReportRecord]] = (
            select(DailyReportRecord)
            .where(
                DailyReportRecord.user_id == user_id,
                DailyReportRecord.date >= from_date,
                DailyReportRecord.date <= to_date,
            )
            .options(joinedload(DailyReportRecord.tags), joinedload(DailyReportRecord.project))
            .order_by(DailyReportRecord.date)
        )
        if project:
            stmt = stmt.join(Project, isouter=True).where(Project.name == project)
        if tag:
            stmt = stmt.join(DailyReportRecord.tags).where(Tag.name == tag)
        return list(self.session.scalars(stmt).unique())

    def list_daily_reports_by_month(
        self,
        user_id: str,
        month: str,
        project: str | None = None,
        tag: str | None = None,
    ) -> list[DailyReportRecord]:
        return [
            item
            for item in self.list_daily_reports(user_id=user_id, project=project, tag=tag)
            if item.date.strftime("%Y-%m") == month
        ]

    def get_daily_report_by_id(self, user_id: str, report_id: str) -> DailyReportRecord | None:
        stmt = (
            select(DailyReportRecord)
            .where(DailyReportRecord.user_id == user_id, DailyReportRecord.id == report_id)
            .options(joinedload(DailyReportRecord.tags), joinedload(DailyReportRecord.project))
        )
        return self.session.scalar(stmt)

    def search_daily_reports(
        self,
        user_id: str,
        query: str,
        week: str | None = None,
        project: str | None = None,
        tag: str | None = None,
    ) -> list[DailyReportRecord]:
        query_lower = query.lower()
        candidates = self.list_daily_reports(user_id=user_id, week=week, project=project, tag=tag)
        return [
            item
            for item in candidates
            if query_lower in str(item.daily_report_json).lower()
        ]

    def find_by_date_project(
        self,
        user_id: str,
        report_date: date,
        project_name: str | None = None,
    ) -> DailyReportRecord | None:
        stmt: Select[tuple[DailyReportRecord]] = select(DailyReportRecord).where(
            DailyReportRecord.user_id == user_id,
            DailyReportRecord.date == report_date,
        )
        if project_name:
            stmt = stmt.join(Project, isouter=True).where(Project.name == project_name)
        return self.session.scalar(stmt)


class DailyNoteRepository:
    """Daily note persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_note(
        self,
        user_id: str,
        note_date: date,
        weekday: str,
        period: str,
        content: str,
        detail_level: int,
    ) -> DailyNoteRecord:
        record = DailyNoteRecord(
            user_id=user_id,
            note_date=note_date,
            weekday=weekday,
            period=period,
            content=content,
            detail_level=detail_level,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_notes(
        self,
        user_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[DailyNoteRecord]:
        stmt = select(DailyNoteRecord).where(DailyNoteRecord.user_id == user_id)
        if from_date:
            stmt = stmt.where(DailyNoteRecord.note_date >= from_date)
        if to_date:
            stmt = stmt.where(DailyNoteRecord.note_date <= to_date)
        stmt = stmt.order_by(DailyNoteRecord.note_date.desc(), DailyNoteRecord.period.asc())
        return list(self.session.scalars(stmt))

    def list_notes_for_date(self, user_id: str, note_date: date) -> list[DailyNoteRecord]:
        return self.list_notes(user_id=user_id, from_date=note_date, to_date=note_date)

    def get_note(self, user_id: str, note_id: str) -> DailyNoteRecord | None:
        return self.session.scalar(
            select(DailyNoteRecord).where(
                DailyNoteRecord.user_id == user_id,
                DailyNoteRecord.id == note_id,
            )
        )

    def update_note(
        self,
        user_id: str,
        note_id: str,
        content: str,
        period: str | None,
        detail_level: int,
    ) -> DailyNoteRecord | None:
        record = self.get_note(user_id=user_id, note_id=note_id)
        if record is None:
            return None
        record.content = content
        record.detail_level = detail_level
        if period:
            record.period = period
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def delete_note(self, user_id: str, note_id: str) -> bool:
        record = self.get_note(user_id=user_id, note_id=note_id)
        if record is None:
            return False
        self.session.delete(record)
        self.session.commit()
        return True


class WeeklyReportRepository:
    """Weekly report persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_weekly_report(
        self,
        user_id: str,
        iso_week: str | None,
        from_date: date | None,
        to_date: date | None,
        project_id: str | None,
        report_format: str,
        style: str,
        file_path: str,
        report_json: dict | None,
        preview_text: str | None,
        tags: list[Tag],
    ) -> WeeklyReportRecord:
        record = WeeklyReportRecord(
            user_id=user_id,
            iso_week=iso_week,
            from_date=from_date,
            to_date=to_date,
            project_id=project_id,
            format=report_format,
            style=style,
            file_path=file_path,
            report_json=report_json,
            preview_text=preview_text,
            tags=tags,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_weekly_reports(self, user_id: str, iso_week: str | None = None) -> list[WeeklyReportRecord]:
        stmt = select(WeeklyReportRecord).where(WeeklyReportRecord.user_id == user_id).order_by(WeeklyReportRecord.created_at.desc())
        if iso_week:
            stmt = stmt.where(WeeklyReportRecord.iso_week == iso_week)
        return list(self.session.scalars(stmt))


class MonthlyReportRepository:
    """Monthly report persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_monthly_report(
        self,
        user_id: str,
        month: str,
        project_id: str | None,
        report_format: str,
        style: str,
        file_path: str,
        report_json: dict | None,
        preview_text: str | None,
        tags: list[Tag],
    ) -> MonthlyReportRecord:
        record = MonthlyReportRecord(
            user_id=user_id,
            month=month,
            project_id=project_id,
            format=report_format,
            style=style,
            file_path=file_path,
            report_json=report_json,
            preview_text=preview_text,
            tags=tags,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_monthly_reports(self, user_id: str, month: str | None = None) -> list[MonthlyReportRecord]:
        stmt = select(MonthlyReportRecord).where(MonthlyReportRecord.user_id == user_id).order_by(MonthlyReportRecord.created_at.desc())
        if month:
            stmt = stmt.where(MonthlyReportRecord.month == month)
        return list(self.session.scalars(stmt))


class UploadedFileRepository:
    """Uploaded/generated file persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_uploaded_file(
        self,
        user_id: str,
        original_filename: str,
        stored_file_path: str,
        purpose: str,
        content_type: str | None = None,
        size_bytes: int | None = None,
    ) -> UploadedFileRecord:
        record = UploadedFileRecord(
            user_id=user_id,
            original_filename=original_filename,
            stored_file_path=stored_file_path,
            purpose=purpose,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_uploaded_file(self, user_id: str, file_id: str) -> UploadedFileRecord | None:
        return self.session.scalar(
            select(UploadedFileRecord).where(
                UploadedFileRecord.user_id == user_id,
                UploadedFileRecord.id == file_id,
            )
        )


class IngestOptimizeTaskRepository:
    """Optimize-preview queue persistence operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_task(self, user_id: str, upload_id: str, request_payload: dict) -> IngestOptimizeTaskRecord:
        last_sequence = self.session.scalar(
            select(func.max(IngestOptimizeTaskRecord.request_sequence)).where(
                IngestOptimizeTaskRecord.user_id == user_id,
                IngestOptimizeTaskRecord.upload_id == upload_id,
            )
        )
        record = IngestOptimizeTaskRecord(
            user_id=user_id,
            upload_id=upload_id,
            request_sequence=(last_sequence or 0) + 1,
            status="pending",
            request_payload=request_payload,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_task(self, user_id: str, task_id: str) -> IngestOptimizeTaskRecord | None:
        return self.session.scalar(
            select(IngestOptimizeTaskRecord).where(
                IngestOptimizeTaskRecord.user_id == user_id,
                IngestOptimizeTaskRecord.id == task_id,
            )
        )

    def get_next_pending_task(self, user_id: str, upload_id: str) -> IngestOptimizeTaskRecord | None:
        stmt = (
            select(IngestOptimizeTaskRecord)
            .where(
                IngestOptimizeTaskRecord.user_id == user_id,
                IngestOptimizeTaskRecord.upload_id == upload_id,
                IngestOptimizeTaskRecord.status == "pending",
            )
            .order_by(IngestOptimizeTaskRecord.request_sequence.asc())
        )
        return self.session.scalar(stmt)

    def get_running_task(self, user_id: str, upload_id: str) -> IngestOptimizeTaskRecord | None:
        stmt = select(IngestOptimizeTaskRecord).where(
            IngestOptimizeTaskRecord.user_id == user_id,
            IngestOptimizeTaskRecord.upload_id == upload_id,
            IngestOptimizeTaskRecord.status == "running",
        )
        return self.session.scalar(stmt)

    def try_mark_running(self, task_id: str) -> IngestOptimizeTaskRecord | None:
        updated = self.session.execute(
            update(IngestOptimizeTaskRecord)
            .where(
                IngestOptimizeTaskRecord.id == task_id,
                IngestOptimizeTaskRecord.status == "pending",
            )
            .values(
                status="running",
                started_at=datetime.utcnow(),
                error_message=None,
            )
        )
        self.session.commit()
        if updated.rowcount == 0:
            return None
        return self.session.scalar(select(IngestOptimizeTaskRecord).where(IngestOptimizeTaskRecord.id == task_id))

    def mark_completed(self, task_id: str, result_payload: dict) -> None:
        self.session.execute(
            update(IngestOptimizeTaskRecord)
            .where(IngestOptimizeTaskRecord.id == task_id)
            .values(
                status="completed",
                result_payload=result_payload,
                error_message=None,
                completed_at=datetime.utcnow(),
            )
        )
        self.session.commit()

    def mark_failed(self, task_id: str, error_message: str) -> None:
        self.session.execute(
            update(IngestOptimizeTaskRecord)
            .where(IngestOptimizeTaskRecord.id == task_id)
            .values(
                status="failed",
                error_message=error_message,
                completed_at=datetime.utcnow(),
            )
        )
        self.session.commit()
