from pathlib import Path
import json

from typer.testing import CliRunner

from dailychewer.cli import app
from dailychewer.config import get_llm_settings, get_mirror_settings, load_settings


def test_get_llm_settings_prefers_minimax(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-M2.7")

    settings = get_llm_settings()

    assert settings.provider == "minimax"
    assert settings.api_key == "minimax-key"
    assert settings.base_url == "https://api.minimaxi.com/v1"
    assert settings.model == "MiniMax-M2.7"


def test_get_llm_settings_falls_back_to_openai(monkeypatch) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "")
    monkeypatch.setenv("MINIMAX_BASE_URL", "")
    monkeypatch.setenv("MINIMAX_MODEL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    settings = get_llm_settings()

    assert settings.provider == "openai-compatible"
    assert settings.api_key == "openai-key"
    assert settings.base_url == "https://api.openai.com/v1"
    assert settings.model == "gpt-4o-mini"


def test_ingest_without_llm_key_shows_clear_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "")
    monkeypatch.setenv("MINIMAX_BASE_URL", "")
    monkeypatch.setenv("MINIMAX_MODEL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_MODEL", "")

    report_file = tmp_path / "example.md"
    report_file.write_text("# 2026-06-03\n\n- 梳理接口逻辑", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(report_file)])

    assert result.exit_code == 1
    assert (
        "No LLM API key configured. Please set MINIMAX_API_KEY or OPENAI_API_KEY in .env."
        in result.output
    )


def test_doctor_without_llm_key_does_not_crash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "DailyChewer Doctor" in result.output
    assert "not configured" in result.output


def test_get_mirror_settings_defaults_to_china_mirrors(monkeypatch) -> None:
    monkeypatch.delenv("USE_CHINA_MIRROR", raising=False)
    monkeypatch.delenv("APT_MIRROR", raising=False)
    monkeypatch.delenv("PIP_INDEX_URL", raising=False)
    monkeypatch.delenv("PIP_TRUSTED_HOST", raising=False)

    settings = get_mirror_settings()

    assert settings.use_china_mirror is True
    assert settings.apt_mirror == "https://mirrors.tuna.tsinghua.edu.cn/debian"
    assert settings.pip_index_url == "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"
    assert settings.pip_trusted_host == "mirrors.tuna.tsinghua.edu.cn"


def test_get_mirror_settings_parses_false(monkeypatch) -> None:
    monkeypatch.setenv("USE_CHINA_MIRROR", "false")

    settings = get_mirror_settings()

    assert settings.use_china_mirror is False


def test_get_mirror_settings_allows_pip_override(monkeypatch) -> None:
    monkeypatch.setenv("PIP_INDEX_URL", "https://mirrors.aliyun.com/pypi/simple/")
    monkeypatch.setenv("PIP_TRUSTED_HOST", "mirrors.aliyun.com")

    settings = get_mirror_settings()

    assert settings.pip_index_url == "https://mirrors.aliyun.com/pypi/simple/"
    assert settings.pip_trusted_host == "mirrors.aliyun.com"


def test_doctor_output_contains_mirror_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "USE_CHINA_MIRROR" in result.output
    assert "APT_MIRROR" in result.output
    assert "PIP_INDEX_URL" in result.output
    assert "PIP_TRUSTED_HOST" in result.output


def test_dockerfile_contains_mirror_build_args() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "ARG USE_CHINA_MIRROR=true" in dockerfile
    assert "ARG APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian" in dockerfile
    assert "ARG PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple" in dockerfile
    assert "ARG PIP_TRUSTED_HOST=mirrors.tuna.tsinghua.edu.cn" in dockerfile


def test_docker_compose_contains_mirror_build_args() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "USE_CHINA_MIRROR: ${USE_CHINA_MIRROR:-true}" in compose
    assert "APT_MIRROR: ${APT_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian}" in compose
    assert "PIP_INDEX_URL: ${PIP_INDEX_URL:-https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple}" in compose
    assert "PIP_TRUSTED_HOST: ${PIP_TRUSTED_HOST:-mirrors.tuna.tsinghua.edu.cn}" in compose


def test_load_settings_reads_dailychewer_toml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DAILYCHEWER_ENABLE_REDACTION", "false")
    (tmp_path / "dailychewer.toml").write_text(
        """
[report]
default_weekly_style = "formal"

[behavior]
auto_save = true

[privacy]
enable_redaction = false
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(project_root=tmp_path)

    assert settings.config_file_exists is True
    assert settings.report.default_weekly_style == "formal"
    assert settings.behavior.auto_save is True
    assert settings.privacy.enable_redaction is False


def test_load_settings_reads_llm_timeouts_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DAILYCHEWER_LLM_CONNECT_TIMEOUT", "15")
    monkeypatch.setenv("DAILYCHEWER_LLM_READ_TIMEOUT", "180")

    settings = load_settings(project_root=tmp_path)

    assert settings.llm_connect_timeout_seconds == 15
    assert settings.llm_read_timeout_seconds == 180
