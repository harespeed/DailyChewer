"""Backup, verification, and restore helpers for file storage and PostgreSQL metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from urllib.parse import urlsplit

from sqlalchemy import text

from dailychewer_backend import __version__
from dailychewer_backend.db.session import get_engine
from dailychewer_backend.models import BackupCreateResult, BackupRestoreResult, BackupVerifyResult
from dailychewer_backend.services import build_runtime
from dailychewer_backend.utils.date_utils import now_timestamp


def _plain_database_url(database_url: str) -> str:
    """Convert SQLAlchemy-style PostgreSQL URLs into plain libpq URLs for tools."""

    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg://")
    return database_url


def _sha256_file(path: Path) -> str:
    """Return the sha256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BackupService:
    """Create and restore DailyChewer file/database backups."""

    MANIFEST_NAME = "backup_manifest.json"

    def __init__(self, project_root: Path | None = None):
        self.settings, _, _, _, self.logger = build_runtime(project_root=project_root)

    def create_backup(
        self,
        output_dir: Path,
        include_logs: bool = False,
        skip_db: bool = False,
        skip_files: bool = False,
        zip_backup: bool = False,
        remove_dir_after_zip: bool = False,
    ) -> BackupCreateResult:
        """Create one timestamped backup directory, optional zip archive, and manifest."""

        stamp = now_timestamp()
        backup_id = f"{stamp.replace('-', '').replace(':', '').replace('T', '_')}_{hashlib.sha256(stamp.encode('utf-8')).hexdigest()[:8]}"
        backup_root = output_dir.expanduser().resolve() / f"dailychewer_backup_{backup_id}"
        backup_root.mkdir(parents=True, exist_ok=True)
        details: list[str] = []
        files_backed_up = False
        database_dumped = False
        manifest_files: list[dict[str, object]] = []
        database_manifest: dict[str, object] | None = None

        if not skip_files:
            files_root = backup_root / "files"
            files_root.mkdir(parents=True, exist_ok=True)
            for relative in ["users", "index.json", "monthly"]:
                source = self.settings.data_dir / relative
                if not source.exists():
                    continue
                target = files_root / relative
                if source.is_dir():
                    shutil.copytree(source, target, dirs_exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            if include_logs and self.settings.logs_dir.exists():
                shutil.copytree(self.settings.logs_dir, files_root / "logs", dirs_exist_ok=True)
            files_backed_up = True
            manifest_files = self._collect_manifest_files(files_root, backup_root)

        if not skip_db:
            if not self.settings.database_url:
                details.append("DATABASE_URL not configured; database dump skipped.")
            else:
                db_dir = backup_root / "db"
                db_dir.mkdir(parents=True, exist_ok=True)
                dump_path = db_dir / "dailychewer.sql"
                try:
                    subprocess.run(
                        ["pg_dump", _plain_database_url(self.settings.database_url), "-f", str(dump_path)],
                        check=True,
                        cwd=self.settings.project_root,
                    )
                    database_dumped = True
                    database_manifest = {
                        "dump_file": str(dump_path.relative_to(backup_root)),
                        "sha256": _sha256_file(dump_path),
                        "size_bytes": dump_path.stat().st_size,
                    }
                except FileNotFoundError:
                    details.append("pg_dump not found; database dump skipped.")
                except subprocess.CalledProcessError as exc:
                    details.append(f"pg_dump failed: {exc}")

        manifest = {
            "backup_id": backup_id,
            "created_at": stamp,
            "dailychewer_version": __version__,
            "includes": {
                "db": database_dumped,
                "files": files_backed_up,
                "logs": include_logs,
            },
            "database": database_manifest,
            "files": manifest_files,
            "source": self._manifest_source(),
        }
        manifest_path = backup_root / self.MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        archive_path: str | None = None
        if zip_backup:
            archive_path = self._zip_backup_directory(backup_root)
            details.append(f"Zip archive created: {archive_path}")
            if remove_dir_after_zip:
                shutil.rmtree(backup_root)
                details.append("Removed backup directory after zip creation.")

        return BackupCreateResult(
            backup_path=str(backup_root),
            manifest_path=str(manifest_path),
            archive_path=archive_path,
            files_backed_up=files_backed_up,
            database_dumped=database_dumped,
            dry_run=False,
            details=details,
        )

    def verify_backup(self, backup_path: Path) -> BackupVerifyResult:
        """Verify a backup directory or zip archive against its manifest."""

        with self._prepare_backup_root(backup_path) as root:
            manifest_path = self._find_manifest(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            result = BackupVerifyResult(
                backup_path=str(backup_path.expanduser().resolve()),
                manifest_path=str(manifest_path),
            )
            file_entries: list[dict[str, object]] = list(manifest.get("files", []))
            database_entry = manifest.get("database")
            if database_entry:
                file_entries.append(
                    {
                        "path": database_entry.get("dump_file"),
                        "sha256": database_entry.get("sha256"),
                        "size_bytes": database_entry.get("size_bytes"),
                    }
                )

            result.total_files = len(file_entries)
            for entry in file_entries:
                relative_path = entry.get("path")
                if not relative_path:
                    continue
                candidate = root / str(relative_path)
                if not candidate.exists():
                    result.missing += 1
                    result.details.append(f"Missing file: {relative_path}")
                    continue
                expected_size = int(entry.get("size_bytes", 0))
                actual_size = candidate.stat().st_size
                size_ok = True
                if expected_size and actual_size != expected_size:
                    result.size_failed += 1
                    result.details.append(f"Size mismatch: {relative_path}")
                    size_ok = False
                expected_hash = str(entry.get("sha256", ""))
                actual_hash = _sha256_file(candidate)
                if expected_hash and expected_hash != actual_hash:
                    result.checksum_failed += 1
                    result.details.append(f"Checksum mismatch: {relative_path}")
                    continue
                if size_ok:
                    result.ok += 1
            return result

    def restore_backup(
        self,
        backup_path: Path,
        apply: bool = False,
        restore_db: bool = False,
        restore_files: bool = False,
        confirm_overwrite_db: bool = False,
        overwrite_files: bool = False,
    ) -> BackupRestoreResult:
        """Preview or apply one backup restore with conflict checks."""

        with self._prepare_backup_root(backup_path) as root:
            manifest_path = self._find_manifest(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files_root = root / "files"
            dump_file = manifest.get("database", {}) or {}
            dump_path = root / str(dump_file.get("dump_file", "db/dailychewer.sql"))
            details: list[str] = []
            result = BackupRestoreResult(
                backup_path=str(backup_path.expanduser().resolve()),
                manifest_path=str(manifest_path),
                dry_run=not apply,
            )

            effective_restore_files = restore_files or (not restore_db and not restore_files)
            effective_restore_db = restore_db or (not restore_db and not restore_files)

            file_conflicts, file_same, files_to_restore = self._plan_file_restore(files_root if files_root.exists() else None)
            result.file_conflicts = file_conflicts
            result.files_same = file_same
            if files_to_restore:
                details.append(f"Files to restore: {len(files_to_restore)}")
            if file_same:
                details.append(f"Files already identical: {file_same}")
            if file_conflicts:
                details.append(f"File conflicts detected: {file_conflicts}")

            database_conflicts = self._database_conflict_count() if effective_restore_db else 0
            result.database_conflicts = database_conflicts
            if effective_restore_db and database_conflicts:
                details.append(f"Database contains existing records in protected tables: {database_conflicts}")

            if not apply:
                result.details = details
                return result

            if effective_restore_files and file_conflicts and not overwrite_files:
                raise ValueError("File conflicts detected. Re-run with --overwrite-files to replace different files.")
            if effective_restore_db and database_conflicts and not confirm_overwrite_db:
                raise ValueError("Database contains existing data. Re-run with --confirm-overwrite-db to restore the database dump.")

            if effective_restore_files:
                result.files_restored = self._restore_files(files_to_restore, overwrite_files=overwrite_files)
                if not files_root.exists():
                    details.append("No backed up files directory found.")

            if effective_restore_db:
                if not dump_path.exists():
                    details.append("No database dump found; database restore skipped.")
                elif not self.settings.database_url:
                    details.append("DATABASE_URL not configured; database restore skipped.")
                else:
                    try:
                        subprocess.run(
                            ["psql", _plain_database_url(self.settings.database_url), "-f", str(dump_path)],
                            check=True,
                            cwd=self.settings.project_root,
                        )
                        result.database_restored = True
                    except FileNotFoundError:
                        details.append("psql not found; database restore skipped.")
                    except subprocess.CalledProcessError as exc:
                        details.append(f"psql restore failed: {exc}")

            result.dry_run = False
            result.details = details
            return result

    def _manifest_source(self) -> dict[str, str | None]:
        """Build the non-sensitive source section for the backup manifest."""

        parsed = urlsplit(self.settings.database_url) if self.settings.database_url else None
        database_name = parsed.path.lstrip("/") if parsed else None
        return {
            "data_dir": self._safe_relative(self.settings.data_dir),
            "database_url_host": parsed.hostname if parsed else None,
            "database_name": database_name or None,
        }

    def _collect_manifest_files(self, files_root: Path, backup_root: Path) -> list[dict[str, object]]:
        """Collect file metadata for the manifest from the copied files tree."""

        entries: list[dict[str, object]] = []
        for file_path in sorted(path for path in files_root.rglob("*") if path.is_file()):
            entries.append(
                {
                    "path": str(file_path.relative_to(backup_root)),
                    "sha256": _sha256_file(file_path),
                    "size_bytes": file_path.stat().st_size,
                }
            )
        return entries

    def _zip_backup_directory(self, backup_root: Path) -> str:
        """Create a zip archive alongside the backup directory."""

        archive_path = backup_root.with_suffix(".zip")
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(path for path in backup_root.rglob("*") if path.is_file()):
                zf.write(file_path, file_path.relative_to(backup_root))
        return str(archive_path)

    def _prepare_backup_root(self, backup_path: Path):
        """Return a context manager yielding a usable backup root for dirs or zip archives."""

        class _PreparedBackup:
            def __init__(self, path: Path, service: BackupService):
                self.path = path.expanduser().resolve()
                self.service = service
                self.temp_dir: tempfile.TemporaryDirectory[str] | None = None
                self.root: Path | None = None

            def __enter__(self) -> Path:
                if self.path.is_dir():
                    self.root = self.path
                    return self.root
                if self.path.is_file() and self.path.suffix.lower() == ".zip":
                    self.temp_dir = tempfile.TemporaryDirectory()
                    with zipfile.ZipFile(self.path, "r") as zf:
                        zf.extractall(self.temp_dir.name)
                    self.root = Path(self.temp_dir.name)
                    return self.root
                raise ValueError("Backup path must be a directory or .zip file.")

            def __exit__(self, exc_type, exc, tb) -> None:
                if self.temp_dir is not None:
                    self.temp_dir.cleanup()

        return _PreparedBackup(backup_path, self)

    def _find_manifest(self, root: Path) -> Path:
        """Locate the preferred backup manifest inside the prepared backup root."""

        for name in [self.MANIFEST_NAME, "manifest.json"]:
            candidate = root / name
            if candidate.exists():
                return candidate
        raise ValueError("Backup manifest not found.")

    def _plan_file_restore(self, files_root: Path | None) -> tuple[int, int, list[tuple[Path, Path, bool]]]:
        """Return conflict counts and planned file restore operations."""

        if files_root is None or not files_root.exists():
            return 0, 0, []
        conflicts = 0
        same = 0
        plans: list[tuple[Path, Path, bool]] = []
        for source in sorted(path for path in files_root.rglob("*") if path.is_file()):
            relative = source.relative_to(files_root)
            target = self.settings.data_dir / relative
            should_copy = True
            if target.exists():
                if _sha256_file(source) == _sha256_file(target):
                    same += 1
                    should_copy = False
                else:
                    conflicts += 1
            plans.append((source, target, should_copy))
        return conflicts, same, plans

    def _database_conflict_count(self) -> int:
        """Count protected tables that currently contain rows."""

        if not self.settings.database_url:
            return 0
        engine = get_engine(self.settings.database_url)
        conflict_tables = ["users", "daily_reports", "weekly_reports", "monthly_reports"]
        count = 0
        with engine.begin() as connection:
            for table_name in conflict_tables:
                try:
                    rows = connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
                except Exception:
                    continue
                if rows:
                    count += 1
        return count

    def _restore_files(self, plans: list[tuple[Path, Path, bool]], overwrite_files: bool) -> bool:
        """Restore planned files into the active data directory."""

        restored = False
        for source, target, should_copy in plans:
            if target.exists() and not should_copy and not overwrite_files:
                continue
            if target.exists() and not overwrite_files and _sha256_file(source) != _sha256_file(target):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored = True
        return restored

    def _safe_relative(self, path: Path) -> str:
        """Return a project-relative path when possible."""

        try:
            return str(path.relative_to(self.settings.project_root))
        except ValueError:
            return str(path)
