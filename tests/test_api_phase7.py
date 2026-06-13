import importlib
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from backend.api.routes.ingest import _build_preview_response
from backend.api.main import app
from dailychewer_backend.auth.security import verify_password
from dailychewer_backend.config import load_settings
from dailychewer_backend.db.models import Base
from dailychewer_backend.db.repositories import UploadedFileRepository, UserRepository
from dailychewer_backend.db.session import get_engine, get_session_maker
from dailychewer_backend.models import DailyQualityScore, DailyReport, ReportSection, UserContext
from dailychewer_backend.services.ingest_service import IngestService
from dailychewer_backend.services.note_service import DailyNoteService
from dailychewer_backend.services.search_service import SearchService
from dailychewer_backend.services.template_service import TemplateService
from dailychewer_backend.services.weekly_service import WeeklyService
from dailychewer_cli.cli import app as cli_app


class FakeOptimizer:
    def optimize_daily_report(self, raw_text: str, date: str, user_answers: dict | None = None) -> DailyReport:
        return DailyReport(
            date=date,
            weekday="Wednesday",
            week="2026-W23",
            morning=ReportSection(work_content=["梳理账号配置逻辑"]),
            afternoon=ReportSection(
                work_content=["调试评论自动回复接口"],
                problems=["错误码没有统一映射"],
            ),
            questions=[],
        )


class InteractiveFakeOptimizer:
    def optimize_daily_report(self, raw_text: str, date: str, user_answers: dict | None = None) -> DailyReport:
        answers = user_answers or {}
        impact_answer = answers.get("请补充影响范围", "").strip()
        output_answer = answers.get("请补充上午具体产出", "").strip()
        if impact_answer and not output_answer:
            questions = ["请补充上午具体产出"]
        elif impact_answer and output_answer:
            questions = []
        else:
            questions = ["请补充影响范围"]

        work_items = ["梳理账号配置逻辑"]
        if output_answer:
            work_items.append(output_answer)

        problems = ["错误码没有统一映射"]
        if impact_answer:
            problems.append(impact_answer)

        return DailyReport(
            date=date,
            weekday="Wednesday",
            week="2026-W23",
            morning=ReportSection(work_content=work_items),
            afternoon=ReportSection(
                work_content=["调试评论自动回复接口"],
                problems=problems,
            ),
            questions=questions,
            quality_score=DailyQualityScore(
                work_clarity=4,
                progress_clarity=4,
                problem_completeness=5 if impact_answer else 3,
                solution_clarity=3,
                growth_reflection=2,
                total=0,
                comments=["信息越完整，评分越稳定"],
            ),
        )


class CountingInteractiveFakeOptimizer:
    def __init__(self) -> None:
        self.call_count = 0

    def optimize_daily_report(self, raw_text: str, date: str, user_answers: dict | None = None) -> DailyReport:
        self.call_count += 1
        return InteractiveFakeOptimizer().optimize_daily_report(raw_text, date, user_answers)


def _install_fake_optimizer(monkeypatch) -> None:
    monkeypatch.setattr("dailychewer_backend.services.ReportOptimizer", lambda settings: FakeOptimizer())


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _poll_optimize_task(client: TestClient, token: str, task_id: str) -> dict:
    for _ in range(10):
        response = client.get(
            f"/api/ingest/optimize-tasks/{task_id}",
            headers=_auth_headers(token),
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"completed", "failed", "superseded"}:
            return payload
    raise AssertionError("optimize task did not finish in time")


def _register_and_login(client: TestClient, username: str, password: str = "password123") -> dict:
    register_response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "display_name": username.title()},
    )
    assert register_response.status_code == 200, register_response.text
    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    return login_response.json()


def _create_db_report(tmp_path: Path, user_id: str, username: str, monkeypatch, file_name: str = "example.md") -> None:
    _install_fake_optimizer(monkeypatch)
    report_file = tmp_path / file_name
    report_file.write_text("# 2026-06-03\n\n- 梳理逻辑\n- 错误码没有统一映射", encoding="utf-8")
    IngestService(
        project_root=tmp_path,
        user_context=UserContext(user_id=user_id, username=username, storage_mode="database"),
    ).ingest_report(
        file_path=report_file,
        date="2026-06-03",
        project="AI-App",
        tags=["automation"],
        save=True,
        no_questions=True,
    )


@pytest.fixture()
def db_client(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DAILYCHEWER_CREATE_DEFAULT_USER", "false")
    _install_fake_optimizer(monkeypatch)

    settings = load_settings(project_root=tmp_path)
    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)

    with TestClient(app) as client:
        yield client, settings


def test_health_endpoint(db_client) -> None:
    client, _ = db_client
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "DailyChewer"}


def test_doctor_endpoint_requires_admin(db_client) -> None:
    client, settings = db_client
    response = client.get("/api/doctor")

    assert response.status_code == 401

    user_auth = _register_and_login(client, "doctor-user")
    user_response = client.get("/api/doctor", headers=_auth_headers(user_auth["access_token"]))

    assert user_response.status_code == 403

    admin_auth = _register_and_login(client, "admin")
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("admin")
        assert user is not None
        user.is_admin = True
        session.add(user)
        session.commit()
    admin_auth = client.post("/api/auth/login", json={"username": "admin", "password": "password123"}).json()
    admin_response = client.get("/api/doctor", headers=_auth_headers(admin_auth["access_token"]))

    assert admin_response.status_code == 200
    assert "checks" in admin_response.json()


def test_user_register_success(db_client) -> None:
    client, _ = db_client

    response = client.post(
        "/api/auth/register",
        json={"username": "user1", "password": "password123", "display_name": "User One"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "user1"


def test_user_login_success(db_client) -> None:
    client, _ = db_client
    _register_and_login(client, "user1")

    response = client.post("/api/auth/login", json={"username": "user1", "password": "password123"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["user"]["username"] == "user1"


def test_password_not_saved_in_plaintext(db_client) -> None:
    client, settings = db_client
    _register_and_login(client, "user1")

    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("user1")

    assert user is not None
    assert user.password_hash != "password123"
    assert verify_password("password123", user.password_hash) is True


def test_auth_me_requires_token(db_client) -> None:
    client, _ = db_client
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_auth_me_returns_current_user(db_client) -> None:
    client, _ = db_client
    auth = _register_and_login(client, "user1")

    response = client.get("/api/auth/me", headers=_auth_headers(auth["access_token"]))

    assert response.status_code == 200
    assert response.json()["username"] == "user1"


def test_reports_requires_login(db_client) -> None:
    client, _ = db_client
    response = client.get("/api/reports")

    assert response.status_code == 401


def test_reports_are_filtered_by_user(db_client, monkeypatch) -> None:
    client, settings = db_client
    auth_a = _register_and_login(client, "usera")
    auth_b = _register_and_login(client, "userb")

    with get_session_maker(settings)() as session:
        repo = UserRepository(session)
        user_a = repo.get_by_username("usera")
        user_b = repo.get_by_username("userb")
    assert user_a is not None and user_b is not None

    _create_db_report(settings.project_root, user_b.id, user_b.username, monkeypatch, "userb.md")

    response_a = client.get("/api/reports", headers=_auth_headers(auth_a["access_token"]))
    response_b = client.get("/api/reports", headers=_auth_headers(auth_b["access_token"]))

    assert response_a.status_code == 200
    assert response_a.json() == []
    assert response_b.status_code == 200
    assert len(response_b.json()) == 1
    assert response_b.json()[0]["project"] == "AI-App"


def test_search_is_filtered_by_user(db_client, monkeypatch) -> None:
    client, settings = db_client
    auth_a = _register_and_login(client, "usera")
    _register_and_login(client, "userb")

    with get_session_maker(settings)() as session:
        user_b = UserRepository(session).get_by_username("userb")
    assert user_b is not None
    _create_db_report(settings.project_root, user_b.id, user_b.username, monkeypatch, "userb.md")

    response = client.get(
        "/api/search",
        params={"q": "错误码"},
        headers=_auth_headers(auth_a["access_token"]),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_daily_notes_calendar_crud(db_client) -> None:
    client, _ = db_client
    auth = _register_and_login(client, "notes-user")
    headers = _auth_headers(auth["access_token"])

    create_response = client.post(
        "/api/notes",
        json={
            "date": "2026-06-05",
            "period": "morning",
            "content": "上午梳理日报便条日历，确认 hover 气泡和绿色深浅规则。",
        },
        headers=headers,
    )
    assert create_response.status_code == 200, create_response.text
    note = create_response.json()
    assert note["date"] == "2026-06-05"
    assert note["period"] == "morning"
    assert note["detail_level"] >= 1

    month_response = client.get("/api/notes", params={"month": "2026-06"}, headers=headers)
    assert month_response.status_code == 200, month_response.text
    days = month_response.json()["days"]
    assert len(days) == 1
    assert days[0]["date"] == "2026-06-05"
    assert days[0]["note_count"] == 1

    update_response = client.patch(
        f"/api/notes/{note['id']}",
        json={"content": "下午继续补全便条编辑、删除和日报生成入口。", "period": "afternoon"},
        headers=headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["period"] == "afternoon"

    delete_response = client.delete(f"/api/notes/{note['id']}", headers=headers)
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json() == {"deleted": True}

    empty_response = client.get("/api/notes", params={"month": "2026-06"}, headers=headers)
    assert empty_response.status_code == 200, empty_response.text
    assert empty_response.json()["days"] == []


def test_daily_notes_weekly_range_route_validates_empty_range(db_client) -> None:
    client, _ = db_client
    auth = _register_and_login(client, "range-user")

    response = client.post(
        "/api/notes/generate-weekly-range",
        json={"from_date": "2026-06-01", "to_date": "2026-06-05"},
        headers=_auth_headers(auth["access_token"]),
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "该时间段还没有便条。"


def test_daily_notes_weekly_range_task_returns_result(db_client, monkeypatch) -> None:
    client, _ = db_client
    auth = _register_and_login(client, "range-task-user")

    class FakeDailyNoteService:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def generate_weekly_range(self, from_date: str, to_date: str) -> dict:
            return {
                "file": "/tmp/stage.md",
                "file_id": "file-1",
                "preview": f"{from_date}..{to_date}",
                "download_url": "/api/files/file-1/download",
            }

    monkeypatch.setattr("dailychewer_backend.services.note_task_service.DailyNoteService", FakeDailyNoteService)

    response = client.post(
        "/api/notes/generate-weekly-range-tasks",
        json={"from_date": "2026-06-01", "to_date": "2026-06-05"},
        headers=_auth_headers(auth["access_token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["task_id"]
    assert payload["status"] in {"pending", "running", "completed"}

    task_response = client.get(
        f"/api/notes/generate-weekly-range-tasks/{payload['task_id']}",
        headers=_auth_headers(auth["access_token"]),
    )

    assert task_response.status_code == 200, task_response.text
    task_payload = task_response.json()
    assert task_payload["status"] == "completed"
    assert task_payload["result"]["download_url"] == "/api/files/file-1/download"


def test_daily_notes_weekly_range_skips_current_daily_reports(tmp_path: Path, monkeypatch) -> None:
    service = DailyNoteService.__new__(DailyNoteService)
    service.settings = SimpleNamespace(project_root=tmp_path)
    service.user_context = UserContext(user_id="user-1", username="user", storage_mode="database")

    class FakeRecord:
        def __init__(self, note_date: date) -> None:
            self.note_date = note_date

    class FakeWeeklyService:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def build_weekly_report(self, **kwargs) -> SimpleNamespace:
            return SimpleNamespace(
                file="/tmp/stage.md",
                file_id="file-1",
                preview="stage preview",
                download_path="/api/files/file-1/download",
            )

    generated_dates: list[str] = []
    monkeypatch.setattr("dailychewer_backend.services.note_service.WeeklyService", FakeWeeklyService)
    monkeypatch.setattr(
        service,
        "_list_notes",
        lambda from_date, to_date: [FakeRecord(date(2026, 6, 10)), FakeRecord(date(2026, 6, 11))],
    )
    monkeypatch.setattr(service, "_daily_report_needs_regeneration", lambda note_date, records: note_date.endswith("-11"))
    monkeypatch.setattr(service, "generate_daily", lambda note_date: generated_dates.append(note_date))

    result = service.generate_weekly_range("2026-06-10", "2026-06-11")

    assert generated_dates == ["2026-06-11"]
    assert result["download_url"] == "/api/files/file-1/download"


def test_weekly_service_builds_fallback_report_when_llm_json_parse_fails(tmp_path: Path) -> None:
    service = WeeklyService.__new__(WeeklyService)
    service.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    daily_report = DailyReport(
        date="2026-06-12",
        weekday="Friday",
        week="2026-W24",
        morning=ReportSection(work_content=["修复阶段报导出"], personal_growth=["解析流程更稳定"]),
        afternoon=ReportSection(problems=["LLM JSON 输出不稳定"], solutions=["增加保守兜底"]),
        questions=[],
    )

    report = service._build_fallback_weekly_report(
        daily_reports=[daily_report],
        week="2026-W24",
        date_range=("2026-06-12", "2026-06-12"),
        style="concise",
    )

    assert report.days["2026-06-12"].morning.work_content == ["修复阶段报导出"]
    assert report.days["2026-06-12"].afternoon.solutions == ["增加保守兜底"]
    assert report.weekly_gains == ["解析流程更稳定"]


def test_download_blocks_path_traversal_for_authenticated_user(db_client) -> None:
    client, _ = db_client
    auth = _register_and_login(client, "user1")

    response = client.get(
        "/api/files/download",
        params={"path": "../pyproject.toml"},
        headers=_auth_headers(auth["access_token"]),
    )

    assert response.status_code == 403


def test_user_cannot_download_another_users_file(db_client) -> None:
    client, settings = db_client
    auth_a = _register_and_login(client, "usera")
    _register_and_login(client, "userb")

    with get_session_maker(settings)() as session:
        user_b = UserRepository(session).get_by_username("userb")
        assert user_b is not None
        target_dir = settings.data_dir / "users" / user_b.id / "templates"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "secret.md"
        target_file.write_text("hidden", encoding="utf-8")
        file_record = UploadedFileRepository(session).create_uploaded_file(
            user_id=user_b.id,
            original_filename="secret.md",
            stored_file_path=str(target_file),
            purpose="template",
            size_bytes=target_file.stat().st_size,
        )

    response = client.get(
        f"/api/files/{file_record.id}/download",
        headers=_auth_headers(auth_a["access_token"]),
    )

    assert response.status_code == 404


def test_ingest_service_save_false_does_not_write_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _install_fake_optimizer(monkeypatch)
    report_file = tmp_path / "example.md"
    report_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")

    result = IngestService(project_root=tmp_path).ingest_report(file_path=report_file, save=False)

    payload = json.loads(load_settings(project_root=tmp_path).index_file.read_text(encoding="utf-8"))
    assert result.saved is False
    assert payload["reports"] == []


def test_ingest_service_database_mode_writes_user_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'ingest.db'}")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key")
    _install_fake_optimizer(monkeypatch)

    settings = load_settings(project_root=tmp_path)
    Base.metadata.create_all(get_engine(settings.database_url))
    with get_session_maker(settings)() as session:
        user = UserRepository(session).create_user(
            username="user1",
            password_hash="hashed",
            display_name="User One",
        )

    report_file = tmp_path / "example.md"
    report_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")
    result = IngestService(
        project_root=tmp_path,
        user_context=UserContext(user_id=user.id, username=user.username, storage_mode="database"),
    ).ingest_report(
        file_path=report_file,
        date="2026-06-03",
        project="AI-App",
        tags=["automation"],
        save=True,
        no_questions=True,
    )

    assert result.saved is True
    with get_session_maker(settings)() as session:
        records = SearchService(
            project_root=tmp_path,
            user_context=UserContext(user_id=user.id, username=user.username, storage_mode="database"),
        ).list_reports(project="AI-App", tag="automation")
    assert len(records) == 1


def test_ingest_preview_payload_returns_quality_score(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dailychewer_backend.services.ReportOptimizer", lambda settings: InteractiveFakeOptimizer())
    report_file = tmp_path / "example.md"
    report_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")

    result = IngestService(project_root=tmp_path).ingest_report(
        file_path=report_file,
        date="2026-06-03",
        save=False,
    )
    payload = _build_preview_response(result)

    assert payload["quality_score"]["total"] == 16
    assert payload["daily_report"]["quality_score"]["total"] == 16
    assert payload["questions"] == ["请补充影响范围"]


def test_ingest_preview_generates_fallback_quality_score(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _install_fake_optimizer(monkeypatch)
    report_file = tmp_path / "example.md"
    report_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")

    result = IngestService(project_root=tmp_path).ingest_report(
        file_path=report_file,
        date="2026-06-03",
        save=False,
    )
    payload = _build_preview_response(result)

    assert payload["quality_score"] is not None
    assert payload["daily_report"]["quality_score"] is not None
    assert payload["quality_score"]["total"] >= 0
    assert payload["quality_score"]["comments"][0] == "该评分由本地规则兜底生成，用于反映信息完整度。"


def test_ingest_optimize_updates_preview_and_continues_questions(db_client, monkeypatch) -> None:
    client, settings = db_client
    monkeypatch.setattr("dailychewer_backend.services.ReportOptimizer", lambda settings: InteractiveFakeOptimizer())
    auth = _register_and_login(client, "optimizer")
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("optimizer")
    assert user is not None
    upload_dir = settings.data_dir / "users" / user.id / "uploads" / "tmp"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_file = upload_dir / "preview.md"
    upload_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")

    optimize_response = client.post(
        "/api/ingest/optimize",
        headers=_auth_headers(auth["access_token"]),
        json={
            "upload_id": upload_file.name,
            "date": "2026-06-03",
            "user_answers": {"请补充影响范围": "影响了评论自动回复的回归验证"},
        },
    )

    assert optimize_response.status_code == 200, optimize_response.text
    queued = optimize_response.json()
    assert queued["upload_id"] == upload_file.name
    assert queued["status"] == "pending"

    payload = _poll_optimize_task(client, auth["access_token"], queued["task_id"])
    assert payload["status"] == "completed"
    assert payload["result"]["upload_id"] == upload_file.name
    assert payload["result"]["daily_report"]["afternoon"]["problems"][-1] == "影响了评论自动回复的回归验证"
    assert payload["result"]["quality_score"]["total"] == 18
    assert payload["result"]["questions"] == ["请补充上午具体产出"]


def test_ingest_optimize_multiple_clicks_each_complete_once(db_client, monkeypatch) -> None:
    client, settings = db_client
    monkeypatch.setattr("dailychewer_backend.services.ReportOptimizer", lambda settings: InteractiveFakeOptimizer())
    auth = _register_and_login(client, "optimizer-seq")
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("optimizer-seq")
    assert user is not None
    upload_dir = settings.data_dir / "users" / user.id / "uploads" / "tmp"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_file = upload_dir / "preview-seq.md"
    upload_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")

    first_response = client.post(
        "/api/ingest/optimize",
        headers=_auth_headers(auth["access_token"]),
        json={
            "upload_id": upload_file.name,
            "date": "2026-06-03",
            "user_answers": {"请补充影响范围": "影响了评论自动回复的回归验证"},
        },
    )
    second_response = client.post(
        "/api/ingest/optimize",
        headers=_auth_headers(auth["access_token"]),
        json={
            "upload_id": upload_file.name,
            "date": "2026-06-03",
            "user_answers": {
                "请补充影响范围": "影响了评论自动回复的回归验证",
                "请补充上午具体产出": "完成了账号配置梳理文档",
            },
        },
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text

    first_task = _poll_optimize_task(client, auth["access_token"], first_response.json()["task_id"])
    second_task = _poll_optimize_task(client, auth["access_token"], second_response.json()["task_id"])

    assert first_task["status"] == "completed"
    assert first_task["result"]["questions"] == ["请补充上午具体产出"]
    assert second_task["status"] == "completed"
    assert second_task["result"]["questions"] == []
    assert second_task["result"]["daily_report"]["morning"]["work_content"][-1] == "完成了账号配置梳理文档"


def test_ingest_optimize_with_answers_calls_llm_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    optimizer = CountingInteractiveFakeOptimizer()
    monkeypatch.setattr("dailychewer_backend.services.ReportOptimizer", lambda settings: optimizer)
    report_file = tmp_path / "example.md"
    report_file.write_text("# 2026-06-03\n\n- 梳理逻辑", encoding="utf-8")

    result = IngestService(project_root=tmp_path).ingest_report(
        file_path=report_file,
        date="2026-06-03",
        save=False,
        user_answers={"请补充影响范围": "影响了评论自动回复的回归验证"},
    )

    assert optimizer.call_count == 1
    assert result.questions == ["请补充上午具体产出"]


def test_cli_local_mode_still_works() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_app, ["version"])

    assert result.exit_code == 0
    assert "DailyChewer 0.1.0" in result.output


def test_cli_user_database_mode_can_find_user(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key")
    settings = load_settings(project_root=tmp_path)
    Base.metadata.create_all(get_engine(settings.database_url))
    with get_session_maker(settings)() as session:
        user = UserRepository(session).create_user(
            username="admin",
            password_hash="hashed",
            display_name="Admin",
        )

    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        ["template", "--date", "2026-06-03", "--format", "markdown", "--user", "admin"],
    )

    assert result.exit_code == 0
    expected_path = settings.data_dir / "users" / user.id / "templates" / "2026-06-03_daily_template.md"
    assert expected_path.exists()


def test_alembic_migration_file_exists() -> None:
    migration = Path("backend/dailychewer_backend/db/migrations/versions/0001_init_multi_user.py")
    assert migration.exists()


def test_db_models_import_normal() -> None:
    assert importlib.import_module("dailychewer_backend.db.models")
    assert importlib.import_module("backend.api.main")
