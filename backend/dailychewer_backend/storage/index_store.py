"""Index persistence for raw, optimized, and weekly reports."""

from __future__ import annotations

import json
from pathlib import Path

from dailychewer_backend.models import DateRange, IndexData, MonthlyIndexItem, ReportIndexItem, WeeklyIndexItem
from dailychewer_backend.utils.date_utils import month_bounds, normalize_date


class IndexStore:
    """Manage `data/index.json` and provide simple query/update methods."""

    def __init__(self, index_file: Path):
        self.index_file = index_file

    def ensure_initialized(self) -> None:
        """Create parent directories and a fresh index file when missing."""

        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self.save(IndexData())

    def load(self) -> IndexData:
        """Load index data or raise a clear error when the file is corrupted."""

        self.ensure_initialized()
        try:
            payload = json.loads(self.index_file.read_text(encoding="utf-8"))
            return IndexData.model_validate(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("index.json 已损坏，无法解析。") from exc
        except Exception as exc:
            raise ValueError("index.json 数据结构无效。") from exc

    def save(self, data: IndexData) -> None:
        """Persist index data back to disk."""

        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        self.index_file.write_text(
            json.dumps(data.model_dump(by_alias=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def find_report_by_date(self, date_str: str) -> ReportIndexItem | None:
        """Return the index item for a date when it exists."""

        data = self.load()
        for item in data.reports:
            if item.date == date_str:
                return item
        return None

    def list_reports(
        self,
        week: str | None = None,
        project: str | None = None,
        tag: str | None = None,
    ) -> list[ReportIndexItem]:
        """Return all indexed reports, optionally filtered by ISO week."""

        reports = self.load().reports
        if week:
            reports = [item for item in reports if item.week == week]
        return self._filter_reports(reports, project=project, tag=tag)

    def list_reports_by_date_range(
        self,
        from_date: str,
        to_date: str,
        project: str | None = None,
        tag: str | None = None,
    ) -> list[ReportIndexItem]:
        """Return reports whose dates fall inside an inclusive range."""

        start = normalize_date(from_date)
        end = normalize_date(to_date)
        if start > end:
            raise ValueError("--from 不能晚于 --to。")
        reports = [
            item for item in self.load().reports if start <= normalize_date(item.date) <= end
        ]
        return self._filter_reports(reports, project=project, tag=tag)

    def list_reports_by_month(
        self,
        month: str,
        project: str | None = None,
        tag: str | None = None,
    ) -> list[ReportIndexItem]:
        """Return reports whose dates fall inside one month."""

        start, end = month_bounds(month)
        return self.list_reports_by_date_range(
            from_date=start,
            to_date=end,
            project=project,
            tag=tag,
        )

    def list_weekly_reports(self, week: str | None = None) -> list[WeeklyIndexItem]:
        """Return all weekly export records, optionally filtered by week."""

        weekly_reports = self.load().weekly_reports
        if week:
            weekly_reports = [item for item in weekly_reports if item.week == week]
        return sorted(weekly_reports, key=lambda item: (item.week, item.format))

    def list_monthly_reports(self, month: str | None = None) -> list[MonthlyIndexItem]:
        """Return all monthly export records, optionally filtered by month."""

        monthly_reports = self.load().monthly_reports
        if month:
            monthly_reports = [item for item in monthly_reports if item.month == month]
        return sorted(monthly_reports, key=lambda item: (item.month, item.format))

    def upsert_report(self, item: ReportIndexItem) -> None:
        """Insert or replace a daily report entry keyed by date."""

        data = self.load()
        updated = False
        reports: list[ReportIndexItem] = []
        for existing in data.reports:
            if existing.date == item.date:
                reports.append(item)
                updated = True
            else:
                reports.append(existing)
        if not updated:
            reports.append(item)
        data.reports = sorted(reports, key=lambda report: report.date)
        self.save(data)

    def upsert_weekly_report(self, item: WeeklyIndexItem) -> None:
        """Insert or replace a weekly export entry keyed by week and format."""

        data = self.load()
        updated = False
        weekly_reports: list[WeeklyIndexItem] = []
        for existing in data.weekly_reports:
            if (
                existing.week == item.week
                and existing.format == item.format
                and self._same_date_range(existing.date_range, item.date_range)
            ):
                weekly_reports.append(item)
                updated = True
            else:
                weekly_reports.append(existing)
        if not updated:
            weekly_reports.append(item)
        data.weekly_reports = sorted(weekly_reports, key=lambda report: (report.week, report.format))
        self.save(data)

    def upsert_monthly_report(self, item: MonthlyIndexItem) -> None:
        """Insert or replace a monthly export entry keyed by month and format."""

        data = self.load()
        updated = False
        monthly_reports: list[MonthlyIndexItem] = []
        for existing in data.monthly_reports:
            if existing.month == item.month and existing.format == item.format:
                monthly_reports.append(item)
                updated = True
            else:
                monthly_reports.append(existing)
        if not updated:
            monthly_reports.append(item)
        data.monthly_reports = sorted(monthly_reports, key=lambda report: (report.month, report.format))
        self.save(data)

    def remove_week(self, week: str) -> tuple[list[ReportIndexItem], list[WeeklyIndexItem]]:
        """Remove all index entries belonging to one ISO week."""

        data = self.load()
        removed_reports = [item for item in data.reports if item.week == week]
        removed_weekly = [item for item in data.weekly_reports if item.week == week]
        data.reports = [item for item in data.reports if item.week != week]
        data.weekly_reports = [item for item in data.weekly_reports if item.week != week]
        self.save(data)
        return removed_reports, removed_weekly

    def remove_reports_by_dates(self, dates: list[str]) -> list[ReportIndexItem]:
        """Remove specific daily report entries by date."""

        target_dates = set(dates)
        data = self.load()
        removed = [item for item in data.reports if item.date in target_dates]
        data.reports = [item for item in data.reports if item.date not in target_dates]
        self.save(data)
        return removed

    def remove_weekly_report_item(
        self,
        week: str,
        report_format: str,
        date_range: DateRange | None = None,
    ) -> list[WeeklyIndexItem]:
        """Remove one or more weekly export entries matching week/format/range."""

        data = self.load()
        removed = [
            item
            for item in data.weekly_reports
            if item.week == week
            and item.format == report_format
            and self._same_date_range(item.date_range, date_range)
        ]
        data.weekly_reports = [
            item
            for item in data.weekly_reports
            if not (
                item.week == week
                and item.format == report_format
                and self._same_date_range(item.date_range, date_range)
            )
        ]
        self.save(data)
        return removed

    def _same_date_range(self, left: DateRange | None, right: DateRange | None) -> bool:
        """Compare optional date ranges while remaining compatible with old index files."""

        if left is None and right is None:
            return True
        if left is None or right is None:
            return False
        return left.from_date == right.from_date and left.to_date == right.to_date

    def _filter_reports(
        self,
        reports: list[ReportIndexItem],
        project: str | None = None,
        tag: str | None = None,
    ) -> list[ReportIndexItem]:
        """Apply project/tag filters to report lists."""

        filtered = reports
        if project:
            filtered = [item for item in filtered if item.project == project]
        if tag:
            filtered = [item for item in filtered if tag in item.tags]
        return sorted(filtered, key=lambda item: item.date)
