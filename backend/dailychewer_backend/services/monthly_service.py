"""Shared monthly report generation service."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.db.repositories import (
    DailyReportRepository,
    MonthlyReportRepository,
    ProjectRepository,
    TagRepository,
    UploadedFileRepository,
)
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import DailyReport, MonthlyIndexItem, ReportBuildResult, UserContext
from dailychewer_backend.report.exporters import export_monthly_report, render_monthly_markdown
from dailychewer_backend.report.weekly_builder import WeeklyReportBuilder
from dailychewer_backend.services import (
    build_runtime,
    normalize_tags,
    read_daily_reports,
    resolve_format,
    resolve_style,
)
from dailychewer_backend.utils.date_utils import now_timestamp


class MonthlyService:
    """Build and optionally persist monthly reports from optimized dailies."""

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

    def build_monthly_report(
        self,
        month: str,
        fmt: str = "markdown",
        style: str = "formal",
        project: str | None = None,
        tags: list[str] | None = None,
        preview: bool = False,
        save: bool = True,
    ) -> ReportBuildResult:
        """Generate a monthly report preview and optionally persist it."""

        normalized_month = month.strip()
        resolved_format = resolve_format(fmt, self.settings.report.default_format)
        resolved_style = resolve_style(style, self.settings.report.default_monthly_style)
        normalized_tags = normalize_tags(tags)
        if self.user_context.storage_mode == "database":
            daily_reports = self._read_database_monthly_reports(normalized_month, project, normalized_tags)
        else:
            _, daily_reports = read_daily_reports(
                index_store=self.index_store,
                file_store=self.file_store,
                month=normalized_month,
                project=project,
                tag=normalized_tags[0] if len(normalized_tags) == 1 else None,
            )
            if len(normalized_tags) > 1:
                report_items = self.index_store.list_reports_by_month(month=normalized_month, project=project)
                report_items = [item for item in report_items if all(tag in item.tags for tag in normalized_tags)]
                daily_reports = [self.file_store.load_optimized_report(Path(item.optimized_file)) for item in report_items]
                if not daily_reports:
                    raise ValueError("No optimized daily reports found for the selected month.")

        self.logger.info(
            "monthly_start month=%s format=%s style=%s reports=%s project=%s tags=%s preview=%s save=%s",
            normalized_month,
            resolved_format,
            resolved_style,
            len(daily_reports),
            project,
            normalized_tags,
            preview,
            save,
        )
        monthly_report = WeeklyReportBuilder(self.optimizer).build_monthly(
            daily_reports,
            normalized_month,
            style=resolved_style,
        )
        preview_text = render_monthly_markdown(monthly_report)
        result = ReportBuildResult(
            report_type="monthly",
            preview=preview_text,
            month=normalized_month,
            format=resolved_format,
            style=resolved_style,
            saved=False,
        )
        if not save:
            return result

        output_path = self.file_store.build_monthly_output_path(
            normalized_month,
            resolved_format,
            user_id=self.user_context.user_id if self.user_context.storage_mode == "database" else None,
        )
        export_monthly_report(monthly_report, output_path, resolved_format)
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
                    purpose="export_monthly",
                    size_bytes=output_path.stat().st_size if output_path.exists() else None,
                )
                MonthlyReportRepository(session).create_monthly_report(
                    user_id=self.user_context.user_id,
                    month=normalized_month,
                    project_id=project_record.id if project_record else None,
                    report_format=resolved_format,
                    style=resolved_style,
                    file_path=str(output_path),
                    report_json=monthly_report.model_dump(by_alias=True),
                    preview_text=preview_text,
                    tags=tag_records,
                )
            self.logger.info("monthly_exported path=%s", output_path)
            result.saved = True
            result.file = str(output_path)
            result.file_id = file_record.id
            result.download_path = f"/api/files/{file_record.id}/download"
            return result
        self.index_store.upsert_monthly_report(
            MonthlyIndexItem(
                month=normalized_month,
                format=resolved_format,
                style=resolved_style,
                project=project,
                tags=normalized_tags,
                file=str(output_path),
                created_at=now_timestamp(),
            )
        )
        self.logger.info("monthly_exported path=%s", output_path)
        result.saved = True
        result.file = str(output_path)
        result.download_path = str(output_path)
        return result

    def _read_database_monthly_reports(
        self,
        month: str,
        project: str | None,
        tags: list[str],
    ) -> list[DailyReport]:
        """Load one user's monthly daily reports from database mode."""

        if not self.user_context.user_id or self.session_factory is None:
            raise ValueError("Database mode requires a valid user context.")
        with self.session_factory() as session:
            records = DailyReportRepository(session).list_daily_reports_by_month(
                user_id=self.user_context.user_id,
                month=month,
                project=project,
                tag=tags[0] if len(tags) == 1 else None,
            )
        if len(tags) > 1:
            records = [record for record in records if all(tag in [item.name for item in record.tags] for tag in tags)]
        if not records:
            raise ValueError("No optimized daily reports found for the selected month.")
        return [DailyReport.model_validate(record.daily_report_json) for record in records]
