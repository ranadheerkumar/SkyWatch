"""add build executions table and batch tracking on test runs

Revision ID: 20260904_build_executions
Revises: 20260903_integrations
"""

from alembic import op
import sqlalchemy as sa


revision = "20260904_build_executions"
down_revision = "20260903_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "build_executions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("trigger_source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("summary_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("ix_build_executions_application_id", "build_executions", ["application_id"])
    op.create_index("ix_build_executions_created_by", "build_executions", ["created_by"])
    op.create_index("ix_build_executions_status", "build_executions", ["status"])

    with op.batch_alter_table("test_runs") as batch_op:
        batch_op.add_column(sa.Column("batch_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("build_name", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("trigger_source", sa.String(length=50), nullable=True, server_default="manual"))
        batch_op.create_index("ix_test_runs_batch_id", ["batch_id"])


def downgrade() -> None:
    with op.batch_alter_table("test_runs") as batch_op:
        batch_op.drop_index("ix_test_runs_batch_id")
        batch_op.drop_column("trigger_source")
        batch_op.drop_column("build_name")
        batch_op.drop_column("batch_id")

    op.drop_index("ix_build_executions_status", table_name="build_executions")
    op.drop_index("ix_build_executions_created_by", table_name="build_executions")
    op.drop_index("ix_build_executions_application_id", table_name="build_executions")
    op.drop_table("build_executions")
