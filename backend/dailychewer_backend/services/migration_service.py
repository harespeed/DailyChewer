"""Legacy `data/index.json` to PostgreSQL migration helpers."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from dailychewer_backend.db.repositories import (
    DailyReportRepository,
    MonthlyReportRepository,
    ProjectRepository,
    TagRepository,
    UploadedFileRepository,
    UserRepository,
    WeeklyReportRepository,
)
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import (
    DailyReport,
    MigrationSummary,
    MonthlyIndexItem,
    ReportIndexItem,
    ReportSection,
    UserContext,
    WeeklyIndexItem,
)
from dailychewer_backend.services import build_runtime
from dailychewer_backend.utils.date_utils import now_timestamp, parse_date


class LegacyIndexMigrationService:
    """Migrate legacy local index data into one database-backed user scope."""

    def __init__(self, project_root: Path | None = None):
        self.settings, self.index_store, self.file_store, _, self.logger = build_runtime(project_root=project_root)
        if not self.settings.database_url:
            raise ValueError("DATABASE_URL is required for migrate-index.")
        self.session_factory = get_session_maker(self.settings)

    def migrate(
        self,
        username: str,
        apply: bool = False,
        copy_files: bool = False,
    ) -> MigrationSummary:
        """Dry-run or apply a migration from legacy index.json into one user scope."""

        with self.session_factory() as session:
            user = UserRepository(session).get_by_username(username)
            if user is None:
                raise ValueError("User not found. Please create the user via Web UI or auth command.")
            user_context = UserContext(user_id=user.id, username=user.username, storage_mode="database")

        data = self.index_store.load()
        summary = MigrationSummary(
            dry_run=not apply,
            reports_found=len(data.reports),
            weekly_found=len(data.weekly_reports),
            monthly_found=len(data.monthly_reports),
        )

        self.file_store.ensure_user_directories(user_context.user_id)
        report_plan = [self._plan_report_migration(user_context, item) for item in data.reports]
        weekly_plan = [self._plan_weekly_migration(user_context, item) for item in data.weekly_reports]
        monthly_plan = [self._plan_monthly_migration(user_context, item) for item in data.monthly_reports]
        summary.skipped_existing += sum(1 for _, exists in report_plan if exists)
        summary.skipped_existing += sum(1 for _, exists in weekly_plan if exists)
        summary.skipped_existing += sum(1 for _, exists in monthly_plan if exists)
        summary.migration_ids.extend(plan["migration_id"] for plan, _ in report_plan)
        summary.migration_ids.extend(plan["migration_id"] for plan, _ in weekly_plan)
        summary.migration_ids.extend(plan["migration_id"] for plan, _ in monthly_plan)
        if copy_files:
            summary.copied_files = sum(
                1
                for path_map, _ in report_plan
                for original, target in (
                    (path_map["raw"], path_map["planned_raw"]),
                    (path_map["optimized"], path_map["planned_optimized"]),
                )
                if str(original) != str(target)
            )
            summary.copied_files += sum(
                1
                for path_map, _ in weekly_plan
                if str(path_map["file"]) != str(path_map["planned_file"])
            )
            summary.copied_files += sum(
                1
                for path_map, _ in monthly_plan
                if str(path_map["file"]) != str(path_map["planned_file"])
            )
        if not apply:
            return summary

        for item, (paths, exists) in zip(data.reports, report_plan):
            if exists:
                summary.skipped += 1
                continue
            try:
                self._migrate_report_item(user_context, item, copy_files=copy_files, planned_paths=paths)
                summary.reports_migrated += 1
            except Exception as exc:
                summary.errors.append(f"report {item.date}: {exc}")
                summary.skipped += 1

        for item, (paths, exists) in zip(data.weekly_reports, weekly_plan):
            if exists:
                summary.skipped += 1
                continue
            try:
                self._migrate_weekly_item(user_context, item, copy_files=copy_files, planned_paths=paths)
                summary.weekly_migrated += 1
            except Exception as exc:
                summary.errors.append(f"weekly {item.week}: {exc}")
                summary.skipped += 1

        for item, (paths, exists) in zip(data.monthly_reports, monthly_plan):
            if exists:
                summary.skipped += 1
                continue
            try:
                self._migrate_monthly_item(user_context, item, copy_files=copy_files, planned_paths=paths)
                summary.monthly_migrated += 1
            except Exception as exc:
                summary.errors.append(f"monthly {item.month}: {exc}")
                summary.skipped += 1
        return summary

    def _migrate_report_item(
        self,
        user_context: UserContext,
        item: ReportIndexItem,
        copy_files: bool,
        planned_paths: dict[str, Path],
    ) -> None:
        raw_path = self._materialize_legacy_copy(Path(item.raw_file), planned_paths["planned_raw"], copy_files)
        optimized_path = self._materialize_legacy_copy(Path(item.optimized_file), planned_paths["planned_optimized"], copy_files)
        report = self._load_or_build_daily_report(item, optimized_path)
        payload = report.model_dump(by_alias=True)
        payload["_migration"] = {
            "migration_id": planned_paths["migration_id"],
            "source": "legacy_index_json",
            "legacy_raw_file": str(Path(item.raw_file).expanduser().resolve()),
            "legacy_optimized_file": str(Path(item.optimized_file).expanduser().resolve()),
            "migrated_at": now_timestamp(),
        }
        with self.session_factory() as session:
            project_record = ProjectRepository(session).get_or_create_project(user_context.user_id, item.project)
            tag_records = TagRepository(session).get_or_create_tags(user_context.user_id, item.tags)
            UploadedFileRepository(session).create_uploaded_file(
                user_id=user_context.user_id,
                original_filename=Path(raw_path).name,
                stored_file_path=str(raw_path),
                purpose="raw_daily",
                size_bytes=Path(raw_path).stat().st_size if Path(raw_path).exists() else None,
            )
            UploadedFileRepository(session).create_uploaded_file(
                user_id=user_context.user_id,
                original_filename=Path(optimized_path).name,
                stored_file_path=str(optimized_path),
                purpose="raw_daily",
                size_bytes=Path(optimized_path).stat().st_size if Path(optimized_path).exists() else None,
            )
            DailyReportRepository(session).create_daily_report(
                user_id=user_context.user_id,
                report_date=parse_date(item.date),
                weekday=item.weekday,
                iso_week=item.week,
                project_id=project_record.id if project_record else None,
                source_format=item.source_format,
                raw_file_path=str(raw_path),
                optimized_file_path=str(optimized_path),
                quality_score_total=item.quality_score,
                daily_report_json=payload,
                tags=tag_records,
            )

    def _migrate_weekly_item(
        self,
        user_context: UserContext,
        item: WeeklyIndexItem,
        copy_files: bool,
        planned_paths: dict[str, Path],
    ) -> None:
        target_path = self._materialize_legacy_copy(Path(item.file), planned_paths["planned_file"], copy_files)
        with self.session_factory() as session:
            project_record = ProjectRepository(session).get_or_create_project(user_context.user_id, item.project)
            tag_records = TagRepository(session).get_or_create_tags(user_context.user_id, item.tags)
            UploadedFileRepository(session).create_uploaded_file(
                user_id=user_context.user_id,
                original_filename=Path(target_path).name,
                stored_file_path=str(target_path),
                purpose="export_weekly",
                size_bytes=Path(target_path).stat().st_size if Path(target_path).exists() else None,
            )
            WeeklyReportRepository(session).create_weekly_report(
                user_id=user_context.user_id,
                iso_week=item.week,
                from_date=parse_date(item.date_range.from_date) if item.date_range else None,
                to_date=parse_date(item.date_range.to_date) if item.date_range else None,
                project_id=project_record.id if project_record else None,
                report_format=item.format,
                style=item.style,
                file_path=str(target_path),
                report_json={
                    "_migration": {
                        "migration_id": planned_paths["migration_id"],
                        "source": "legacy_index_json",
                        "legacy_weekly_file": str(Path(item.file).expanduser().resolve()),
                        "migrated_at": now_timestamp(),
                    }
                },
                preview_text=None,
                tags=tag_records,
            )

    def _migrate_monthly_item(
        self,
        user_context: UserContext,
        item: MonthlyIndexItem,
        copy_files: bool,
        planned_paths: dict[str, Path],
    ) -> None:
        target_path = self._materialize_legacy_copy(Path(item.file), planned_paths["planned_file"], copy_files)
        with self.session_factory() as session:
            project_record = ProjectRepository(session).get_or_create_project(user_context.user_id, item.project)
            tag_records = TagRepository(session).get_or_create_tags(user_context.user_id, item.tags)
            UploadedFileRepository(session).create_uploaded_file(
                user_id=user_context.user_id,
                original_filename=Path(target_path).name,
                stored_file_path=str(target_path),
                purpose="export_monthly",
                size_bytes=Path(target_path).stat().st_size if Path(target_path).exists() else None,
            )
            MonthlyReportRepository(session).create_monthly_report(
                user_id=user_context.user_id,
                month=item.month,
                project_id=project_record.id if project_record else None,
                report_format=item.format,
                style=item.style,
                file_path=str(target_path),
                report_json={
                    "_migration": {
                        "migration_id": planned_paths["migration_id"],
                        "source": "legacy_index_json",
                        "legacy_monthly_file": str(Path(item.file).expanduser().resolve()),
                        "migrated_at": now_timestamp(),
                    }
                },
                preview_text=None,
                tags=tag_records,
            )

    def _plan_report_migration(self, user_context: UserContext, item: ReportIndexItem) -> tuple[dict[str, Path], bool]:
        """Prepare paths and existence checks for one daily report migration."""

        raw = Path(item.raw_file).expanduser().resolve()
        optimized = Path(item.optimized_file).expanduser().resolve()
        planned_raw = self._build_legacy_copy_target(user_context, raw, "raw")
        planned_optimized = self._build_legacy_copy_target(user_context, optimized, "optimized")
        migration_id = self._daily_migration_id(user_context.user_id, item)
        return {
            "raw": raw,
            "optimized": optimized,
            "planned_raw": planned_raw,
            "planned_optimized": planned_optimized,
            "migration_id": migration_id,
        }, self._daily_migration_exists(user_context, item, migration_id)

    def _plan_weekly_migration(self, user_context: UserContext, item: WeeklyIndexItem) -> tuple[dict[str, Path], bool]:
        file_path = Path(item.file).expanduser().resolve()
        migration_id = self._weekly_migration_id(user_context.user_id, item)
        return {
            "file": file_path,
            "planned_file": self._build_legacy_copy_target(user_context, file_path, "weekly"),
            "migration_id": migration_id,
        }, self._weekly_migration_exists(user_context, item, migration_id)

    def _plan_monthly_migration(self, user_context: UserContext, item: MonthlyIndexItem) -> tuple[dict[str, Path], bool]:
        file_path = Path(item.file).expanduser().resolve()
        migration_id = self._monthly_migration_id(user_context.user_id, item)
        return {
            "file": file_path,
            "planned_file": self._build_legacy_copy_target(user_context, file_path, "monthly"),
            "migration_id": migration_id,
        }, self._monthly_migration_exists(user_context, item, migration_id)

    def _daily_migration_exists(self, user_context: UserContext, item: ReportIndexItem, migration_id: str) -> bool:
        with self.session_factory() as session:
            records = DailyReportRepository(session).list_daily_reports(user_context.user_id)
        legacy_raw = str(Path(item.raw_file).expanduser().resolve())
        legacy_optimized = str(Path(item.optimized_file).expanduser().resolve())
        for record in records:
            payload = record.daily_report_json or {}
            migration = payload.get("_migration", {})
            if migration.get("migration_id") == migration_id:
                return True
            if migration.get("legacy_optimized_file") == legacy_optimized:
                return True
            if migration.get("legacy_raw_file") == legacy_raw:
                return True
            if record.raw_file_path == legacy_raw or record.optimized_file_path == legacy_optimized:
                return True
        return False

    def _weekly_migration_exists(self, user_context: UserContext, item: WeeklyIndexItem, migration_id: str) -> bool:
        with self.session_factory() as session:
            records = WeeklyReportRepository(session).list_weekly_reports(user_context.user_id)
        legacy_file = str(Path(item.file).expanduser().resolve())
        for record in records:
            payload = record.report_json or {}
            migration = payload.get("_migration", {})
            if migration.get("migration_id") == migration_id:
                return True
            if migration.get("legacy_weekly_file") == legacy_file:
                return True
            if record.file_path == legacy_file:
                return True
        return False

    def _monthly_migration_exists(self, user_context: UserContext, item: MonthlyIndexItem, migration_id: str) -> bool:
        with self.session_factory() as session:
            records = MonthlyReportRepository(session).list_monthly_reports(user_context.user_id)
        legacy_file = str(Path(item.file).expanduser().resolve())
        for record in records:
            payload = record.report_json or {}
            migration = payload.get("_migration", {})
            if migration.get("migration_id") == migration_id:
                return True
            if migration.get("legacy_monthly_file") == legacy_file:
                return True
            if record.file_path == legacy_file:
                return True
        return False

    def _daily_migration_id(self, user_id: str, item: ReportIndexItem) -> str:
        raw = str(Path(item.raw_file).expanduser().resolve())
        optimized = str(Path(item.optimized_file).expanduser().resolve())
        seed = f"daily_report|{user_id}|{item.date}|{raw}|{optimized}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def _weekly_migration_id(self, user_id: str, item: WeeklyIndexItem) -> str:
        file_path = str(Path(item.file).expanduser().resolve())
        seed = f"weekly_report|{user_id}|{item.week}|{file_path}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def _monthly_migration_id(self, user_id: str, item: MonthlyIndexItem) -> str:
        file_path = str(Path(item.file).expanduser().resolve())
        seed = f"monthly_report|{user_id}|{item.month}|{file_path}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def _build_legacy_copy_target(self, user_context: UserContext, path: Path, bucket: str) -> Path:
        """Build a unique target path for one copied legacy file without overwriting existing files."""

        resolved = path.expanduser().resolve()
        target_dir = self.file_store.user_root(user_context.user_id) / "legacy" / bucket
        target_dir.mkdir(parents=True, exist_ok=True)
        short_hash = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
        timestamp = now_timestamp().replace("-", "").replace(":", "").replace("T", "_")[:15]
        base_name = f"{timestamp}_{short_hash}_{resolved.name}"
        candidate = target_dir / base_name
        counter = 1
        while candidate.exists():
            suffix = resolved.suffix
            stem = candidate.stem if candidate.suffix else candidate.name
            candidate = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        return candidate

    def _materialize_legacy_copy(self, source: Path, target: Path, copy_files: bool) -> Path:
        """Copy one legacy file to a unique target when requested, otherwise keep original path."""

        resolved = source.expanduser().resolve()
        if not copy_files or not resolved.exists():
            return resolved
        shutil.copy2(resolved, target)
        return target

    def _load_or_build_daily_report(self, item: ReportIndexItem, optimized_path: Path) -> DailyReport:
        """Load embedded structured JSON when possible, otherwise build a conservative fallback."""

        if optimized_path.exists():
            try:
                report = self.file_store.load_optimized_report(optimized_path)
                report.date = item.date
                report.weekday = item.weekday
                report.week = item.week
                return report
            except Exception:
                pass
        return DailyReport(
            date=item.date,
            weekday=item.weekday,
            week=item.week,
            morning=ReportSection(work_content=["Legacy optimized report content not fully recoverable."]),
            afternoon=ReportSection(work_content=[]),
            questions=[],
        )
