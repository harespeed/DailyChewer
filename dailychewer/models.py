"""Pydantic models used across DailyChewer."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class DateRange(BaseModel):
    """Inclusive date range metadata used by custom weekly exports."""

    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")

    model_config = {"populate_by_name": True}


class ReportSection(BaseModel):
    """Structured content for one half-day section."""

    work_content: list[str] = Field(default_factory=list)
    personal_growth: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    solutions: list[str] = Field(default_factory=list)


class DailyQualityScore(BaseModel):
    """Quality score derived from the original daily report text."""

    work_clarity: int
    progress_clarity: int
    problem_completeness: int
    solution_clarity: int
    growth_reflection: int
    total: int
    comments: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_score_range(self) -> "DailyQualityScore":
        """Ensure sub-scores and total stay consistent with the 25-point rubric."""

        parts = [
            self.work_clarity,
            self.progress_clarity,
            self.problem_completeness,
            self.solution_clarity,
            self.growth_reflection,
        ]
        if any(score < 0 or score > 5 for score in parts):
            raise ValueError("Daily quality score sub-items must stay between 0 and 5.")
        computed_total = sum(parts)
        if self.total != computed_total:
            self.total = computed_total
        return self


class DailyReport(BaseModel):
    """Structured optimized daily report."""

    date: str
    weekday: str
    week: str
    morning: ReportSection
    afternoon: ReportSection
    questions: list[str] = Field(default_factory=list)
    quality_score: DailyQualityScore | None = None


class WeeklyReport(BaseModel):
    """Structured weekly report built from daily reports."""

    week: str
    start_date: str
    end_date: str
    date_range: DateRange | None = None
    style: str = "concise"
    days: dict[str, DailyReport] = Field(default_factory=dict)
    weekly_gains: list[str] = Field(default_factory=list)


class MonthlyReport(BaseModel):
    """Structured monthly report built from optimized daily reports."""

    month: str
    start_date: str
    end_date: str
    style: str = "formal"
    main_work: list[str] = Field(default_factory=list)
    key_progress: list[str] = Field(default_factory=list)
    problems_and_solutions: list[str] = Field(default_factory=list)
    personal_growth: list[str] = Field(default_factory=list)
    monthly_gains: list[str] = Field(default_factory=list)
    next_improvements: list[str] = Field(default_factory=list)


class ReportIndexItem(BaseModel):
    """Metadata entry for one ingested daily report."""

    date: str
    weekday: str
    week: str
    raw_file: str
    optimized_file: str
    source_format: str
    created_at: str
    updated_at: str
    status: str
    quality_score: int | None = None
    project: str | None = None
    tags: list[str] = Field(default_factory=list)


class WeeklyIndexItem(BaseModel):
    """Metadata entry for one exported weekly report."""

    week: str
    date_range: DateRange | None = None
    format: str
    style: str = "concise"
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    file: str
    created_at: str


class MonthlyIndexItem(BaseModel):
    """Metadata entry for one exported monthly report."""

    month: str
    format: str
    style: str = "formal"
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    file: str
    created_at: str


class IndexData(BaseModel):
    """Container persisted in `data/index.json`."""

    reports: list[ReportIndexItem] = Field(default_factory=list)
    weekly_reports: list[WeeklyIndexItem] = Field(default_factory=list)
    monthly_reports: list[MonthlyIndexItem] = Field(default_factory=list)
