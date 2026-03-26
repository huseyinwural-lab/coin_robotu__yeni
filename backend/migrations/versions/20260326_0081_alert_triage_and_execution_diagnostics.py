"""alert triage and execution diagnostics

Revision ID: 20260326_0081
Revises: 20260326_0080
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0081"
down_revision = "20260326_0080"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "system_alerts"):
        additions = [
            ("acknowledged_by", sa.Column("acknowledged_by", sa.String(length=120), nullable=True)),
            ("acknowledged_at", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True)),
            ("resolved_by", sa.Column("resolved_by", sa.String(length=120), nullable=True)),
            ("resolved_at", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)),
            ("mute_until", sa.Column("mute_until", sa.DateTime(timezone=True), nullable=True)),
            ("operator_note", sa.Column("operator_note", sa.Text(), nullable=True)),
        ]
        for name, column in additions:
            if not _has_column(bind, "system_alerts", name):
                op.add_column("system_alerts", column)

    if not _has_table(bind, "alert_triage_actions"):
        op.create_table(
            "alert_triage_actions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("alert_id", sa.String(), sa.ForeignKey("system_alerts.id"), nullable=False),
            sa.Column("action_type", sa.String(length=40), nullable=False),
            sa.Column("actor_user_id", sa.String(length=120), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("mute_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_alert_triage_actions_alert_id", "alert_triage_actions", ["alert_id"])
        op.create_index("ix_alert_triage_actions_action_type", "alert_triage_actions", ["action_type"])
        op.create_index("ix_alert_triage_actions_actor_user_id", "alert_triage_actions", ["actor_user_id"])

    if _has_table(bind, "execution_jobs"):
        diagnostics = [
            ("queue_wait_ms", sa.Column("queue_wait_ms", sa.Integer(), nullable=True)),
            ("execution_ms", sa.Column("execution_ms", sa.Integer(), nullable=True)),
            ("total_ms", sa.Column("total_ms", sa.Integer(), nullable=True)),
            ("failure_class", sa.Column("failure_class", sa.String(length=80), nullable=True)),
        ]
        for name, column in diagnostics:
            if not _has_column(bind, "execution_jobs", name):
                op.add_column("execution_jobs", column)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "alert_triage_actions"):
        op.drop_table("alert_triage_actions")
