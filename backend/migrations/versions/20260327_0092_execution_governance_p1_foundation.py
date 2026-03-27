"""execution governance p1 foundation

Revision ID: 20260327_0092
Revises: 20260327_0091
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0092"
down_revision = "20260327_0091"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in sa.inspect(bind).get_columns(table_name))


def _has_index(bind, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "execution_policy_decision_logs"):
        if not _has_column(bind, "execution_policy_decision_logs", "portfolio_id"):
            op.add_column("execution_policy_decision_logs", sa.Column("portfolio_id", sa.String(length=120), nullable=True))
        if not _has_column(bind, "execution_policy_decision_logs", "trace_id"):
            op.add_column("execution_policy_decision_logs", sa.Column("trace_id", sa.String(length=120), nullable=True))
        if not _has_column(bind, "execution_policy_decision_logs", "execution_mode"):
            op.add_column("execution_policy_decision_logs", sa.Column("execution_mode", sa.String(length=20), nullable=False, server_default="SIMULATION"))
        if not _has_column(bind, "execution_policy_decision_logs", "simulation_mode"):
            op.add_column("execution_policy_decision_logs", sa.Column("simulation_mode", sa.Boolean(), nullable=False, server_default=sa.text("true")))
        if not _has_index(bind, "execution_policy_decision_logs", "ix_execution_policy_logs_portfolio_id"):
            op.create_index("ix_execution_policy_logs_portfolio_id", "execution_policy_decision_logs", ["portfolio_id"], unique=False)
        if not _has_index(bind, "execution_policy_decision_logs", "ix_execution_policy_logs_trace_id"):
            op.create_index("ix_execution_policy_logs_trace_id", "execution_policy_decision_logs", ["trace_id"], unique=False)
        if not _has_index(bind, "execution_policy_decision_logs", "ix_execution_policy_logs_execution_mode"):
            op.create_index("ix_execution_policy_logs_execution_mode", "execution_policy_decision_logs", ["execution_mode"], unique=False)
        if not _has_index(bind, "execution_policy_decision_logs", "ix_execution_policy_logs_simulation_mode"):
            op.create_index("ix_execution_policy_logs_simulation_mode", "execution_policy_decision_logs", ["simulation_mode"], unique=False)

    if not _has_table(bind, "execution_policy_versions"):
        op.create_table(
            "execution_policy_versions",
            sa.Column("version_id", sa.String(length=120), primary_key=True),
            sa.Column("policy_code", sa.String(length=160), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("state", sa.String(length=20), nullable=False, server_default="DRAFT"),
            sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("change_summary", sa.Text(), nullable=True),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rollback_target_version", sa.String(length=120), nullable=True),
            sa.Column("rollout_strategy", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("conditions_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("rules_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("policy_code", "version_number", name="uq_execution_policy_version_number"),
        )
        op.create_index("ix_execution_policy_versions_policy_code", "execution_policy_versions", ["policy_code"], unique=False)
        op.create_index("ix_execution_policy_versions_state", "execution_policy_versions", ["state"], unique=False)
        op.create_index("ix_execution_policy_versions_approval_status", "execution_policy_versions", ["approval_status"], unique=False)

    if not _has_table(bind, "execution_strategy_bindings"):
        op.create_table(
            "execution_strategy_bindings",
            sa.Column("strategy_id", sa.String(length=120), primary_key=True),
            sa.Column("bound_policy_set", sa.String(length=160), nullable=False),
            sa.Column("risk_class", sa.String(length=20), nullable=False, server_default="MEDIUM"),
            sa.Column("execution_mode", sa.String(length=20), nullable=False, server_default="SIMULATION"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("auto_disable_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("max_violation_count", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("limits", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("allowed_symbols", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("allowed_margin_modes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("allowed_environments", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("state", sa.String(length=20), nullable=False, server_default="enabled"),
            sa.Column("state_reason", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_strategy_bindings_bound_policy_set", "execution_strategy_bindings", ["bound_policy_set"], unique=False)
        op.create_index("ix_execution_strategy_bindings_risk_class", "execution_strategy_bindings", ["risk_class"], unique=False)
        op.create_index("ix_execution_strategy_bindings_enabled", "execution_strategy_bindings", ["enabled"], unique=False)
        op.create_index("ix_execution_strategy_bindings_state", "execution_strategy_bindings", ["state"], unique=False)

    if not _has_table(bind, "execution_remediation_recommendations"):
        op.create_table(
            "execution_remediation_recommendations",
            sa.Column("recommendation_id", sa.String(length=120), primary_key=True),
            sa.Column("trace_id", sa.String(length=120), nullable=True),
            sa.Column("source_violation_id", sa.String(length=120), nullable=True),
            sa.Column("recommendation_type", sa.String(length=40), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("reason_code", sa.String(length=120), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("requires_manual_approval", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejected_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_remediation_status", "execution_remediation_recommendations", ["status"], unique=False)
        op.create_index("ix_execution_remediation_trace_id", "execution_remediation_recommendations", ["trace_id"], unique=False)
        op.create_index("ix_execution_remediation_reason_code", "execution_remediation_recommendations", ["reason_code"], unique=False)

    if not _has_table(bind, "execution_governance_events"):
        op.create_table(
            "execution_governance_events",
            sa.Column("event_id", sa.String(length=120), primary_key=True),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("idempotency_key", sa.String(length=180), nullable=False, unique=True),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_governance_events_type", "execution_governance_events", ["event_type"], unique=False)
        op.create_index("ix_execution_governance_events_status", "execution_governance_events", ["status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "execution_governance_events"):
        op.drop_table("execution_governance_events")
    if _has_table(bind, "execution_remediation_recommendations"):
        op.drop_table("execution_remediation_recommendations")
    if _has_table(bind, "execution_strategy_bindings"):
        op.drop_table("execution_strategy_bindings")
    if _has_table(bind, "execution_policy_versions"):
        op.drop_table("execution_policy_versions")
