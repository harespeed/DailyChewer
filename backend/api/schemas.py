"""API request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IngestSaveRequest(BaseModel):
    """Request payload for saving an uploaded report."""

    upload_id: str
    date: str | None = None
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    user_answers: dict[str, str] = Field(default_factory=dict)


class IngestOptimizeRequest(BaseModel):
    """Request payload for re-optimizing one uploaded report preview."""

    upload_id: str
    date: str | None = None
    user_answers: dict[str, str] = Field(default_factory=dict)


class IngestOptimizeTaskResponse(BaseModel):
    """Queued optimize task metadata for API callers."""

    task_id: str
    upload_id: str
    sequence: int
    status: str
    result: dict | None = None
    error_message: str | None = None


class WeeklyRequest(BaseModel):
    """Request payload for weekly report generation."""

    week: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    format: str = "markdown"
    style: str = "concise"
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    save: bool = True


class MonthlyRequest(BaseModel):
    """Request payload for monthly report generation."""

    month: str
    format: str = "markdown"
    style: str = "formal"
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    save: bool = True


class TemplateRequest(BaseModel):
    """Request payload for template generation."""

    date: str | None = None
    format: str = "markdown"


class DailyNoteCreateRequest(BaseModel):
    """Request payload for creating one daily note."""

    content: str
    date: str | None = None
    period: str | None = None


class DailyNoteUpdateRequest(BaseModel):
    """Request payload for editing one daily note."""

    content: str
    period: str | None = None


class DailyNoteRangeWeeklyRequest(BaseModel):
    """Request payload for generating a range weekly/stage report from notes."""

    from_date: str
    to_date: str


class DailyNoteRangeWeeklyTaskResponse(BaseModel):
    """Queued stage report task metadata for API callers."""

    task_id: str
    from_date: str
    to_date: str
    status: str
    result: dict | None = None
    error_message: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class DailyNoteResponse(BaseModel):
    """Daily note payload returned to the frontend."""

    id: str
    date: str
    weekday: str
    period: str
    content: str
    detail_level: int
    created_at: str
    updated_at: str


class DailyNoteDayResponse(BaseModel):
    """Calendar summary for one date."""

    date: str
    weekday: str
    note_count: int
    detail_level: int
    preview: str
    notes: list[DailyNoteResponse]
