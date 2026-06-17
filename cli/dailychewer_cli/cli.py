"""Typer CLI entrypoint for DailyChewer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dailychewer_backend import __version__
from dailychewer_backend.services.backup_service import BackupService
from dailychewer_backend.config import load_settings
from dailychewer_backend.models import DailyReport
from dailychewer_backend.services.database_service import DatabaseService
from dailychewer_backend.services import normalize_tags, resolve_user_context
from dailychewer_backend.services.doctor_service import DoctorService
from dailychewer_backend.services.ingest_service import IngestService
from dailychewer_backend.services.migration_service import LegacyIndexMigrationService
from dailychewer_backend.services.monthly_service import MonthlyService
from dailychewer_backend.services.note_service import DailyNoteService
from dailychewer_backend.services.search_service import SearchService
from dailychewer_backend.services.template_service import TemplateService
from dailychewer_backend.services.user_service import UserService
from dailychewer_backend.services.weekly_service import WeeklyService
from dailychewer_backend.utils.logger import get_logger
from dailychewer_cli.note_calendar import current_month, render_note_calendar
from dailychewer_cli.tui import run_tui


app = typer.Typer(help="DailyChewer: 日报优化 + 周报生成器", add_completion=False)
user_app = typer.Typer(help="数据库用户管理命令。")
db_app = typer.Typer(help="数据库初始化与检查命令。")
backup_app = typer.Typer(help="备份与恢复命令。")
notes_app = typer.Typer(help="日报便条日历与只读查看命令。")
console = Console(width=160)


def _print_error(message: str) -> None:
    """Render a CLI error message in red."""

    console.print(f"[red]{message}[/red]")


def _confirm_no_default(question: str, auto_yes: bool = False) -> bool:
    """Ask a y/[n] confirmation where Enter defaults to no."""

    if auto_yes:
        return True
    answer = typer.prompt(question, default="n").strip().lower()
    return answer in {"y", "yes"}


def _confirm_yes_default(question: str, auto_yes: bool = False) -> bool:
    """Ask a [Y/n] confirmation where Enter defaults to yes."""

    if auto_yes:
        return True
    answer = typer.prompt(question, default="y").strip().lower()
    return answer in {"", "y", "yes"}


def _prompt_export_format(default_format: str) -> str:
    """Ask the user which export format to use."""

    while True:
        answer = typer.prompt(
            "请选择导出格式：csv / xlsx / markdown / docx",
            default=default_format,
        ).strip().lower()
        if answer in {"csv", "xlsx", "markdown", "docx"}:
            return answer
        _print_error("导出格式不支持，请输入 csv、xlsx、markdown 或 docx。")


def _collect_user_answers(questions: list[str]) -> dict[str, str]:
    """Ask up to three clarification questions and collect non-empty answers."""

    answers: dict[str, str] = {}
    for index, question in enumerate(questions[:3], start=1):
        answer = typer.prompt(f"补充问题 {index}: {question}", default="").strip()
        if answer:
            answers[question] = answer
    return answers


def _render_preview_list(items: list[str]) -> str:
    """Render one field in preview-friendly bullet format."""

    return "\n".join(f"- {item}" for item in (items or ["原始日报未提供更多细节"]))


def _preview_daily_report(report: DailyReport) -> None:
    """Show the optimized daily report preview before persisting it."""

    quality_summary = f"{report.quality_score.total}/25" if report.quality_score else "未生成评分"
    body = f"""[bold]日期[/bold]: {report.date}
[bold]星期[/bold]: {report.weekday}
[bold]周次[/bold]: {report.week}
[bold]质量评分[/bold]: {quality_summary}

[bold]上午工作内容[/bold]
{_render_preview_list(report.morning.work_content)}

[bold]上午个人成长[/bold]
{_render_preview_list(report.morning.personal_growth)}

[bold]上午问题总结[/bold]
{_render_preview_list(report.morning.problems)}

[bold]上午解决方案[/bold]
{_render_preview_list(report.morning.solutions)}

[bold]下午工作内容[/bold]
{_render_preview_list(report.afternoon.work_content)}

[bold]下午个人成长[/bold]
{_render_preview_list(report.afternoon.personal_growth)}

[bold]下午问题总结[/bold]
{_render_preview_list(report.afternoon.problems)}

[bold]下午解决方案[/bold]
{_render_preview_list(report.afternoon.solutions)}

[bold]需要补充的信息[/bold]
{_render_preview_list(report.questions or ["无"])}
"""
    console.print(Panel(body, title="优化日报预览", expand=False))


def _preview_markdown_document(title: str, content: str) -> None:
    """Render a markdown-like preview block in the terminal."""

    console.print(Panel(content, title=title, expand=False))


def _status_markup(status: str) -> str:
    """Return colored markup for doctor statuses."""

    mapping = {"OK": "[green]OK[/green]", "WARN": "[yellow]WARN[/yellow]", "FAIL": "[red]FAIL[/red]"}
    return mapping.get(status, status)


def _render_user_table(items: list[dict[str, str]]) -> None:
    """Render user rows in a consistent rich table."""

    table = Table(title="DailyChewer Users", expand=True)
    for column in ["id", "username", "display_name", "is_active", "is_admin", "created_at"]:
        table.add_column(column, overflow="fold" if column in {"id", "created_at"} else "ellipsis")
    for item in items:
        table.add_row(
            item["id"],
            item["username"],
            item["display_name"] or "-",
            item["is_active"],
            item["is_admin"],
            item["created_at"],
        )
    console.print(table)


@app.command("version")
def version() -> None:
    """Print the current DailyChewer version."""

    console.print(f"DailyChewer {__version__}")


@app.command("tui")
def tui() -> None:
    """Start the interactive DailyChewer terminal UI."""

    run_tui()


@app.command("template")
def template(
    date: str | None = typer.Option(None, "--date", help="模板日期 YYYY-MM-DD"),
    template_format: str | None = typer.Option(None, "--format", help="模板格式：markdown/csv/xlsx/docx"),
    output: Path | None = typer.Option(None, "--output", help="模板输出路径"),
    user: str | None = typer.Option(None, "--user", help="使用指定数据库用户作用域生成模板。"),
) -> None:
    """Generate a daily report template file."""

    logger = None
    try:
        settings = load_settings()
        logger = get_logger(settings)
        user_context = resolve_user_context(user, settings=settings)
        generated = TemplateService(user_context=user_context).generate_template(
            date=date,
            fmt=template_format or settings.report.default_format,
            output=output,
        )
        logger.info("template_generated output=%s", generated.file)
        console.print(f"[green]日报模板已生成：{generated.file}[/green]")
    except Exception as exc:
        if logger is not None:
            logger.error("template_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("ingest")
def ingest(
    file_path: Path = typer.Argument(..., help="日报文件路径"),
    date: str | None = typer.Option(None, "--date", help="手动指定日报日期 YYYY-MM-DD"),
    project: str | None = typer.Option(None, "--project", help="为日报指定项目名称。"),
    tag: list[str] = typer.Option([], "--tag", help="为日报追加标签，可多次传入。"),
    yes: bool = typer.Option(False, "--yes", help="对普通确认项自动回答 yes。"),
    no_weekly: bool = typer.Option(False, "--no-weekly", help="导入完成后不询问是否生成周报。"),
    no_questions: bool = typer.Option(False, "--no-questions", help="忽略追问，直接生成保守版本。"),
    save: bool = typer.Option(False, "--save", help="跳过保存确认，直接保存优化日报。"),
    user: str | None = typer.Option(None, "--user", help="使用指定数据库用户作用域保存日报。"),
) -> None:
    """Import one raw report, optimize it, and optionally generate a weekly report."""

    logger = None
    try:
        settings = load_settings()
        logger = get_logger(settings)
        user_context = resolve_user_context(user, settings=settings)
        service = IngestService(user_context=user_context)
        normalized_tags = normalize_tags(tag)
        effective_save = save or settings.behavior.auto_save
        effective_no_questions = no_questions or (not settings.behavior.ask_questions)

        preview_result = service.ingest_report(
            file_path=file_path,
            date=date,
            project=project,
            tags=normalized_tags,
            save=False,
            no_questions=False,
        )
        answers: dict[str, str] = {}
        if preview_result.questions and not effective_no_questions:
            answers = _collect_user_answers(preview_result.questions)
            preview_result = service.ingest_report(
                file_path=file_path,
                date=date,
                project=project,
                tags=normalized_tags,
                save=False,
                no_questions=False,
                user_answers=answers,
            )
        elif preview_result.questions and effective_no_questions:
            preview_result = service.ingest_report(
                file_path=file_path,
                date=date,
                project=project,
                tags=normalized_tags,
                save=False,
                no_questions=True,
                user_answers={},
            )

        _preview_daily_report(preview_result.daily_report)
        if not _confirm_yes_default("是否保存这份优化日报？ [Y/n]", auto_yes=(yes or effective_save)):
            console.print("[yellow]已取消保存，本次导入未写入 data。[/yellow]")
            return

        if preview_result.existing_report and not _confirm_no_default(
            f"{preview_result.daily_report.date} 已存在日报，是否覆盖？ y/[n]",
            auto_yes=yes,
        ):
            console.print("[yellow]已取消导入。[/yellow]")
            return

        saved_result = service.ingest_report(
            file_path=file_path,
            date=date,
            project=project,
            tags=normalized_tags,
            save=True,
            no_questions=effective_no_questions,
            user_answers=answers if answers else ({ } if effective_no_questions else None),
            overwrite=True,
        )
        console.print(f"[green]日报优化完成：{saved_result.optimized_file}[/green]")

        if no_weekly:
            return
        auto_generate_weekly = yes or settings.behavior.generate_weekly_after_ingest
        if _confirm_no_default("是否要基于当前已保存日报生成周报？ y/[n]", auto_yes=auto_generate_weekly):
            export_format = _prompt_export_format(settings.report.default_format)
            weekly_service = WeeklyService(user_context=user_context)
            weekly_result = weekly_service.build_weekly_report(
                week=saved_result.daily_report.week,
                fmt=export_format,
                style=settings.report.default_weekly_style,
                project=project,
                tags=normalized_tags,
                save=True,
            )
            console.print(f"[green]周报已生成：{weekly_result.file}[/green]")
    except Exception as exc:
        if logger is not None:
            logger.error("ingest_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("weekly")
def weekly(
    week: str | None = typer.Option(None, "--week", help="指定 ISO week，例如 2026-W23"),
    from_date: str | None = typer.Option(None, "--from", help="指定起始日期 YYYY-MM-DD"),
    to_date: str | None = typer.Option(None, "--to", help="指定结束日期 YYYY-MM-DD"),
    export_format: str | None = typer.Option(None, "--format", help="导出格式：csv/xlsx/markdown/docx"),
    style: str | None = typer.Option(None, "--style", help="周报风格：concise/formal/detailed/interview"),
    project: str | None = typer.Option(None, "--project", help="只汇总指定项目的日报。"),
    tag: list[str] = typer.Option([], "--tag", help="只汇总带指定标签的日报，可多次传入。"),
    preview: bool = typer.Option(False, "--preview", help="先预览周报，再确认是否保存。"),
    save: bool = typer.Option(False, "--save", help="在预览模式下直接保存，不再询问。"),
    yes: bool = typer.Option(False, "--yes", help="对普通确认项自动回答 yes。"),
    delete_after_export: bool = typer.Option(
        False,
        "--delete-after-export",
        help="导出后删除对应日报和周报文件。该危险操作必须显式传入。",
    ),
    no_delete_prompt: bool = typer.Option(
        False,
        "--no-delete-prompt",
        help="导出后不询问是否删除内容，适合自动化流程。",
    ),
    user: str | None = typer.Option(None, "--user", help="使用指定数据库用户作用域生成周报。"),
) -> None:
    """Generate a weekly report from optimized daily reports."""

    logger = None
    try:
        settings = load_settings()
        logger = get_logger(settings)
        user_context = resolve_user_context(user, settings=settings)
        service = WeeklyService(user_context=user_context)
        normalized_tags = normalize_tags(tag)
        if preview and not save:
            preview_result = service.build_weekly_report(
                week=week,
                from_date=from_date,
                to_date=to_date,
                fmt=export_format or settings.report.default_format,
                style=style or settings.report.default_weekly_style,
                project=project,
                tags=normalized_tags,
                preview=True,
                save=False,
            )
            _preview_markdown_document("周报预览", preview_result.preview)
            if not _confirm_yes_default("是否保存这份周报？ [Y/n]", auto_yes=yes):
                console.print("[yellow]已取消保存，本次周报未写入 data。[/yellow]")
                return

        result = service.build_weekly_report(
            week=week,
            from_date=from_date,
            to_date=to_date,
            fmt=export_format or settings.report.default_format,
            style=style or settings.report.default_weekly_style,
            project=project,
            tags=normalized_tags,
            preview=preview,
            save=True,
        )
        console.print(f"[green]周报已生成：{result.file}[/green]")

        if delete_after_export:
            if from_date and to_date:
                deleted = service.cleanup_date_range_export(
                    week=result.week or "",
                    from_date=from_date,
                    to_date=to_date,
                    report_format=result.format,
                )
            else:
                deleted = service.cleanup_week(result.week or week or "")
            console.print(f"[green]已删除 {deleted} 个文件，并更新 index.json。[/green]")
            return

        if no_delete_prompt:
            return
        if _confirm_no_default(
            "是否删除本周日报和周报文件？ y/[n]" if not (from_date and to_date) else "是否删除本次范围内日报和生成的周报文件？ y/[n]"
        ):
            if from_date and to_date:
                deleted = service.cleanup_date_range_export(
                    week=result.week or "",
                    from_date=from_date,
                    to_date=to_date,
                    report_format=result.format,
                )
            else:
                deleted = service.cleanup_week(result.week or week or "")
            console.print(f"[green]已删除 {deleted} 个文件，并更新 index.json。[/green]")
    except Exception as exc:
        if logger is not None:
            logger.error("weekly_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("monthly")
def monthly(
    month: str = typer.Option(..., "--month", help="指定月份 YYYY-MM"),
    export_format: str | None = typer.Option(None, "--format", help="导出格式：csv/xlsx/markdown/docx"),
    style: str | None = typer.Option(None, "--style", help="月报风格：concise/formal/detailed/interview"),
    project: str | None = typer.Option(None, "--project", help="只汇总指定项目的日报。"),
    tag: list[str] = typer.Option([], "--tag", help="只汇总带指定标签的日报，可多次传入。"),
    preview: bool = typer.Option(False, "--preview", help="先预览月报，再确认是否保存。"),
    save: bool = typer.Option(False, "--save", help="在预览模式下直接保存，不再询问。"),
    yes: bool = typer.Option(False, "--yes", help="对普通确认项自动回答 yes。"),
    user: str | None = typer.Option(None, "--user", help="使用指定数据库用户作用域生成月报。"),
) -> None:
    """Generate a monthly report from optimized daily reports."""

    logger = None
    try:
        settings = load_settings()
        logger = get_logger(settings)
        user_context = resolve_user_context(user, settings=settings)
        service = MonthlyService(user_context=user_context)
        normalized_tags = normalize_tags(tag)
        if preview and not save:
            preview_result = service.build_monthly_report(
                month=month,
                fmt=export_format or settings.report.default_format,
                style=style or settings.report.default_monthly_style,
                project=project,
                tags=normalized_tags,
                preview=True,
                save=False,
            )
            _preview_markdown_document("月报预览", preview_result.preview)
            if not _confirm_yes_default("是否保存这份月报？ [Y/n]", auto_yes=yes):
                console.print("[yellow]已取消保存，本次月报未写入 data。[/yellow]")
                return

        result = service.build_monthly_report(
            month=month,
            fmt=export_format or settings.report.default_format,
            style=style or settings.report.default_monthly_style,
            project=project,
            tags=normalized_tags,
            preview=preview,
            save=True,
        )
        console.print(f"[green]月报已生成：{result.file}[/green]")
    except Exception as exc:
        if logger is not None:
            logger.error("monthly_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("list")
def list_reports(
    week: str | None = typer.Option(None, "--week", help="仅展示指定 ISO week"),
    project: str | None = typer.Option(None, "--project", help="仅展示指定项目"),
    tag: str | None = typer.Option(None, "--tag", help="仅展示包含指定标签的日报"),
    user: str | None = typer.Option(None, "--user", help="使用指定数据库用户作用域查看日报。"),
) -> None:
    """List indexed daily reports in a rich table."""

    logger = None
    try:
        logger = get_logger(load_settings())
        settings = load_settings()
        user_context = resolve_user_context(user, settings=settings)
        reports = SearchService(user_context=user_context).list_reports(week=week, project=project, tag=tag)
        if not reports:
            console.print("[yellow]No daily reports found.[/yellow]")
            return

        table = Table(title="DailyChewer 日报列表", expand=True)
        for column in ["date", "weekday", "week", "project", "tags", "quality_score", "source_format", "status", "optimized_file"]:
            table.add_column(column, overflow="fold" if column in {"tags", "optimized_file"} else "ellipsis")
        for item in reports:
            table.add_row(
                item.date,
                item.weekday,
                item.week,
                item.project or "-",
                ", ".join(item.tags) if item.tags else "-",
                str(item.quality_score) if item.quality_score is not None else "-",
                item.source_format,
                item.status,
                item.optimized_file,
            )
        console.print(table)
    except Exception as exc:
        if logger is not None:
            logger.error("list_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("search")
def search(
    query: str = typer.Argument(..., help="关键词"),
    week: str | None = typer.Option(None, "--week", help="按 ISO week 过滤"),
    from_date: str | None = typer.Option(None, "--from", help="指定起始日期 YYYY-MM-DD"),
    to_date: str | None = typer.Option(None, "--to", help="指定结束日期 YYYY-MM-DD"),
    project: str | None = typer.Option(None, "--project", help="只搜索指定项目"),
    tag: list[str] = typer.Option([], "--tag", help="只搜索包含指定标签的日报"),
    limit: int = typer.Option(10, "--limit", help="最多返回多少条匹配结果"),
    user: str | None = typer.Option(None, "--user", help="使用指定数据库用户作用域搜索日报。"),
) -> None:
    """Search historical optimized reports by keyword."""

    logger = None
    try:
        settings = load_settings()
        logger = get_logger(settings)
        user_context = resolve_user_context(user, settings=settings)
        results = SearchService(user_context=user_context).search_reports(
            query=query,
            week=week,
            from_date=from_date,
            to_date=to_date,
            project=project,
            tags=normalize_tags(tag),
            limit=limit,
        )
        if not results:
            console.print("[yellow]No matching reports found.[/yellow]")
            return

        table = Table(title=f"Search Results: {query}", expand=True)
        table.add_column("date")
        table.add_column("week")
        table.add_column("matched section", overflow="fold")
        table.add_column("matched text snippet", overflow="fold")
        table.add_column("optimized_file", overflow="fold")
        for item in results:
            table.add_row(item.date, item.week, item.matched_section, item.snippet, item.optimized_file)
        console.print(table)
    except Exception as exc:
        if logger is not None:
            logger.error("search_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("clean")
def clean(
    week: str = typer.Option(..., "--week", help="指定 ISO week，例如 2026-W23"),
) -> None:
    """Delete one week's raw, optimized, and weekly files."""

    logger = None
    try:
        logger = get_logger(load_settings())
        if not _confirm_no_default(f"确认删除 {week} 的日报和周报文件？ y/[n]"):
            console.print("[yellow]已取消删除。[/yellow]")
            return
        deleted = WeeklyService().cleanup_week(week)
        console.print(f"[green]已删除 {deleted} 个文件，并更新 index.json。[/green]")
    except Exception as exc:
        if logger is not None:
            logger.error("clean_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("doctor")
def doctor(
    check_api: bool = typer.Option(
        False,
        "--check-api",
        help="发送一个最小 JSON 请求检查当前 LLM API 是否可连通。",
    ),
) -> None:
    """Check environment, storage, and optional API connectivity."""

    logger = None
    try:
        logger = get_logger(load_settings())
        result = DoctorService().get_status(check_api=check_api)
        table = Table(title="DailyChewer Doctor")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Value")
        table.add_column("Details")
        for item in result.checks:
            table.add_row(item.name, _status_markup(item.status), item.value, item.details)
        console.print(table)
    except Exception as exc:
        if logger is not None:
            logger.error("doctor_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@notes_app.command("calendar")
def notes_calendar(
    month: str = typer.Option(current_month(), "--month", help="目标月份 YYYY-MM。默认当前月份。"),
    user: str = typer.Option(..., "--user", help="数据库用户名；CLI 便条日历需要明确用户作用域。"),
) -> None:
    """Show a GUI-aligned month calendar for daily notes without changing data."""

    logger = None
    try:
        settings = load_settings()
        logger = get_logger(settings)
        user_context = resolve_user_context(user, settings=settings)
        payload = DailyNoteService(user_context=user_context).list_month(month)
        console.print(render_note_calendar(month, payload, username=user_context.username or user))
    except Exception as exc:
        if logger is not None:
            logger.error("notes_calendar_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@user_app.command("create")
def user_create(
    username: str = typer.Argument(..., help="用户名"),
    password: str = typer.Option(..., "--password", prompt=False, hide_input=True, help="登录密码，至少 6 位。"),
    display_name: str | None = typer.Option(None, "--display-name", help="展示名称"),
    admin: bool = typer.Option(False, "--admin", help="是否创建为管理员"),
) -> None:
    """Create one database user."""

    logger = None
    try:
        logger = get_logger(load_settings())
        user = UserService().create_user(
            username=username,
            password=password,
            display_name=display_name,
            is_admin=admin,
        )
        _render_user_table(
            [
                {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name or "",
                    "is_active": str(user.is_active).lower(),
                    "is_admin": str(user.is_admin).lower(),
                    "created_at": user.created_at,
                }
            ]
        )
    except Exception as exc:
        if logger is not None:
            logger.error("user_create_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@user_app.command("list")
def user_list() -> None:
    """List database users without exposing password hashes."""

    logger = None
    try:
        logger = get_logger(load_settings())
        users = UserService().list_users()
        _render_user_table(
            [
                {
                    "id": item.id,
                    "username": item.username,
                    "display_name": item.display_name or "",
                    "is_active": str(item.is_active).lower(),
                    "is_admin": str(item.is_admin).lower(),
                    "created_at": item.created_at,
                }
                for item in users
            ]
        )
    except Exception as exc:
        if logger is not None:
            logger.error("user_list_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@user_app.command("disable")
def user_disable(username: str = typer.Argument(..., help="用户名")) -> None:
    """Disable one user without deleting their data."""

    logger = None
    try:
        logger = get_logger(load_settings())
        user = UserService().set_user_active(username, is_active=False)
        console.print(f"[green]User disabled:[/green] {user.username}")
    except Exception as exc:
        if logger is not None:
            logger.error("user_disable_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@user_app.command("enable")
def user_enable(username: str = typer.Argument(..., help="用户名")) -> None:
    """Enable one previously disabled user."""

    logger = None
    try:
        logger = get_logger(load_settings())
        user = UserService().set_user_active(username, is_active=True)
        console.print(f"[green]User enabled:[/green] {user.username}")
    except Exception as exc:
        if logger is not None:
            logger.error("user_enable_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@user_app.command("reset-password")
def user_reset_password(
    username: str = typer.Argument(..., help="用户名"),
    password: str = typer.Option(..., "--password", prompt=False, hide_input=True, help="新密码，至少 6 位。"),
) -> None:
    """Reset one user's password."""

    logger = None
    try:
        logger = get_logger(load_settings())
        user = UserService().reset_password(username, password=password)
        console.print(f"[green]Password reset for user:[/green] {user.username}")
    except Exception as exc:
        if logger is not None:
            logger.error("user_reset_password_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@db_app.command("check")
def db_check() -> None:
    """Check database connectivity, schema, and admin readiness."""

    logger = None
    try:
        logger = get_logger(load_settings())
        result = DatabaseService().check()
        table = Table(title="DailyChewer DB Check")
        table.add_column("Check")
        table.add_column("Value")
        table.add_column("Status")
        table.add_column("Details")
        rows = [
            ("DATABASE_URL configured", str(result.database_url_configured).lower(), "OK" if result.database_url_configured else "WARN", result.database_url_masked),
            ("Database reachable", str(result.database_reachable).lower(), "OK" if result.database_reachable else ("WARN" if not result.database_url_configured else "FAIL"), ""),
            ("Alembic revision", result.alembic_revision or "unknown", "OK" if result.alembic_revision else "WARN", ""),
            ("users table exists", str(result.users_table_exists).lower(), "OK" if result.users_table_exists else ("WARN" if not result.database_reachable else "FAIL"), ""),
            ("active admin exists", str(result.active_admin_exists).lower(), "OK" if result.active_admin_exists else ("WARN" if not result.database_reachable else "FAIL"), ""),
        ]
        for name, value, status, details in rows:
            table.add_row(name, value, _status_markup(status), details)
        console.print(table)
        for detail in result.details:
            console.print(f"[yellow]{detail}[/yellow]")
    except Exception as exc:
        if logger is not None:
            logger.error("db_check_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@db_app.command("init")
def db_init() -> None:
    """Initialize database schema and optional default admin user."""

    logger = None
    try:
        logger = get_logger(load_settings())
        result = DatabaseService().init()
        table = Table(title="DailyChewer DB Init")
        table.add_column("Step")
        table.add_column("Status")
        table.add_column("Details")
        table.add_row("Database reachable", _status_markup("OK" if result.database_reachable else "FAIL"), "")
        table.add_row("Migration applied", _status_markup("OK" if result.migration_applied else "FAIL"), result.migration_mode)
        table.add_row(
            "Default admin",
            _status_markup("OK" if result.default_user_created else "WARN"),
            result.default_username or "not created",
        )
        console.print(table)
        for detail in result.details:
            console.print(f"[yellow]{detail}[/yellow]")
    except Exception as exc:
        if logger is not None:
            logger.error("db_init_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@app.command("migrate-index")
def migrate_index(
    user: str = typer.Option(..., "--user", help="目标数据库用户名"),
    apply: bool = typer.Option(False, "--apply", help="真正执行迁移；默认 dry-run。"),
    copy_files: bool = typer.Option(False, "--copy-files", help="复制 legacy 文件到 data/users/{user_id}/legacy/"),
) -> None:
    """Migrate legacy data/index.json into one database user scope."""

    logger = None
    try:
        logger = get_logger(load_settings())
        summary = LegacyIndexMigrationService().migrate(user, apply=apply, copy_files=copy_files)
        table = Table(title="Legacy Index Migration")
        table.add_column("Metric")
        table.add_column("Value")
        for key, value in [
            ("dry_run", str(summary.dry_run).lower()),
            ("reports found", str(summary.reports_found)),
            ("reports migrated", str(summary.reports_migrated)),
            ("weekly found", str(summary.weekly_found)),
            ("weekly migrated", str(summary.weekly_migrated)),
            ("monthly found", str(summary.monthly_found)),
            ("monthly migrated", str(summary.monthly_migrated)),
            ("skipped_existing", str(summary.skipped_existing)),
            ("copied_files", str(summary.copied_files)),
            ("skipped", str(summary.skipped)),
            ("errors", str(len(summary.errors))),
        ]:
            table.add_row(key, value)
        console.print(table)
        if summary.migration_ids:
            console.print("[cyan]migration_ids[/cyan]")
            for migration_id in summary.migration_ids[:10]:
                console.print(f"  - {migration_id}")
            if len(summary.migration_ids) > 10:
                console.print(f"  ... and {len(summary.migration_ids) - 10} more")
        for error in summary.errors:
            console.print(f"[yellow]{error}[/yellow]")
    except Exception as exc:
        if logger is not None:
            logger.error("migrate_index_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@backup_app.command("create")
def backup_create(
    output: Path = typer.Option(..., "--output", help="备份输出目录，例如 backups/"),
    include_logs: bool = typer.Option(False, "--include-logs", help="是否包含 data/logs。"),
    skip_db: bool = typer.Option(False, "--skip-db", help="跳过数据库备份。"),
    skip_files: bool = typer.Option(False, "--skip-files", help="跳过本地文件备份。"),
    zip_backup: bool = typer.Option(False, "--zip", help="创建 zip 归档。"),
    remove_dir_after_zip: bool = typer.Option(False, "--remove-dir-after-zip", help="zip 完成后删除原目录。"),
) -> None:
    """Create one backup snapshot."""

    logger = None
    try:
        logger = get_logger(load_settings())
        result = BackupService().create_backup(
            output_dir=output,
            include_logs=include_logs,
            skip_db=skip_db,
            skip_files=skip_files,
            zip_backup=zip_backup,
            remove_dir_after_zip=remove_dir_after_zip,
        )
        console.print(f"[green]Backup created:[/green] {result.backup_path}")
        console.print(f"[green]Manifest:[/green] {result.manifest_path}")
        if result.archive_path:
            console.print(f"[green]Archive:[/green] {result.archive_path}")
        for detail in result.details:
            console.print(f"[yellow]{detail}[/yellow]")
    except Exception as exc:
        if logger is not None:
            logger.error("backup_create_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@backup_app.command("restore")
def backup_restore(
    backup_path: Path = typer.Argument(..., help="备份目录路径"),
    apply: bool = typer.Option(False, "--apply", help="真正执行恢复；默认 dry-run。"),
    restore_db: bool = typer.Option(False, "--restore-db", help="恢复数据库备份。"),
    restore_files: bool = typer.Option(False, "--restore-files", help="恢复文件备份。"),
    confirm_overwrite_db: bool = typer.Option(False, "--confirm-overwrite-db", help="允许覆盖已有数据库内容。"),
    overwrite_files: bool = typer.Option(False, "--overwrite-files", help="允许覆盖内容不同的现有文件。"),
) -> None:
    """Preview or apply one backup restore."""

    logger = None
    try:
        logger = get_logger(load_settings())
        result = BackupService().restore_backup(
            backup_path=backup_path,
            apply=apply,
            restore_db=restore_db,
            restore_files=restore_files,
            confirm_overwrite_db=confirm_overwrite_db,
            overwrite_files=overwrite_files,
        )
        title = "Backup Restore Dry Run" if result.dry_run else "Backup Restore Applied"
        table = Table(title=title)
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("backup_path", result.backup_path)
        table.add_row("manifest_path", result.manifest_path)
        table.add_row("dry_run", str(result.dry_run).lower())
        table.add_row("files_restored", str(result.files_restored).lower())
        table.add_row("database_restored", str(result.database_restored).lower())
        table.add_row("files_same", str(result.files_same))
        table.add_row("file_conflicts", str(result.file_conflicts))
        table.add_row("database_conflicts", str(result.database_conflicts))
        console.print(table)
        for detail in result.details:
            console.print(f"[yellow]{detail}[/yellow]")
    except Exception as exc:
        if logger is not None:
            logger.error("backup_restore_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


@backup_app.command("verify")
def backup_verify(
    backup_path: Path = typer.Argument(..., help="备份目录或 zip 路径"),
) -> None:
    """Verify one backup against its manifest."""

    logger = None
    try:
        logger = get_logger(load_settings())
        result = BackupService().verify_backup(backup_path)
        table = Table(title="Backup Verify")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("backup_path", result.backup_path)
        table.add_row("manifest_path", result.manifest_path)
        table.add_row("total_files", str(result.total_files))
        table.add_row("ok", str(result.ok))
        table.add_row("missing", str(result.missing))
        table.add_row("checksum_failed", str(result.checksum_failed))
        table.add_row("size_failed", str(result.size_failed))
        console.print(table)
        for detail in result.details:
            console.print(f"[yellow]{detail}[/yellow]")
        if result.missing == 0 and result.checksum_failed == 0 and result.size_failed == 0:
            console.print("[green]Backup verification passed.[/green]")
        else:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        if logger is not None:
            logger.error("backup_verify_failed error=%s", exc)
        _print_error(str(exc))
        raise typer.Exit(code=1)


app.add_typer(user_app, name="user")
app.add_typer(db_app, name="db")
app.add_typer(backup_app, name="backup")
app.add_typer(notes_app, name="notes")


if __name__ == "__main__":
    app()
