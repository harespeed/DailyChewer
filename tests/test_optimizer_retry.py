from http.client import RemoteDisconnected
from pathlib import Path

import requests

from dailychewer.config import load_settings
from dailychewer.llm.optimizer import ReportOptimizer
from dailychewer.utils.text_utils import extract_json_payload


def test_optimizer_repairs_invalid_json(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    settings = load_settings()
    optimizer = ReportOptimizer(settings=settings)

    responses = iter(
        [
            '{"date": "2026-06-03", "morning": ',  # invalid JSON
            """
            {
              "date": "2026-06-03",
              "weekday": "Wednesday",
              "week": "2026-W23",
              "morning": {
                "work_content": ["梳理逻辑"],
                "personal_growth": ["理解更清晰"],
                "problems": ["暂无明显问题"],
                "solutions": ["持续跟进"]
              },
              "afternoon": {
                "work_content": ["调试接口"],
                "personal_growth": ["排查更系统"],
                "problems": ["错误码未统一映射"],
                "solutions": ["整理映射表"]
              },
              "questions": []
            }
            """,
        ]
    )

    monkeypatch.setattr(optimizer, "_call_chat_completion", lambda *args, **kwargs: next(responses))

    report = optimizer.optimize_daily_report(raw_text="日报原文", date="2026-06-03")

    assert report.date == "2026-06-03"
    assert report.morning.work_content == ["梳理逻辑"]
    assert report.afternoon.problems == ["错误码未统一映射"]


def test_optimizer_retries_transient_connection_abort(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    settings = load_settings()
    optimizer = ReportOptimizer(settings=settings)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": """
                            {
                              "date": "2026-06-03",
                              "weekday": "Wednesday",
                              "week": "2026-W23",
                              "morning": {
                                "work_content": ["梳理逻辑"],
                                "personal_growth": ["理解更清晰"],
                                "problems": ["暂无明显问题"],
                                "solutions": ["持续跟进"]
                              },
                              "afternoon": {
                                "work_content": ["调试接口"],
                                "personal_growth": ["排查更系统"],
                                "problems": ["错误码未统一映射"],
                                "solutions": ["整理映射表"]
                              },
                              "questions": []
                            }
                            """
                        }
                    }
                ]
            }

    attempts = {"count": 0}

    def fake_post(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise requests.ConnectionError(
                "Connection aborted.",
                RemoteDisconnected("Remote end closed connection without response"),
            )
        return FakeResponse()

    monkeypatch.setattr("dailychewer.llm.optimizer.requests.post", fake_post)
    monkeypatch.setattr("dailychewer.llm.optimizer.time.sleep", lambda _: None)

    report = optimizer.optimize_daily_report(raw_text="日报原文", date="2026-06-03")

    assert attempts["count"] == 2
    assert report.date == "2026-06-03"
    assert report.morning.work_content == ["梳理逻辑"]


def test_extract_json_payload_handles_fenced_text_and_trailing_commas() -> None:
    payload = extract_json_payload(
        """
        下面是结果：
        ```json
        {
          "date": "2026-06-12",
          "morning": {"work_content": ["联调接口",],},
          "afternoon": {}
        }
        ```
        """
    )

    assert payload["date"] == "2026-06-12"
    assert payload["morning"]["work_content"] == ["联调接口"]


def test_optimizer_coerces_loose_daily_report_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    settings = load_settings()
    optimizer = ReportOptimizer(settings=settings)

    report = optimizer._validate_daily_report(
        {
            "morning": "整理便条生成逻辑",
            "afternoon": {"problems": "模型输出字段不稳定"},
            "questions": "是否需要补充影响范围",
            "quality_score": {"work_clarity": "4", "progress_clarity": 3},
        },
        date="2026-06-12",
    )

    assert report.morning.work_content == ["整理便条生成逻辑"]
    assert report.afternoon.problems == ["模型输出字段不稳定"]
    assert report.questions == ["是否需要补充影响范围"]
    assert report.quality_score is not None
    assert report.quality_score.work_clarity == 4


def test_optimizer_coerces_weekly_days_list(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    settings = load_settings()
    optimizer = ReportOptimizer(settings=settings)

    report = optimizer._validate_weekly_report(
        {
            "days": [
                {
                    "date": "2026-06-12",
                    "weekday": "Friday",
                    "morning": {"work_content": "修复 JSON 解析"},
                    "afternoon": ["补充回归测试"],
                }
            ],
            "weekly_gains": "解析容错更稳定",
        },
        week="2026-W24",
        date_range=("2026-06-12", "2026-06-12"),
        style="concise",
    )

    day = report.days["2026-06-12"]
    assert day.morning.work_content == ["修复 JSON 解析"]
    assert day.afternoon.work_content == ["补充回归测试"]
    assert report.weekly_gains == ["解析容错更稳定"]
