"""File persistence for raw and optimized reports."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from dailychewer_backend.config import Settings
from dailychewer_backend.models import DailyReport
from dailychewer_backend.utils.text_utils import ensure_non_empty_text


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
        (self.settings.data_dir / "users").mkdir(parents=True, exist_ok=True)

    def user_root(self, user_id: str) -> Path:
        """Return the root data directory for one user."""

        return self.settings.data_dir / "users" / user_id

    def ensure_user_directories(self, user_id: str) -> None:
        """Create all user-scoped directories used by database mode."""

        root = self.user_root(user_id)
        for directory in [
            root / "raw",
            root / "optimized",
            root / "weekly",
            root / "monthly",
            root / "uploads" / "tmp",
            root / "templates",
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def user_uploads_tmp_dir(self, user_id: str) -> Path:
        """Return the temporary upload directory for one user."""

        self.ensure_user_directories(user_id)
        return self.user_root(user_id) / "uploads" / "tmp"

    def save_raw_copy(self, source_file: Path, week: str, date_str: str, user_id: str | None = None) -> Path:
        """Copy the original input file into the weekly raw directory."""

        self.ensure_directories()
        if user_id:
            self.ensure_user_directories(user_id)
            target_dir = self.user_root(user_id) / "raw" / week
        else:
            target_dir = self.settings.raw_dir / week
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{date_str}_original{source_file.suffix.lower()}"
        shutil.copy2(source_file, target_path)
        return target_path

    def save_optimized_report(self, report: DailyReport, user_id: str | None = None) -> Path:
        """Write a human-readable markdown report with an embedded JSON payload."""

        self.ensure_directories()
        if user_id:
            self.ensure_user_directories(user_id)
            target_dir = self.user_root(user_id) / "optimized" / report.week
        else:
            target_dir = self.settings.optimized_dir / report.week
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{report.date}_optimized.md"
        target_path.write_text(self.render_daily_report_markdown(report), encoding="utf-8")
        return target_path

    def save_uploaded_temp(self, file_name: str, content: bytes, user_id: str) -> Path:
        """Persist one temporary uploaded file under the user's isolated root."""

        target_dir = self.user_uploads_tmp_dir(user_id)
        target_path = target_dir / file_name
        target_path.write_bytes(content)
        return target_path

    def build_weekly_output_path(
        self,
        week: str,
        fmt: str,
        date_range_slug: str | None = None,
        user_id: str | None = None,
    ) -> Path:
        """Return the weekly output path for local or user-scoped storage."""

        suffix_map = {"markdown": ".md", "docx": ".docx", "xlsx": ".xlsx", "csv": ".csv"}
        if user_id:
            self.ensure_user_directories(user_id)
            output_dir = self.user_root(user_id) / "weekly" / week
        else:
            output_dir = self.settings.weekly_dir / week
        output_dir.mkdir(parents=True, exist_ok=True)
        file_stub = f"weekly_report_{date_range_slug}" if date_range_slug else f"weekly_report_{week}"
        return output_dir / f"{file_stub}{suffix_map[fmt]}"

    def build_monthly_output_path(self, month: str, fmt: str, user_id: str | None = None) -> Path:
        """Return the monthly output path for local or user-scoped storage."""

        suffix_map = {"markdown": ".md", "docx": ".docx", "xlsx": ".xlsx", "csv": ".csv"}
        if user_id:
            self.ensure_user_directories(user_id)
            output_dir = self.user_root(user_id) / "monthly" / month
        else:
            output_dir = self.settings.monthly_dir / month
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"monthly_report_{month}{suffix_map[fmt]}"

    def build_template_output_path(self, date_str: str, fmt: str, user_id: str | None = None) -> Path:
        """Return the template output path for local or user-scoped storage."""

        suffix_map = {"markdown": ".md", "csv": ".csv", "xlsx": ".xlsx", "docx": ".docx"}
        if user_id:
            self.ensure_user_directories(user_id)
            output_dir = self.user_root(user_id) / "templates"
        else:
            output_dir = self.settings.input_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{date_str}_daily_template{suffix_map[fmt]}"

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
