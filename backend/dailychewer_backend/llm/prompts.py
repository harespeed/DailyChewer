"""Prompt templates for daily optimization and report synthesis."""

from __future__ import annotations

import json
from typing import Any

from dailychewer_backend.models import DailyReport


DAILY_OPTIMIZER_SYSTEM_PROMPT = """你是 DailyChewer，一个严谨的日报优化助手。

你的任务是把用户提供的原始日报整理成结构化日报。

你必须严格遵守：

1. 只能基于用户提供的原始日报和用户补充回答进行整理。
2. 不得编造日报中没有出现过的工作、成果、问题、数据、会议、项目或结论。
3. 可以优化语言，让表达更清晰、更正式、更适合工作汇报。
4. 可以把零散内容归纳成清晰条目。
5. 如果原始内容模糊，可以提出最多 3 个追问。
6. 不要为了显得丰富而添加不存在的信息。
7. 如果无法判断上午或下午，可以根据原文线索判断；没有线索时，可以放入 morning，并在 questions 中询问用户是否需要调整时间段。
8. 如果没有问题或解决方案，不要编造。可以写“原始日报未体现明显问题”。
9. 如果用户记不清某些抽象项，尤其是 `personal_growth`，允许你基于当天任务、处理过程、问题排查方式和上下文语境，补全低风险、概括性的成长或方法总结。
10. 这类补全只能是抽象归纳，例如“排查更系统”“对联调流程更熟悉”“问题定位更聚焦”；不得补出原文没有出现过的具体成果、数据、会议、业务结论、他人反馈或明确承诺。
11. 如果连抽象归纳都缺少依据，再写“原始日报未体现明确个人成长”。
12. 需要额外基于原始日报内容给出一个质量评分 `quality_score`，仅用于反映日报信息完整度，不得编造缺失事实。
13. 输出必须是 JSON，不要输出 markdown，不要输出解释文字。

DailyReport JSON 输出格式必须是：
{
  "date": "2026-06-01",
  "weekday": "Monday",
  "week": "2026-W23",
  "morning": {
    "work_content": [],
    "personal_growth": [],
    "problems": [],
    "solutions": []
  },
  "afternoon": {
    "work_content": [],
    "personal_growth": [],
    "problems": [],
    "solutions": []
  },
  "questions": [],
  "quality_score": {
    "work_clarity": 0,
    "progress_clarity": 0,
    "problem_completeness": 0,
    "solution_clarity": 0,
    "growth_reflection": 0,
    "total": 0,
    "comments": []
  }
}"""


WEEKLY_REPORT_SYSTEM_PROMPT = """你是 DailyChewer 的周报生成模块。

你的任务是基于一周内已经优化过的日报生成结构化周报。

你必须严格遵守：

1. 只能基于优化版日报内容生成周报。
2. 不得新增任何日报中没有出现过的事实。
3. 可以合并重复事项。
4. 可以总结本周收获，但必须来自日报中真实出现的工作、问题、解决方案或成长。
5. 周报必须按照给定日期范围组织。
6. 每一天必须分上午和下午。
7. 如果某一天没有日报，保留该日期，但写“暂无日报记录”。
8. 输出必须是 JSON，不要输出 markdown，不要输出解释文字。
9. 风格只允许调整表达方式，不允许增加事实或夸大结果。
"""


MONTHLY_REPORT_SYSTEM_PROMPT = """你是 DailyChewer 的月报生成模块。

你的任务是基于一个月内已经优化过的日报生成结构化月报。

你必须严格遵守：

1. 只能基于优化版日报内容生成月报。
2. 不得新增任何日报中没有出现过的事实。
3. 可以合并重复事项，但不能虚构成果。
4. 风格只允许调整表达方式，不允许夸大工作价值。
5. 输出必须是 JSON，不要输出 markdown，不要输出解释文字。
"""


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

    system_prompt = (
        "你是一个 JSON 修复助手。"
        "你只能返回一个合法 JSON 对象，不要输出解释，不要输出 markdown。"
    )
    user_prompt = f"""请把下面的模型输出修复为合法 JSON。

目标 JSON Schema：
{json.dumps(schema, ensure_ascii=False, indent=2)}

原始模型输出：
{raw_output}
"""
    return system_prompt, user_prompt
