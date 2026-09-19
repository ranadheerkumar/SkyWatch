"""harden required model columns

Revision ID: 20260902_required_columns
Revises: 20260901_ai_jobs
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_required_columns"
down_revision = "20260901_ai_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "role",
            existing_type=sa.String(length=20),
            nullable=False,
            existing_server_default=sa.text("'tester'"),
        )

    with op.batch_alter_table("test_cases") as batch:
        batch.alter_column(
            "priority",
            existing_type=sa.String(length=20),
            nullable=False,
            existing_server_default=sa.text("'medium'"),
        )
        batch.alter_column(
            "category",
            existing_type=sa.String(length=40),
            nullable=False,
            existing_server_default=sa.text("'positive'"),
        )
        batch.alter_column(
            "tags",
            existing_type=sa.JSON(),
            nullable=False,
            existing_server_default=sa.text("'[]'"),
        )
        batch.alter_column(
            "version",
            existing_type=sa.Integer(),
            nullable=False,
            existing_server_default=sa.text("1"),
        )
        batch.alter_column(
            "automation_status",
            existing_type=sa.String(length=40),
            nullable=False,
            existing_server_default=sa.text("'automated'"),
        )


def downgrade() -> None:
    with op.batch_alter_table("test_cases") as batch:
        batch.alter_column(
            "automation_status",
            existing_type=sa.String(length=40),
            nullable=True,
            existing_server_default=sa.text("'automated'"),
        )
        batch.alter_column(
            "version",
            existing_type=sa.Integer(),
            nullable=True,
            existing_server_default=sa.text("1"),
        )
        batch.alter_column(
            "tags",
            existing_type=sa.JSON(),
            nullable=True,
            existing_server_default=sa.text("'[]'"),
        )
        batch.alter_column(
            "category",
            existing_type=sa.String(length=40),
            nullable=True,
            existing_server_default=sa.text("'positive'"),
        )
        batch.alter_column(
            "priority",
            existing_type=sa.String(length=20),
            nullable=True,
            existing_server_default=sa.text("'medium'"),
        )

    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "role",
            existing_type=sa.String(length=20),
            nullable=True,
            existing_server_default=sa.text("'tester'"),
        )
