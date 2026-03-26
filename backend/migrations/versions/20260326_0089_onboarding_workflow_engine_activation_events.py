"""onboarding workflow engine and activation events

Revision ID: 20260326_0089
Revises: 20260326_0088
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0089"
down_revision = "20260326_0088"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "user_onboarding_workflow_cases"):
        op.create_table(
            "user_onboarding_workflow_cases",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, unique=True),
            sa.Column("workflow_status", sa.String(length=30), nullable=False, server_default="active"),
            sa.Column("current_step", sa.String(length=20), nullable=False, server_default="ops"),
            sa.Column("assigned_admin_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("priority_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("escalation_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("supervisor_queue", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_onboarding_workflow_cases_status", "user_onboarding_workflow_cases", ["workflow_status"], unique=False)
        op.create_index("ix_onboarding_workflow_cases_step", "user_onboarding_workflow_cases", ["current_step"], unique=False)
        op.create_index("ix_onboarding_workflow_cases_assignee", "user_onboarding_workflow_cases", ["assigned_admin_id"], unique=False)

    if not _has_table(bind, "user_onboarding_workflow_step_logs"):
        op.create_table(
            "user_onboarding_workflow_step_logs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("workflow_case_id", sa.String(), sa.ForeignKey("user_onboarding_workflow_cases.id"), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("step_name", sa.String(length=20), nullable=False),
            sa.Column("step_status", sa.String(length=20), nullable=False, server_default="completed"),
            sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_onboarding_workflow_step_logs_case", "user_onboarding_workflow_step_logs", ["workflow_case_id"], unique=False)
        op.create_index("ix_onboarding_workflow_step_logs_user", "user_onboarding_workflow_step_logs", ["user_id"], unique=False)

    if not _has_table(bind, "user_activation_events"):
        op.create_table(
            "user_activation_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_user_activation_events_user", "user_activation_events", ["user_id"], unique=False)
        op.create_index("ix_user_activation_events_type", "user_activation_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_activation_events_type", table_name="user_activation_events")
    op.drop_index("ix_user_activation_events_user", table_name="user_activation_events")
    op.drop_table("user_activation_events")

    op.drop_index("ix_onboarding_workflow_step_logs_user", table_name="user_onboarding_workflow_step_logs")
    op.drop_index("ix_onboarding_workflow_step_logs_case", table_name="user_onboarding_workflow_step_logs")
    op.drop_table("user_onboarding_workflow_step_logs")

    op.drop_index("ix_onboarding_workflow_cases_assignee", table_name="user_onboarding_workflow_cases")
    op.drop_index("ix_onboarding_workflow_cases_step", table_name="user_onboarding_workflow_cases")
    op.drop_index("ix_onboarding_workflow_cases_status", table_name="user_onboarding_workflow_cases")
    op.drop_table("user_onboarding_workflow_cases")
