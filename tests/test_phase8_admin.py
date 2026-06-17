import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from backend.api.main import app
from dailychewer_backend.auth.security import verify_password
from dailychewer_backend.services.backup_service import BackupService
from dailychewer_backend.config import load_settings
from dailychewer_backend.db.models import Base
from dailychewer_backend.db.repositories import DailyReportRepository, UserRepository
from dailychewer_backend.db.session import get_engine, get_session_maker
from dailychewer_backend.models import DailyReport, ReportIndexItem, ReportSection, UserContext
from dailychewer_backend.services.note_service import DailyNoteService
from dailychewer_backend.services.migration_service import LegacyIndexMigrationService
from dailychewer_backend.storage.file_store import FileStore
from dailychewer_backend.storage.index_store import IndexStore
from dailychewer_cli.cli import app as cli_app
from dailychewer_cli.tui import authenticate_user


def _register_and_login(client: TestClient, username: str, password: str = "password123", *, admin: bool = False, settings=None):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "display_name": username.title()},
    )
    assert response.status_code == 200, response.text
    if admin and settings is not None:
        with get_session_maker(settings)() as session:
            repo = UserRepository(session)
            user = repo.get_by_username(username)
            assert user is not None
            user.is_admin = True
            session.add(user)
            session.commit()
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def db_env(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'phase8.db'}")
    monkeypatch.setenv("JWT_SECRET_KEY", "phase8-secret")
    monkeypatch.setenv("DAILYCHEWER_CREATE_DEFAULT_USER", "false")
    settings = load_settings(project_root=tmp_path)
    Base.metadata.create_all(get_engine(settings.database_url))
    return tmp_path, settings


@pytest.fixture()
def client(db_env):
    with TestClient(app) as test_client:
        yield test_client


def test_cli_user_create_and_list(db_env) -> None:
    _, settings = db_env
    runner = CliRunner()

    create_result = runner.invoke(
        cli_app,
        ["user", "create", "admin", "--password", "admin123", "--display-name", "Admin", "--admin"],
    )
    list_result = runner.invoke(cli_app, ["user", "list"])

    assert create_result.exit_code == 0
    assert "admin" in create_result.output
    assert list_result.exit_code == 0
    assert "password_hash" not in list_result.output
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("admin")
    assert user is not None
    assert user.is_admin is True


def test_cli_user_disable_enable_and_reset_password(db_env) -> None:
    _, settings = db_env
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "testuser", "--password", "password123"])

    disable_result = runner.invoke(cli_app, ["user", "disable", "testuser"])
    enable_result = runner.invoke(cli_app, ["user", "enable", "testuser"])
    reset_result = runner.invoke(cli_app, ["user", "reset-password", "testuser", "--password", "newpass123"])

    assert disable_result.exit_code == 0
    assert enable_result.exit_code == 0
    assert reset_result.exit_code == 0
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("testuser")
    assert user is not None
    assert verify_password("newpass123", user.password_hash) is True


def test_cli_notes_calendar_renders_daily_note_depth(db_env) -> None:
    _, settings = db_env
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "writer", "--password", "password123"])
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("writer")
        assert user is not None
        user_id = user.id

    service = DailyNoteService(
        user_context=UserContext(
            user_id=user_id,
            username="writer",
            storage_mode="database",
        )
    )
    service.create_note("短日志", note_date="2026-06-03", period="morning")
    service.create_note("详细日志" * 80, note_date="2026-06-04", period="afternoon")

    result = runner.invoke(cli_app, ["notes", "calendar", "--month", "2026-06", "--user", "writer"])

    assert result.exit_code == 0
    assert "DailyChewer CLI" in result.output
    assert "Daily Notes Calendar 2026-06" in result.output
    assert "Sun" in result.output
    assert "Mon" in result.output
    assert "Tue" in result.output
    assert "2026-06-03" in result.output
    assert "2026-06-04" in result.output
    assert "1 条日志" in result.output
    assert "●●●●" in result.output
    assert "Next commands" in result.output
    assert "dailychewer notes calendar --month 2026-06 --user writer" in result.output


def test_tui_authenticate_user_uses_database_credentials(db_env) -> None:
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "writer", "--password", "password123"])

    user = authenticate_user("writer", "password123")

    assert user.username == "writer"
    assert user.context.storage_mode == "database"


def test_cli_tui_help_is_registered() -> None:
    runner = CliRunner()

    result = runner.invoke(cli_app, ["tui", "--help"])

    assert result.exit_code == 0
    assert "interactive DailyChewer terminal UI" in result.output


def test_change_password_rejects_wrong_old_password(client: TestClient, db_env) -> None:
    _, settings = db_env
    auth = _register_and_login(client, "user1", settings=settings)

    response = client.post(
        "/api/auth/change-password",
        json={"old_password": "wrong", "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )

    assert response.status_code == 401


def test_change_password_updates_hash(client: TestClient, db_env) -> None:
    _, settings = db_env
    auth = _register_and_login(client, "user1", settings=settings)

    response = client.post(
        "/api/auth/change-password",
        json={"old_password": "password123", "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )

    assert response.status_code == 200
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("user1")
    assert user is not None
    assert verify_password("newpass123", user.password_hash) is True


def test_admin_can_list_users(client: TestClient, db_env) -> None:
    _, settings = db_env
    admin = _register_and_login(client, "admin1", settings=settings, admin=True)
    _register_and_login(client, "user2", settings=settings)

    response = client.get("/api/users", headers={"Authorization": f"Bearer {admin['access_token']}"})

    assert response.status_code == 200
    assert len(response.json()) >= 2


def test_normal_user_cannot_list_users(client: TestClient, db_env) -> None:
    _, settings = db_env
    user = _register_and_login(client, "user1", settings=settings)

    response = client.get("/api/users", headers={"Authorization": f"Bearer {user['access_token']}"})

    assert response.status_code == 403


def test_migrate_index_dry_run_does_not_write_database(db_env) -> None:
    tmp_path, settings = db_env
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "admin", "--password", "admin123", "--admin"])
    file_store = FileStore(settings)
    index_store = IndexStore(settings.index_file)
    file_store.ensure_directories()
    index_store.ensure_initialized()
    source = tmp_path / "legacy.md"
    source.write_text("legacy", encoding="utf-8")
    raw = file_store.save_raw_copy(source, "2026-W23", "2026-06-03")
    optimized = file_store.save_optimized_report(
        DailyReport(
            date="2026-06-03",
            weekday="Wednesday",
            week="2026-W23",
            morning=ReportSection(work_content=["legacy"]),
            afternoon=ReportSection(work_content=["legacy"]),
            questions=[],
        )
    )
    index_store.upsert_report(
        ReportIndexItem(
            date="2026-06-03",
            weekday="Wednesday",
            week="2026-W23",
            raw_file=str(raw),
            optimized_file=str(optimized),
            source_format="markdown",
            created_at="2026-06-03T10:00:00",
            updated_at="2026-06-03T10:00:00",
            status="optimized",
        )
    )

    result = runner.invoke(cli_app, ["migrate-index", "--user", "admin"])

    assert result.exit_code == 0
    with get_session_maker(settings)() as session:
        count = len(DailyReportRepository(session).list_daily_reports(next(u.id for u in UserRepository(session).list_users() if u.username == "admin")))
    assert count == 0


def test_migrate_index_apply_writes_database(db_env) -> None:
    tmp_path, settings = db_env
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "admin", "--password", "admin123", "--admin"])
    file_store = FileStore(settings)
    index_store = IndexStore(settings.index_file)
    file_store.ensure_directories()
    index_store.ensure_initialized()
    source = tmp_path / "legacy.md"
    source.write_text("legacy", encoding="utf-8")
    raw = file_store.save_raw_copy(source, "2026-W23", "2026-06-03")
    optimized_report = DailyReport(
        date="2026-06-03",
        weekday="Wednesday",
        week="2026-W23",
        morning=ReportSection(work_content=["legacy"]),
        afternoon=ReportSection(work_content=["legacy"]),
        questions=[],
    )
    optimized = file_store.save_optimized_report(optimized_report)
    index_store.upsert_report(
        ReportIndexItem(
            date="2026-06-03",
            weekday="Wednesday",
            week="2026-W23",
            raw_file=str(raw),
            optimized_file=str(optimized),
            source_format="markdown",
            created_at="2026-06-03T10:00:00",
            updated_at="2026-06-03T10:00:00",
            status="optimized",
        )
    )

    result = runner.invoke(cli_app, ["migrate-index", "--user", "admin", "--apply"])

    assert result.exit_code == 0
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("admin")
        assert user is not None
        records = DailyReportRepository(session).list_daily_reports(user.id)
    assert len(records) == 1
    migration = (records[0].daily_report_json or {}).get("_migration", {})
    assert migration.get("migration_id")


def test_migrate_index_apply_is_idempotent(db_env) -> None:
    tmp_path, settings = db_env
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "admin", "--password", "admin123", "--admin"])
    file_store = FileStore(settings)
    index_store = IndexStore(settings.index_file)
    file_store.ensure_directories()
    index_store.ensure_initialized()
    source = tmp_path / "legacy.md"
    source.write_text("legacy", encoding="utf-8")
    raw = file_store.save_raw_copy(source, "2026-W23", "2026-06-03")
    optimized = file_store.save_optimized_report(
        DailyReport(
            date="2026-06-03",
            weekday="Wednesday",
            week="2026-W23",
            morning=ReportSection(work_content=["legacy"]),
            afternoon=ReportSection(work_content=["legacy"]),
            questions=[],
        )
    )
    index_store.upsert_report(
        ReportIndexItem(
            date="2026-06-03",
            weekday="Wednesday",
            week="2026-W23",
            raw_file=str(raw),
            optimized_file=str(optimized),
            source_format="markdown",
            created_at="2026-06-03T10:00:00",
            updated_at="2026-06-03T10:00:00",
            status="optimized",
        )
    )

    first = runner.invoke(cli_app, ["migrate-index", "--user", "admin", "--apply"])
    second = runner.invoke(cli_app, ["migrate-index", "--user", "admin", "--apply"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("admin")
        assert user is not None
        records = DailyReportRepository(session).list_daily_reports(user.id)
    assert len(records) == 1
    assert "skipped_existing" in second.output


def test_migrate_index_copy_files_avoids_overwrite(db_env) -> None:
    tmp_path, settings = db_env
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "admin", "--password", "admin123", "--admin"])
    with get_session_maker(settings)() as session:
        user = UserRepository(session).get_by_username("admin")
        assert user is not None
    file_store = FileStore(settings)
    index_store = IndexStore(settings.index_file)
    file_store.ensure_directories()
    index_store.ensure_initialized()
    source_dir = tmp_path / "legacy_sources"
    source_dir.mkdir()
    source_a = source_dir / "same.md"
    source_b = source_dir / "same2.md"
    source_a.write_text("legacy-a", encoding="utf-8")
    source_b.write_text("legacy-b", encoding="utf-8")
    raw_a = file_store.save_raw_copy(source_a, "2026-W23", "2026-06-03")
    optimized_a = file_store.save_optimized_report(
        DailyReport(date="2026-06-03", weekday="Wednesday", week="2026-W23", morning=ReportSection(work_content=["a"]), afternoon=ReportSection(), questions=[])
    )
    raw_b = file_store.save_raw_copy(source_b, "2026-W23", "2026-06-04")
    optimized_b = file_store.save_optimized_report(
        DailyReport(date="2026-06-04", weekday="Thursday", week="2026-W23", morning=ReportSection(work_content=["b"]), afternoon=ReportSection(), questions=[])
    )
    # Force same visible filenames through index references.
    dup_a = tmp_path / "dup" / "same.md"
    dup_b = tmp_path / "dup2" / "same.md"
    dup_a.parent.mkdir()
    dup_b.parent.mkdir()
    dup_a.write_text("dup-a", encoding="utf-8")
    dup_b.write_text("dup-b", encoding="utf-8")
    index_store.upsert_report(
        ReportIndexItem(
            date="2026-06-03",
            weekday="Wednesday",
            week="2026-W23",
            raw_file=str(dup_a),
            optimized_file=str(optimized_a),
            source_format="markdown",
            created_at="2026-06-03T10:00:00",
            updated_at="2026-06-03T10:00:00",
            status="optimized",
        )
    )
    index_store.upsert_report(
        ReportIndexItem(
            date="2026-06-04",
            weekday="Thursday",
            week="2026-W23",
            raw_file=str(dup_b),
            optimized_file=str(optimized_b),
            source_format="markdown",
            created_at="2026-06-04T10:00:00",
            updated_at="2026-06-04T10:00:00",
            status="optimized",
        )
    )

    result = runner.invoke(cli_app, ["migrate-index", "--user", "admin", "--apply", "--copy-files"])

    assert result.exit_code == 0
    legacy_raw_dir = settings.data_dir / "users" / user.id / "legacy" / "raw"
    copied = sorted(path.name for path in legacy_raw_dir.iterdir())
    assert len(copied) == 2
    assert copied[0] != copied[1]


def test_db_check_without_database_url_does_not_crash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    runner = CliRunner()

    result = runner.invoke(cli_app, ["db", "check"])

    assert result.exit_code == 0
    assert "DATABASE_URL configured" in result.output


def test_db_init_with_sqlite_database(db_env) -> None:
    runner = CliRunner()

    result = runner.invoke(cli_app, ["db", "init"])

    assert result.exit_code == 0
    assert "DailyChewer DB Init" in result.output


def test_doctor_hides_database_url_password(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secret@localhost:5432/dailychewer")
    runner = CliRunner()

    result = runner.invoke(cli_app, ["doctor"])

    assert result.exit_code == 0
    assert "secret" not in result.output
    assert "****" in result.output


def test_doctor_contains_npm_registry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com")
    runner = CliRunner()

    result = runner.invoke(cli_app, ["doctor"])

    assert result.exit_code == 0
    assert "NPM_CONFIG_REGISTRY" in result.output
    assert "backup manifest support" in result.output


def test_backup_create_and_restore_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings(project_root=tmp_path)
    users_dir = settings.data_dir / "users" / "u1"
    users_dir.mkdir(parents=True, exist_ok=True)
    (users_dir / "note.txt").write_text("backup me", encoding="utf-8")
    settings.index_file.parent.mkdir(parents=True, exist_ok=True)
    settings.index_file.write_text(json.dumps({"reports": [], "weekly_reports": [], "monthly_reports": []}), encoding="utf-8")

    service = BackupService(project_root=tmp_path)
    backup = service.create_backup(tmp_path / "backups", skip_db=True)
    restore = service.restore_backup(Path(backup.backup_path), apply=False)

    assert Path(backup.backup_path).exists()
    assert Path(backup.manifest_path).exists()
    assert restore.dry_run is True


def test_frontend_dockerfile_dev_exists_and_has_registry() -> None:
    dockerfile = Path("frontend/Dockerfile.dev").read_text(encoding="utf-8")

    assert "ARG NPM_CONFIG_REGISTRY=https://registry.npmmirror.com" in dockerfile
    assert "npm config set registry" in dockerfile


def test_docker_compose_frontend_contains_npm_registry() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "NPM_CONFIG_REGISTRY=${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}" in compose


def test_pg_smoke_test_script_exists() -> None:
    assert Path("scripts/pg_smoke_test.py").exists()


def test_docker_smoke_test_script_exists_and_executable() -> None:
    script = Path("scripts/docker_smoke_test.sh")
    assert script.exists()
    assert script.stat().st_mode & 0o111


def test_release_check_script_exists_and_executable() -> None:
    script = Path("scripts/release_check.sh")
    assert script.exists()
    assert script.stat().st_mode & 0o111


def test_download_url_prefers_file_id(client: TestClient, db_env) -> None:
    _, settings = db_env
    auth = _register_and_login(client, "admin1", settings=settings, admin=True)

    response = client.post(
        "/api/template",
        json={"date": "2026-06-03", "format": "markdown"},
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["download_url"].startswith("/api/files/")


def test_migration_service_dry_run_no_write(db_env) -> None:
    tmp_path, settings = db_env
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "admin", "--password", "admin123"])
    settings.index_file.write_text(json.dumps({"reports": [], "weekly_reports": [], "monthly_reports": []}), encoding="utf-8")

    summary = LegacyIndexMigrationService(project_root=tmp_path).migrate("admin", apply=False)

    assert summary.dry_run is True
    assert summary.migration_ids == []


def test_backup_manifest_hides_database_password(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secret@localhost:5432/dailychewer")
    settings = load_settings(project_root=tmp_path)
    users_dir = settings.data_dir / "users" / "u1"
    users_dir.mkdir(parents=True, exist_ok=True)
    (users_dir / "note.txt").write_text("backup me", encoding="utf-8")

    backup = BackupService(project_root=tmp_path).create_backup(tmp_path / "backups", skip_db=True)
    manifest = json.loads(Path(backup.manifest_path).read_text(encoding="utf-8"))

    assert "secret" not in json.dumps(manifest)
    assert manifest["source"]["database_url_host"] == "localhost"


def test_backup_verify_success_and_checksum_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings(project_root=tmp_path)
    users_dir = settings.data_dir / "users" / "u1"
    users_dir.mkdir(parents=True, exist_ok=True)
    note = users_dir / "note.txt"
    note.write_text("backup me", encoding="utf-8")

    service = BackupService(project_root=tmp_path)
    backup = service.create_backup(tmp_path / "backups", skip_db=True)
    verified = service.verify_backup(Path(backup.backup_path))
    assert verified.missing == 0
    assert verified.checksum_failed == 0

    note_backup = Path(backup.backup_path) / "files" / "users" / "u1" / "note.txt"
    note_backup.write_text("tampered", encoding="utf-8")
    failed = service.verify_backup(Path(backup.backup_path))
    assert failed.checksum_failed == 1


def test_backup_restore_conflict_and_overwrite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings(project_root=tmp_path)
    users_dir = settings.data_dir / "users" / "u1"
    users_dir.mkdir(parents=True, exist_ok=True)
    live_file = users_dir / "note.txt"
    live_file.write_text("current", encoding="utf-8")

    service = BackupService(project_root=tmp_path)
    backup = service.create_backup(tmp_path / "backups", skip_db=True)
    backup_file = Path(backup.backup_path) / "files" / "users" / "u1" / "note.txt"
    backup_file.write_text("from-backup", encoding="utf-8")

    preview = service.restore_backup(Path(backup.backup_path), apply=False, restore_files=True)
    assert preview.dry_run is True
    assert preview.file_conflicts == 1
    assert live_file.read_text(encoding="utf-8") == "current"

    with pytest.raises(ValueError, match="overwrite-files"):
        service.restore_backup(Path(backup.backup_path), apply=True, restore_files=True)

    applied = service.restore_backup(
        Path(backup.backup_path),
        apply=True,
        restore_files=True,
        overwrite_files=True,
    )
    assert applied.files_restored is True
    assert live_file.read_text(encoding="utf-8") == "from-backup"


def test_backup_restore_requires_confirm_overwrite_db(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'phase10.db'}")
    monkeypatch.setenv("JWT_SECRET_KEY", "phase10-secret")
    settings = load_settings(project_root=tmp_path)
    Base.metadata.create_all(get_engine(settings.database_url))
    with get_session_maker(settings)() as session:
        UserRepository(session).create_user("admin", "hashed", is_admin=True)
    backup_root = tmp_path / "backups" / "manual_backup"
    db_dir = backup_root / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    (db_dir / "dailychewer.sql").write_text("-- noop", encoding="utf-8")
    (backup_root / "backup_manifest.json").write_text(
        json.dumps(
            {
                "backup_id": "manual",
                "created_at": "2026-06-03T10:00:00",
                "dailychewer_version": "0.1.0",
                "includes": {"db": True, "files": False, "logs": False},
                "database": {
                    "dump_file": "db/dailychewer.sql",
                    "sha256": "",
                    "size_bytes": (db_dir / "dailychewer.sql").stat().st_size,
                },
                "files": [],
                "source": {"data_dir": "data", "database_url_host": "localhost", "database_name": "phase10"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="confirm-overwrite-db"):
        BackupService(project_root=tmp_path).restore_backup(
            backup_root,
            apply=True,
            restore_db=True,
        )


def test_backup_zip_create_and_verify(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings(project_root=tmp_path)
    users_dir = settings.data_dir / "users" / "u1"
    users_dir.mkdir(parents=True, exist_ok=True)
    (users_dir / "note.txt").write_text("backup me", encoding="utf-8")

    service = BackupService(project_root=tmp_path)
    backup = service.create_backup(tmp_path / "backups", skip_db=True, zip_backup=True)

    assert backup.archive_path is not None
    verify = service.verify_backup(Path(backup.archive_path))
    assert verify.missing == 0
    assert verify.checksum_failed == 0


def test_migration_service_generates_deterministic_migration_id(db_env) -> None:
    tmp_path, settings = db_env
    runner = CliRunner()
    runner.invoke(cli_app, ["user", "create", "admin", "--password", "admin123"])
    file_store = FileStore(settings)
    index_store = IndexStore(settings.index_file)
    file_store.ensure_directories()
    index_store.ensure_initialized()
    source = tmp_path / "legacy.md"
    source.write_text("legacy", encoding="utf-8")
    raw = file_store.save_raw_copy(source, "2026-W23", "2026-06-03")
    optimized = file_store.save_optimized_report(
        DailyReport(
            date="2026-06-03",
            weekday="Wednesday",
            week="2026-W23",
            morning=ReportSection(work_content=["legacy"]),
            afternoon=ReportSection(work_content=["legacy"]),
            questions=[],
        )
    )
    index_store.upsert_report(
        ReportIndexItem(
            date="2026-06-03",
            weekday="Wednesday",
            week="2026-W23",
            raw_file=str(raw),
            optimized_file=str(optimized),
            source_format="markdown",
            created_at="2026-06-03T10:00:00",
            updated_at="2026-06-03T10:00:00",
            status="optimized",
        )
    )

    service = LegacyIndexMigrationService(project_root=tmp_path)
    summary_a = service.migrate("admin", apply=False)
    summary_b = service.migrate("admin", apply=False)

    assert len(summary_a.migration_ids) == 1
    assert summary_a.migration_ids == summary_b.migration_ids
