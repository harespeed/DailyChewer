"""Prompt templates for daily optimization and report synthesis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dailychewer_backend.models import DailyReport


def load_system_prompt(filename: str) -> str:
    """Load a system prompt from the project-level config directory."""

    candidates = [
        Path.cwd() / "config" / filename,
        Path(__file__).resolve().parents[3] / "config" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Prompt file not found: config/{filename}")


DAILY_OPTIMIZER_SYSTEM_PROMPT = load_system_prompt("dailyreport-system-prompt.md")
WEEKLY_REPORT_SYSTEM_PROMPT = load_system_prompt("weeklyreport-system-prompt.md")
MONTHLY_REPORT_SYSTEM_PROMPT = load_system_prompt("monthlyreport-system-prompt.md")
JSON_REPAIR_SYSTEM_PROMPT = load_system_prompt("jsonrepair-system-prompt.md")


STYLE_GUIDANCE = {
    "concise": "表达简洁，适合快速提交。",
    "formal": "表达正式，适合领导或部门周会。",
    "detailed": "表达更完整，适合个人复盘和存档。",
    "interview": "表达更偏成果归纳，适合复述给面试官，但不得新增事实。",
}


def build_daily_optimizer_user_prompt(
    raw_text: str,
    date: str,
    user_answers: dict[str, str] | None = None,
) -> str:
    """Compose the user prompt for one daily optimization round."""

    answers_text = "无"
    if user_answers is not None:
        answers_text = (
            json.dumps(user_answers, ensure_ascii=False, indent=2)
            if user_answers
            else "用户未补充更多信息，请基于现有内容生成保守版本。"
        )

    return f"""请基于以下内容生成结构化日报 JSON。

日期：{date}

原始日报内容：
{raw_text}

用户补充回答：
{answers_text}
"""


def build_weekly_report_user_prompt(
    daily_reports: list[DailyReport],
    week: str,
    style: str,
) -> str:
    """Compose the user prompt for weekly report generation."""

    payload = [report.model_dump(by_alias=True) for report in daily_reports]
    return f"""请基于以下优化版日报生成 WeeklyReport JSON。

周次：{week}
风格：{style}
风格说明：{STYLE_GUIDANCE.get(style, STYLE_GUIDANCE["concise"])}

优化版日报数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def build_weekly_report_user_prompt_for_range(
    daily_reports: list[DailyReport],
    week: str,
    from_date: str,
    to_date: str,
    style: str,
) -> str:
    """Compose the weekly prompt for a custom date range selection."""

    payload = [report.model_dump(by_alias=True) for report in daily_reports]
    return f"""请基于以下优化版日报生成 WeeklyReport JSON。

周次标签：{week}
日期范围：{from_date} 至 {to_date}
风格：{style}
风格说明：{STYLE_GUIDANCE.get(style, STYLE_GUIDANCE["concise"])}

要求：
1. 仅基于给定日报内容总结，不得新增事实。
2. `days` 中请覆盖该日期范围内已有或缺失的日期。
3. 若某个日期没有日报，仍保留该日期，并写“暂无日报记录”。
4. 输出必须是合法 JSON。
5. 合并重复事项，不要把占位句总结为真实工作、问题、方案或收获。

优化版日报数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def build_monthly_report_user_prompt(
    daily_reports: list[DailyReport],
    month: str,
    style: str,
) -> str:
    """Compose the user prompt for monthly report generation."""

    payload = [report.model_dump(by_alias=True) for report in daily_reports]
    return f"""请基于以下优化版日报生成 MonthlyReport JSON。

月份：{month}
风格：{style}
风格说明：{STYLE_GUIDANCE.get(style, STYLE_GUIDANCE["formal"])}

MonthlyReport JSON 输出格式：
{{
  "month": "{month}",
  "start_date": "{month}-01",
  "end_date": "{month}-30",
  "style": "{style}",
  "main_work": [],
  "key_progress": [],
  "problems_and_solutions": [],
  "personal_growth": [],
  "monthly_gains": [],
  "next_improvements": []
}}

优化版日报数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def build_json_repair_prompt(raw_output: str, schema: dict[str, Any]) -> tuple[str, str]:
    """Build the system and user prompts for JSON repair attempts."""

    user_prompt = f"""请把下面的模型输出修复为合法 JSON。

目标 JSON Schema：
{json.dumps(schema, ensure_ascii=False, indent=2)}

原始模型输出：
{raw_output}
"""
    return JSON_REPAIR_SYSTEM_PROMPT, user_prompt
