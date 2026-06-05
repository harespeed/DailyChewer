"""add ingest optimize tasks"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_add_ingest_optimize_tasks"
down_revision = "0001_init_multi_user"
branch_labels = None
depends_on = None


def _json_type():
    return postgresql.JSONB(astext_type=sa.Text())


def _uuid_type():
    return postgresql.UUID(as_uuid=False)


def upgrade():
    op.create_table(
        "ingest_optimize_tasks",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upload_id", sa.String(length=255), nullable=False),
        sa.Column("request_sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("request_payload", _json_type(), nullable=False),
        sa.Column("result_payload", _json_type(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "upload_id", "request_sequence", name="uq_ingest_optimize_tasks_sequence"),
    )
    op.create_index("ix_ingest_optimize_tasks_user_id", "ingest_optimize_tasks", ["user_id"])
    op.create_index("ix_ingest_optimize_tasks_upload_id", "ingest_optimize_tasks", ["upload_id"])
    op.create_index("ix_ingest_optimize_tasks_status", "ingest_optimize_tasks", ["status"])


def downgrade():
    op.drop_index("ix_ingest_optimize_tasks_status", table_name="ingest_optimize_tasks")
    op.drop_index("ix_ingest_optimize_tasks_upload_id", table_name="ingest_optimize_tasks")
    op.drop_index("ix_ingest_optimize_tasks_user_id", table_name="ingest_optimize_tasks")
    op.drop_table("ingest_optimize_tasks")
