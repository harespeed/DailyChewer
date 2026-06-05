"""Shared environment diagnostics service."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from dailychewer_backend import __version__
from dailychewer_backend.models import DoctorCheckItem, DoctorResult
from dailychewer_backend.services.database_service import DatabaseService
from dailychewer_backend.services import build_runtime


def _mask_key(api_key: str | None) -> str:
    """Mask API keys before returning them to callers."""

    if not api_key:
        return "not configured"
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}****{api_key[-4:]}"


def _is_running_in_docker() -> bool:
    """Return whether the current process appears to run inside Docker."""

    return Path("/.dockerenv").exists() or bool(__import__("os").getenv("container"))


class DoctorService:
    """Gather runtime and connectivity checks without presentation concerns."""

    def __init__(self, project_root: Path | None = None):
        self.settings, self.index_store, _, self.optimizer, self.logger = build_runtime(
            project_root=project_root
        )

    def get_status(self, check_api: bool = False) -> DoctorResult:
        """Return all doctor checks as structured data."""

        checks: list[DoctorCheckItem] = []
        add = checks.append
        db_status = DatabaseService().check()

        add(DoctorCheckItem(name="Python Version", status="OK", value=sys.version.split()[0]))
        add(DoctorCheckItem(name="DailyChewer version", status="OK", value=__version__))
        add(
            DoctorCheckItem(
                name="Data Directory",
                status="OK" if self.settings.data_dir.exists() else "FAIL",
                value=str(self.settings.data_dir),
            )
        )
        add(
            DoctorCheckItem(
                name="Input Directory",
                status="OK" if self.settings.input_dir.exists() else "WARN",
                value=str(self.settings.input_dir),
            )
        )
        add(
            DoctorCheckItem(
                name="Config File",
                status="OK" if self.settings.config_file_exists else "WARN",
                value=str(self.settings.config_file_path),
                details="detected" if self.settings.config_file_exists else "not found, using defaults",
            )
        )
        if self.settings.index_file.exists():
            try:
                self.index_store.load()
                add(DoctorCheckItem(name="Index File", status="OK", value=str(self.settings.index_file)))
            except Exception as exc:
                add(
                    DoctorCheckItem(
                        name="Index File",
                        status="FAIL",
                        value=str(self.settings.index_file),
                        details=str(exc),
                    )
                )
        else:
            add(
                DoctorCheckItem(
                    name="Index File",
                    status="WARN",
                    value=str(self.settings.index_file),
                    details="not found yet",
                )
            )

        add(DoctorCheckItem(name="LLM Provider", status="OK", value=self.settings.llm.provider))
        add(DoctorCheckItem(name="LLM Base URL", status="OK", value=self.settings.llm.base_url))
        add(DoctorCheckItem(name="LLM Model", status="OK", value=self.settings.llm.model))
        add(
            DoctorCheckItem(
                name="Database URL",
                status="OK" if self.settings.database_url else "WARN",
                value=db_status.database_url_masked if self.settings.database_url else "not configured",
                details=(
                    "PostgreSQL-backed multi-user mode enabled."
                    if self.settings.database_url
                    else "CLI local mode can still use data/index.json."
                ),
            )
        )
        add(
            DoctorCheckItem(
                name="Database reachable",
                status="OK" if db_status.database_reachable else ("WARN" if not db_status.database_url_configured else "FAIL"),
                value=str(db_status.database_reachable).lower(),
                details="; ".join(db_status.details),
            )
        )
        add(
            DoctorCheckItem(
                name="Alembic revision",
                status="OK" if db_status.alembic_revision else "WARN",
                value=db_status.alembic_revision or "unknown",
            )
        )
        add(
            DoctorCheckItem(
                name="users table exists",
                status="OK" if db_status.users_table_exists else ("WARN" if not db_status.database_reachable else "FAIL"),
                value=str(db_status.users_table_exists).lower(),
            )
        )
        add(
            DoctorCheckItem(
                name="active admin exists",
                status="OK" if db_status.active_admin_exists else ("WARN" if not db_status.database_reachable else "FAIL"),
                value=str(db_status.active_admin_exists).lower(),
            )
        )
        add(
            DoctorCheckItem(
                name="API Key",
                status="OK" if self.settings.api_key else "WARN",
                value=_mask_key(self.settings.api_key),
                details=(
                    "configured" if self.settings.api_key else "No LLM API key configured. Please set MINIMAX_API_KEY or OPENAI_API_KEY in .env."
                ),
            )
        )
        add(
            DoctorCheckItem(
                name="Redaction",
                status="OK" if self.settings.privacy.enable_redaction else "WARN",
                value=str(self.settings.privacy.enable_redaction).lower(),
            )
        )
        add(
            DoctorCheckItem(
                name="Running in Docker",
                status="OK",
                value=str(_is_running_in_docker()).lower(),
            )
        )
        add(
            DoctorCheckItem(
                name="USE_CHINA_MIRROR",
                status="OK",
                value=str(self.settings.mirror.use_china_mirror).lower(),
            )
        )
        add(DoctorCheckItem(name="APT_MIRROR", status="OK", value=self.settings.mirror.apt_mirror))
        add(
            DoctorCheckItem(
                name="PIP_INDEX_URL",
                status="OK",
                value=self.settings.mirror.pip_index_url,
            )
        )
        add(
            DoctorCheckItem(
                name="PIP_TRUSTED_HOST",
                status="OK",
                value=self.settings.mirror.pip_trusted_host,
            )
        )
        frontend_dir = self.settings.project_root / "frontend"
        package_json = frontend_dir / "package.json"
        package_lock = frontend_dir / "package-lock.json"
        node_modules = frontend_dir / "node_modules"
        compose_file = self.settings.project_root / "docker-compose.yml"
        add(
            DoctorCheckItem(
                name="NPM_CONFIG_REGISTRY",
                status="OK",
                value=os.getenv("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com"),
            )
        )
        add(
            DoctorCheckItem(
                name="frontend package.json",
                status="OK" if package_json.exists() else "FAIL",
                value=str(package_json),
            )
        )
        add(
            DoctorCheckItem(
                name="frontend package-lock.json",
                status="OK" if package_lock.exists() else "WARN",
                value=str(package_lock),
            )
        )
        add(
            DoctorCheckItem(
                name="frontend node_modules",
                status="OK" if node_modules.exists() else "WARN",
                value=str(node_modules),
            )
        )
        compose_text = compose_file.read_text(encoding="utf-8") if compose_file.exists() else ""
        add(
            DoctorCheckItem(
                name="docker-compose.yml",
                status="OK" if compose_file.exists() else "FAIL",
                value=str(compose_file),
            )
        )
        add(
            DoctorCheckItem(
                name="postgres service in compose",
                status="OK" if "postgres:" in compose_text else "WARN",
                value=str("postgres:" in compose_text).lower(),
            )
        )
        backups_dir = self.settings.project_root / "backups"
        release_check = self.settings.project_root / "scripts" / "release_check.sh"
        docker_smoke = self.settings.project_root / "scripts" / "docker_smoke_test.sh"
        pg_smoke = self.settings.project_root / "scripts" / "pg_smoke_test.py"
        add(
            DoctorCheckItem(
                name="backup directory",
                status="OK" if backups_dir.exists() else "WARN",
                value=str(backups_dir),
            )
        )
        add(
            DoctorCheckItem(
                name="pg_dump available",
                status="OK" if shutil.which("pg_dump") else "WARN",
                value=str(bool(shutil.which("pg_dump"))).lower(),
            )
        )
        add(
            DoctorCheckItem(
                name="psql available",
                status="OK" if shutil.which("psql") else "WARN",
                value=str(bool(shutil.which("psql"))).lower(),
            )
        )
        add(
            DoctorCheckItem(
                name="release_check.sh",
                status="OK" if release_check.exists() else "FAIL",
                value=str(release_check),
            )
        )
        add(
            DoctorCheckItem(
                name="release_check.sh executable",
                status="OK" if release_check.exists() and os.access(release_check, os.X_OK) else "WARN",
                value=str(release_check.exists() and os.access(release_check, os.X_OK)).lower(),
            )
        )
        add(
            DoctorCheckItem(
                name="docker_smoke_test.sh executable",
                status="OK" if docker_smoke.exists() and os.access(docker_smoke, os.X_OK) else "WARN",
                value=str(docker_smoke.exists() and os.access(docker_smoke, os.X_OK)).lower(),
            )
        )
        add(
            DoctorCheckItem(
                name="pg_smoke_test.py",
                status="OK" if pg_smoke.exists() else "FAIL",
                value=str(pg_smoke),
            )
        )
        add(
            DoctorCheckItem(
                name="backup manifest support",
                status="OK",
                value="enabled",
            )
        )

        if check_api:
            if not self.settings.api_key:
                add(
                    DoctorCheckItem(
                        name="API Connectivity",
                        status="WARN",
                        value="skipped",
                        details="No LLM API key configured. Please set MINIMAX_API_KEY or OPENAI_API_KEY in .env.",
                    )
                )
            else:
                try:
                    result = self.optimizer.check_api_connectivity()
                    add(
                        DoctorCheckItem(
                            name="API Connectivity",
                            status="OK",
                            value="ok",
                            details=str(result),
                        )
                    )
                except Exception as exc:
                    add(
                        DoctorCheckItem(
                            name="API Connectivity",
                            status="FAIL",
                            value="failed",
                            details=str(exc),
                        )
                    )

        return DoctorResult(checks=checks)
