import json
from pathlib import Path

from typer.testing import CliRunner

from dailychewer_backend.config import load_settings
from dailychewer_backend.models import DailyQualityScore, DailyReport, ReportIndexItem, ReportSection
from dailychewer_backend.storage.file_store import FileStore
from dailychewer_backend.storage.index_store import IndexStore
from dailychewer_backend.utils.redactor import redact_sensitive_text
from dailychewer_cli.cli import app


class FakeOptimizer:
    def __init__(self) -> None:
        self.weekly_styles: list[str] = []

    def build_weekly_report(
        self,
        daily_reports: list[DailyReport],
        week: str,
        date_range: tuple[str, str] | None = None,
        style: str = "concise",
    ):
        from dailychewer_backend.models import WeeklyReport

        self.weekly_styles.append(style)
        return WeeklyReport(
            week=week,
            start_date="2026-06-01",
            end_date="2026-06-05",
            style=style,
            days={daily_reports[0].weekday: daily_reports[0]},
            weekly_gains=["示例"],
        )


def _create_saved_daily_report(tmp_path: Path, date: str) -> None:
    settings = load_settings(project_root=tmp_path)
    file_store = FileStore(settings)
    index_store = IndexStore(settings.index_file)
    file_store.ensure_directories()
    index_store.ensure_initialized()
    week = "2026-W23"
    source_file = tmp_path / f"source_{date}.md"
    source_file.write_text("日报原文", encoding="utf-8")
    raw_path = file_store.save_raw_copy(source_file, week, date)
    optimized_path = file_store.save_optimized_report(
        DailyReport(
            date=date,
            weekday="Monday",
            week=week,
            morning=ReportSection(work_content=["上午工作"]),
            afternoon=ReportSection(work_content=["下午工作"]),
            questions=[],
        )
    )
    index_store.upsert_report(
        ReportIndexItem(
            date=date,
            weekday="Monday",
            week=week,
            raw_file=str(raw_path),
            optimized_file=str(optimized_path),
            source_format="markdown",
            created_at="2026-06-01T10:00:00",
            updated_at="2026-06-01T10:00:00",
            status="optimized",
        )
    )


def test_cli_parameter_priority_over_toml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dailychewer.toml").write_text(
        """
[report]
default_weekly_style = "concise"
""".strip(),
        encoding="utf-8",
    )
    _create_saved_daily_report(tmp_path, "2026-06-01")
    optimizer = FakeOptimizer()
    monkeypatch.setattr("dailychewer_backend.services.ReportOptimizer", lambda settings: optimizer)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["weekly", "--week", "2026-W23", "--format", "markdown", "--style", "formal", "--no-delete-prompt"],
    )

    assert result.exit_code == 0
    assert optimizer.weekly_styles[-1] == "formal"


def test_template_markdown_generation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    output_path = tmp_path / "input" / "2026-06-03.md"

    result = runner.invoke(
        app,
        ["template", "--date", "2026-06-03", "--format", "markdown", "--output", str(output_path)],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert "# 2026-06-03 日报" in output_path.read_text(encoding="utf-8")


def test_template_csv_generation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    output_path = tmp_path / "input" / "2026-06-03.csv"

    result = runner.invoke(
        app,
        ["template", "--date", "2026-06-03", "--format", "csv", "--output", str(output_path)],
    )

    assert result.exit_code == 0
    content = output_path.read_text(encoding="utf-8-sig")
    assert "Date,Period,Category,Content" in content


def test_redactor_email() -> None:
    result = redact_sensitive_text(
        "Contact me at example@example.com",
        load_settings().privacy,
    )
    assert "[REDACTED_EMAIL]" in result


def test_redactor_phone() -> None:
    result = redact_sensitive_text(
        "手机号是 13812345678",
        load_settings().privacy,
    )
    assert "[REDACTED_PHONE]" in result


def test_redactor_api_key() -> None:
    result = redact_sensitive_text(
        "sk-1234567890abcdef token=abcdef bearer abcdefgh",
        load_settings().privacy,
    )
    assert "[REDACTED_API_KEY]" in result or "[REDACTED_TOKEN]" in result


def test_old_index_json_compatibility(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings(project_root=tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.index_file.write_text(
        json.dumps({"reports": [], "weekly_reports": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    store = IndexStore(settings.index_file)
    data = store.load()

    assert data.monthly_reports == []


def test_quality_score_model_validation() -> None:
    score = DailyQualityScore(
        work_clarity=5,
        progress_clarity=4,
        problem_completeness=3,
        solution_clarity=2,
        growth_reflection=1,
        total=0,
        comments=["示例"],
    )

    assert score.total == 15
