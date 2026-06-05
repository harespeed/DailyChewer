"""Pydantic models used across DailyChewer."""

from __future__ import annotations

from typing import Literal

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


class IngestResult(BaseModel):
    """Result returned by the shared ingest service."""

    saved: bool = False
    source_format: str
    daily_report: DailyReport
    questions: list[str] = Field(default_factory=list)
    quality_score: DailyQualityScore | None = None
    raw_text_length: int = 0
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    raw_file: str | None = None
    optimized_file: str | None = None
    index_item: ReportIndexItem | None = None
    existing_report: bool = False


class ReportBuildResult(BaseModel):
    """Shared result for weekly and monthly report generation."""

    report_type: str
    preview: str
    file: str | None = None
    file_id: str | None = None
    download_path: str | None = None
    week: str | None = None
    month: str | None = None
    format: str
    style: str
    saved: bool = False


class SearchResult(BaseModel):
    """One keyword match found in optimized daily reports."""

    date: str
    weekday: str
    week: str
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    matched_section: str
    snippet: str
    optimized_file: str


class DoctorCheckItem(BaseModel):
    """One doctor check row."""

    name: str
    status: str
    value: str
    details: str = ""


class DoctorResult(BaseModel):
    """Structured doctor output for CLI and API consumers."""

    checks: list[DoctorCheckItem] = Field(default_factory=list)


class UserContext(BaseModel):
    """Execution context used to isolate local and database-backed modes."""

    user_id: str | None = None
    username: str | None = None
    storage_mode: Literal["local", "database"] = "local"


class TemplateResult(BaseModel):
    """Structured result for template generation."""

    file: str
    file_id: str | None = None


class UserReadModel(BaseModel):
    """Shared safe user payload for CLI/API/service usage."""

    id: str
    username: str
    display_name: str | None = None
    is_active: bool
    is_admin: bool
    created_at: str


class DatabaseCheckResult(BaseModel):
    """Structured database environment check result."""

    database_url_configured: bool
    database_url_masked: str
    database_reachable: bool = False
    alembic_revision: str | None = None
    users_table_exists: bool = False
    active_admin_exists: bool = False
    details: list[str] = Field(default_factory=list)


class DatabaseInitResult(BaseModel):
    """Structured initialization result for CLI output."""

    database_reachable: bool
    migration_applied: bool
    migration_mode: str
    default_user_created: bool = False
    default_username: str | None = None
    details: list[str] = Field(default_factory=list)


class MigrationSummary(BaseModel):
    """Structured result for legacy index migration."""

    dry_run: bool = True
    reports_found: int = 0
    reports_migrated: int = 0
    weekly_found: int = 0
    weekly_migrated: int = 0
    monthly_found: int = 0
    monthly_migrated: int = 0
    skipped: int = 0
    skipped_existing: int = 0
    copied_files: int = 0
    migration_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BackupCreateResult(BaseModel):
    """Structured backup creation result."""

    backup_path: str
    manifest_path: str
    archive_path: str | None = None
    files_backed_up: bool = False
    database_dumped: bool = False
    dry_run: bool = False
    details: list[str] = Field(default_factory=list)


class BackupVerifyResult(BaseModel):
    """Structured backup verification result."""

    backup_path: str
    manifest_path: str
    total_files: int = 0
    ok: int = 0
    missing: int = 0
    checksum_failed: int = 0
    size_failed: int = 0
    details: list[str] = Field(default_factory=list)


class BackupRestoreResult(BaseModel):
    """Structured backup restore result."""

    backup_path: str
    manifest_path: str
    dry_run: bool = True
    files_restored: bool = False
    database_restored: bool = False
    files_same: int = 0
    file_conflicts: int = 0
    database_conflicts: int = 0
    details: list[str] = Field(default_factory=list)
