"""Shared weekly report generation and cleanup service."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.db.repositories import (
    DailyReportRepository,
    ProjectRepository,
    TagRepository,
    UploadedFileRepository,
    WeeklyReportRepository,
)
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import DateRange, ReportBuildResult, WeeklyIndexItem, WeeklyReport
from dailychewer_backend.report.exporters import export_weekly_report, render_weekly_markdown
from dailychewer_backend.report.weekly_builder import WeeklyReportBuilder
from dailychewer_backend.services import (
    build_runtime,
    normalize_tags,
    read_daily_reports,
    resolve_format,
    resolve_style,
)
from dailychewer_backend.utils.date_utils import (
    current_date_str,
    format_date_range_slug,
    iso_week_for_date,
    normalize_date,
    now_timestamp,
    parse_date,
    week_label_for_range,
)
from dailychewer_backend.models import DailyReport, UserContext


class WeeklyService:
    """Build and optionally persist weekly reports from optimized dailies."""

    def __init__(self, project_root: Path | None = None, user_context: UserContext | None = None):
        self.settings, self.index_store, self.file_store, self.optimizer, self.logger = build_runtime(
            project_root=project_root
        )
        self.user_context = user_context or UserContext(storage_mode="local")
        self.session_factory = (
            get_session_maker(self.settings)
            if self.user_context.storage_mode == "database" and self.settings.database_url
            else None
        )

    def build_weekly_report(
        self,
        week: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        fmt: str = "markdown",
        style: str = "concise",
        project: str | None = None,
        tags: list[str] | None = None,
        preview: bool = False,
        save: bool = True,
    ) -> ReportBuildResult:
        """Generate a weekly report preview and optionally persist it."""

        target_week, date_range = self._resolve_target(week=week, from_date=from_date, to_date=to_date)
        resolved_format = resolve_format(fmt, self.settings.report.default_format)
        resolved_style = resolve_style(style, self.settings.report.default_weekly_style)
        normalized_tags = normalize_tags(tags)
        if self.user_context.storage_mode == "database":
            report_items, daily_reports = self._read_database_daily_reports(
                week=target_week if date_range is None else None,
                from_date=date_range[0] if date_range else None,
                to_date=date_range[1] if date_range else None,
                project=project,
                tags=normalized_tags,
            )
        else:
            report_items, daily_reports = read_daily_reports(
                index_store=self.index_store,
                file_store=self.file_store,
                week=target_week if date_range is None else None,
                from_date=date_range[0] if date_range else None,
                to_date=date_range[1] if date_range else None,
                project=project,
                tag=normalized_tags[0] if len(normalized_tags) == 1 else None,
            )
            if len(normalized_tags) > 1:
                report_items = [item for item in report_items if all(tag in item.tags for tag in normalized_tags)]
                daily_reports = [self.file_store.load_optimized_report(Path(item.optimized_file)) for item in report_items]
                if not report_items:
                    raise ValueError("No optimized daily reports found for the selected week or date range.")

        self.logger.info(
            "weekly_start week=%s date_range=%s format=%s style=%s reports=%s project=%s tags=%s preview=%s save=%s",
            target_week,
            date_range,
            resolved_format,
            resolved_style,
            len(report_items),
            project,
            normalized_tags,
            preview,
            save,
        )
        try:
            weekly_report = WeeklyReportBuilder(self.optimizer).build(
                daily_reports,
                target_week,
                date_range=date_range,
                style=resolved_style,
            )
        except ValueError as exc:
            if "Failed to parse LLM JSON response after retries" not in str(exc):
                raise
            self.logger.warning(
                "weekly_llm_parse_failed_using_fallback week=%s date_range=%s reports=%s error=%s",
                target_week,
                date_range,
                len(daily_reports),
                exc,
            )
            weekly_report = self._build_fallback_weekly_report(
                daily_reports=daily_reports,
                week=target_week,
                date_range=date_range,
                style=resolved_style,
            )
        preview_text = render_weekly_markdown(weekly_report)
        result = ReportBuildResult(
            report_type="weekly",
            preview=preview_text,
            week=target_week,
            format=resolved_format,
            style=resolved_style,
            saved=False,
        )
        if not save:
            return result

        slug = format_date_range_slug(date_range[0], date_range[1]) if date_range else None
        output_path = self.file_store.build_weekly_output_path(
            target_week,
            resolved_format,
            date_range_slug=slug,
            user_id=self.user_context.user_id if self.user_context.storage_mode == "database" else None,
        )
        export_weekly_report(weekly_report, output_path, resolved_format)
        if self.user_context.storage_mode == "database":
            if not self.user_context.user_id or self.session_factory is None:
                raise ValueError("Database mode requires a valid user context.")
            with self.session_factory() as session:
                project_record = ProjectRepository(session).get_or_create_project(
                    self.user_context.user_id,
                    project,
                )
                tag_records = TagRepository(session).get_or_create_tags(
                    self.user_context.user_id,
                    normalized_tags,
                )
                file_record = UploadedFileRepository(session).create_uploaded_file(
                    user_id=self.user_context.user_id,
                    original_filename=output_path.name,
                    stored_file_path=str(output_path),
                    purpose="export_weekly",
                    size_bytes=output_path.stat().st_size if output_path.exists() else None,
                )
                WeeklyReportRepository(session).create_weekly_report(
                    user_id=self.user_context.user_id,
                    iso_week=target_week,
                    from_date=parse_date(date_range[0]) if date_range else None,
                    to_date=parse_date(date_range[1]) if date_range else None,
                    project_id=project_record.id if project_record else None,
                    report_format=resolved_format,
                    style=resolved_style,
                    file_path=str(output_path),
                    report_json=weekly_report.model_dump(by_alias=True),
                    preview_text=preview_text,
                    tags=tag_records,
                )
            self.logger.info("weekly_exported path=%s", output_path)
            result.saved = True
            result.file = str(output_path)
            result.file_id = file_record.id
            result.download_path = f"/api/files/{file_record.id}/download"
            return result
        weekly_item = WeeklyIndexItem(
            week=target_week,
            date_range=DateRange.model_validate({"from": date_range[0], "to": date_range[1]}) if date_range else None,
            format=resolved_format,
            style=resolved_style,
            project=project,
            tags=normalized_tags,
            file=str(output_path),
            created_at=now_timestamp(),
        )
        self.index_store.upsert_weekly_report(weekly_item)
        self.logger.info("weekly_exported path=%s", output_path)
        result.saved = True
        result.file = str(output_path)
        result.download_path = str(output_path)
        return result

    def cleanup_week(self, week: str) -> int:
        """Delete all raw, optimized, and weekly artifacts for one ISO week."""

        reports = self.index_store.list_reports(week=week)
        weekly_reports = self.index_store.list_weekly_reports(week=week)
        raw_dir = self.file_store.settings.raw_dir / week
        optimized_dir = self.file_store.settings.optimized_dir / week
        weekly_dir = self.file_store.settings.weekly_dir / week

        paths_to_delete = {Path(item.raw_file) for item in reports} | {
            Path(item.optimized_file) for item in reports
        } | {Path(item.file) for item in weekly_reports}
        for directory in (raw_dir, optimized_dir, weekly_dir):
            if directory.exists():
                paths_to_delete.update(path for path in directory.iterdir() if path.is_file())

        deleted = self.file_store.delete_paths(sorted(paths_to_delete, key=lambda path: str(path)))
        self.file_store.cleanup_empty_directories([raw_dir, optimized_dir, weekly_dir])
        self.index_store.remove_week(week)
        self.logger.info("week_deleted week=%s deleted_files=%s", week, len(deleted))
        return len(deleted)

    def cleanup_date_range_export(
        self,
        week: str,
        from_date: str,
        to_date: str,
        report_format: str,
    ) -> int:
        """Delete one explicit range export and underlying daily reports."""

        report_items = self.index_store.list_reports_by_date_range(from_date, to_date)
        raw_paths = [Path(item.raw_file) for item in report_items]
        optimized_paths = [Path(item.optimized_file) for item in report_items]
        weekly_paths = [
            Path(item.file)
            for item in self.index_store.list_weekly_reports(week=week)
            if item.format == report_format
            and item.date_range
            and item.date_range.from_date == normalize_date(from_date)
            and item.date_range.to_date == normalize_date(to_date)
        ]
        deleted = self.file_store.delete_paths(raw_paths + optimized_paths + weekly_paths)
        self.file_store.cleanup_empty_directories(
            sorted(
                {path.parent for path in raw_paths + optimized_paths + weekly_paths},
                key=lambda path: str(path),
            )
        )
        self.index_store.remove_reports_by_dates([item.date for item in report_items])
        self.index_store.remove_weekly_report_item(
            week=week,
            report_format=report_format,
            date_range=DateRange.model_validate({"from": from_date, "to": to_date}),
        )
        self.logger.info("range_deleted week=%s date_range=%s..%s deleted_files=%s", week, from_date, to_date, len(deleted))
        return len(deleted)

    def _resolve_target(
        self,
        week: str | None,
        from_date: str | None,
        to_date: str | None,
    ) -> tuple[str, tuple[str, str] | None]:
        """Resolve week mode vs explicit date-range mode."""

        if bool(from_date) ^ bool(to_date):
            raise ValueError("使用日期范围时必须同时提供 --from 和 --to。")
        if from_date and to_date:
            normalized_from = normalize_date(from_date)
            normalized_to = normalize_date(to_date)
            return week_label_for_range(normalized_from, normalized_to), (normalized_from, normalized_to)
        return week or iso_week_for_date(current_date_str()), None

    def _read_database_daily_reports(
        self,
        week: str | None,
        from_date: str | None,
        to_date: str | None,
        project: str | None,
        tags: list[str],
    ) -> tuple[list[object], list[DailyReport]]:
        """Load user-scoped daily reports from PostgreSQL-backed metadata."""

        if not self.user_context.user_id or self.session_factory is None:
            raise ValueError("Database mode requires a valid user context.")
        with self.session_factory() as session:
            repo = DailyReportRepository(session)
            if from_date and to_date:
                records = repo.list_daily_reports_by_date_range(
                    user_id=self.user_context.user_id,
                    from_date=parse_date(normalize_date(from_date)),
                    to_date=parse_date(normalize_date(to_date)),
                    project=project,
                    tag=tags[0] if len(tags) == 1 else None,
                )
            else:
                records = repo.list_daily_reports(
                    user_id=self.user_context.user_id,
                    week=week,
                    project=project,
                    tag=tags[0] if len(tags) == 1 else None,
                )
        if len(tags) > 1:
            records = [record for record in records if all(tag in [item.name for item in record.tags] for tag in tags)]
        if not records:
            raise ValueError("No optimized daily reports found for the selected week or date range.")
        return records, [DailyReport.model_validate(record.daily_report_json) for record in records]

    def _build_fallback_weekly_report(
        self,
        daily_reports: list[DailyReport],
        week: str,
        date_range: tuple[str, str] | None,
        style: str,
    ) -> WeeklyReport:
        """Build a deterministic stage report from optimized dailies when LLM JSON fails."""

        days = {report.date: report for report in sorted(daily_reports, key=lambda item: item.date)}
        start_date = date_range[0] if date_range else (daily_reports[0].date if daily_reports else current_date_str())
        end_date = date_range[1] if date_range else (daily_reports[-1].date if daily_reports else current_date_str())
        gains: list[str] = []
        seen: set[str] = set()
        for report in sorted(daily_reports, key=lambda item: item.date):
            for item in report.morning.personal_growth + report.afternoon.personal_growth:
                cleaned = item.strip()
                if cleaned and cleaned not in seen and cleaned != "暂无日报记录":
                    seen.add(cleaned)
                    gains.append(cleaned)
        return WeeklyReport(
            week=week,
            start_date=start_date,
            end_date=end_date,
            date_range=DateRange.model_validate({"from": date_range[0], "to": date_range[1]}) if date_range else None,
            style=style,
            days=days,
            weekly_gains=gains or ["LLM 周报汇总失败，已基于优化日报生成保守阶段报。"],
        )
