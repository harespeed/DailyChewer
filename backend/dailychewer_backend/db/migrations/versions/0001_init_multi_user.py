"""initial multi-user schema"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_init_multi_user"
down_revision = None
branch_labels = None
depends_on = None


def _json_type():
    return postgresql.JSONB(astext_type=sa.Text())


def _uuid_type():
    return postgresql.UUID(as_uuid=False)


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_projects_user_name"),
    )

    op.create_table(
        "tags",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )

    op.create_table(
        "daily_reports",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("weekday", sa.String(length=30), nullable=False),
        sa.Column("iso_week", sa.String(length=20), nullable=False),
        sa.Column("project_id", _uuid_type(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_format", sa.String(length=30), nullable=False),
        sa.Column("raw_file_path", sa.Text(), nullable=False),
        sa.Column("optimized_file_path", sa.Text(), nullable=False),
        sa.Column("quality_score_total", sa.Integer(), nullable=True),
        sa.Column("daily_report_json", _json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_daily_reports_user_id", "daily_reports", ["user_id"])
    op.create_index("ix_daily_reports_date", "daily_reports", ["date"])
    op.create_index("ix_daily_reports_iso_week", "daily_reports", ["iso_week"])

    op.create_table(
        "daily_report_tags",
        sa.Column("daily_report_id", _uuid_type(), sa.ForeignKey("daily_reports.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", _uuid_type(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "weekly_reports",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iso_week", sa.String(length=50), nullable=True),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("project_id", _uuid_type(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("format", sa.String(length=30), nullable=False),
        sa.Column("style", sa.String(length=30), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("report_json", _json_type(), nullable=True),
        sa.Column("preview_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_weekly_reports_user_id", "weekly_reports", ["user_id"])
    op.create_index("ix_weekly_reports_iso_week", "weekly_reports", ["iso_week"])

    op.create_table(
        "weekly_report_tags",
        sa.Column("weekly_report_id", _uuid_type(), sa.ForeignKey("weekly_reports.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", _uuid_type(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "monthly_reports",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.String(length=20), nullable=False),
        sa.Column("project_id", _uuid_type(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("format", sa.String(length=30), nullable=False),
        sa.Column("style", sa.String(length=30), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("report_json", _json_type(), nullable=True),
        sa.Column("preview_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_monthly_reports_user_id", "monthly_reports", ["user_id"])
    op.create_index("ix_monthly_reports_month", "monthly_reports", ["month"])

    op.create_table(
        "monthly_report_tags",
        sa.Column("monthly_report_id", _uuid_type(), sa.ForeignKey("monthly_reports.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", _uuid_type(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "uploaded_files",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_file_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_uploaded_files_user_id", "uploaded_files", ["user_id"])
    op.create_index("ix_uploaded_files_purpose", "uploaded_files", ["purpose"])


def downgrade():
    op.drop_index("ix_uploaded_files_purpose", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_user_id", table_name="uploaded_files")
    op.drop_table("uploaded_files")
    op.drop_table("monthly_report_tags")
    op.drop_index("ix_monthly_reports_month", table_name="monthly_reports")
    op.drop_index("ix_monthly_reports_user_id", table_name="monthly_reports")
    op.drop_table("monthly_reports")
    op.drop_table("weekly_report_tags")
    op.drop_index("ix_weekly_reports_iso_week", table_name="weekly_reports")
    op.drop_index("ix_weekly_reports_user_id", table_name="weekly_reports")
    op.drop_table("weekly_reports")
    op.drop_table("daily_report_tags")
    op.drop_index("ix_daily_reports_iso_week", table_name="daily_reports")
    op.drop_index("ix_daily_reports_date", table_name="daily_reports")
    op.drop_index("ix_daily_reports_user_id", table_name="daily_reports")
    op.drop_table("daily_reports")
    op.drop_table("tags")
    op.drop_table("projects")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
