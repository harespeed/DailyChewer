"""Shared service-layer helpers for CLI and Web API."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.config import (
    SUPPORTED_EXPORT_FORMATS,
    SUPPORTED_REPORT_STYLES,
    Settings,
    load_settings,
)
from dailychewer_backend.db.repositories import UserRepository
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.llm.optimizer import ReportOptimizer
from dailychewer_backend.models import DailyReport, ReportIndexItem, UserContext
from dailychewer_backend.storage.file_store import FileStore
from dailychewer_backend.storage.index_store import IndexStore
from dailychewer_backend.utils.date_utils import (
    current_date_str,
    format_date_range_slug,
    iso_week_for_date,
)
from dailychewer_backend.utils.logger import get_logger


def build_runtime(project_root: Path | None = None) -> tuple[Settings, IndexStore, FileStore, ReportOptimizer, object]:
    """Create the shared runtime objects used by service classes."""

    settings = load_settings(project_root=project_root)
    logger = get_logger(settings)
    index_store = IndexStore(settings.index_file)
    file_store = FileStore(settings)
    optimizer = ReportOptimizer(settings)
    file_store.ensure_directories()
    index_store.ensure_initialized()
    return settings, index_store, file_store, optimizer, logger


def resolve_user_context(
    username: str | None = None,
    settings: Settings | None = None,
) -> UserContext:
    """Resolve CLI or API execution into local or database-backed user context."""

    resolved_settings = settings or load_settings()
    if not username:
        return UserContext(storage_mode="local")
    if not resolved_settings.database_url:
        raise ValueError("DATABASE_URL is required for --user database mode.")
    session_factory = get_session_maker(resolved_settings)
    with session_factory() as session:
        user = UserRepository(session).get_by_username(username)
        if user is None:
            raise ValueError("User not found. Please create the user via Web UI or auth command.")
        return UserContext(user_id=user.id, username=user.username, storage_mode="database")


def normalize_tags(tags: list[str] | None) -> list[str]:
    """Normalize, trim, and deduplicate tag inputs."""

    if not tags:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for tag in tags:
        cleaned = tag.strip()
        if cleaned and cleaned not in seen:
            normalized.append(cleaned)
            seen.add(cleaned)
    return normalized


def resolve_format(export_format: str | None, default_format: str) -> str:
    """Resolve one export format against supported values."""

    resolved = (export_format or default_format).strip().lower()
    if resolved not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError(f"导出格式不支持：{resolved}")
    return resolved


def resolve_style(style: str | None, default_style: str) -> str:
    """Resolve one report style against supported values."""

    resolved = (style or default_style).strip().lower()
    if resolved not in SUPPORTED_REPORT_STYLES:
        raise ValueError(f"Unsupported style: {resolved}")
    return resolved


def build_weekly_output_path(
    file_store: FileStore,
    week: str,
    fmt: str,
    date_range: tuple[str, str] | None = None,
) -> Path:
    """Return the canonical weekly export path for one format."""

    suffix_map = {"markdown": ".md", "docx": ".docx", "xlsx": ".xlsx", "csv": ".csv"}
    output_dir = file_store.settings.weekly_dir / week
    output_dir.mkdir(parents=True, exist_ok=True)
    if date_range:
        slug = format_date_range_slug(date_range[0], date_range[1])
        return output_dir / f"weekly_report_{slug}{suffix_map[fmt]}"
    return output_dir / f"weekly_report_{week}{suffix_map[fmt]}"


def build_monthly_output_path(file_store: FileStore, month: str, fmt: str) -> Path:
    """Return the canonical monthly export path for one format."""

    suffix_map = {"markdown": ".md", "docx": ".docx", "xlsx": ".xlsx", "csv": ".csv"}
    output_dir = file_store.settings.monthly_dir / month
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"monthly_report_{month}{suffix_map[fmt]}"


def read_daily_reports(
    index_store: IndexStore,
    file_store: FileStore,
    week: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    month: str | None = None,
    project: str | None = None,
    tag: str | None = None,
) -> tuple[list[ReportIndexItem], list[DailyReport]]:
    """Load optimized daily reports with week, range, or month filters."""

    if month:
        report_items = index_store.list_reports_by_month(month=month, project=project, tag=tag)
        if not report_items:
            raise ValueError("No optimized daily reports found for the selected month.")
    elif from_date and to_date:
        report_items = index_store.list_reports_by_date_range(
            from_date=from_date,
            to_date=to_date,
            project=project,
            tag=tag,
        )
        if not report_items:
            raise ValueError("No optimized daily reports found for the selected week or date range.")
    else:
        target_week = week or iso_week_for_date(current_date_str())
        report_items = index_store.list_reports(week=target_week, project=project, tag=tag)
        if not report_items:
            raise ValueError("No optimized daily reports found for the selected week or date range.")

    daily_reports: list[DailyReport] = []
    for item in report_items:
        optimized_path = Path(item.optimized_file)
        if not optimized_path.exists():
            raise ValueError(f"找不到优化日报文件：{optimized_path}")
        daily_reports.append(file_store.load_optimized_report(optimized_path))
    return report_items, daily_reports


def search_report_matches(report: DailyReport, query: str) -> list[tuple[str, str]]:
    """Return simple keyword matches across structured report sections."""

    lowered_query = query.lower()
    matches: list[tuple[str, str]] = []
    sections = {
        "morning.work_content": report.morning.work_content,
        "morning.personal_growth": report.morning.personal_growth,
        "morning.problems": report.morning.problems,
        "morning.solutions": report.morning.solutions,
        "afternoon.work_content": report.afternoon.work_content,
        "afternoon.personal_growth": report.afternoon.personal_growth,
        "afternoon.problems": report.afternoon.problems,
        "afternoon.solutions": report.afternoon.solutions,
    }
    for section, items in sections.items():
        for item in items:
            if lowered_query in item.lower():
                matches.append((section, item))
    return matches
