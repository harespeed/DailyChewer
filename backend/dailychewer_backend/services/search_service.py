"""Shared historical report search and listing service."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.db.repositories import DailyReportRepository
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import DailyReport, ReportIndexItem, SearchResult, UserContext
from dailychewer_backend.services import build_runtime, read_daily_reports, search_report_matches
from dailychewer_backend.utils.date_utils import normalize_date, parse_date


class SearchService:
    """Provide shared report listing and keyword search logic."""

    def __init__(self, project_root: Path | None = None, user_context: UserContext | None = None):
        self.settings, self.index_store, self.file_store, _, self.logger = build_runtime(
            project_root=project_root
        )
        self.user_context = user_context or UserContext(storage_mode="local")
        self.session_factory = (
            get_session_maker(self.settings)
            if self.user_context.storage_mode == "database" and self.settings.database_url
            else None
        )

    def list_reports(
        self,
        week: str | None = None,
        project: str | None = None,
        tag: str | None = None,
    ) -> list[ReportIndexItem]:
        """Return indexed daily reports with optional filters."""

        if self.user_context.storage_mode == "database":
            if not self.user_context.user_id or self.session_factory is None:
                raise ValueError("Database mode requires a valid user context.")
            with self.session_factory() as session:
                records = DailyReportRepository(session).list_daily_reports(
                    user_id=self.user_context.user_id,
                    week=week,
                    project=project,
                    tag=tag,
                )
            return [self._record_to_index_item(record) for record in records]
        return self.index_store.list_reports(week=week, project=project, tag=tag)

    def search_reports(
        self,
        query: str,
        week: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        project: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Search optimized daily report content without invoking the LLM."""

        if self.user_context.storage_mode == "database":
            return self._search_database_reports(
                query=query,
                week=week,
                from_date=from_date,
                to_date=to_date,
                project=project,
                tags=tags,
                limit=limit,
            )

        tag = tags[0] if tags else None
        if from_date and to_date:
            report_items, daily_reports = read_daily_reports(
                index_store=self.index_store,
                file_store=self.file_store,
                from_date=from_date,
                to_date=to_date,
                project=project,
                tag=tag,
            )
        elif week:
            report_items, daily_reports = read_daily_reports(
                index_store=self.index_store,
                file_store=self.file_store,
                week=week,
                project=project,
                tag=tag,
            )
        else:
            report_items = self.index_store.list_reports(project=project, tag=tag)
            daily_reports = [
                self.file_store.load_optimized_report(Path(item.optimized_file))
                for item in report_items
            ]

        results: list[SearchResult] = []
        for item, report in zip(report_items, daily_reports):
            if tags and not all(candidate in item.tags for candidate in tags):
                continue
            for section, snippet in search_report_matches(report, query):
                results.append(
                    SearchResult(
                        date=item.date,
                        weekday=item.weekday,
                        week=item.week,
                        project=item.project,
                        tags=item.tags,
                        matched_section=section,
                        snippet=snippet,
                        optimized_file=item.optimized_file,
                    )
                )
                if len(results) >= limit:
                    self.logger.info("search_complete query=%s count=%s", query, len(results))
                    return results
        self.logger.info("search_complete query=%s count=%s", query, len(results))
        return results

    def _search_database_reports(
        self,
        query: str,
        week: str | None,
        from_date: str | None,
        to_date: str | None,
        project: str | None,
        tags: list[str] | None,
        limit: int,
    ) -> list[SearchResult]:
        """Search user-scoped reports from the database-backed mode."""

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
                    tag=tags[0] if tags else None,
                )
            elif week:
                records = repo.list_daily_reports(
                    user_id=self.user_context.user_id,
                    week=week,
                    project=project,
                    tag=tags[0] if tags else None,
                )
            else:
                records = repo.list_daily_reports(
                    user_id=self.user_context.user_id,
                    project=project,
                    tag=tags[0] if tags else None,
                )
        results: list[SearchResult] = []
        for record in records:
            if tags and not all(candidate in [tag.name for tag in record.tags] for candidate in tags):
                continue
            report = DailyReport.model_validate(record.daily_report_json)
            for section, snippet in search_report_matches(report, query):
                results.append(
                    SearchResult(
                        date=record.date.isoformat(),
                        weekday=record.weekday,
                        week=record.iso_week,
                        project=record.project.name if getattr(record, "project", None) else None,
                        tags=[tag.name for tag in record.tags],
                        matched_section=section,
                        snippet=snippet,
                        optimized_file=record.optimized_file_path,
                    )
                )
                if len(results) >= limit:
                    return results
        return results

    def _record_to_index_item(self, record) -> ReportIndexItem:
        """Map one ORM record into the shared CLI/API metadata model."""

        return ReportIndexItem(
            date=record.date.isoformat(),
            weekday=record.weekday,
            week=record.iso_week,
            raw_file=record.raw_file_path,
            optimized_file=record.optimized_file_path,
            source_format=record.source_format,
            created_at=record.created_at.replace(microsecond=0).isoformat(),
            updated_at=record.updated_at.replace(microsecond=0).isoformat(),
            status="optimized",
            quality_score=record.quality_score_total,
            project=record.project.name if getattr(record, "project", None) else None,
            tags=[tag.name for tag in record.tags],
        )
