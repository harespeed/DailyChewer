"""OpenAI-compatible LLM optimizer and weekly report builder."""

from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

import requests

from dailychewer_backend.config import Settings, get_llm_settings
from dailychewer_backend.llm.prompts import (
    DAILY_OPTIMIZER_SYSTEM_PROMPT,
    MONTHLY_REPORT_SYSTEM_PROMPT,
    WEEKLY_REPORT_SYSTEM_PROMPT,
    build_json_repair_prompt,
    build_daily_optimizer_user_prompt,
    build_monthly_report_user_prompt,
    build_weekly_report_user_prompt,
    build_weekly_report_user_prompt_for_range,
)
from dailychewer_backend.models import DailyQualityScore, DailyReport, DateRange, MonthlyReport, ReportSection, WeeklyReport
from dailychewer_backend.utils.date_utils import (
    date_for_weekday,
    iso_week_for_date,
    iter_date_strings,
    month_bounds,
    normalize_date,
    weekday_name,
    week_bounds,
)
from dailychewer_backend.utils.logger import get_logger
from dailychewer_backend.utils.text_utils import extract_json_payload


T = TypeVar("T")


class ReportOptimizer:
    """Call a chat-completions API and coerce responses into Pydantic models."""

    def __init__(
        self,
        settings: Settings,
        timeout: int | tuple[int, int] | None = None,
        max_retries: int = 2,
    ):
        self.settings = settings
        self.llm_settings = settings.llm if hasattr(settings, "llm") else get_llm_settings()
        self.timeout = timeout or (
            settings.llm_connect_timeout_seconds,
            settings.llm_read_timeout_seconds,
        )
        self.max_retries = max_retries
        self.logger = get_logger(settings)

    def optimize_daily_report(
        self,
        raw_text: str,
        date: str,
        user_answers: dict | None = None,
    ) -> DailyReport:
        """Optimize one raw daily report into a structured `DailyReport`."""

        self._ensure_api_configured()
        return self._call_with_json_retry(
            system_prompt=DAILY_OPTIMIZER_SYSTEM_PROMPT,
            user_prompt=build_daily_optimizer_user_prompt(
                raw_text=raw_text,
                date=date,
                user_answers=user_answers,
            ),
            schema_model=DailyReport,
            validator=lambda payload: self._validate_daily_report(payload, date=date),
            operation_name="optimize_daily_report",
        )

    def build_weekly_report(
        self,
        daily_reports: list[DailyReport],
        week: str,
        date_range: tuple[str, str] | None = None,
        style: str = "concise",
    ) -> WeeklyReport:
        """Build a `WeeklyReport` from optimized daily reports."""

        self._ensure_api_configured()
        if date_range:
            from_date, to_date = date_range
            user_prompt = build_weekly_report_user_prompt_for_range(
                daily_reports=daily_reports,
                week=week,
                from_date=from_date,
                to_date=to_date,
                style=style,
            )
        else:
            user_prompt = build_weekly_report_user_prompt(
                daily_reports=daily_reports,
                week=week,
                style=style,
            )

        return self._call_with_json_retry(
            system_prompt=WEEKLY_REPORT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_model=WeeklyReport,
            validator=lambda payload: self._validate_weekly_report(
                payload,
                week=week,
                date_range=date_range,
                style=style,
            ),
            operation_name="build_weekly_report",
        )

    def build_monthly_report(
        self,
        daily_reports: list[DailyReport],
        month: str,
        style: str = "formal",
    ) -> MonthlyReport:
        """Build a `MonthlyReport` from optimized daily reports."""

        self._ensure_api_configured()
        return self._call_with_json_retry(
            system_prompt=MONTHLY_REPORT_SYSTEM_PROMPT,
            user_prompt=build_monthly_report_user_prompt(
                daily_reports=daily_reports,
                month=month,
                style=style,
            ),
            schema_model=MonthlyReport,
            validator=lambda payload: self._validate_monthly_report(
                payload,
                month=month,
                style=style,
            ),
            operation_name="build_monthly_report",
        )

    def check_api_connectivity(self) -> dict[str, Any]:
        """Perform a minimal JSON-only API check for the `doctor --check-api` command."""

        self._ensure_api_configured()
        return self._call_with_json_retry(
            system_prompt="You are a connectivity check assistant. Return JSON only.",
            user_prompt='return {"ok": true} as valid JSON only',
            schema_model=dict,
            validator=self._validate_connectivity_response,
            operation_name="check_api_connectivity",
        )

    def _call_chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        """Send one chat-completions request and return assistant text."""

        headers = {
            "Authorization": f"Bearer {self.llm_settings.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.llm_settings.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        response: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    self.llm_settings.chat_completions_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                if attempt >= self.max_retries or not self._should_retry_request_exception(exc):
                    raise RuntimeError(f"LLM 调用失败：{exc}") from exc
                self.logger.warning(
                    "llm_request_retry provider=%s model=%s attempt=%s error=%s",
                    self.llm_settings.provider,
                    self.llm_settings.model,
                    attempt + 1,
                    exc,
                )
                time.sleep(min(attempt + 1, 2))

        if response is None:
            raise RuntimeError("LLM 调用失败：未收到响应。")

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("LLM 响应不是合法 JSON。") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM 响应格式异常，缺少 message content。") from exc

        if isinstance(content, list):
            text = "".join(
                chunk.get("text", "") for chunk in content if isinstance(chunk, dict)
            )
        elif isinstance(content, str):
            text = content
        else:
            raise RuntimeError("LLM 响应内容不是文本。")
        self.logger.info(
            "llm_response provider=%s model=%s response_length=%s",
            self.llm_settings.provider,
            self.llm_settings.model,
            len(text),
        )
        return text

    def _should_retry_request_exception(self, exc: requests.RequestException) -> bool:
        """Return whether an HTTP failure is likely transient and worth retrying."""

        if isinstance(exc, requests.HTTPError):
            status_code = exc.response.status_code if exc.response is not None else None
            return status_code in {408, 429, 500, 502, 503, 504}
        return isinstance(exc, (requests.ConnectionError, requests.Timeout))

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """Extract and decode a JSON object from raw model output."""

        return extract_json_payload(content)

    def _repair_json_response(self, raw_output: str, schema_model: type[Any]) -> str:
        """Ask the LLM to repair an invalid JSON response into valid JSON only."""

        system_prompt, user_prompt = build_json_repair_prompt(
            raw_output=raw_output,
            schema=schema_model.model_json_schema() if hasattr(schema_model, "model_json_schema") else {},
        )
        repaired = self._call_chat_completion(system_prompt=system_prompt, user_prompt=user_prompt)
        self.logger.warning(
            "llm_json_repair provider=%s model=%s response_length=%s",
            self.llm_settings.provider,
            self.llm_settings.model,
            len(repaired),
        )
        return repaired

    def _call_with_json_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[Any],
        validator: Callable[[dict[str, Any]], T],
        operation_name: str,
    ) -> T:
        """Run one JSON-producing LLM operation with repair and regeneration retries."""

        self._ensure_api_configured()
        last_error: Exception | None = None

        content = self._call_chat_completion(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            return validator(self._parse_json_response(content))
        except Exception as exc:
            last_error = exc
            self.logger.warning("%s initial_parse_failed error=%s", operation_name, exc)

        if self.max_retries >= 1:
            try:
                repaired = self._repair_json_response(content, schema_model=schema_model)
                return validator(self._parse_json_response(repaired))
            except Exception as exc:
                last_error = exc
                self.logger.warning("%s repair_parse_failed error=%s", operation_name, exc)

        for attempt in range(max(self.max_retries - 1, 0)):
            regenerated = self._call_chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            try:
                return validator(self._parse_json_response(regenerated))
            except Exception as exc:
                last_error = exc
                self.logger.warning(
                    "%s regenerate_parse_failed attempt=%s error=%s",
                    operation_name,
                    attempt + 1,
                    exc,
                )

        self.logger.error("%s failed_after_retries error=%s", operation_name, last_error)
        raise ValueError("Failed to parse LLM JSON response after retries.")

    def _ensure_api_configured(self) -> None:
        """Guard every LLM operation with a clear API key check."""

        if not self.llm_settings.api_key:
            raise RuntimeError(
                "No LLM API key configured. Please set MINIMAX_API_KEY or OPENAI_API_KEY in .env."
            )

    def _validate_daily_report(self, payload: dict[str, Any], date: str) -> DailyReport:
        """Apply defaults and validate one daily report payload."""

        payload = self._coerce_daily_report_payload(payload)
        payload.setdefault("date", date)
        payload.setdefault("weekday", weekday_name(date))
        payload.setdefault("week", iso_week_for_date(date))
        quality_payload = payload.get("quality_score")
        if quality_payload is not None:
            try:
                payload["quality_score"] = DailyQualityScore.model_validate(quality_payload).model_dump()
            except Exception:
                payload["quality_score"] = None
        report = DailyReport.model_validate(payload)
        self.logger.info(
            "daily_report_validated date=%s questions_count=%s quality_total=%s",
            report.date,
            len(report.questions),
            report.quality_score.total if report.quality_score else None,
        )
        return report

    def _validate_weekly_report(
        self,
        payload: dict[str, Any],
        week: str,
        date_range: tuple[str, str] | None = None,
        style: str = "concise",
    ) -> WeeklyReport:
        """Apply defaults and validate one weekly report payload."""

        payload = self._coerce_weekly_report_payload(payload, week=week)
        if date_range:
            from_date, to_date = date_range
            payload.setdefault("start_date", normalize_date(from_date))
            payload.setdefault("end_date", normalize_date(to_date))
            payload.setdefault(
                "date_range",
                {"from": normalize_date(from_date), "to": normalize_date(to_date)},
            )
        else:
            payload.setdefault("start_date", week_bounds(week)[0])
            payload.setdefault("end_date", week_bounds(week)[1])
        payload.setdefault("week", week)
        payload.setdefault("style", style)
        report = WeeklyReport.model_validate(payload)
        if date_range:
            return self._fill_missing_dates(report, from_date=date_range[0], to_date=date_range[1])
        return self._fill_missing_weekdays(report)

    def _validate_monthly_report(
        self,
        payload: dict[str, Any],
        month: str,
        style: str,
    ) -> MonthlyReport:
        """Apply defaults and validate one monthly report payload."""

        start_date, end_date = month_bounds(month)
        payload.setdefault("month", month)
        payload.setdefault("start_date", start_date)
        payload.setdefault("end_date", end_date)
        payload.setdefault("style", style)
        return MonthlyReport.model_validate(payload)

    def _validate_connectivity_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate the doctor connectivity payload."""

        if "ok" not in payload:
            raise ValueError("Connectivity response is missing the `ok` field.")
        return payload

    def _coerce_weekly_report_payload(self, payload: dict[str, Any], week: str) -> dict[str, Any]:
        """Normalize common LLM weekly shapes before Pydantic validation."""

        normalized = dict(payload)
        days_payload = normalized.get("days", {})
        normalized_days: dict[str, Any] = {}
        if isinstance(days_payload, list):
            iterable_days = days_payload
        elif isinstance(days_payload, dict):
            iterable_days = []
            for key, value in days_payload.items():
                if isinstance(value, dict):
                    day_payload = dict(value)
                    if "date" not in day_payload and self._looks_like_date(key):
                        day_payload["date"] = key
                    if "weekday" not in day_payload and not self._looks_like_date(key):
                        day_payload["weekday"] = key
                    iterable_days.append(day_payload)
                else:
                    iterable_days.append(
                        {
                            "date": key if self._looks_like_date(key) else "",
                            "weekday": weekday_name(key) if self._looks_like_date(key) else key,
                            "morning": {"work_content": value},
                            "afternoon": {},
                        }
                    )
        else:
            iterable_days = []

        for index, day_payload in enumerate(iterable_days):
            if not isinstance(day_payload, dict):
                continue
            daily_payload = self._coerce_daily_report_payload(day_payload)
            daily_payload.setdefault("week", week)
            date_value = str(daily_payload.get("date") or "").strip()
            weekday_value = str(daily_payload.get("weekday") or "").strip()
            key = date_value or weekday_value or f"day_{index + 1}"
            normalized_days[key] = daily_payload
        normalized["days"] = normalized_days
        normalized["weekly_gains"] = self._coerce_string_list(normalized.get("weekly_gains", []))
        return normalized

    def _coerce_daily_report_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize common LLM daily shapes before Pydantic validation."""

        normalized = dict(payload)
        normalized["morning"] = self._coerce_report_section(normalized.get("morning"))
        normalized["afternoon"] = self._coerce_report_section(normalized.get("afternoon"))
        normalized["questions"] = self._coerce_string_list(normalized.get("questions", []))
        if "quality_score" in normalized and normalized["quality_score"] is not None:
            normalized["quality_score"] = self._coerce_quality_score(normalized["quality_score"])
        return normalized

    def _coerce_report_section(self, payload: Any) -> dict[str, list[str]]:
        """Convert loose section output into the expected section fields."""

        if isinstance(payload, str):
            payload = {"work_content": [payload]}
        elif isinstance(payload, list):
            payload = {"work_content": payload}
        elif not isinstance(payload, dict):
            payload = {}
        return {
            "work_content": self._coerce_string_list(payload.get("work_content") or payload.get("work") or payload.get("工作内容")),
            "personal_growth": self._coerce_string_list(
                payload.get("personal_growth") or payload.get("growth") or payload.get("个人成长")
            ),
            "problems": self._coerce_string_list(payload.get("problems") or payload.get("issues") or payload.get("问题")),
            "solutions": self._coerce_string_list(payload.get("solutions") or payload.get("解决方案")),
        }

    def _coerce_quality_score(self, payload: Any) -> dict[str, Any] | None:
        """Keep quality score validation from failing on partial model output."""

        if not isinstance(payload, dict):
            return None
        normalized: dict[str, Any] = {}
        for field in [
            "work_clarity",
            "progress_clarity",
            "problem_completeness",
            "solution_clarity",
            "growth_reflection",
        ]:
            try:
                normalized[field] = max(0, min(5, int(payload.get(field, 0))))
            except (TypeError, ValueError):
                normalized[field] = 0
        try:
            normalized["total"] = int(payload.get("total", sum(normalized.values())))
        except (TypeError, ValueError):
            normalized["total"] = sum(normalized.values())
        normalized["comments"] = self._coerce_string_list(payload.get("comments", []))
        return normalized

    def _coerce_string_list(self, value: Any) -> list[str]:
        """Convert scalar or mixed values into a clean list of strings."""

        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = value
        else:
            items = [value]
        return [str(item).strip() for item in items if str(item).strip()]

    def _looks_like_date(self, value: Any) -> bool:
        """Return whether a value is an ISO date string."""

        try:
            normalize_date(str(value))
            return True
        except Exception:
            return False

    def _fill_missing_weekdays(self, report: WeeklyReport) -> WeeklyReport:
        """Guarantee Monday-Friday keys exist, even when some days are missing."""

        for weekday in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            if weekday in report.days:
                continue
            date_str = date_for_weekday(report.week, weekday)
            report.days[weekday] = DailyReport(
                date=date_str,
                weekday=weekday,
                week=report.week,
                morning=self._empty_section(),
                afternoon=self._empty_section(),
                questions=[],
            )
        return report

    def _fill_missing_dates(self, report: WeeklyReport, from_date: str, to_date: str) -> WeeklyReport:
        """Guarantee every date inside a custom range exists exactly once."""

        existing_by_date = {item.date: item for item in report.days.values()}
        normalized_days: dict[str, DailyReport] = {}
        for date_str in iter_date_strings(from_date, to_date):
            normalized_days[date_str] = existing_by_date.get(
                date_str,
                DailyReport(
                    date=date_str,
                    weekday=weekday_name(date_str),
                    week=iso_week_for_date(date_str),
                    morning=self._empty_section(),
                    afternoon=self._empty_section(),
                    questions=[],
                ),
            )
        report.days = normalized_days
        report.date_range = DateRange.model_validate(
            {"from": normalize_date(from_date), "to": normalize_date(to_date)}
        )
        return report

    def _empty_section(self) -> ReportSection:
        """Return the standard placeholder section for missing daily entries."""

        return ReportSection(
            work_content=["暂无日报记录"],
            personal_growth=["暂无日报记录"],
            problems=["暂无日报记录"],
            solutions=["暂无日报记录"],
        )
