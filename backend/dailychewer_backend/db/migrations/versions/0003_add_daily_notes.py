"""add daily notes"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_add_daily_notes"
down_revision = "0002_add_ingest_optimize_tasks"
branch_labels = None
depends_on = None


def _uuid_type():
    return postgresql.UUID(as_uuid=False)


def upgrade():
    op.create_table(
        "daily_notes",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note_date", sa.Date(), nullable=False),
        sa.Column("weekday", sa.String(length=30), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("detail_level", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_daily_notes_user_id", "daily_notes", ["user_id"])
    op.create_index("ix_daily_notes_note_date", "daily_notes", ["note_date"])


def downgrade():
    op.drop_index("ix_daily_notes_note_date", table_name="daily_notes")
    op.drop_index("ix_daily_notes_user_id", table_name="daily_notes")
    op.drop_table("daily_notes")
