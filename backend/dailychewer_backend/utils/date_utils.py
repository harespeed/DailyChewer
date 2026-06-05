"""Date utilities for report ingestion and weekly grouping."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
import re

from dailychewer_backend.config import WEEKDAY_ORDER


DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b"),
    re.compile(r"\b(\d{4})\.(\d{1,2})\.(\d{1,2})\b"),
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
]


def current_date_str() -> str:
    """Return today's local date in ISO format."""

    return date.today().isoformat()


def normalize_date(value: str) -> str:
    """Validate and normalize a date string to `YYYY-MM-DD`."""

    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def parse_date(value: str) -> date:
    """Parse an ISO date string into a `date` object."""

    return datetime.strptime(value, "%Y-%m-%d").date()


def extract_date_from_text(text: str) -> str | None:
    """Find the first recognizable date inside free-form text."""

    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            return date(year, month, day).isoformat()
    return None


def resolve_report_date(raw_text: str, explicit_date: str | None = None) -> str:
    """Resolve the daily report date from CLI input, content, or today."""

    if explicit_date:
        return normalize_date(explicit_date)
    extracted = extract_date_from_text(raw_text)
    if extracted:
        return extracted
    return current_date_str()


def iso_week_for_date(date_str: str) -> str:
    """Convert `YYYY-MM-DD` into an ISO week identifier like `2026-W23`."""

    report_date = parse_date(date_str)
    iso_year, iso_week, _ = report_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def weekday_name(date_str: str) -> str:
    """Return the English weekday name for a given ISO date."""

    report_date = parse_date(date_str)
    return report_date.strftime("%A")


def week_bounds(week: str) -> tuple[str, str]:
    """Return Monday and Friday dates for an ISO week identifier."""

    year_str, week_str = week.split("-W", maxsplit=1)
    monday = date.fromisocalendar(int(year_str), int(week_str), 1)
    friday = monday + timedelta(days=4)
    return monday.isoformat(), friday.isoformat()


def date_for_weekday(week: str, weekday: str) -> str:
    """Return the date string for a weekday inside one ISO week."""

    if weekday not in WEEKDAY_ORDER:
        raise ValueError(f"Unsupported weekday: {weekday}")
    year_str, week_str = week.split("-W", maxsplit=1)
    monday = date.fromisocalendar(int(year_str), int(week_str), 1)
    target = monday + timedelta(days=WEEKDAY_ORDER.index(weekday))
    return target.isoformat()


def now_timestamp() -> str:
    """Return the current timestamp in ISO 8601 format without timezone."""

    return datetime.now().replace(microsecond=0).isoformat()


def iter_date_strings(from_date: str, to_date: str) -> list[str]:
    """Return all dates between `from_date` and `to_date`, inclusive."""

    start = parse_date(normalize_date(from_date))
    end = parse_date(normalize_date(to_date))
    if start > end:
        raise ValueError("--from 不能晚于 --to。")
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def week_label_for_range(from_date: str, to_date: str) -> str:
    """Build a stable weekly label for a custom date range."""

    normalized_from = normalize_date(from_date)
    normalized_to = normalize_date(to_date)
    from_week = iso_week_for_date(normalized_from)
    to_week = iso_week_for_date(normalized_to)
    if from_week == to_week:
        return from_week
    return f"{normalized_from}_to_{normalized_to}"


def format_date_range_slug(from_date: str, to_date: str) -> str:
    """Build the file-name slug used for date-range weekly exports."""

    return f"{normalize_date(from_date)}_to_{normalize_date(to_date)}"


def month_bounds(month: str) -> tuple[str, str]:
    """Return the first and last day for a `YYYY-MM` month string."""

    start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    last_day = monthrange(start.year, start.month)[1]
    end = start.replace(day=last_day)
    return start.isoformat(), end.isoformat()
