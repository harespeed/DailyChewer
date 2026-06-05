"""Shared daily template generation service."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.db.repositories import UploadedFileRepository
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import TemplateResult, UserContext
from dailychewer_backend.report.templates import generate_daily_template
from dailychewer_backend.services import build_runtime, resolve_format
from dailychewer_backend.utils.date_utils import current_date_str, normalize_date


class TemplateService:
    """Generate reusable daily report templates."""

    def __init__(self, project_root: Path | None = None, user_context: UserContext | None = None):
        self.settings, _, self.file_store, _, self.logger = build_runtime(project_root=project_root)
        self.user_context = user_context or UserContext(storage_mode="local")
        self.session_factory = (
            get_session_maker(self.settings)
            if self.user_context.storage_mode == "database" and self.settings.database_url
            else None
        )

    def generate_template(
        self,
        date: str | None = None,
        fmt: str = "markdown",
        output: Path | None = None,
    ) -> TemplateResult:
        """Generate a template file and return its path."""

        resolved_date = normalize_date(date) if date else current_date_str()
        resolved_format = resolve_format(fmt, self.settings.report.default_format)
        output_path = output or self.file_store.build_template_output_path(
            resolved_date,
            resolved_format,
            user_id=self.user_context.user_id if self.user_context.storage_mode == "database" else None,
        )
        generated_path = generate_daily_template(
            output_path=output_path,
            date_str=resolved_date,
            fmt=resolved_format,
        )
        self.logger.info("template_generated format=%s output=%s", resolved_format, generated_path)
        if self.user_context.storage_mode == "database":
            if not self.user_context.user_id or self.session_factory is None:
                raise ValueError("Database mode requires a valid user context.")
            with self.session_factory() as session:
                file_record = UploadedFileRepository(session).create_uploaded_file(
                    user_id=self.user_context.user_id,
                    original_filename=generated_path.name,
                    stored_file_path=str(generated_path),
                    purpose="template",
                    size_bytes=generated_path.stat().st_size if generated_path.exists() else None,
                )
            return TemplateResult(file=str(generated_path), file_id=file_record.id)
        return TemplateResult(file=str(generated_path))
