"""Rich renderers for CLI daily-note calendar views."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
PERIOD_LABELS = {
    "morning": "上午",
    "afternoon": "下午",
}
DETAIL_STYLES = {
    1: "green3",
    2: "bright_green",
    3: "yellow3",
    4: "red3 bold",
}
EMPTY_STYLE = "grey50"
TODAY_STYLE = "bold cyan"


@dataclass(frozen=True)
class CalendarDay:
    """One day summary prepared for terminal rendering."""

    date: str
    weekday: str
    note_count: int
    detail_level: int
    preview: str
    notes: list[dict]


def current_month() -> str:
    """Return the current month in YYYY-MM format."""

    return date.today().strftime("%Y-%m")


def render_note_calendar(month: str, payload: dict, username: str | None = None) -> Group:
    """Build a Rich renderable matching the Web UI's month-first note view."""

    year, month_number = _parse_month(month)
    days = {
        item["date"]: CalendarDay(
            date=item["date"],
            weekday=item.get("weekday", ""),
            note_count=int(item.get("note_count", 0)),
            detail_level=int(item.get("detail_level", 0)),
            preview=item.get("preview", ""),
            notes=list(item.get("notes", [])),
        )
        for item in payload.get("days", [])
    }
    header = _build_header(year, month_number, days, username=username)
    calendar_table = _build_calendar_table(year, month_number, days)
    summary_table = _build_summary_table(days)
    legend = _build_legend()
    next_commands = _build_next_commands(month, username=username)
    return Group(header, calendar_table, legend, summary_table, next_commands)


def _parse_month(month: str) -> tuple[int, int]:
    try:
        year_part, month_part = month.split("-", 1)
        year = int(year_part)
        month_number = int(month_part)
    except ValueError as exc:
        raise ValueError("month 必须使用 YYYY-MM 格式。") from exc
    if month_number < 1 or month_number > 12:
        raise ValueError("month 必须使用 YYYY-MM 格式。")
    return year, month_number


def _build_header(year: int, month_number: int, days: dict[str, CalendarDay], username: str | None = None) -> Panel:
    total_notes = sum(day.note_count for day in days.values())
    active_days = len(days)
    deepest_level = max((day.detail_level for day in days.values()), default=0)
    title = Text()
    title.append("DailyChewer CLI", style="bold cyan")
    title.append("  notes calendar", style="grey70")
    subtitle = Text()
    subtitle.append(f"{year}-{month_number:02d}", style="bold")
    if username:
        subtitle.append(f"  user:{username}", style="green3")
    subtitle.append(f"  active days:{active_days}", style="cyan")
    subtitle.append(f"  notes:{total_notes}", style="yellow3")
    subtitle.append(f"  deepest:{deepest_level}", style=_detail_style(deepest_level or 1))
    return Panel(
        Group(Align.left(title), Align.left(subtitle)),
        border_style="cyan",
        padding=(1, 2),
    )


def _build_calendar_table(year: int, month_number: int, days: dict[str, CalendarDay]) -> Table:
    table = Table(
        title=f"Daily Notes Calendar {year}-{month_number:02d}",
        show_lines=True,
        expand=True,
        padding=(0, 1),
    )
    for label in WEEKDAY_LABELS:
        table.add_column(label, justify="center", ratio=1, overflow="fold")

    today = date.today().isoformat()
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(year, month_number):
        row = []
        for day in week:
            if day.month != month_number:
                row.append(Text(str(day.day), style="grey35"))
                continue
            key = day.isoformat()
            summary = days.get(key)
            if summary is None:
                row.append(Text(str(day.day), style=EMPTY_STYLE))
                continue
            style = _detail_style(summary.detail_level)
            cell = Text()
            day_label = f"{day.day}"
            if key == today:
                cell.append(f"{day_label} ", style=TODAY_STYLE)
            else:
                cell.append(f"{day_label} ", style=style)
            cell.append("●" * min(summary.detail_level, 4), style=style)
            cell.append(f"\n{summary.note_count} 条日志", style=style)
            row.append(cell)
        table.add_row(*row)
    return table


def _build_summary_table(days: dict[str, CalendarDay]) -> Table | Panel:
    if not days:
        return Panel("本月暂无日志。", title="Daily Note Logs", border_style="grey50")

    table = Table(title="Daily Note Logs", expand=True, show_lines=False)
    table.add_column("Date", style="bold", no_wrap=True)
    table.add_column("Level", no_wrap=True)
    table.add_column("Logs", no_wrap=True)
    table.add_column("Preview", overflow="fold")

    for summary in sorted(days.values(), key=lambda item: item.date):
        style = _detail_style(summary.detail_level)
        period_labels = _period_summary(summary.notes)
        table.add_row(
            Text(summary.date, style=style),
            Text(str(summary.detail_level), style=style),
            Text(f"{summary.note_count} ({period_labels})", style=style),
            Text(_compact_preview(summary.preview), style=style),
        )
    return table


def _build_legend() -> Panel:
    legend = Text()
    legend.append("detail level: ")
    for level in range(1, 5):
        if level > 1:
            legend.append("  ")
        legend.append(f"{level} ", style=_detail_style(level))
        legend.append("●" * level, style=_detail_style(level))
    legend.append("   ")
    legend.append("today", style=TODAY_STYLE)
    return Panel(legend, title="Legend", border_style="grey50")


def _build_next_commands(month: str, username: str | None = None) -> Panel:
    user_suffix = f" --user {username}" if username else " --user <username>"
    commands = [
        f"dailychewer notes calendar --month {month}{user_suffix}",
        f"dailychewer notes calendar --month <YYYY-MM>{user_suffix}",
        f"dailychewer list{user_suffix}",
        f"dailychewer search <keyword>{user_suffix}",
        "dailychewer doctor",
    ]
    body = Text()
    for index, command in enumerate(commands, start=1):
        body.append(f"{index}. ", style="grey70")
        body.append(command, style="bold cyan")
        if index < len(commands):
            body.append("\n")
    return Panel(body, title="Next commands", border_style="green3", padding=(1, 2))


def _period_summary(notes: list[dict]) -> str:
    periods = []
    for note in notes:
        label = PERIOD_LABELS.get(str(note.get("period", "")), str(note.get("period", "")) or "-")
        if label not in periods:
            periods.append(label)
    return "/".join(periods) if periods else "-"


def _compact_preview(value: str, limit: int = 96) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1]}..."


def _detail_style(level: int) -> str:
    return DETAIL_STYLES.get(max(1, min(level, 4)), DETAIL_STYLES[1])
