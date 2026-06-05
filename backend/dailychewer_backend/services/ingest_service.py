"""Shared daily report ingest workflow."""

from __future__ import annotations

from pathlib import Path

from dailychewer_backend.config import SUPPORTED_INPUT_FORMATS
from dailychewer_backend.db.repositories import (
    DailyReportRepository,
    ProjectRepository,
    TagRepository,
    UploadedFileRepository,
)
from dailychewer_backend.db.session import get_session_maker
from dailychewer_backend.models import DailyQualityScore, DailyReport, IngestResult, ReportIndexItem, UserContext
from dailychewer_backend.parser import get_parser
from dailychewer_backend.services import build_runtime, normalize_tags
from dailychewer_backend.utils.date_utils import (
    iso_week_for_date,
    now_timestamp,
    parse_date,
    resolve_report_date,
    weekday_name,
)
from dailychewer_backend.utils.redactor import redact_sensitive_text


class IngestService:
    """Parse, optimize, preview, and optionally save one daily report."""

    def __init__(self, project_root: Path | None = None, user_context: UserContext | None = None):
        self.settings, self.index_store, self.file_store, self.optimizer, self.logger = build_runtime(
            project_root=project_root
        )
        self.user_context = user_context or UserContext(storage_mode="local")
        self.session_factory = (
            get_session_maker(self.settings)
            if self.user_context.storage_mode == "database" and self.settings.database_url
            else None
        )

    def ingest_report(
        self,
        file_path: Path,
        date: str | None = None,
        project: str | None = None,
        tags: list[str] | None = None,
        save: bool = False,
        no_questions: bool = False,
        user_answers: dict | None = None,
        overwrite: bool = True,
    ) -> IngestResult:
        """Run the shared ingest flow and optionally persist the result."""

        source_file = file_path.expanduser().resolve()
        normalized_tags = normalize_tags(tags)
        if not source_file.exists() or not source_file.is_file():
            raise ValueError(f"文件不存在：{file_path}")

        source_format = SUPPORTED_INPUT_FORMATS.get(source_file.suffix.lower())
        if not source_format:
            raise ValueError(f"文件格式不支持：{source_file.suffix or 'unknown'}")

        parser = get_parser(source_file)
        self.logger.info(
            "ingest_start file=%s parser=%s provider=%s model=%s save=%s",
            source_file,
            parser.__class__.__name__,
            self.settings.llm.provider,
            self.settings.llm.model,
            save,
        )
        try:
            raw_text = parser.parse(source_file)
        except Exception as exc:
            raise ValueError("Input report file is empty or could not be parsed.") from exc

        if not raw_text.strip():
            raise ValueError("Input report file is empty or could not be parsed.")

        report_date = resolve_report_date(raw_text=raw_text, explicit_date=date)
        week = iso_week_for_date(report_date)
        weekday = weekday_name(report_date)
        existing = self.index_store.find_report_by_date(report_date)
        if self.user_context.storage_mode == "local" and existing and not overwrite:
            raise ValueError(f"{report_date} 已存在日报，请确认是否覆盖。")

        redacted_text = redact_sensitive_text(raw_text, self.settings.privacy)
        answers = user_answers or {}
        optimized_report = self.optimizer.optimize_daily_report(
            raw_text=redacted_text,
            date=report_date,
            user_answers=answers if answers else None,
        )
        if optimized_report.questions and no_questions and not answers:
            optimized_report = self.optimizer.optimize_daily_report(
                raw_text=redacted_text,
                date=report_date,
                user_answers=answers,
            )

        optimized_report.date = report_date
        optimized_report.week = week
        optimized_report.weekday = weekday
        optimized_report.quality_score = self._ensure_quality_score(optimized_report)

        result = IngestResult(
            saved=False,
            source_format=source_format,
            daily_report=optimized_report,
            questions=optimized_report.questions[:3],
            quality_score=optimized_report.quality_score,
            raw_text_length=len(raw_text),
            project=project if project is not None else (existing.project if existing else None),
            tags=normalized_tags if normalized_tags else (existing.tags if existing else []),
            existing_report=(existing is not None) if self.user_context.storage_mode == "local" else False,
        )

        if not save:
            self.logger.info(
                "ingest_preview_ready file=%s raw_text_length=%s questions_count=%s quality_total=%s",
                source_file,
                len(raw_text),
                len(result.questions),
                optimized_report.quality_score.total if optimized_report.quality_score else None,
            )
            return result

        if self.user_context.storage_mode == "database":
            if not self.user_context.user_id or self.session_factory is None:
                raise ValueError("Database mode requires a valid user context.")
            raw_copy_path = self.file_store.save_raw_copy(
                source_file,
                week,
                report_date,
                user_id=self.user_context.user_id,
            )
            optimized_path = self.file_store.save_optimized_report(
                optimized_report,
                user_id=self.user_context.user_id,
            )
            with self.session_factory() as session:
                project_record = ProjectRepository(session).get_or_create_project(
                    self.user_context.user_id,
                    result.project,
                )
                tag_records = TagRepository(session).get_or_create_tags(
                    self.user_context.user_id,
                    result.tags,
                )
                UploadedFileRepository(session).create_uploaded_file(
                    user_id=self.user_context.user_id,
                    original_filename=source_file.name,
                    stored_file_path=str(raw_copy_path),
                    purpose="raw_daily",
                    size_bytes=source_file.stat().st_size if source_file.exists() else None,
                )
                optimized_file_record = UploadedFileRepository(session).create_uploaded_file(
                    user_id=self.user_context.user_id,
                    original_filename=optimized_path.name,
                    stored_file_path=str(optimized_path),
                    purpose="raw_daily",
                    size_bytes=optimized_path.stat().st_size if optimized_path.exists() else None,
                )
                record = DailyReportRepository(session).create_daily_report(
                    user_id=self.user_context.user_id,
                    report_date=parse_date(report_date),
                    weekday=weekday,
                    iso_week=week,
                    project_id=project_record.id if project_record else None,
                    source_format=source_format,
                    raw_file_path=str(raw_copy_path),
                    optimized_file_path=str(optimized_path),
                    quality_score_total=optimized_report.quality_score.total if optimized_report.quality_score else None,
                    daily_report_json=optimized_report.model_dump(by_alias=True),
                    tags=tag_records,
                )
            index_item = ReportIndexItem(
                date=report_date,
                weekday=weekday,
                week=week,
                raw_file=str(raw_copy_path),
                optimized_file=str(optimized_path),
                source_format=source_format,
                created_at=record.created_at.replace(microsecond=0).isoformat(),
                updated_at=record.updated_at.replace(microsecond=0).isoformat(),
                status="optimized",
                quality_score=optimized_report.quality_score.total if optimized_report.quality_score else None,
                project=result.project,
                tags=result.tags,
            )
            result.saved = True
            result.raw_file = str(raw_copy_path)
            result.optimized_file = str(optimized_path)
            result.index_item = index_item
            return result

        raw_copy_path = self.file_store.save_raw_copy(source_file, week, report_date)
        optimized_path = self.file_store.save_optimized_report(optimized_report)
        if existing:
            stale_paths: list[Path] = []
            if Path(existing.raw_file) != raw_copy_path:
                stale_paths.append(Path(existing.raw_file))
            if Path(existing.optimized_file) != optimized_path:
                stale_paths.append(Path(existing.optimized_file))
            self.file_store.delete_paths(stale_paths)

        timestamp = now_timestamp()
        index_item = ReportIndexItem(
            date=report_date,
            weekday=weekday,
            week=week,
            raw_file=str(raw_copy_path),
            optimized_file=str(optimized_path),
            source_format=source_format,
            created_at=existing.created_at if existing else timestamp,
            updated_at=timestamp,
            status="optimized",
            quality_score=optimized_report.quality_score.total if optimized_report.quality_score else None,
            project=result.project,
            tags=result.tags,
        )
        self.index_store.upsert_report(index_item)
        self.logger.info(
            "ingest_saved raw_path=%s optimized_path=%s raw_text_length=%s questions_count=%s quality_total=%s",
            raw_copy_path,
            optimized_path,
            len(raw_text),
            len(result.questions),
            optimized_report.quality_score.total if optimized_report.quality_score else None,
        )
        result.saved = True
        result.raw_file = str(raw_copy_path)
        result.optimized_file = str(optimized_path)
        result.index_item = index_item
        return result

    def _ensure_quality_score(self, report: DailyReport) -> DailyQualityScore:
        """Guarantee that preview and saved reports always expose one quality score."""

        if report.quality_score is not None:
            return report.quality_score

        def count_meaningful(items: list[str]) -> int:
            placeholders = {
                "原始日报未提供更多细节",
                "原始日报未体现明显问题",
                "原始日报未体现明确个人成长",
            }
            return sum(1 for item in items if item.strip() and item.strip() not in placeholders)

        work_count = count_meaningful(report.morning.work_content) + count_meaningful(report.afternoon.work_content)
        problem_count = count_meaningful(report.morning.problems) + count_meaningful(report.afternoon.problems)
        solution_count = count_meaningful(report.morning.solutions) + count_meaningful(report.afternoon.solutions)
        growth_count = count_meaningful(report.morning.personal_growth) + count_meaningful(report.afternoon.personal_growth)
        question_penalty = min(len(report.questions), 3)

        work_clarity = min(5, max(1 if work_count else 0, work_count + 1))
        progress_clarity = min(5, max(1 if work_count else 0, work_count))
        problem_completeness = min(5, problem_count + (1 if solution_count else 0))
        solution_clarity = min(5, solution_count + (1 if problem_count and solution_count else 0))
        growth_reflection = min(5, growth_count + (1 if growth_count else 0))

        if question_penalty:
            work_clarity = max(0, work_clarity - 1)
            progress_clarity = max(0, progress_clarity - 1)
            problem_completeness = max(0, problem_completeness - 1)

        comments: list[str] = ["该评分由本地规则兜底生成，用于反映信息完整度。"]
        if report.questions:
            comments.append("当前仍有待补充信息，继续完善后评分会更稳定。")

        return DailyQualityScore(
            work_clarity=work_clarity,
            progress_clarity=progress_clarity,
            problem_completeness=problem_completeness,
            solution_clarity=solution_clarity,
            growth_reflection=growth_reflection,
            total=0,
            comments=comments,
        )
