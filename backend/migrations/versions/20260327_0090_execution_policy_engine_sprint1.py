"""execution policy engine sprint1 tables and columns

Revision ID: 20260327_0090
Revises: 20260326_0089
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0090"
down_revision = "20260326_0089"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def _has_index(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx.get("name") == index_name for idx in indexes)


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "execution_policies"):
        if not _has_column(bind, "execution_policies", "policy_scope"):
            op.add_column("execution_policies", sa.Column("policy_scope", sa.String(length=30), nullable=False, server_default="strategy"))
        if not _has_column(bind, "execution_policies", "scope_key"):
            op.add_column("execution_policies", sa.Column("scope_key", sa.String(length=120), nullable=False, server_default="default"))
        if not _has_column(bind, "execution_policies", "policy_code"):
            op.add_column("execution_policies", sa.Column("policy_code", sa.String(length=160), nullable=True))
        if not _has_column(bind, "execution_policies", "priority"):
            op.add_column("execution_policies", sa.Column("priority", sa.Integer(), nullable=False, server_default="100"))
        if not _has_column(bind, "execution_policies", "override_behavior"):
            op.add_column("execution_policies", sa.Column("override_behavior", sa.String(length=20), nullable=False, server_default="merge"))
        if not _has_column(bind, "execution_policies", "conditions_payload"):
            op.add_column("execution_policies", sa.Column("conditions_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        if not _has_column(bind, "execution_policies", "rules_payload"):
            op.add_column("execution_policies", sa.Column("rules_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        if not _has_column(bind, "execution_policies", "enforcement_action"):
            op.add_column("execution_policies", sa.Column("enforcement_action", sa.String(length=20), nullable=False, server_default="BLOCK"))
        if not _has_column(bind, "execution_policies", "severity"):
            op.add_column("execution_policies", sa.Column("severity", sa.String(length=20), nullable=False, server_default="HIGH"))
        if not _has_column(bind, "execution_policies", "description"):
            op.add_column("execution_policies", sa.Column("description", sa.Text(), nullable=True))

        if not _has_index(bind, "execution_policies", "ix_execution_policies_policy_scope"):
            op.create_index("ix_execution_policies_policy_scope", "execution_policies", ["policy_scope"], unique=False)
        if not _has_index(bind, "execution_policies", "ix_execution_policies_scope_key"):
            op.create_index("ix_execution_policies_scope_key", "execution_policies", ["scope_key"], unique=False)
        if not _has_index(bind, "execution_policies", "ix_execution_policies_priority"):
            op.create_index("ix_execution_policies_priority", "execution_policies", ["priority"], unique=False)
        if not _has_index(bind, "execution_policies", "ix_execution_policies_policy_code"):
            op.create_index("ix_execution_policies_policy_code", "execution_policies", ["policy_code"], unique=True)

    if not _has_table(bind, "execution_policy_decision_logs"):
        op.create_table(
            "execution_policy_decision_logs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("pipeline_id", sa.String(length=120), nullable=True),
            sa.Column("lifecycle_action", sa.String(length=20), nullable=False, server_default="preview"),
            sa.Column("stage", sa.String(length=30), nullable=False, server_default="PRE_TRADE"),
            sa.Column("intent_id", sa.String(length=120), nullable=True),
            sa.Column("intent_token", sa.String(length=120), nullable=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("symbol", sa.String(length=30), nullable=True),
            sa.Column("strategy_binding", sa.String(length=120), nullable=True),
            sa.Column("environment", sa.String(length=30), nullable=False, server_default="live"),
            sa.Column("rollout_mode", sa.String(length=20), nullable=False, server_default="shadow"),
            sa.Column("recommended_action", sa.String(length=20), nullable=False, server_default="ALLOW"),
            sa.Column("enforced_action", sa.String(length=20), nullable=False, server_default="ALLOW"),
            sa.Column("reason_code", sa.String(length=120), nullable=True),
            sa.Column("reason_message", sa.Text(), nullable=True),
            sa.Column("policy_id", sa.String(length=120), nullable=True),
            sa.Column("rule_id", sa.String(length=120), nullable=True),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="INFO"),
            sa.Column("action_taken", sa.String(length=80), nullable=False, server_default="ALLOW"),
            sa.Column("is_violation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("trace_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_policy_logs_pipeline", "execution_policy_decision_logs", ["pipeline_id"], unique=False)
        op.create_index("ix_execution_policy_logs_stage", "execution_policy_decision_logs", ["stage"], unique=False)
        op.create_index("ix_execution_policy_logs_lifecycle", "execution_policy_decision_logs", ["lifecycle_action"], unique=False)
        op.create_index("ix_execution_policy_logs_user", "execution_policy_decision_logs", ["user_id"], unique=False)
        op.create_index("ix_execution_policy_logs_intent", "execution_policy_decision_logs", ["intent_id"], unique=False)
        op.create_index("ix_execution_policy_logs_reason", "execution_policy_decision_logs", ["reason_code"], unique=False)
        op.create_index("ix_execution_policy_logs_violation", "execution_policy_decision_logs", ["is_violation"], unique=False)
        op.create_index("ix_execution_policy_logs_created", "execution_policy_decision_logs", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "execution_policy_decision_logs"):
        op.drop_table("execution_policy_decision_logs")
