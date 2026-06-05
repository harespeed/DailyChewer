"""Minimal PostgreSQL smoke test for DailyChewer multi-user isolation."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
for extra_path in (PROJECT_ROOT, PROJECT_ROOT / "backend", PROJECT_ROOT / "cli"):
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))

from dailychewer_backend.auth.security import hash_password
from dailychewer_backend.config import load_settings
from dailychewer_backend.db.models import Base, DailyReportRecord, User
from dailychewer_backend.db.repositories import DailyReportRepository, UserRepository
from dailychewer_backend.db.session import get_engine, get_session_maker
from dailychewer_backend.models import UserContext
from dailychewer_backend.services.search_service import SearchService
from sqlalchemy import delete


def main() -> int:
    settings = load_settings(project_root=PROJECT_ROOT)
    if not settings.database_url:
        print("DATABASE_URL is not configured. Skipping PostgreSQL smoke test.")
        return 2

    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = get_session_maker(settings)
    user_a = None
    user_b = None
    try:
        with session_factory() as session:
            users = UserRepository(session)
            user_a = users.get_by_username("smoke_user_a")
            if user_a is None:
                user_a = users.create_user("smoke_user_a", hash_password("password123"), "Smoke User A")
            user_b = users.get_by_username("smoke_user_b")
            if user_b is None:
                user_b = users.create_user("smoke_user_b", hash_password("password123"), "Smoke User B")

            daily_repo = DailyReportRepository(session)
            for user, marker in ((user_a, "alpha"), (user_b, "beta")):
                if not daily_repo.find_by_date_project(user.id, date(2026, 6, 3), None):
                    daily_repo.create_daily_report(
                        user_id=user.id,
                        report_date=date(2026, 6, 3),
                        weekday="Wednesday",
                        iso_week="2026-W23",
                        project_id=None,
                        source_format="markdown",
                        raw_file_path=f"data/users/{user.id}/raw/{marker}.md",
                        optimized_file_path=f"data/users/{user.id}/optimized/{marker}.md",
                        quality_score_total=10,
                        daily_report_json={
                            "date": "2026-06-03",
                            "weekday": "Wednesday",
                            "week": "2026-W23",
                            "morning": {"work_content": [marker], "personal_growth": [], "problems": [], "solutions": []},
                            "afternoon": {"work_content": [f"{marker}-pm"], "personal_growth": [], "problems": [f"{marker}-problem"], "solutions": []},
                            "questions": [],
                        },
                        tags=[],
                    )

        search_a = SearchService(
            project_root=PROJECT_ROOT,
            user_context=UserContext(user_id=user_a.id, username=user_a.username, storage_mode="database"),
        )
        search_b = SearchService(
            project_root=PROJECT_ROOT,
            user_context=UserContext(user_id=user_b.id, username=user_b.username, storage_mode="database"),
        )
        reports_a = search_a.list_reports()
        reports_b = search_b.list_reports()
        if any(item.project == "beta" or "beta" in item.optimized_file for item in reports_a):
            print("Isolation failed: user A can see user B report metadata.")
            return 3
        if any(item.project == "alpha" or "alpha" in item.optimized_file for item in reports_b):
            print("Isolation failed: user B can see user A report metadata.")
            return 4
        if search_a.search_reports("beta") or search_b.search_reports("alpha"):
            print("Isolation failed: cross-user search results leaked.")
            return 5
        print("PASS")
        return 0
    finally:
        if user_a and user_b:
            with session_factory() as session:
                session.execute(delete(DailyReportRecord).where(DailyReportRecord.user_id.in_([user_a.id, user_b.id])))
                session.execute(delete(User).where(User.id.in_([user_a.id, user_b.id])))
                session.commit()


if __name__ == "__main__":
    raise SystemExit(main())
