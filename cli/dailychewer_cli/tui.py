"""Interactive Rich TUI entrypoint for DailyChewer."""

from __future__ import annotations

from dataclasses import dataclass

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from dailychewer_backend.auth.security import verify_password
from dailychewer_backend.config import load_settings
from dailychewer_backend.db.repositories import UserRepository
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.doctor_service import DoctorService
from dailychewer_backend.services.note_service import DailyNoteService
from dailychewer_backend.services.search_service import SearchService
from dailychewer_backend.services.user_service import UserService
from dailychewer_cli.note_calendar import current_month, render_note_calendar


console = Console(width=160)


@dataclass(frozen=True)
class TuiUser:
    """Authenticated terminal user session."""

    id: str
    username: str
    display_name: str | None = None
    is_admin: bool = False

    @property
    def context(self) -> UserContext:
        return UserContext(user_id=self.id, username=self.username, storage_mode="database")


class DailyChewerTui:
    """Small command-loop TUI built on Rich, without extra runtime dependencies."""

    def __init__(self, terminal: Console | None = None):
        self.console = terminal or console
        self.user: TuiUser | None = None

    def run(self) -> None:
        """Run the interactive TUI loop until the user quits."""

        self.console.clear()
        while True:
            if self.user is None:
                if not self._guest_menu():
                    return
                continue
            if not self._user_menu():
                return

    def _guest_menu(self) -> bool:
        self.console.print(_welcome_panel())
        self.console.print(_next_panel(["login", "signup", "doctor", "quit"], title="Next commands"))
        action = _normalize_action(
            Prompt.ask(
                "dailychewer.cli",
                choices=["1", "2", "3", "4", "login", "signup", "doctor", "quit", "q"],
                default="login",
                console=self.console,
            ),
            aliases={"1": "login", "2": "signup", "3": "doctor", "4": "quit", "q": "quit"},
        )
        if action == "login":
            self._login()
        elif action == "signup":
            self._signup()
        elif action == "doctor":
            self._doctor()
        elif action == "quit":
            return False
        return True

    def _user_menu(self) -> bool:
        assert self.user is not None
        self.console.print(_session_panel(self.user))
        self.console.print(
            _next_panel(
                ["calendar", "reports", "search", "doctor", "logout", "quit"],
                title="Next commands",
            )
        )
        action = _normalize_action(
            Prompt.ask(
                "dailychewer.cli",
                choices=[
                    "1",
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "calendar",
                    "reports",
                    "search",
                    "doctor",
                    "logout",
                    "quit",
                    "q",
                ],
                default="calendar",
                console=self.console,
            ),
            aliases={
                "1": "calendar",
                "2": "reports",
                "3": "search",
                "4": "doctor",
                "5": "logout",
                "6": "quit",
                "q": "quit",
            },
        )
        if action == "calendar":
            self._calendar()
        elif action == "reports":
            self._reports()
        elif action == "search":
            self._search()
        elif action == "doctor":
            self._doctor()
        elif action == "logout":
            self.user = None
            self.console.print("[yellow]已退出当前用户。[/yellow]")
        elif action == "quit":
            return False
        return True

    def _login(self) -> None:
        username = Prompt.ask("Username", console=self.console).strip()
        password = Prompt.ask("Password", password=True, console=self.console)
        try:
            self.user = authenticate_user(username, password)
        except Exception as exc:
            self.console.print(f"[red]登录失败：{exc}[/red]")
            return
        self.console.print(f"[green]已登录：{self.user.username}[/green]")

    def _signup(self) -> None:
        username = Prompt.ask("Username", console=self.console).strip()
        display_name = Prompt.ask("Display name", default="", console=self.console).strip() or None
        password = Prompt.ask("Password", password=True, console=self.console)
        confirm = Prompt.ask("Confirm password", password=True, console=self.console)
        if password != confirm:
            self.console.print("[red]两次密码不一致。[/red]")
            return
        try:
            created = UserService().create_user(
                username=username,
                password=password,
                display_name=display_name,
                is_admin=False,
            )
            self.user = TuiUser(
                id=created.id,
                username=created.username,
                display_name=created.display_name,
                is_admin=created.is_admin,
            )
        except Exception as exc:
            self.console.print(f"[red]注册失败：{exc}[/red]")
            return
        self.console.print(f"[green]已注册并登录：{self.user.username}[/green]")

    def _calendar(self) -> None:
        assert self.user is not None
        month = Prompt.ask("Month", default=current_month(), console=self.console).strip()
        try:
            payload = DailyNoteService(user_context=self.user.context).list_month(month)
            self.console.print(render_note_calendar(month, payload, username=self.user.username))
        except Exception as exc:
            self.console.print(f"[red]日历加载失败：{exc}[/red]")

    def _reports(self) -> None:
        assert self.user is not None
        try:
            reports = SearchService(user_context=self.user.context).list_reports()
        except Exception as exc:
            self.console.print(f"[red]日报列表加载失败：{exc}[/red]")
            return
        table = Table(title="Optimized Reports", expand=True)
        for column in ["Date", "Week", "Project", "Tags", "Score", "File"]:
            table.add_column(column, overflow="fold" if column in {"Tags", "File"} else "ellipsis")
        for item in reports[-20:]:
            table.add_row(
                item.date,
                item.week,
                item.project or "-",
                ", ".join(item.tags) if item.tags else "-",
                str(item.quality_score) if item.quality_score is not None else "-",
                item.optimized_file,
            )
        if not reports:
            self.console.print(Panel("暂无优化日报。", title="Optimized Reports", border_style="grey50"))
            return
        self.console.print(table)

    def _search(self) -> None:
        assert self.user is not None
        query = Prompt.ask("Keyword", console=self.console).strip()
        if not query:
            self.console.print("[yellow]关键词不能为空。[/yellow]")
            return
        try:
            results = SearchService(user_context=self.user.context).search_reports(query=query, limit=10)
        except Exception as exc:
            self.console.print(f"[red]搜索失败：{exc}[/red]")
            return
        if not results:
            self.console.print(Panel("没有匹配结果。", title=f"Search: {query}", border_style="grey50"))
            return
        table = Table(title=f"Search: {query}", expand=True)
        table.add_column("Date", no_wrap=True)
        table.add_column("Section", overflow="fold")
        table.add_column("Snippet", overflow="fold")
        for item in results:
            table.add_row(item.date, item.matched_section, item.snippet)
        self.console.print(table)

    def _doctor(self) -> None:
        try:
            result = DoctorService().get_status(check_api=False)
        except Exception as exc:
            self.console.print(f"[red]Doctor failed：{exc}[/red]")
            return
        table = Table(title="DailyChewer Doctor")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Value")
        table.add_column("Details")
        for item in result.checks:
            table.add_row(item.name, _status_markup(item.status), item.value, item.details)
        self.console.print(table)


def authenticate_user(username: str, password: str) -> TuiUser:
    """Authenticate one database-backed user for the interactive TUI."""

    settings = load_settings()
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for login/signup TUI mode.")
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise ValueError("用户名或密码错误。")
        if not user.is_active:
            raise ValueError("该用户已被禁用。")
        return TuiUser(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            is_admin=user.is_admin,
        )


def run_tui() -> None:
    """Run the interactive DailyChewer terminal UI."""

    DailyChewerTui().run()


def main() -> None:
    """Console-script entrypoint for `dailychewer.cli`."""

    run_tui()


def _welcome_panel() -> Panel:
    title = Text()
    title.append("DailyChewer CLI", style="bold cyan")
    title.append("  interactive mode", style="grey70")
    subtitle = Text("登录或注册后进入你的日报日历、检索和报告视图。", style="grey70")
    return Panel(Group(Align.left(title), Align.left(subtitle)), border_style="cyan", padding=(1, 2))


def _session_panel(user: TuiUser) -> Panel:
    name = user.display_name or user.username
    title = Text()
    title.append("DailyChewer CLI", style="bold cyan")
    title.append("  workspace", style="grey70")
    subtitle = Text()
    subtitle.append(f"user:{user.username}", style="green3")
    subtitle.append(f"  name:{name}", style="yellow3")
    subtitle.append(f"  role:{'admin' if user.is_admin else 'user'}", style="cyan")
    return Panel(Group(Align.left(title), Align.left(subtitle)), border_style="cyan", padding=(1, 2))


def _next_panel(commands: list[str], title: str) -> Panel:
    body = Text()
    for index, command in enumerate(commands, start=1):
        body.append(f"{index}. ", style="grey70")
        body.append(command, style="bold cyan")
        if index < len(commands):
            body.append("\n")
    return Panel(body, title=title, border_style="green3", padding=(1, 2))


def _normalize_action(value: str, aliases: dict[str, str]) -> str:
    return aliases.get(value.strip().lower(), value.strip().lower())


def _status_markup(status: str) -> str:
    mapping = {"OK": "[green]OK[/green]", "WARN": "[yellow]WARN[/yellow]", "FAIL": "[red]FAIL[/red]"}
    return mapping.get(status, status)


if __name__ == "__main__":
    main()
