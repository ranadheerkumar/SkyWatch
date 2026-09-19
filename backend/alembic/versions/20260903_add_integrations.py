"""add Jira and qTest integration profiles and external issue links

Revision ID: 20260903_integrations
Revises: 20260902_required_columns
"""

from alembic import op
import sqlalchemy as sa


revision = "20260903_integrations"
down_revision = "20260902_required_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("system", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("project_key", sa.String(length=120), nullable=True),
        sa.Column("project_name", sa.String(length=200), nullable=True),
        sa.Column("project_id", sa.String(length=120), nullable=True),
        sa.Column("username", sa.String(length=320), nullable=True),
        sa.Column("auth_type", sa.String(length=40), nullable=False, server_default="api_token"),
        sa.Column("environment", sa.String(length=120), nullable=True),
        sa.Column("secret_ref", sa.String(length=160), nullable=True),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="untested"),
        sa.Column("last_test_status", sa.String(length=20), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("last_test_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_metadata", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("created_by", "system", "name", name="uq_integration_connection_owner_system_name"),
    )
    op.create_index("ix_integration_connections_system", "integration_connections", ["system"])
    op.create_index("ix_integration_connections_status", "integration_connections", ["status"])
    op.create_index("ix_integration_connections_created_by", "integration_connections", ["created_by"])

    op.create_table(
        "external_issue_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("defect_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("test_case_id", sa.Integer(), nullable=True),
        sa.Column("system", sa.String(length=20), nullable=False),
        sa.Column("external_key", sa.String(length=120), nullable=False),
        sa.Column("external_url", sa.String(length=2048), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["integration_connections.id"]),
        sa.ForeignKeyConstraint(["defect_id"], ["defects.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["test_runs.id"]),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("connection_id", "idempotency_key", name="uq_external_issue_link_connection_idempotency"),
    )
    op.create_index("ix_external_issue_links_connection_id", "external_issue_links", ["connection_id"])
    op.create_index("ix_external_issue_links_defect_id", "external_issue_links", ["defect_id"])
    op.create_index("ix_external_issue_links_run_id", "external_issue_links", ["run_id"])
    op.create_index("ix_external_issue_links_test_case_id", "external_issue_links", ["test_case_id"])
    op.create_index("ix_external_issue_links_system", "external_issue_links", ["system"])
    op.create_index("ix_external_issue_links_created_by", "external_issue_links", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_external_issue_links_created_by", table_name="external_issue_links")
    op.drop_index("ix_external_issue_links_system", table_name="external_issue_links")
    op.drop_index("ix_external_issue_links_test_case_id", table_name="external_issue_links")
    op.drop_index("ix_external_issue_links_run_id", table_name="external_issue_links")
    op.drop_index("ix_external_issue_links_defect_id", table_name="external_issue_links")
    op.drop_index("ix_external_issue_links_connection_id", table_name="external_issue_links")
    op.drop_table("external_issue_links")
    op.drop_index("ix_integration_connections_created_by", table_name="integration_connections")
    op.drop_index("ix_integration_connections_status", table_name="integration_connections")
    op.drop_index("ix_integration_connections_system", table_name="integration_connections")
    op.drop_table("integration_connections")