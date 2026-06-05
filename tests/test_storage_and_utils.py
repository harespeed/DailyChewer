import json
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("openpyxl")

from dailychewer.config import load_settings
from dailychewer.models import DailyReport, ReportSection, WeeklyReport
from dailychewer.report.exporters import export_weekly_report
from dailychewer.storage.file_store import FileStore
from dailychewer.storage.index_store import IndexStore
from dailychewer.utils.date_utils import iso_week_for_date


def test_index_store_initializes_index_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    store = IndexStore(settings.index_file)

    store.ensure_initialized()

    assert settings.index_file.exists()
    payload = json.loads(settings.index_file.read_text(encoding="utf-8"))
    assert payload == {"reports": [], "weekly_reports": [], "monthly_reports": []}


def test_iso_week_calculation() -> None:
    assert iso_week_for_date("2026-06-03") == "2026-W23"


def test_markdown_exporter(tmp_path: Path) -> None:
    report = WeeklyReport(
        week="2026-W23",
        start_date="2026-06-01",
        end_date="2026-06-05",
        days={
            "Monday": DailyReport(
                date="2026-06-01",
                weekday="Monday",
                week="2026-W23",
                morning=ReportSection(
                    work_content=["梳理流程"],
                    personal_growth=["理解业务链路"],
                    problems=["字段定义不清晰"],
                    solutions=["后续确认字段边界"],
                ),
                afternoon=ReportSection(
                    work_content=["跟进测试反馈"],
                    personal_growth=["提升排查思路"],
                    problems=["暂无明显问题"],
                    solutions=["持续跟进"],
                ),
                questions=[],
            ),
            "Tuesday": DailyReport(
                date="2026-06-02",
                weekday="Tuesday",
                week="2026-W23",
                morning=ReportSection(
                    work_content=["暂无日报记录"],
                    personal_growth=["暂无日报记录"],
                    problems=["暂无日报记录"],
                    solutions=["暂无日报记录"],
                ),
                afternoon=ReportSection(
                    work_content=["暂无日报记录"],
                    personal_growth=["暂无日报记录"],
                    problems=["暂无日报记录"],
                    solutions=["暂无日报记录"],
                ),
                questions=[],
            ),
            "Wednesday": DailyReport(
                date="2026-06-03",
                weekday="Wednesday",
                week="2026-W23",
                morning=ReportSection(),
                afternoon=ReportSection(),
                questions=[],
            ),
            "Thursday": DailyReport(
                date="2026-06-04",
                weekday="Thursday",
                week="2026-W23",
                morning=ReportSection(),
                afternoon=ReportSection(),
                questions=[],
            ),
            "Friday": DailyReport(
                date="2026-06-05",
                weekday="Friday",
                week="2026-W23",
                morning=ReportSection(),
                afternoon=ReportSection(),
                questions=[],
            ),
        },
        weekly_gains=["加深了对业务流程的理解"],
    )
    output_path = tmp_path / "weekly.md"

    export_weekly_report(report, output_path, "markdown")

    content = output_path.read_text(encoding="utf-8")
    assert "# DailyChewer 周报" in content
    assert "## Monday 2026-06-01" in content
    assert "## 本周收获" in content


def test_clean_deletes_week_files(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from dailychewer.cli import app

    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    file_store = FileStore(settings)
    index_store = IndexStore(settings.index_file)
    file_store.ensure_directories()
    index_store.ensure_initialized()

    week = "2026-W23"
    raw_dir = settings.raw_dir / week
    optimized_dir = settings.optimized_dir / week
    weekly_dir = settings.weekly_dir / week
    raw_dir.mkdir(parents=True, exist_ok=True)
    optimized_dir.mkdir(parents=True, exist_ok=True)
    weekly_dir.mkdir(parents=True, exist_ok=True)

    raw_file = raw_dir / "2026-06-01_original.md"
    optimized_file = optimized_dir / "2026-06-01_optimized.md"
    weekly_file = weekly_dir / "weekly_report_2026-W23.md"
    raw_file.write_text("raw", encoding="utf-8")
    optimized_file.write_text("optimized", encoding="utf-8")
    weekly_file.write_text("weekly", encoding="utf-8")

    index_store.index_file.write_text(
        json.dumps(
            {
                "reports": [
                    {
                        "date": "2026-06-01",
                        "weekday": "Monday",
                        "week": week,
                        "raw_file": str(raw_file),
                        "optimized_file": str(optimized_file),
                        "source_format": "markdown",
                        "created_at": "2026-06-01T19:30:00",
                        "updated_at": "2026-06-01T19:35:00",
                        "status": "optimized",
                    }
                ],
                "weekly_reports": [
                    {
                        "week": week,
                        "format": "markdown",
                        "file": str(weekly_file),
                        "created_at": "2026-06-05T18:00:00",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["clean", "--week", week], input="y\n")

    assert result.exit_code == 0
    assert not raw_file.exists()
    assert not optimized_file.exists()
    assert not weekly_file.exists()
    payload = json.loads(settings.index_file.read_text(encoding="utf-8"))
    assert payload == {"reports": [], "weekly_reports": [], "monthly_reports": []}
