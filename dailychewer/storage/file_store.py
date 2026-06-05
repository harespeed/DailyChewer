"""File persistence for raw and optimized reports."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from dailychewer.config import Settings
from dailychewer.models import DailyReport
from dailychewer.utils.text_utils import ensure_non_empty_text


DAILY_JSON_MARKER = "DAILY_REPORT_JSON"


class FileStore:
    """Persist raw, optimized, and weekly report files under `data/`."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def ensure_directories(self) -> None:
        """Create the main data directories when they are missing."""

        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.input_dir.mkdir(parents=True, exist_ok=True)
        self.settings.raw_dir.mkdir(parents=True, exist_ok=True)
        self.settings.optimized_dir.mkdir(parents=True, exist_ok=True)
        self.settings.weekly_dir.mkdir(parents=True, exist_ok=True)
        self.settings.monthly_dir.mkdir(parents=True, exist_ok=True)
        self.settings.logs_dir.mkdir(parents=True, exist_ok=True)

    def save_raw_copy(self, source_file: Path, week: str, date_str: str) -> Path:
        """Copy the original input file into the weekly raw directory."""

        self.ensure_directories()
        target_dir = self.settings.raw_dir / week
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{date_str}_original{source_file.suffix.lower()}"
        shutil.copy2(source_file, target_path)
        return target_path

    def save_optimized_report(self, report: DailyReport) -> Path:
        """Write a human-readable markdown report with an embedded JSON payload."""

        self.ensure_directories()
        target_dir = self.settings.optimized_dir / report.week
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{report.date}_optimized.md"
        target_path.write_text(self.render_daily_report_markdown(report), encoding="utf-8")
        return target_path

    def render_daily_report_markdown(self, report: DailyReport) -> str:
        """Render one optimized daily report into markdown."""

        def render_list(items: list[str]) -> str:
            if not items:
                return "- 原始日报未提供更多细节"
            return "\n".join(f"- {item}" for item in items)

        content = f"""# DailyChewer 优化日报

- 日期: {report.date}
- 星期: {report.weekday}
- 周次: {report.week}

## 上午

### 工作内容
{render_list(report.morning.work_content)}

### 个人成长
{render_list(report.morning.personal_growth)}

### 问题总结
{render_list(report.morning.problems)}

### 解决方案
{render_list(report.morning.solutions)}

## 下午

### 工作内容
{render_list(report.afternoon.work_content)}

### 个人成长
{render_list(report.afternoon.personal_growth)}

### 问题总结
{render_list(report.afternoon.problems)}

### 解决方案
{render_list(report.afternoon.solutions)}

## 追问
{render_list(report.questions)}

<!-- {DAILY_JSON_MARKER}
{json.dumps(report.model_dump(by_alias=True), ensure_ascii=False, indent=2)}
-->
"""
        return content.strip() + "\n"

    def load_optimized_report(self, file_path: Path) -> DailyReport:
        """Read an optimized markdown report back into a `DailyReport`."""

        content = ensure_non_empty_text(file_path.read_text(encoding="utf-8"))
        marker_pattern = rf"<!-- {DAILY_JSON_MARKER}\s*(\{{.*?\}})\s*-->"
        match = re.search(marker_pattern, content, flags=re.DOTALL)
        if not match:
            raise ValueError(f"优化日报缺少结构化 JSON：{file_path}")
        payload = json.loads(match.group(1))
        return DailyReport.model_validate(payload)

    def delete_paths(self, paths: list[Path]) -> list[Path]:
        """Delete existing files and return the list of deleted paths."""

        deleted: list[Path] = []
        for path in paths:
            if not path.exists():
                continue
            try:
                path.unlink()
                deleted.append(path)
            except OSError as exc:
                raise ValueError(f"删除文件失败：{path}") from exc
        return deleted

    def cleanup_empty_directories(self, directories: list[Path]) -> None:
        """Remove directories that became empty after cleanup."""

        for directory in directories:
            if directory.exists() and directory.is_dir():
                try:
                    next(directory.iterdir())
                except StopIteration:
                    directory.rmdir()
