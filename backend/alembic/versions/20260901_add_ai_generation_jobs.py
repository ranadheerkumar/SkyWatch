"""add durable AI generation jobs

Revision ID: 20260901_ai_jobs
Revises: 20260902_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "20260901_ai_jobs"
down_revision = "20260902_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_generation_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("phase", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("generated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_generation_jobs_application_id", "ai_generation_jobs", ["application_id"])
    op.create_index("ix_ai_generation_jobs_created_by", "ai_generation_jobs", ["created_by"])
    op.create_index("ix_ai_generation_jobs_status", "ai_generation_jobs", ["status"])
    op.create_index("ix_ai_generation_jobs_correlation_id", "ai_generation_jobs", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_generation_jobs_correlation_id", table_name="ai_generation_jobs")
    op.drop_index("ix_ai_generation_jobs_status", table_name="ai_generation_jobs")
    op.drop_index("ix_ai_generation_jobs_created_by", table_name="ai_generation_jobs")
    op.drop_index("ix_ai_generation_jobs_application_id", table_name="ai_generation_jobs")
    op.drop_table("ai_generation_jobs")
