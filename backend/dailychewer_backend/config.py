"""Configuration loading for DailyChewer."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
from urllib.parse import urljoin

from dotenv import load_dotenv
from pydantic import BaseModel, Field


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"
DEFAULT_LLM_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_LLM_READ_TIMEOUT_SECONDS = 60
DEFAULT_USE_CHINA_MIRROR = True
DEFAULT_APT_MIRROR = "https://mirrors.tuna.tsinghua.edu.cn/debian"
DEFAULT_PIP_INDEX_URL = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"
DEFAULT_PIP_TRUSTED_HOST = "mirrors.tuna.tsinghua.edu.cn"
DEFAULT_REPORT_FORMAT = "markdown"
DEFAULT_WEEKLY_STYLE = "concise"
DEFAULT_MONTHLY_STYLE = "formal"
DEFAULT_LANGUAGE = "zh-CN"
DEFAULT_JWT_ALGORITHM = "HS256"
DEFAULT_JWT_EXPIRE_MINUTES = 10080


class FileLLMConfig(BaseModel):
    """Optional LLM defaults loaded from `dailychewer.toml`."""

    provider: str = "openai-compatible"
    model: str | None = None
    base_url: str | None = None


class ReportConfig(BaseModel):
    """Report formatting defaults loaded from config."""

    default_format: str = DEFAULT_REPORT_FORMAT
    default_weekly_style: str = DEFAULT_WEEKLY_STYLE
    default_monthly_style: str = DEFAULT_MONTHLY_STYLE
    language: str = DEFAULT_LANGUAGE


class PrivacyConfig(BaseModel):
    """Privacy and redaction settings loaded from config."""

    enable_redaction: bool = True
    redact_phone: bool = True
    redact_email: bool = True
    redact_api_key: bool = True


class StorageConfig(BaseModel):
    """Storage directory defaults loaded from config."""

    data_dir: str = "data"
    input_dir: str = "input"


class BehaviorConfig(BaseModel):
    """CLI behavior defaults loaded from config."""

    ask_questions: bool = True
    auto_save: bool = False
    generate_weekly_after_ingest: bool = False


class AppConfig(BaseModel):
    """Top-level `dailychewer.toml` configuration model."""

    llm: FileLLMConfig = Field(default_factory=FileLLMConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)


@dataclass(slots=True)
class LLMSettings:
    """Resolved LLM provider settings with provider metadata."""

    provider: str
    api_key: str | None
    base_url: str
    model: str

    @property
    def chat_completions_url(self) -> str:
        """Return the OpenAI-compatible chat completions endpoint."""

        base_url = self.base_url.rstrip("/") + "/"
        return urljoin(base_url, "chat/completions")


class MirrorSettings(BaseModel):
    """Resolved Docker and pip mirror settings."""

    use_china_mirror: bool
    apt_mirror: str
    pip_index_url: str
    pip_trusted_host: str


class DatabaseSettings(BaseModel):
    """Resolved database and auth settings."""

    database_url: str | None = None
    jwt_secret_key: str | None = None
    jwt_algorithm: str = DEFAULT_JWT_ALGORITHM
    jwt_expire_minutes: int = DEFAULT_JWT_EXPIRE_MINUTES
    create_default_user: bool = True
    default_username: str = "admin"
    default_password: str = "admin123"
    default_display_name: str = "Admin"


@dataclass(slots=True)
class Settings:
    """Runtime settings resolved from CLI environment and config file."""

    llm: LLMSettings
    mirror: MirrorSettings
    database: DatabaseSettings
    app_config: AppConfig
    project_root: Path
    config_file_path: Path
    config_file_exists: bool
    data_dir: Path
    input_dir: Path
    raw_dir: Path
    optimized_dir: Path
    weekly_dir: Path
    monthly_dir: Path
    logs_dir: Path
    log_file: Path
    index_file: Path
    llm_connect_timeout_seconds: int
    llm_read_timeout_seconds: int

    @property
    def report(self) -> ReportConfig:
        """Shortcut accessor for report defaults."""

        return self.app_config.report

    @property
    def privacy(self) -> PrivacyConfig:
        """Shortcut accessor for privacy defaults."""

        return self.app_config.privacy

    @property
    def behavior(self) -> BehaviorConfig:
        """Shortcut accessor for behavior defaults."""

        return self.app_config.behavior

    @property
    def api_key(self) -> str | None:
        """Compatibility accessor for the active LLM API key."""

        return self.llm.api_key

    @property
    def base_url(self) -> str:
        """Compatibility accessor for the active LLM base URL."""

        return self.llm.base_url

    @property
    def model(self) -> str:
        """Compatibility accessor for the active LLM model name."""

        return self.llm.model

    @property
    def chat_completions_url(self) -> str:
        """Compatibility accessor for the active chat completions endpoint."""

        return self.llm.chat_completions_url

    @property
    def database_url(self) -> str | None:
        """Compatibility accessor for the configured database URL."""

        return self.database.database_url

    @property
    def database_enabled(self) -> bool:
        """Return whether a database URL has been configured."""

        return bool(self.database.database_url)


def _parse_bool_env(value: str | None, default: bool) -> bool:
    """Parse common boolean env var spellings with a fallback default."""

    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return default


def _env_or_value(env_name: str, config_value: str | None, default: str) -> str:
    """Resolve a string setting with env > config-file > default precedence."""

    return os.getenv(env_name, config_value or default)


def _env_or_bool(env_name: str, config_value: bool, default: bool) -> bool:
    """Resolve a boolean setting with env > config-file > default precedence."""

    if env_name in os.environ:
        return _parse_bool_env(os.getenv(env_name), default)
    return config_value if config_value is not None else default


def _env_or_int(env_name: str, default: int) -> int:
    """Resolve one positive integer env var with fallback default."""

    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def load_project_config(project_root: Path | None = None) -> tuple[Path, bool, AppConfig]:
    """Load `dailychewer.toml` when present, otherwise return default config."""

    load_dotenv()
    root = (project_root or Path.cwd()).resolve()
    config_path = root / "dailychewer.toml"
    if not config_path.exists():
        return config_path, False, AppConfig()

    try:
        with config_path.open("rb") as handle:
            payload = tomllib.load(handle)
        return config_path, True, AppConfig.model_validate(payload)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Failed to parse dailychewer.toml: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Invalid dailychewer.toml configuration: {exc}") from exc


def get_llm_settings(config: AppConfig | None = None) -> LLMSettings:
    """Resolve active LLM settings with env > config-file > default precedence."""

    load_dotenv()
    app_config = config or AppConfig()
    configured_provider = app_config.llm.provider.strip().lower()

    minimax_api_key = os.getenv("MINIMAX_API_KEY") or None
    if minimax_api_key:
        return LLMSettings(
            provider="minimax",
            api_key=minimax_api_key,
            base_url=_env_or_value(
                "MINIMAX_BASE_URL",
                app_config.llm.base_url if configured_provider == "minimax" else None,
                DEFAULT_MINIMAX_BASE_URL,
            ).rstrip("/"),
            model=_env_or_value(
                "MINIMAX_MODEL",
                app_config.llm.model if configured_provider == "minimax" else None,
                DEFAULT_MINIMAX_MODEL,
            ),
        )

    openai_api_key = os.getenv("OPENAI_API_KEY") or None
    if openai_api_key:
        return LLMSettings(
            provider="openai-compatible",
            api_key=openai_api_key,
            base_url=_env_or_value(
                "OPENAI_BASE_URL",
                app_config.llm.base_url if configured_provider != "minimax" else None,
                DEFAULT_OPENAI_BASE_URL,
            ).rstrip("/"),
            model=_env_or_value(
                "OPENAI_MODEL",
                app_config.llm.model if configured_provider != "minimax" else None,
                DEFAULT_OPENAI_MODEL,
            ),
        )

    if configured_provider == "minimax":
        return LLMSettings(
            provider="minimax",
            api_key=None,
            base_url=_env_or_value(
                "MINIMAX_BASE_URL",
                app_config.llm.base_url,
                DEFAULT_MINIMAX_BASE_URL,
            ).rstrip("/"),
            model=_env_or_value(
                "MINIMAX_MODEL",
                app_config.llm.model,
                DEFAULT_MINIMAX_MODEL,
            ),
        )

    return LLMSettings(
        provider="openai-compatible",
        api_key=None,
        base_url=_env_or_value(
            "OPENAI_BASE_URL",
            app_config.llm.base_url,
            DEFAULT_OPENAI_BASE_URL,
        ).rstrip("/"),
        model=_env_or_value(
            "OPENAI_MODEL",
            app_config.llm.model,
            DEFAULT_OPENAI_MODEL,
        ),
    )


def get_mirror_settings() -> MirrorSettings:
    """Resolve Docker build and local pip mirror settings from environment variables."""

    load_dotenv()
    return MirrorSettings(
        use_china_mirror=_parse_bool_env(
            os.getenv("USE_CHINA_MIRROR"),
            DEFAULT_USE_CHINA_MIRROR,
        ),
        apt_mirror=os.getenv("APT_MIRROR", DEFAULT_APT_MIRROR),
        pip_index_url=os.getenv("PIP_INDEX_URL", DEFAULT_PIP_INDEX_URL),
        pip_trusted_host=os.getenv("PIP_TRUSTED_HOST", DEFAULT_PIP_TRUSTED_HOST),
    )


def get_database_settings() -> DatabaseSettings:
    """Resolve database and auth settings from environment variables."""

    load_dotenv()
    expire_minutes = os.getenv("JWT_EXPIRE_MINUTES", str(DEFAULT_JWT_EXPIRE_MINUTES))
    try:
        parsed_expire_minutes = int(expire_minutes)
    except ValueError:
        parsed_expire_minutes = DEFAULT_JWT_EXPIRE_MINUTES
    return DatabaseSettings(
        database_url=os.getenv("DATABASE_URL") or None,
        jwt_secret_key=os.getenv("JWT_SECRET_KEY") or None,
        jwt_algorithm=os.getenv("JWT_ALGORITHM", DEFAULT_JWT_ALGORITHM),
        jwt_expire_minutes=parsed_expire_minutes,
        create_default_user=_parse_bool_env(
            os.getenv("DAILYCHEWER_CREATE_DEFAULT_USER"),
            True,
        ),
        default_username=os.getenv("DAILYCHEWER_DEFAULT_USERNAME", "admin"),
        default_password=os.getenv("DAILYCHEWER_DEFAULT_PASSWORD", "admin123"),
        default_display_name=os.getenv("DAILYCHEWER_DEFAULT_DISPLAY_NAME", "Admin"),
    )


def load_settings(project_root: Path | None = None) -> Settings:
    """Load `.env`, optional `dailychewer.toml`, and derive all important local paths."""

    load_dotenv()
    root = (project_root or Path.cwd()).resolve()
    config_file_path, config_file_exists, app_config = load_project_config(root)
    resolved_config = AppConfig(
        llm=app_config.llm,
        report=ReportConfig(
            default_format=os.getenv("DAILYCHEWER_DEFAULT_FORMAT", app_config.report.default_format),
            default_weekly_style=os.getenv(
                "DAILYCHEWER_DEFAULT_WEEKLY_STYLE",
                app_config.report.default_weekly_style,
            ),
            default_monthly_style=os.getenv(
                "DAILYCHEWER_DEFAULT_MONTHLY_STYLE",
                app_config.report.default_monthly_style,
            ),
            language=os.getenv("DAILYCHEWER_LANGUAGE", app_config.report.language),
        ),
        privacy=PrivacyConfig(
            enable_redaction=_env_or_bool(
                "DAILYCHEWER_ENABLE_REDACTION",
                app_config.privacy.enable_redaction,
                True,
            ),
            redact_phone=app_config.privacy.redact_phone,
            redact_email=app_config.privacy.redact_email,
            redact_api_key=app_config.privacy.redact_api_key,
        ),
        storage=app_config.storage,
        behavior=BehaviorConfig(
            ask_questions=_env_or_bool(
                "DAILYCHEWER_ASK_QUESTIONS",
                app_config.behavior.ask_questions,
                True,
            ),
            auto_save=_env_or_bool(
                "DAILYCHEWER_AUTO_SAVE",
                app_config.behavior.auto_save,
                False,
            ),
            generate_weekly_after_ingest=_env_or_bool(
                "DAILYCHEWER_GENERATE_WEEKLY_AFTER_INGEST",
                app_config.behavior.generate_weekly_after_ingest,
                False,
            ),
        ),
    )
    data_dir_name = os.getenv("DAILYCHEWER_DATA_DIR", app_config.storage.data_dir)
    input_dir_name = os.getenv("DAILYCHEWER_INPUT_DIR", app_config.storage.input_dir)
    data_dir = (root / data_dir_name).resolve()
    return Settings(
        llm=get_llm_settings(resolved_config),
        mirror=get_mirror_settings(),
        database=get_database_settings(),
        app_config=resolved_config,
        project_root=root,
        config_file_path=config_file_path,
        config_file_exists=config_file_exists,
        data_dir=data_dir,
        input_dir=(root / input_dir_name).resolve(),
        raw_dir=data_dir / "raw",
        optimized_dir=data_dir / "optimized",
        weekly_dir=data_dir / "weekly",
        monthly_dir=data_dir / "monthly",
        logs_dir=data_dir / "logs",
        log_file=data_dir / "logs" / "dailychewer.log",
        index_file=data_dir / "index.json",
        llm_connect_timeout_seconds=_env_or_int(
            "DAILYCHEWER_LLM_CONNECT_TIMEOUT",
            DEFAULT_LLM_CONNECT_TIMEOUT_SECONDS,
        ),
        llm_read_timeout_seconds=_env_or_int(
            "DAILYCHEWER_LLM_READ_TIMEOUT",
            DEFAULT_LLM_READ_TIMEOUT_SECONDS,
        ),
    )


SUPPORTED_INPUT_FORMATS = {
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".md": "markdown",
    ".markdown": "markdown",
    ".docx": "docx",
}

SUPPORTED_EXPORT_FORMATS = {"csv", "xlsx", "markdown", "docx"}
SUPPORTED_REPORT_STYLES = {"concise", "formal", "detailed", "interview"}
WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
