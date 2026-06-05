import json
from pathlib import Path

from typer.testing import CliRunner

from dailychewer_backend.config import load_settings
from dailychewer_backend.models import (
    DailyQualityScore,
    DailyReport,
    MonthlyReport,
    ReportIndexItem,
    ReportSection,
    WeeklyReport,
)
from dailychewer_backend.storage.file_store import FileStore
from dailychewer_backend.storage.index_store import IndexStore
from dailychewer_cli.cli import app


class FakeOptimizer:
    def __init__(self) -> None:
        self.calls: list[dict | None] = []
        self.weekly_styles: list[str] = []
        self.monthly_styles: list[str] = []

    def optimize_daily_report(self, raw_text: str, date: str, user_answers: dict | None = None) -> DailyReport:
        self.calls.append(user_answers)
        if user_answers is None:
            return DailyReport(
                date=date,
                weekday="Wednesday",
                week="2026-W23",
                morning=ReportSection(work_content=["梳理账号配置逻辑"]),
                afternoon=ReportSection(work_content=["调试评论自动回复接口"]),
                questions=["请补充错误码影响范围"],
                quality_score=DailyQualityScore(
                    work_clarity=4,
                    progress_clarity=3,
                    problem_completeness=3,
                    solution_clarity=2,
                    growth_reflection=3,
                    total=15,
                    comments=["基础信息较完整"],
                ),
            )
        return DailyReport(
            date=date,
            weekday="Wednesday",
            week="2026-W23",
            morning=ReportSection(
                work_content=["梳理账号配置逻辑"],
                personal_growth=["理解账号授权流程"],
                problems=["暂无明显问题"],
                solutions=["持续跟进"],
            ),
            afternoon=ReportSection(
                work_content=["调试评论自动回复接口"],
                personal_growth=["理解平台字段差异"],
                problems=["错误码没有统一映射"],
                solutions=["整理错误码映射表"],
            ),
            questions=[],
            quality_score=DailyQualityScore(
                work_clarity=4,
                progress_clarity=4,
                problem_completeness=4,
                solution_clarity=3,
                growth_reflection=4,
                total=19,
                comments=["信息较完整"],
            ),
        )

    def build_weekly_report(
        self,
        daily_reports: list[DailyReport],
        week: str,
        date_range: tuple[str, str] | None = None,
        style: str = "concise",
    ) -> WeeklyReport:
        self.weekly_styles.append(style)
        days = {item.date if date_range else item.weekday: item for item in daily_reports}
        start_date = date_range[0] if date_range else "2026-06-01"
        end_date = date_range[1] if date_range else "2026-06-05"
        return WeeklyReport(
            week=week,
            start_date=start_date,
            end_date=end_date,
            style=style,
            days=days,
            weekly_gains=["对平台差异有更清晰理解"],
        )

    def build_monthly_report(
        self,
        daily_reports: list[DailyReport],
        month: str,
        style: str = "formal",
    ) -> MonthlyReport:
        self.monthly_styles.append(style)
        return MonthlyReport(
            month=month,
            start_date=f"{month}-01",
            end_date=f"{month}-30",
            style=style,
            main_work=["本月主要工作 1"],
            key_progress=["关键进展 1"],
            problems_and_solutions=["问题与解决方案 1"],
            personal_growth=["个人成长 1"],
            monthly_gains=["本月收获 1"],
            next_improvements=["下月改进方向 1"],
        )


def _install_fake_optimizer(monkeypatch, optimizer: FakeOptimizer) -> None:
    monkeypatch.setattr("dailychewer_backend.services.ReportOptimizer", lambda settings: optimizer)


def _create_saved_daily_report(
    tmp_path: Path,
    date: str,
    source_suffix: str = ".md",
) -> tuple[Path, Path]:
    settings = load_settings(project_root=tmp_path)
    file_store = FileStore(settings)
    index_store = IndexStore(settings.index_file)
    file_store.ensure_directories()
    index_store.ensure_initialized()

    week = "2026-W23"
    source_file = tmp_path / f"source_{date}{source_suffix}"
    source_file.write_text("日报原文", encoding="utf-8")
    raw_path = file_store.save_raw_copy(source_file, week, date)
    report = DailyReport(
        date=date,
        weekday="Monday" if date == "2026-06-01" else "Tuesday",
        week=week,
        morning=ReportSection(work_content=["上午工作"]),
        afternoon=ReportSection(work_content=["下午工作"]),
        questions=[],
        quality_score=DailyQualityScore(
            work_clarity=4,
            progress_clarity=4,
            problem_completeness=3,
            solution_clarity=3,
            growth_reflection=3,
            total=17,
            comments=[],
        ),
    )
    optimized_path = file_store.save_optimized_report(report)
    index_store.upsert_report(
        ReportIndexItem(
            date=date,
            weekday=report.weekday,
            week=week,
            raw_file=str(raw_path),
            optimized_file=str(optimized_path),
            source_format="markdown",
            created_at="2026-06-01T10:00:00",
            updated_at="2026-06-01T10:00:00",
            status="optimized",
        )
    )
    return raw_path, optimized_path


def test_no_questions_skips_follow_up_prompts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _install_fake_optimizer(monkeypatch, FakeOptimizer())
    report_file = tmp_path / "example.md"
    report_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(report_file), "--save", "--no-weekly", "--no-questions"])

    assert result.exit_code == 0
    assert "补充问题" not in result.output


def test_date_range_filter_and_filename(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _install_fake_optimizer(monkeypatch, FakeOptimizer())
    _create_saved_daily_report(tmp_path, "2026-06-01")
    _create_saved_daily_report(tmp_path, "2026-06-02")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["weekly", "--from", "2026-06-01", "--to", "2026-06-07", "--format", "markdown", "--no-delete-prompt"],
    )

    assert result.exit_code == 0
    output_file = tmp_path / "data" / "weekly" / "2026-W23" / "weekly_report_2026-06-01_to_2026-06-07.md"
    assert output_file.exists()

    payload = json.loads((tmp_path / "data" / "index.json").read_text(encoding="utf-8"))
    weekly_entry = payload["weekly_reports"][0]
    assert weekly_entry["date_range"] == {"from": "2026-06-01", "to": "2026-06-07"}


def test_yes_does_not_delete_without_explicit_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _install_fake_optimizer(monkeypatch, FakeOptimizer())
    raw_path, optimized_path = _create_saved_daily_report(tmp_path, "2026-06-01")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["weekly", "--week", "2026-W23", "--format", "markdown", "--yes", "--no-delete-prompt"],
    )

    assert result.exit_code == 0
    assert raw_path.exists()
    assert optimized_path.exists()


def test_delete_after_export_requires_explicit_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _install_fake_optimizer(monkeypatch, FakeOptimizer())
    raw_path, optimized_path = _create_saved_daily_report(tmp_path, "2026-06-01")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["weekly", "--week", "2026-W23", "--format", "markdown", "--delete-after-export", "--no-delete-prompt"],
    )

    assert result.exit_code == 0
    assert not raw_path.exists()
    assert not optimized_path.exists()


def test_ingest_project_tags_written_to_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _install_fake_optimizer(monkeypatch, FakeOptimizer())
    report_file = tmp_path / "example.md"
    report_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ingest",
            str(report_file),
            "--project",
            "AI-App",
            "--tag",
            "automation",
            "--tag",
            "api",
            "--save",
            "--no-weekly",
            "--no-questions",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((tmp_path / "data" / "index.json").read_text(encoding="utf-8"))
    report = payload["reports"][0]
    assert report["project"] == "AI-App"
    assert report["tags"] == ["automation", "api"]
    assert report["quality_score"] == 19


def test_list_filters_by_project_and_tag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_saved_daily_report(tmp_path, "2026-06-01")
    settings = load_settings(project_root=tmp_path)
    payload = json.loads(settings.index_file.read_text(encoding="utf-8"))
    payload["reports"][0]["project"] = "AI-App"
    payload["reports"][0]["tags"] = ["automation"]
    settings.index_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    runner = CliRunner()
    project_result = runner.invoke(app, ["list", "--project", "AI-App"])
    tag_result = runner.invoke(app, ["list", "--tag", "automation"])

    assert project_result.exit_code == 0
    assert "AI-App" in project_result.output
    assert tag_result.exit_code == 0
    assert "automation" in tag_result.output


def test_search_command_keyword_match(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _create_saved_daily_report(tmp_path, "2026-06-01")
    settings = load_settings(project_root=tmp_path)
    file_store = FileStore(settings)
    report_path = settings.optimized_dir / "2026-W23" / "2026-06-01_optimized.md"
    report = file_store.load_optimized_report(report_path)
    report.afternoon.problems = ["错误码没有统一映射"]
    file_store.save_optimized_report(report)

    runner = CliRunner()
    result = runner.invoke(app, ["search", "错误码"])

    assert result.exit_code == 0
    assert "错误码没有统一映射" in result.output


def test_weekly_style_parameter_reaches_optimizer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    optimizer = FakeOptimizer()
    _install_fake_optimizer(monkeypatch, optimizer)
    _create_saved_daily_report(tmp_path, "2026-06-01")

    runner = CliRunner()
    result = runner.invoke(app, ["weekly", "--week", "2026-W23", "--format", "markdown", "--style", "formal", "--no-delete-prompt"])

    assert result.exit_code == 0
    assert optimizer.weekly_styles[-1] == "formal"


def test_weekly_preview_no_does_not_write_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _install_fake_optimizer(monkeypatch, FakeOptimizer())
    _create_saved_daily_report(tmp_path, "2026-06-01")

    runner = CliRunner()
    result = runner.invoke(app, ["weekly", "--week", "2026-W23", "--format", "markdown", "--preview"], input="n\n")

    assert result.exit_code == 0
    output_file = tmp_path / "data" / "weekly" / "2026-W23" / "weekly_report_2026-W23.md"
    assert not output_file.exists()
    payload = json.loads((tmp_path / "data" / "index.json").read_text(encoding="utf-8"))
    assert payload["weekly_reports"] == []


def test_monthly_markdown_export(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    optimizer = FakeOptimizer()
    _install_fake_optimizer(monkeypatch, optimizer)
    _create_saved_daily_report(tmp_path, "2026-06-01")

    runner = CliRunner()
    result = runner.invoke(app, ["monthly", "--month", "2026-06", "--format", "markdown", "--style", "formal"])

    assert result.exit_code == 0
    assert optimizer.monthly_styles[-1] == "formal"
    output_file = tmp_path / "data" / "monthly" / "2026-06" / "monthly_report_2026-06.md"
    assert output_file.exists()
