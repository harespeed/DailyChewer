"""Weekly report orchestration."""

from __future__ import annotations

from dailychewer.llm.optimizer import ReportOptimizer
from dailychewer.models import DailyReport, MonthlyReport, WeeklyReport


class WeeklyReportBuilder:
    """Thin orchestration layer around the LLM weekly synthesis step."""

    def __init__(self, optimizer: ReportOptimizer):
        self.optimizer = optimizer

    def build(
        self,
        daily_reports: list[DailyReport],
        week: str,
        date_range: tuple[str, str] | None = None,
        style: str = "concise",
    ) -> WeeklyReport:
        """Sort daily reports and delegate the synthesis to the optimizer."""

        ordered = sorted(daily_reports, key=lambda report: report.date)
        return self.optimizer.build_weekly_report(
            ordered,
            week,
            date_range=date_range,
            style=style,
        )

    def build_monthly(
        self,
        daily_reports: list[DailyReport],
        month: str,
        style: str = "formal",
    ) -> MonthlyReport:
        """Sort daily reports and delegate monthly synthesis to the optimizer."""

        ordered = sorted(daily_reports, key=lambda report: report.date)
        return self.optimizer.build_monthly_report(ordered, month, style=style)
