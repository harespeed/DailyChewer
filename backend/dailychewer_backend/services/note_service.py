"""Daily note service and report generation helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from dailychewer_backend.db.models import DailyNoteRecord
from dailychewer_backend.db.repositories import DailyNoteRepository, DailyReportRepository
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import UserContext
from dailychewer_backend.services import build_runtime
from dailychewer_backend.services.ingest_service import IngestService
from dailychewer_backend.services.weekly_service import WeeklyService
from dailychewer_backend.utils.date_utils import iso_week_for_date, month_bounds, normalize_date, parse_date, weekday_name, week_bounds


PERIOD_LABELS = {
    "morning": "上午",
    "afternoon": "下午",
}


class DailyNoteService:
    """Manage user notes and convert them into optimized reports."""

    def __init__(self, project_root: Path | None = None, user_context: UserContext | None = None):
        self.settings, _, _, _, _ = build_runtime(project_root=project_root)
        self.user_context = user_context or UserContext(storage_mode="local")
        self.session_factory = get_session_maker(self.settings) if self.settings.database_url else None

    def create_note(self, content: str, note_date: str | None = None, period: str | None = None) -> DailyNoteRecord:
        """Create one note for the resolved date and period."""

        cleaned = content.strip()
        if not cleaned:
            raise ValueError("便条内容不能为空。")
        resolved_date = normalize_date(note_date) if note_date else date.today().isoformat()
        resolved_period = self._normalize_period(period)
        self._ensure_database_context()
        with self.session_factory() as session:
            return DailyNoteRepository(session).create_note(
                user_id=self.user_context.user_id,
                note_date=parse_date(resolved_date),
                weekday=weekday_name(resolved_date),
                period=resolved_period,
                content=cleaned,
                detail_level=self._detail_level(cleaned),
            )

    def update_note(self, note_id: str, content: str, period: str | None = None) -> DailyNoteRecord:
        """Update one note body or period."""

        cleaned = content.strip()
        if not cleaned:
            raise ValueError("便条内容不能为空。")
        resolved_period = self._normalize_period(period) if period else None
        self._ensure_database_context()
        with self.session_factory() as session:
            record = DailyNoteRepository(session).update_note(
                user_id=self.user_context.user_id,
                note_id=note_id,
                content=cleaned,
                period=resolved_period,
                detail_level=self._detail_level(cleaned),
            )
            if record is None:
                raise ValueError("便条不存在。")
            return record

    def delete_note(self, note_id: str) -> None:
        """Delete one note by id."""

        self._ensure_database_context()
        with self.session_factory() as session:
            deleted = DailyNoteRepository(session).delete_note(user_id=self.user_context.user_id, note_id=note_id)
        if not deleted:
            raise ValueError("便条不存在。")

    def list_month(self, month: str) -> dict:
        """Return note records and date summaries for one month."""

        start, end = month_bounds(month)
        return self._serialize_collection(
            self._list_notes(from_date=parse_date(start), to_date=parse_date(end))
        )

    def list_date(self, note_date: str) -> dict:
        """Return note records for one date."""

        resolved_date = normalize_date(note_date)
        return self._serialize_collection(self._list_notes(from_date=parse_date(resolved_date), to_date=parse_date(resolved_date)))

    def generate_daily(self, note_date: str) -> dict:
        """Generate and save an optimized daily report from that date's notes."""

        resolved_date = normalize_date(note_date)
        records = self._list_notes(from_date=parse_date(resolved_date), to_date=parse_date(resolved_date))
        if not records:
            raise ValueError("该日期还没有便条。")
        notes_file = self._write_notes_markdown(resolved_date, records)
        result = IngestService(
            project_root=self.settings.project_root,
            user_context=self.user_context,
        ).ingest_report(
            file_path=notes_file,
            date=resolved_date,
            project="Daily Notes",
            tags=["note-generated"],
            save=True,
            no_questions=True,
        )
        return {
            "saved": result.saved,
            "raw_file": result.raw_file,
            "optimized_file": result.optimized_file,
            "index_item": result.index_item.model_dump() if result.index_item else None,
        }

    def generate_weekly(self, note_date: str) -> dict:
        """Generate and save a weekly report for the ISO week containing the date."""

        resolved_date = normalize_date(note_date)
        week = iso_week_for_date(resolved_date)
        from_date, to_date = week_bounds(week)
        return self.generate_weekly_range(from_date=from_date, to_date=to_date)

    def generate_weekly_range(self, from_date: str, to_date: str) -> dict:
        """Generate and save a weekly/stage report for an explicit note date range."""

        resolved_from = normalize_date(from_date)
        resolved_to = normalize_date(to_date)
        if parse_date(resolved_from) > parse_date(resolved_to):
            raise ValueError("起始日期不能晚于目标日期。")
        records = self._list_notes(from_date=parse_date(resolved_from), to_date=parse_date(resolved_to))
        if not records:
            raise ValueError("该时间段还没有便条。")
        records_by_date: dict[str, list[DailyNoteRecord]] = defaultdict(list)
        for record in records:
            records_by_date[record.note_date.isoformat()].append(record)
        note_dates = sorted(records_by_date)
        for note_date in note_dates:
            if self._daily_report_needs_regeneration(note_date, records_by_date[note_date]):
                self.generate_daily(note_date)
        result = WeeklyService(
            project_root=self.settings.project_root,
            user_context=self.user_context,
        ).build_weekly_report(
            week=None,
            from_date=resolved_from,
            to_date=resolved_to,
            fmt="markdown",
            style="concise",
            project=None,
            tags=[],
            preview=False,
            save=True,
        )
        return {
            "file": result.file,
            "file_id": result.file_id,
            "preview": result.preview,
            "download_url": result.download_path,
        }

    def _list_notes(self, from_date: date, to_date: date) -> list[DailyNoteRecord]:
        self._ensure_database_context()
        with self.session_factory() as session:
            records = DailyNoteRepository(session).list_notes(
                user_id=self.user_context.user_id,
                from_date=from_date,
                to_date=to_date,
            )
            for record in records:
                session.expunge(record)
            return records

    def _daily_report_needs_regeneration(self, note_date: str, records: list[DailyNoteRecord]) -> bool:
        """Return whether note-generated optimized daily output is missing or stale."""

        self._ensure_database_context()
        with self.session_factory() as session:
            report = DailyReportRepository(session).find_by_date_project(
                user_id=self.user_context.user_id,
                report_date=parse_date(note_date),
                project_name="Daily Notes",
            )
            if report is None:
                return True
            if not Path(report.optimized_file_path).exists():
                return True
            latest_note_update = max(record.updated_at for record in records)
            return latest_note_update > report.updated_at

    def _serialize_collection(self, records: list[DailyNoteRecord]) -> dict:
        notes = [self.serialize_note(record) for record in records]
        by_date: dict[str, list[dict]] = defaultdict(list)
        for note in notes:
            by_date[note["date"]].append(note)
        days = []
        for note_date, day_notes in sorted(by_date.items(), reverse=True):
            content = "\n".join(note["content"] for note in day_notes)
            days.append(
                {
                    "date": note_date,
                    "weekday": day_notes[0]["weekday"],
                    "note_count": len(day_notes),
                    "detail_level": max(note["detail_level"] for note in day_notes),
                    "preview": content[:220],
                    "notes": day_notes,
                }
            )
        return {"notes": notes, "days": days}

    def _write_notes_markdown(self, note_date: str, records: list[DailyNoteRecord]) -> Path:
        target_dir = self.settings.data_dir / "users" / self.user_context.user_id / "notes" / "generated"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{note_date}_daily_notes.md"
        lines = [f"# {note_date}", "", "这些内容来自用户当天写下的日报便条，请在不虚构具体事实的前提下生成结构化日报。", ""]
        for record in sorted(records, key=lambda item: item.period):
            label = PERIOD_LABELS.get(record.period, record.period)
            lines.extend([f"## {label}", "", record.content.strip(), ""])
        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    def _normalize_period(self, period: str | None) -> str:
        if period:
            cleaned = period.strip().lower()
            if cleaned in {"morning", "am", "上午"}:
                return "morning"
            if cleaned in {"afternoon", "pm", "下午"}:
                return "afternoon"
            raise ValueError("period 只支持 morning 或 afternoon。")
        return "morning" if datetime.now().hour < 12 else "afternoon"

    def _ensure_database_context(self) -> None:
        if self.user_context.storage_mode != "database" or not self.user_context.user_id or self.session_factory is None:
            raise ValueError("Database mode requires a valid user context.")

    @staticmethod
    def _detail_level(content: str) -> int:
        length = len(content.strip())
        if length >= 520:
            return 4
        if length >= 260:
            return 3
        if length >= 90:
            return 2
        return 1

    @staticmethod
    def serialize_note(record: DailyNoteRecord) -> dict:
        """Serialize a detached ORM record for API responses."""

        return {
            "id": record.id,
            "date": record.note_date.isoformat(),
            "weekday": record.weekday,
            "period": record.period,
            "content": record.content,
            "detail_level": record.detail_level,
            "created_at": record.created_at.replace(microsecond=0).isoformat(),
            "updated_at": record.updated_at.replace(microsecond=0).isoformat(),
        }
