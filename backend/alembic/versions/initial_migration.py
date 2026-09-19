"""create the initial application schema

Revision ID: 20260902_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.create_table(
		"users",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("email", sa.String(length=320), nullable=False),
		sa.Column("password_hash", sa.String(length=512), nullable=False),
		sa.Column("role", sa.String(length=20), nullable=False, server_default="tester"),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
	)
	op.create_index("ix_users_email", "users", ["email"], unique=True)
	op.create_index("ix_users_role", "users", ["role"], unique=False)

	op.create_table(
		"applications",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("name", sa.String(length=120), nullable=False),
		sa.Column("platform", sa.String(length=20), nullable=False),
		sa.Column("target", sa.String(length=2048), nullable=False),
		sa.Column("created_by", sa.Integer(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
	)
	op.create_index("ix_applications_name", "applications", ["name"], unique=False)
	op.create_index("ix_applications_created_by", "applications", ["created_by"], unique=False)

	op.create_table(
		"projects",
		sa.Column("id", sa.String(length=80), primary_key=True),
		sa.Column("name", sa.String(length=200), nullable=False),
		sa.Column("description", sa.Text(), nullable=False, server_default=""),
		sa.Column("lifecycle", sa.String(length=20), nullable=False, server_default="active"),
		sa.Column("owner", sa.String(length=120), nullable=False, server_default="Admin QA"),
		sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_projects_name", "projects", ["name"], unique=False)
	op.create_index("ix_projects_lifecycle", "projects", ["lifecycle"], unique=False)
	op.create_index("ix_projects_created_by", "projects", ["created_by"], unique=False)

	op.create_table(
		"test_cases",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=False),
		sa.Column("title", sa.String(length=200), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("preconditions", sa.Text(), nullable=True),
		sa.Column("steps", sa.Text(), nullable=False, server_default=""),
		sa.Column("expected_result", sa.Text(), nullable=True),
		sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
		sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
		sa.Column("category", sa.String(length=40), nullable=False, server_default="positive"),
		sa.Column("tags", sa.JSON(), nullable=False),
		sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
		sa.Column("automation_status", sa.String(length=40), nullable=False, server_default="automated"),
		sa.Column("test_data", sa.JSON(), nullable=True),
		sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_test_cases_application_id", "test_cases", ["application_id"], unique=False)
	op.create_index("ix_test_cases_title", "test_cases", ["title"], unique=False)
	op.create_index("ix_test_cases_status", "test_cases", ["status"], unique=False)
	op.create_index("ix_test_cases_priority", "test_cases", ["priority"], unique=False)
	op.create_index("ix_test_cases_category", "test_cases", ["category"], unique=False)
	op.create_index("ix_test_cases_automation_status", "test_cases", ["automation_status"], unique=False)
	op.create_index("ix_test_cases_created_by", "test_cases", ["created_by"], unique=False)

	op.create_table(
		"test_case_automations",
		sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id"), primary_key=True),
		sa.Column("steps", sa.JSON(), nullable=False),
		sa.Column("checks", sa.JSON(), nullable=False),
		sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
	)
	op.create_index("ix_test_case_automations_updated_by", "test_case_automations", ["updated_by"], unique=False)

	op.create_table(
		"test_suites",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=False),
		sa.Column("name", sa.String(length=160), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("case_ids", sa.JSON(), nullable=False),
		sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_test_suites_application_id", "test_suites", ["application_id"], unique=False)
	op.create_index("ix_test_suites_name", "test_suites", ["name"], unique=False)
	op.create_index("ix_test_suites_created_by", "test_suites", ["created_by"], unique=False)

	op.create_table(
		"test_datasets",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=False),
		sa.Column("name", sa.String(length=200), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("data_rows", sa.JSON(), nullable=False),
		sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_test_datasets_application_id", "test_datasets", ["application_id"], unique=False)
	op.create_index("ix_test_datasets_name", "test_datasets", ["name"], unique=False)
	op.create_index("ix_test_datasets_created_by", "test_datasets", ["created_by"], unique=False)

	op.create_table(
		"execution_plans",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=False),
		sa.Column("name", sa.String(length=200), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("target_type", sa.String(length=40), nullable=False, server_default="web"),
		sa.Column("case_ids", sa.JSON(), nullable=False),
		sa.Column("suite_ids", sa.JSON(), nullable=False),
		sa.Column("execution_mode", sa.String(length=40), nullable=False, server_default="watch_live"),
		sa.Column("schedule_cron", sa.String(length=100), nullable=True),
		sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
		sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_execution_plans_application_id", "execution_plans", ["application_id"], unique=False)
	op.create_index("ix_execution_plans_name", "execution_plans", ["name"], unique=False)
	op.create_index("ix_execution_plans_target_type", "execution_plans", ["target_type"], unique=False)
	op.create_index("ix_execution_plans_status", "execution_plans", ["status"], unique=False)
	op.create_index("ix_execution_plans_created_by", "execution_plans", ["created_by"], unique=False)

	op.create_table(
		"test_runs",
		sa.Column("id", sa.String(length=32), primary_key=True),
		sa.Column("application_id", sa.Integer(), nullable=False),
		sa.Column("created_by", sa.Integer(), nullable=False),
		sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
		sa.Column("steps", sa.JSON(), nullable=False),
		sa.Column("result", sa.JSON(), nullable=True),
		sa.Column("log", sa.Text(), nullable=False, server_default=""),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_test_runs_application_id", "test_runs", ["application_id"], unique=False)
	op.create_index("ix_test_runs_created_by", "test_runs", ["created_by"], unique=False)
	op.create_index("ix_test_runs_status", "test_runs", ["status"], unique=False)

	op.create_table(
		"case_executions",
		sa.Column("run_id", sa.String(length=32), sa.ForeignKey("test_runs.id"), primary_key=True),
		sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id"), nullable=False),
		sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_case_executions_test_case_id", "case_executions", ["test_case_id"], unique=False)
	op.create_index("ix_case_executions_status", "case_executions", ["status"], unique=False)

	op.create_table(
		"defects",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("title", sa.String(length=200), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
		sa.Column("severity", sa.String(length=20), nullable=False, server_default="major"),
		sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
		sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=True),
		sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_defects_title", "defects", ["title"], unique=False)
	op.create_index("ix_defects_status", "defects", ["status"], unique=False)
	op.create_index("ix_defects_application_id", "defects", ["application_id"], unique=False)
	op.create_index("ix_defects_created_by", "defects", ["created_by"], unique=False)

	op.create_table(
		"audit_logs",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("action", sa.String(length=120), nullable=False),
		sa.Column("resource_type", sa.String(length=80), nullable=False),
		sa.Column("resource_id", sa.String(length=120), nullable=True),
		sa.Column("old_value", sa.JSON(), nullable=True),
		sa.Column("new_value", sa.JSON(), nullable=True),
		sa.Column("ai_recommendation_id", sa.Integer(), nullable=True),
		sa.Column("approval_status", sa.String(length=40), nullable=True),
		sa.Column("metadata_json", sa.JSON(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
	)
	op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)
	op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
	op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"], unique=False)
	op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"], unique=False)
	op.create_index("ix_audit_logs_ai_recommendation_id", "audit_logs", ["ai_recommendation_id"], unique=False)
	op.create_index("ix_audit_logs_approval_status", "audit_logs", ["approval_status"], unique=False)
	op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)

	op.create_table(
		"agent_recommendations",
		sa.Column("id", sa.Integer(), primary_key=True),
		sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=False),
		sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id"), nullable=True),
		sa.Column("recommendation_type", sa.String(length=80), nullable=False),
		sa.Column("title", sa.String(length=200), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("proposed_steps", sa.JSON(), nullable=True),
		sa.Column("proposed_checks", sa.JSON(), nullable=True),
		sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
		sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
		sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_agent_recommendations_application_id", "agent_recommendations", ["application_id"], unique=False)
	op.create_index("ix_agent_recommendations_test_case_id", "agent_recommendations", ["test_case_id"], unique=False)
	op.create_index("ix_agent_recommendations_recommendation_type", "agent_recommendations", ["recommendation_type"], unique=False)
	op.create_index("ix_agent_recommendations_status", "agent_recommendations", ["status"], unique=False)
	op.create_index("ix_agent_recommendations_created_by", "agent_recommendations", ["created_by"], unique=False)


def downgrade() -> None:
	op.drop_index("ix_agent_recommendations_created_by", table_name="agent_recommendations")
	op.drop_index("ix_agent_recommendations_status", table_name="agent_recommendations")
	op.drop_index("ix_agent_recommendations_recommendation_type", table_name="agent_recommendations")
	op.drop_index("ix_agent_recommendations_test_case_id", table_name="agent_recommendations")
	op.drop_index("ix_agent_recommendations_application_id", table_name="agent_recommendations")
	op.drop_table("agent_recommendations")
	op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
	op.drop_index("ix_audit_logs_approval_status", table_name="audit_logs")
	op.drop_index("ix_audit_logs_ai_recommendation_id", table_name="audit_logs")
	op.drop_index("ix_audit_logs_resource_id", table_name="audit_logs")
	op.drop_index("ix_audit_logs_resource_type", table_name="audit_logs")
	op.drop_index("ix_audit_logs_action", table_name="audit_logs")
	op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
	op.drop_table("audit_logs")
	op.drop_index("ix_defects_created_by", table_name="defects")
	op.drop_index("ix_defects_application_id", table_name="defects")
	op.drop_index("ix_defects_status", table_name="defects")
	op.drop_index("ix_defects_title", table_name="defects")
	op.drop_table("defects")
	op.drop_index("ix_case_executions_status", table_name="case_executions")
	op.drop_index("ix_case_executions_test_case_id", table_name="case_executions")
	op.drop_table("case_executions")
	op.drop_index("ix_test_runs_status", table_name="test_runs")
	op.drop_index("ix_test_runs_created_by", table_name="test_runs")
	op.drop_index("ix_test_runs_application_id", table_name="test_runs")
	op.drop_table("test_runs")
	op.drop_index("ix_execution_plans_created_by", table_name="execution_plans")
	op.drop_index("ix_execution_plans_status", table_name="execution_plans")
	op.drop_index("ix_execution_plans_target_type", table_name="execution_plans")
	op.drop_index("ix_execution_plans_name", table_name="execution_plans")
	op.drop_index("ix_execution_plans_application_id", table_name="execution_plans")
	op.drop_table("execution_plans")
	op.drop_index("ix_test_datasets_created_by", table_name="test_datasets")
	op.drop_index("ix_test_datasets_name", table_name="test_datasets")
	op.drop_index("ix_test_datasets_application_id", table_name="test_datasets")
	op.drop_table("test_datasets")
	op.drop_index("ix_test_suites_created_by", table_name="test_suites")
	op.drop_index("ix_test_suites_name", table_name="test_suites")
	op.drop_index("ix_test_suites_application_id", table_name="test_suites")
	op.drop_table("test_suites")
	op.drop_index("ix_test_case_automations_updated_by", table_name="test_case_automations")
	op.drop_table("test_case_automations")
	op.drop_index("ix_test_cases_created_by", table_name="test_cases")
	op.drop_index("ix_test_cases_automation_status", table_name="test_cases")
	op.drop_index("ix_test_cases_category", table_name="test_cases")
	op.drop_index("ix_test_cases_priority", table_name="test_cases")
	op.drop_index("ix_test_cases_status", table_name="test_cases")
	op.drop_index("ix_test_cases_title", table_name="test_cases")
	op.drop_index("ix_test_cases_application_id", table_name="test_cases")
	op.drop_table("test_cases")
	op.drop_index("ix_projects_created_by", table_name="projects")
	op.drop_index("ix_projects_lifecycle", table_name="projects")
	op.drop_index("ix_projects_name", table_name="projects")
	op.drop_table("projects")
	op.drop_index("ix_applications_created_by", table_name="applications")
	op.drop_index("ix_applications_name", table_name="applications")
	op.drop_table("applications")
	op.drop_index("ix_users_role", table_name="users")
	op.drop_index("ix_users_email", table_name="users")
	op.drop_table("users")
