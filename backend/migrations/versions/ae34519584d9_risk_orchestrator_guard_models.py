"""risk orchestrator guard models

Revision ID: ae34519584d9
Revises: 20260323_0064
Create Date: 2026-03-23 15:03:18.267854

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'ae34519584d9'
down_revision = '20260323_0064'
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _create_risk_orchestrator_guard_tables(bind) -> None:
    if _table_exists(bind, "risk_orchestrator_policies") and not _column_exists(bind, "risk_orchestrator_policies", "policy_version"):
        op.add_column("risk_orchestrator_policies", sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"))

    if not _table_exists(bind, "risk_orchestrator_policy_versions"):
        op.create_table(
            "risk_orchestrator_policy_versions",
            sa.Column("version_id", sa.String(length=120), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("policy_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("diff_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("changed_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("changed_role", sa.String(length=40), nullable=False, server_default="admin"),
            sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("simulation_id", sa.String(length=120), nullable=True),
            sa.Column("approval_request_id", sa.String(length=120), nullable=True),
            sa.Column("reverted_from_version_id", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("version_id"),
        )
        _create_index_if_missing("risk_orchestrator_policy_versions", "ix_risk_orchestrator_policy_versions_version_no", ["version_no"])
        _create_index_if_missing("risk_orchestrator_policy_versions", "ix_risk_orchestrator_policy_versions_changed_by", ["changed_by"])
        _create_index_if_missing("risk_orchestrator_policy_versions", "ix_risk_orchestrator_policy_versions_simulation_id", ["simulation_id"])
        _create_index_if_missing("risk_orchestrator_policy_versions", "ix_risk_orchestrator_policy_versions_approval_request_id", ["approval_request_id"])
        _create_index_if_missing("risk_orchestrator_policy_versions", "ix_risk_orchestrator_policy_versions_reverted_from_version_id", ["reverted_from_version_id"])
        _create_index_if_missing("risk_orchestrator_policy_versions", "ix_risk_orchestrator_policy_versions_created_at", ["created_at"])

    if not _table_exists(bind, "risk_orchestrator_policy_change_requests"):
        op.create_table(
            "risk_orchestrator_policy_change_requests",
            sa.Column("request_id", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("requested_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("requested_role", sa.String(length=40), nullable=False, server_default="admin"),
            sa.Column("approved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approval_note", sa.Text(), nullable=True),
            sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("simulation_id", sa.String(length=120), nullable=True),
            sa.Column("critical_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("double_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("request_id"),
        )
        _create_index_if_missing("risk_orchestrator_policy_change_requests", "ix_risk_orchestrator_policy_change_requests_status", ["status"])
        _create_index_if_missing("risk_orchestrator_policy_change_requests", "ix_risk_orchestrator_policy_change_requests_requested_by", ["requested_by"])
        _create_index_if_missing("risk_orchestrator_policy_change_requests", "ix_risk_orchestrator_policy_change_requests_approved_by", ["approved_by"])
        _create_index_if_missing("risk_orchestrator_policy_change_requests", "ix_risk_orchestrator_policy_change_requests_simulation_id", ["simulation_id"])
        _create_index_if_missing("risk_orchestrator_policy_change_requests", "ix_risk_orchestrator_policy_change_requests_created_at", ["created_at"])

    if not _table_exists(bind, "risk_orchestrator_policy_simulations"):
        op.create_table(
            "risk_orchestrator_policy_simulations",
            sa.Column("simulation_id", sa.String(length=120), nullable=False),
            sa.Column("actor_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("actor_role", sa.String(length=40), nullable=False, server_default="admin"),
            sa.Column("baseline_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("candidate_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("result_status", sa.String(length=20), nullable=False, server_default="safe"),
            sa.Column("diff_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("impacted_strategies", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("impacted_symbols", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("simulation_id"),
        )
        _create_index_if_missing("risk_orchestrator_policy_simulations", "ix_risk_orchestrator_policy_simulations_actor_id", ["actor_id"])
        _create_index_if_missing("risk_orchestrator_policy_simulations", "ix_risk_orchestrator_policy_simulations_result_status", ["result_status"])
        _create_index_if_missing("risk_orchestrator_policy_simulations", "ix_risk_orchestrator_policy_simulations_created_at", ["created_at"])

    if not _table_exists(bind, "risk_orchestrator_manual_overrides"):
        op.create_table(
            "risk_orchestrator_manual_overrides",
            sa.Column("override_id", sa.String(length=120), nullable=False),
            sa.Column("override_type", sa.String(length=40), nullable=False, server_default="symbol"),
            sa.Column("target_key", sa.String(length=120), nullable=False),
            sa.Column("override_value", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("actor_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("actor_role", sa.String(length=40), nullable=False, server_default="admin"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("override_id"),
        )
        _create_index_if_missing("risk_orchestrator_manual_overrides", "ix_risk_orchestrator_manual_overrides_override_type", ["override_type"])
        _create_index_if_missing("risk_orchestrator_manual_overrides", "ix_risk_orchestrator_manual_overrides_target_key", ["target_key"])
        _create_index_if_missing("risk_orchestrator_manual_overrides", "ix_risk_orchestrator_manual_overrides_actor_id", ["actor_id"])
        _create_index_if_missing("risk_orchestrator_manual_overrides", "ix_risk_orchestrator_manual_overrides_status", ["status"])
        _create_index_if_missing("risk_orchestrator_manual_overrides", "ix_risk_orchestrator_manual_overrides_expires_at", ["expires_at"])
        _create_index_if_missing("risk_orchestrator_manual_overrides", "ix_risk_orchestrator_manual_overrides_created_at", ["created_at"])

    if not _table_exists(bind, "risk_orchestrator_intervention_logs"):
        op.create_table(
            "risk_orchestrator_intervention_logs",
            sa.Column("intervention_id", sa.String(length=120), nullable=False),
            sa.Column("intent_id", sa.String(length=120), nullable=True),
            sa.Column("action_type", sa.String(length=80), nullable=False),
            sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("actor_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("actor_role", sa.String(length=40), nullable=False, server_default="admin"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="success"),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("result_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("intervention_id"),
        )
        _create_index_if_missing("risk_orchestrator_intervention_logs", "ix_risk_orchestrator_intervention_logs_intent_id", ["intent_id"])
        _create_index_if_missing("risk_orchestrator_intervention_logs", "ix_risk_orchestrator_intervention_logs_action_type", ["action_type"])
        _create_index_if_missing("risk_orchestrator_intervention_logs", "ix_risk_orchestrator_intervention_logs_actor_id", ["actor_id"])
        _create_index_if_missing("risk_orchestrator_intervention_logs", "ix_risk_orchestrator_intervention_logs_status", ["status"])
        _create_index_if_missing("risk_orchestrator_intervention_logs", "ix_risk_orchestrator_intervention_logs_created_at", ["created_at"])

    if not _table_exists(bind, "risk_orchestrator_auto_trigger_logs"):
        op.create_table(
            "risk_orchestrator_auto_trigger_logs",
            sa.Column("trigger_id", sa.String(length=120), nullable=False),
            sa.Column("breach_type", sa.String(length=80), nullable=False),
            sa.Column("target_key", sa.String(length=120), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
            sa.Column("suggested_action", sa.String(length=80), nullable=False, server_default="review"),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("acknowledged_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("trigger_id"),
        )
        _create_index_if_missing("risk_orchestrator_auto_trigger_logs", "ix_risk_orchestrator_auto_trigger_logs_breach_type", ["breach_type"])
        _create_index_if_missing("risk_orchestrator_auto_trigger_logs", "ix_risk_orchestrator_auto_trigger_logs_target_key", ["target_key"])
        _create_index_if_missing("risk_orchestrator_auto_trigger_logs", "ix_risk_orchestrator_auto_trigger_logs_severity", ["severity"])
        _create_index_if_missing("risk_orchestrator_auto_trigger_logs", "ix_risk_orchestrator_auto_trigger_logs_acknowledged_by", ["acknowledged_by"])
        _create_index_if_missing("risk_orchestrator_auto_trigger_logs", "ix_risk_orchestrator_auto_trigger_logs_created_at", ["created_at"])


def _drop_guard_tables(bind) -> None:
    for table_name in [
        "risk_orchestrator_auto_trigger_logs",
        "risk_orchestrator_intervention_logs",
        "risk_orchestrator_manual_overrides",
        "risk_orchestrator_policy_simulations",
        "risk_orchestrator_policy_change_requests",
        "risk_orchestrator_policy_versions",
    ]:
        if _table_exists(bind, table_name):
            op.drop_table(table_name)

    if _table_exists(bind, "risk_orchestrator_policies") and _column_exists(bind, "risk_orchestrator_policies", "policy_version"):
        op.drop_column("risk_orchestrator_policies", "policy_version")


def upgrade() -> None:
    bind = op.get_bind()
    _create_risk_orchestrator_guard_tables(bind)
    return
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('risk_orchestrator_auto_trigger_logs',
    sa.Column('trigger_id', sa.String(length=120), nullable=False),
    sa.Column('breach_type', sa.String(length=80), nullable=False),
    sa.Column('target_key', sa.String(length=120), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('suggested_action', sa.String(length=80), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('acknowledged_by', sa.String(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['acknowledged_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('trigger_id')
    )
    op.create_index(op.f('ix_risk_orchestrator_auto_trigger_logs_acknowledged_by'), 'risk_orchestrator_auto_trigger_logs', ['acknowledged_by'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_auto_trigger_logs_breach_type'), 'risk_orchestrator_auto_trigger_logs', ['breach_type'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_auto_trigger_logs_created_at'), 'risk_orchestrator_auto_trigger_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_auto_trigger_logs_severity'), 'risk_orchestrator_auto_trigger_logs', ['severity'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_auto_trigger_logs_target_key'), 'risk_orchestrator_auto_trigger_logs', ['target_key'], unique=False)
    op.create_table('risk_orchestrator_intervention_logs',
    sa.Column('intervention_id', sa.String(length=120), nullable=False),
    sa.Column('intent_id', sa.String(length=120), nullable=True),
    sa.Column('action_type', sa.String(length=80), nullable=False),
    sa.Column('reason_note', sa.Text(), nullable=False),
    sa.Column('actor_id', sa.String(), nullable=False),
    sa.Column('actor_role', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('result_summary', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('intervention_id')
    )
    op.create_index(op.f('ix_risk_orchestrator_intervention_logs_action_type'), 'risk_orchestrator_intervention_logs', ['action_type'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_intervention_logs_actor_id'), 'risk_orchestrator_intervention_logs', ['actor_id'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_intervention_logs_created_at'), 'risk_orchestrator_intervention_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_intervention_logs_intent_id'), 'risk_orchestrator_intervention_logs', ['intent_id'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_intervention_logs_status'), 'risk_orchestrator_intervention_logs', ['status'], unique=False)
    op.create_table('risk_orchestrator_manual_overrides',
    sa.Column('override_id', sa.String(length=120), nullable=False),
    sa.Column('override_type', sa.String(length=40), nullable=False),
    sa.Column('target_key', sa.String(length=120), nullable=False),
    sa.Column('override_value', sa.JSON(), nullable=False),
    sa.Column('reason_note', sa.Text(), nullable=False),
    sa.Column('actor_id', sa.String(), nullable=False),
    sa.Column('actor_role', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('override_id')
    )
    op.create_index(op.f('ix_risk_orchestrator_manual_overrides_actor_id'), 'risk_orchestrator_manual_overrides', ['actor_id'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_manual_overrides_created_at'), 'risk_orchestrator_manual_overrides', ['created_at'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_manual_overrides_expires_at'), 'risk_orchestrator_manual_overrides', ['expires_at'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_manual_overrides_override_type'), 'risk_orchestrator_manual_overrides', ['override_type'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_manual_overrides_status'), 'risk_orchestrator_manual_overrides', ['status'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_manual_overrides_target_key'), 'risk_orchestrator_manual_overrides', ['target_key'], unique=False)
    op.create_table('risk_orchestrator_policy_change_requests',
    sa.Column('request_id', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('requested_by', sa.String(), nullable=False),
    sa.Column('requested_role', sa.String(length=40), nullable=False),
    sa.Column('approved_by', sa.String(), nullable=True),
    sa.Column('approval_note', sa.Text(), nullable=True),
    sa.Column('reason_note', sa.Text(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('simulation_id', sa.String(length=120), nullable=True),
    sa.Column('critical_fields', sa.JSON(), nullable=False),
    sa.Column('double_confirmed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('request_id')
    )
    op.create_index(op.f('ix_risk_orchestrator_policy_change_requests_approved_by'), 'risk_orchestrator_policy_change_requests', ['approved_by'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_change_requests_created_at'), 'risk_orchestrator_policy_change_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_change_requests_requested_by'), 'risk_orchestrator_policy_change_requests', ['requested_by'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_change_requests_simulation_id'), 'risk_orchestrator_policy_change_requests', ['simulation_id'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_change_requests_status'), 'risk_orchestrator_policy_change_requests', ['status'], unique=False)
    op.create_table('risk_orchestrator_policy_simulations',
    sa.Column('simulation_id', sa.String(length=120), nullable=False),
    sa.Column('actor_id', sa.String(), nullable=False),
    sa.Column('actor_role', sa.String(length=40), nullable=False),
    sa.Column('baseline_policy', sa.JSON(), nullable=False),
    sa.Column('candidate_policy', sa.JSON(), nullable=False),
    sa.Column('result_status', sa.String(length=20), nullable=False),
    sa.Column('diff_summary', sa.JSON(), nullable=False),
    sa.Column('impacted_strategies', sa.JSON(), nullable=False),
    sa.Column('impacted_symbols', sa.JSON(), nullable=False),
    sa.Column('metrics', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('simulation_id')
    )
    op.create_index(op.f('ix_risk_orchestrator_policy_simulations_actor_id'), 'risk_orchestrator_policy_simulations', ['actor_id'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_simulations_created_at'), 'risk_orchestrator_policy_simulations', ['created_at'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_simulations_result_status'), 'risk_orchestrator_policy_simulations', ['result_status'], unique=False)
    op.create_table('risk_orchestrator_policy_versions',
    sa.Column('version_id', sa.String(length=120), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('policy_payload', sa.JSON(), nullable=False),
    sa.Column('diff_payload', sa.JSON(), nullable=False),
    sa.Column('changed_by', sa.String(), nullable=False),
    sa.Column('changed_role', sa.String(length=40), nullable=False),
    sa.Column('reason_note', sa.Text(), nullable=False),
    sa.Column('simulation_id', sa.String(length=120), nullable=True),
    sa.Column('approval_request_id', sa.String(length=120), nullable=True),
    sa.Column('reverted_from_version_id', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('version_id')
    )
    op.create_index(op.f('ix_risk_orchestrator_policy_versions_approval_request_id'), 'risk_orchestrator_policy_versions', ['approval_request_id'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_versions_changed_by'), 'risk_orchestrator_policy_versions', ['changed_by'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_versions_created_at'), 'risk_orchestrator_policy_versions', ['created_at'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_versions_reverted_from_version_id'), 'risk_orchestrator_policy_versions', ['reverted_from_version_id'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_versions_simulation_id'), 'risk_orchestrator_policy_versions', ['simulation_id'], unique=False)
    op.create_index(op.f('ix_risk_orchestrator_policy_versions_version_no'), 'risk_orchestrator_policy_versions', ['version_no'], unique=False)
    op.create_table('simulation_runs',
    sa.Column('run_id', sa.String(length=120), nullable=False),
    sa.Column('actor_id', sa.String(), nullable=True),
    sa.Column('actor_role', sa.String(length=40), nullable=True),
    sa.Column('scope', sa.String(length=60), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('request_mode', sa.String(length=20), nullable=False),
    sa.Column('symbols', sa.JSON(), nullable=False),
    sa.Column('summary_hash', sa.String(length=128), nullable=True),
    sa.Column('input_payload', sa.JSON(), nullable=False),
    sa.Column('output_payload', sa.JSON(), nullable=False),
    sa.Column('approval_request_id', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('run_id')
    )
    op.create_index(op.f('ix_simulation_runs_actor_id'), 'simulation_runs', ['actor_id'], unique=False)
    op.create_index(op.f('ix_simulation_runs_actor_role'), 'simulation_runs', ['actor_role'], unique=False)
    op.create_index(op.f('ix_simulation_runs_approval_request_id'), 'simulation_runs', ['approval_request_id'], unique=False)
    op.create_index(op.f('ix_simulation_runs_created_at'), 'simulation_runs', ['created_at'], unique=False)
    op.create_index(op.f('ix_simulation_runs_scope'), 'simulation_runs', ['scope'], unique=False)
    op.create_index(op.f('ix_simulation_runs_status'), 'simulation_runs', ['status'], unique=False)
    op.create_index(op.f('ix_simulation_runs_summary_hash'), 'simulation_runs', ['summary_hash'], unique=False)
    op.create_table('universe_export_jobs',
    sa.Column('job_id', sa.String(), nullable=False),
    sa.Column('trace_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('result_url', sa.String(length=500), nullable=True),
    sa.Column('result_format', sa.String(length=10), nullable=False),
    sa.Column('result_row_count', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('job_id')
    )
    op.create_index(op.f('ix_universe_export_jobs_created_at'), 'universe_export_jobs', ['created_at'], unique=False)
    op.create_index(op.f('ix_universe_export_jobs_created_by'), 'universe_export_jobs', ['created_by'], unique=False)
    op.create_index(op.f('ix_universe_export_jobs_status'), 'universe_export_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_universe_export_jobs_trace_id'), 'universe_export_jobs', ['trace_id'], unique=False)
    op.create_table('user_mfa_backup_codes',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('code_hash', sa.String(length=128), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_mfa_backup_codes_code_hash'), 'user_mfa_backup_codes', ['code_hash'], unique=False)
    op.create_index(op.f('ix_user_mfa_backup_codes_user_id'), 'user_mfa_backup_codes', ['user_id'], unique=False)
    op.create_table('decision_approval_requests',
    sa.Column('request_id', sa.String(length=120), nullable=False),
    sa.Column('request_type', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('requested_by', sa.String(), nullable=False),
    sa.Column('requested_role', sa.String(length=40), nullable=False),
    sa.Column('reason_note', sa.Text(), nullable=False),
    sa.Column('simulation_run_id', sa.String(length=120), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by', sa.String(), nullable=True),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('assigned_to', sa.String(length=120), nullable=True),
    sa.Column('ack_by', sa.String(length=120), nullable=True),
    sa.Column('ack_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('target_type', sa.String(length=80), nullable=True),
    sa.Column('target_id', sa.String(length=160), nullable=True),
    sa.Column('explanation_summary', sa.Text(), nullable=False),
    sa.Column('decision_factors', sa.JSON(), nullable=False),
    sa.Column('previous_state_snapshot', sa.JSON(), nullable=False),
    sa.Column('source_request_id', sa.String(length=120), nullable=True),
    sa.Column('linked_revert_request_id', sa.String(length=120), nullable=True),
    sa.Column('reverted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reverted_by', sa.String(length=120), nullable=True),
    sa.Column('revert_reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['simulation_run_id'], ['simulation_runs.run_id'], ),
    sa.PrimaryKeyConstraint('request_id')
    )
    op.create_index(op.f('ix_decision_approval_requests_ack_by'), 'decision_approval_requests', ['ack_by'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_approved_by'), 'decision_approval_requests', ['approved_by'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_assigned_to'), 'decision_approval_requests', ['assigned_to'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_created_at'), 'decision_approval_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_expires_at'), 'decision_approval_requests', ['expires_at'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_linked_revert_request_id'), 'decision_approval_requests', ['linked_revert_request_id'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_request_type'), 'decision_approval_requests', ['request_type'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_requested_by'), 'decision_approval_requests', ['requested_by'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_reverted_by'), 'decision_approval_requests', ['reverted_by'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_simulation_run_id'), 'decision_approval_requests', ['simulation_run_id'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_source_request_id'), 'decision_approval_requests', ['source_request_id'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_status'), 'decision_approval_requests', ['status'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_target_id'), 'decision_approval_requests', ['target_id'], unique=False)
    op.create_index(op.f('ix_decision_approval_requests_target_type'), 'decision_approval_requests', ['target_type'], unique=False)
    op.create_table('simulation_scenario_items',
    sa.Column('scenario_id', sa.String(length=120), nullable=False),
    sa.Column('run_id', sa.String(length=120), nullable=False),
    sa.Column('symbol', sa.String(length=30), nullable=False),
    sa.Column('scenario_label', sa.String(length=80), nullable=False),
    sa.Column('input_payload', sa.JSON(), nullable=False),
    sa.Column('output_payload', sa.JSON(), nullable=False),
    sa.Column('risk_delta', sa.Float(), nullable=False),
    sa.Column('decision_delta', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['simulation_runs.run_id'], ),
    sa.PrimaryKeyConstraint('scenario_id')
    )
    op.create_index(op.f('ix_simulation_scenario_items_created_at'), 'simulation_scenario_items', ['created_at'], unique=False)
    op.create_index(op.f('ix_simulation_scenario_items_run_id'), 'simulation_scenario_items', ['run_id'], unique=False)
    op.create_index(op.f('ix_simulation_scenario_items_symbol'), 'simulation_scenario_items', ['symbol'], unique=False)
    op.create_table('escalation_center_items',
    sa.Column('escalation_id', sa.String(length=120), nullable=False),
    sa.Column('linked_request_id', sa.String(length=120), nullable=False),
    sa.Column('linked_simulation_run_id', sa.String(length=120), nullable=True),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('escalation_level', sa.String(length=20), nullable=False),
    sa.Column('escalation_reason', sa.Text(), nullable=False),
    sa.Column('breach_age_seconds', sa.Integer(), nullable=False),
    sa.Column('current_owner', sa.String(length=120), nullable=False),
    sa.Column('ack_by', sa.String(), nullable=True),
    sa.Column('ack_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by', sa.String(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['ack_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['linked_request_id'], ['decision_approval_requests.request_id'], ),
    sa.ForeignKeyConstraint(['linked_simulation_run_id'], ['simulation_runs.run_id'], ),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('escalation_id')
    )
    op.create_index(op.f('ix_escalation_center_items_ack_by'), 'escalation_center_items', ['ack_by'], unique=False)
    op.create_index(op.f('ix_escalation_center_items_created_at'), 'escalation_center_items', ['created_at'], unique=False)
    op.create_index(op.f('ix_escalation_center_items_current_owner'), 'escalation_center_items', ['current_owner'], unique=False)
    op.create_index(op.f('ix_escalation_center_items_linked_request_id'), 'escalation_center_items', ['linked_request_id'], unique=False)
    op.create_index(op.f('ix_escalation_center_items_linked_simulation_run_id'), 'escalation_center_items', ['linked_simulation_run_id'], unique=False)
    op.create_index(op.f('ix_escalation_center_items_resolved_by'), 'escalation_center_items', ['resolved_by'], unique=False)
    op.create_index(op.f('ix_escalation_center_items_state'), 'escalation_center_items', ['state'], unique=False)
    op.alter_column('alert_channel_configs', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.create_index(op.f('ix_backtest_result_cards_strategy_type'), 'backtest_result_cards', ['strategy_type'], unique=False)
    op.drop_index(op.f('ix_canonical_strategy_registry_enabled'), table_name='canonical_strategy_registry')
    op.drop_index(op.f('ix_canonical_strategy_registry_family'), table_name='canonical_strategy_registry')
    op.create_index(op.f('ix_canonical_strategy_registry_strategy_family'), 'canonical_strategy_registry', ['strategy_family'], unique=False)
    op.drop_constraint(op.f('exchange_registry_exchange_code_key'), 'exchange_registry', type_='unique')
    op.drop_index(op.f('ix_execution_alert_delivery_attempts_next_retry_at'), table_name='execution_alert_delivery_attempts')
    op.drop_index(op.f('ix_execution_alert_delivery_attempts_request_timestamp'), table_name='execution_alert_delivery_attempts')
    op.drop_index(op.f('ix_execution_alert_delivery_attempts_status'), table_name='execution_alert_delivery_attempts')
    op.drop_constraint(op.f('execution_intents_intent_hash_key'), 'execution_intents', type_='unique')
    op.drop_constraint(op.f('unique_intent'), 'execution_intents', type_='unique')
    op.drop_index(op.f('ix_exec_manual_corr'), table_name='execution_manual_actions')
    op.drop_index(op.f('ix_exec_manual_event'), table_name='execution_manual_actions')
    op.drop_index(op.f('ix_exec_manual_type'), table_name='execution_manual_actions')
    op.create_index(op.f('ix_execution_manual_actions_action_type'), 'execution_manual_actions', ['action_type'], unique=False)
    op.create_index(op.f('ix_execution_manual_actions_correlation_id'), 'execution_manual_actions', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_execution_manual_actions_execution_event_id'), 'execution_manual_actions', ['execution_event_id'], unique=False)
    op.create_index(op.f('ix_execution_manual_actions_requested_by'), 'execution_manual_actions', ['requested_by'], unique=False)
    op.drop_constraint(op.f('execution_policies_strategy_type_key'), 'execution_policies', type_='unique')
    op.create_index(op.f('ix_execution_policies_strategy_type'), 'execution_policies', ['strategy_type'], unique=True)
    op.drop_index(op.f('ix_exec_trans_corr'), table_name='execution_state_transitions')
    op.drop_index(op.f('ix_exec_trans_env'), table_name='execution_state_transitions')
    op.drop_index(op.f('ix_exec_trans_source'), table_name='execution_state_transitions')
    op.create_index(op.f('ix_execution_state_transitions_correlation_id'), 'execution_state_transitions', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_execution_state_transitions_environment'), 'execution_state_transitions', ['environment'], unique=False)
    op.create_index(op.f('ix_execution_state_transitions_source_type'), 'execution_state_transitions', ['source_type'], unique=False)
    op.create_foreign_key(None, 'execution_state_transitions', 'execution_events', ['execution_event_id'], ['id'])
    op.drop_index(op.f('ix_exec_trace_corr'), table_name='execution_trace_index')
    op.drop_index(op.f('ix_exec_trace_event'), table_name='execution_trace_index')
    op.drop_index(op.f('ix_exec_trace_intent'), table_name='execution_trace_index')
    op.drop_index(op.f('ix_exec_trace_stage'), table_name='execution_trace_index')
    op.create_index(op.f('ix_execution_trace_index_correlation_id'), 'execution_trace_index', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_execution_trace_index_execution_event_id'), 'execution_trace_index', ['execution_event_id'], unique=False)
    op.create_index(op.f('ix_execution_trace_index_intent_id'), 'execution_trace_index', ['intent_id'], unique=False)
    op.create_index(op.f('ix_execution_trace_index_stage'), 'execution_trace_index', ['stage'], unique=False)
    op.create_index(op.f('ix_failed_events_entity_id'), 'failed_events', ['entity_id'], unique=False)
    op.create_index(op.f('ix_failed_events_event_type'), 'failed_events', ['event_type'], unique=False)
    op.drop_index(op.f('ix_idemp_collisions_corr'), table_name='idempotency_collisions')
    op.drop_index(op.f('ix_idemp_collisions_intent'), table_name='idempotency_collisions')
    op.drop_index(op.f('ix_idemp_collisions_key'), table_name='idempotency_collisions')
    op.drop_index(op.f('ix_idemp_collisions_status'), table_name='idempotency_collisions')
    op.create_index(op.f('ix_idempotency_collisions_correlation_id'), 'idempotency_collisions', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_idempotency_collisions_idempotency_key'), 'idempotency_collisions', ['idempotency_key'], unique=False)
    op.create_index(op.f('ix_idempotency_collisions_intent_id'), 'idempotency_collisions', ['intent_id'], unique=False)
    op.create_index(op.f('ix_idempotency_collisions_status'), 'idempotency_collisions', ['status'], unique=False)
    op.drop_constraint(op.f('learning_decision_events_pending_signal_id_key'), 'learning_decision_events', type_='unique')
    op.drop_constraint(op.f('learning_decision_events_scanner_result_id_key'), 'learning_decision_events', type_='unique')
    op.create_index(op.f('ix_learning_decision_events_closed_at'), 'learning_decision_events', ['closed_at'], unique=False)
    op.create_index(op.f('ix_learning_decision_events_pending_signal_id'), 'learning_decision_events', ['pending_signal_id'], unique=True)
    op.create_index(op.f('ix_learning_decision_events_position_id'), 'learning_decision_events', ['position_id'], unique=False)
    op.create_index(op.f('ix_learning_decision_events_scanner_result_id'), 'learning_decision_events', ['scanner_result_id'], unique=True)
    op.create_index(op.f('ix_learning_decision_events_strategy_family'), 'learning_decision_events', ['strategy_family'], unique=False)
    op.create_index(op.f('ix_learning_decision_events_strategy_id'), 'learning_decision_events', ['strategy_id'], unique=False)
    op.create_index(op.f('ix_learning_decision_events_user_id'), 'learning_decision_events', ['user_id'], unique=False)
    op.create_foreign_key(None, 'learning_decision_events', 'paper_positions', ['position_id'], ['id'])
    op.drop_index(op.f('ix_learning_recommendations_type'), table_name='learning_recommendations')
    op.create_index(op.f('ix_learning_recommendations_recommendation_type'), 'learning_recommendations', ['recommendation_type'], unique=False)
    op.alter_column('manual_override_log', 'timestamp',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('pending_signals', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.create_foreign_key(None, 'pending_signals', 'bot_profiles', ['bot_profile_id'], ['id'])
    op.create_foreign_key(None, 'pending_signals', 'signal_events', ['signal_id'], ['id'])
    op.create_foreign_key(None, 'pending_signals', 'paper_positions', ['order_position_id'], ['id'])
    op.drop_index(op.f('ix_playbook_execution_runs_retry_attempt'), table_name='playbook_execution_runs')
    op.create_foreign_key(None, 'playbook_execution_runs', 'playbook_execution_runs', ['parent_run_id'], ['id'])
    op.alter_column('portfolio_exposure_snapshot', 'timestamp',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('positions', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('positions', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('risk_clusters', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('risk_clusters', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.drop_constraint(op.f('risk_exposure_groups_name_key'), 'risk_exposure_groups', type_='unique')
    op.create_index(op.f('ix_risk_exposure_groups_name'), 'risk_exposure_groups', ['name'], unique=True)
    op.add_column('risk_orchestrator_policies', sa.Column('policy_version', sa.Integer(), nullable=False))
    op.create_index(op.f('ix_signal_governance_decisions_acted_at'), 'signal_governance_decisions', ['acted_at'], unique=False)
    op.drop_index(op.f('ix_alloc_appr_lnk_rev'), table_name='strategy_allocation_approval_requests')
    op.drop_index(op.f('ix_alloc_appr_reverted_by'), table_name='strategy_allocation_approval_requests')
    op.drop_index(op.f('ix_alloc_appr_src_req'), table_name='strategy_allocation_approval_requests')
    op.create_index(op.f('ix_strategy_allocation_approval_requests_linked_revert_request_id'), 'strategy_allocation_approval_requests', ['linked_revert_request_id'], unique=False)
    op.create_index(op.f('ix_strategy_allocation_approval_requests_reverted_by'), 'strategy_allocation_approval_requests', ['reverted_by'], unique=False)
    op.create_index(op.f('ix_strategy_allocation_approval_requests_source_request_id'), 'strategy_allocation_approval_requests', ['source_request_id'], unique=False)
    op.alter_column('strategy_allocations', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.create_foreign_key(None, 'strategy_observability_events', 'audit_logs', ['audit_log_id'], ['id'])
    op.create_foreign_key(None, 'strategy_observability_events', 'bot_profiles', ['bot_profile_id'], ['id'])
    op.drop_index(op.f('ix_strategy_templates_strategy_type'), table_name='strategy_templates')
    op.drop_index(op.f('ix_system_alerts_delivery_provider'), table_name='system_alerts')
    op.drop_index(op.f('ix_system_alerts_next_retry_at'), table_name='system_alerts')
    op.alter_column('user_decision_traces', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('user_decision_traces', 'expires_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.drop_index(op.f('ix_user_decision_traces_decision'), table_name='user_decision_traces')
    op.drop_index(op.f('ix_user_decision_traces_scope'), table_name='user_decision_traces')
    op.drop_index(op.f('ix_user_decision_traces_strategy'), table_name='user_decision_traces')
    op.create_index(op.f('ix_user_decision_traces_decision_status'), 'user_decision_traces', ['decision_status'], unique=False)
    op.create_index(op.f('ix_user_decision_traces_strategy_code'), 'user_decision_traces', ['strategy_code'], unique=False)
    op.create_index(op.f('ix_user_decision_traces_trace_scope'), 'user_decision_traces', ['trace_scope'], unique=False)
    op.drop_constraint(op.f('user_exchange_settings_user_id_key'), 'user_exchange_settings', type_='unique')
    op.alter_column('user_execution_intents', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('user_execution_intents', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.drop_constraint(op.f('unique_user_execution_intent_idempotency_key'), 'user_execution_intents', type_='unique')
    op.drop_constraint(op.f('unique_user_execution_intent_intent_id'), 'user_execution_intents', type_='unique')
    op.drop_constraint(op.f('user_execution_intents_intent_token_key'), 'user_execution_intents', type_='unique')
    op.drop_index(op.f('ix_user_execution_intents_intent_token'), table_name='user_execution_intents')
    op.create_index(op.f('ix_user_execution_intents_intent_token'), 'user_execution_intents', ['intent_token'], unique=True)
    op.create_index(op.f('ix_user_execution_intents_idempotency_key'), 'user_execution_intents', ['idempotency_key'], unique=True)
    op.create_index(op.f('ix_user_execution_intents_intent_id'), 'user_execution_intents', ['intent_id'], unique=True)
    op.alter_column('user_indicator_saved_queries', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('user_indicator_saved_queries', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('user_indicator_watchlist', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.drop_constraint(op.f('user_risk_settings_user_id_key'), 'user_risk_settings', type_='unique')
    op.drop_index(op.f('ix_user_scanner_automation_configs_auto_enabled'), table_name='user_scanner_automation_configs')
    op.drop_constraint(op.f('user_scanner_automation_configs_user_id_key'), 'user_scanner_automation_configs', type_='unique')
    op.drop_index(op.f('ix_user_scanner_automation_configs_user_id'), table_name='user_scanner_automation_configs')
    op.create_index(op.f('ix_user_scanner_automation_configs_user_id'), 'user_scanner_automation_configs', ['user_id'], unique=True)
    op.drop_index(op.f('ix_user_scanner_automation_profiles_auto_enabled'), table_name='user_scanner_automation_profiles')
    op.alter_column('user_scanner_results', 'generated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('user_signal_modes', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.drop_constraint(op.f('user_signal_modes_user_id_key'), 'user_signal_modes', type_='unique')
    op.drop_index(op.f('ix_user_signal_modes_user_id'), table_name='user_signal_modes')
    op.create_index(op.f('ix_user_signal_modes_user_id'), 'user_signal_modes', ['user_id'], unique=True)
    op.drop_constraint(op.f('users_email_key'), 'users', type_='unique')
    op.drop_index(op.f('ix_weekly_report_archives_generated_at'), table_name='weekly_report_archives')
    op.drop_index(op.f('ix_weekly_report_archives_report_type'), table_name='weekly_report_archives')
    op.drop_index(op.f('ix_weekly_report_archives_status'), table_name='weekly_report_archives')
    op.drop_index(op.f('ix_weekly_report_archives_trigger_source'), table_name='weekly_report_archives')
    # ### end Alembic commands ###


def downgrade() -> None:
    bind = op.get_bind()
    _drop_guard_tables(bind)
    return
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index(op.f('ix_weekly_report_archives_trigger_source'), 'weekly_report_archives', ['trigger_source'], unique=False)
    op.create_index(op.f('ix_weekly_report_archives_status'), 'weekly_report_archives', ['status'], unique=False)
    op.create_index(op.f('ix_weekly_report_archives_report_type'), 'weekly_report_archives', ['report_type'], unique=False)
    op.create_index(op.f('ix_weekly_report_archives_generated_at'), 'weekly_report_archives', ['generated_at'], unique=False)
    op.create_unique_constraint(op.f('users_email_key'), 'users', ['email'], postgresql_nulls_not_distinct=False)
    op.drop_index(op.f('ix_user_signal_modes_user_id'), table_name='user_signal_modes')
    op.create_index(op.f('ix_user_signal_modes_user_id'), 'user_signal_modes', ['user_id'], unique=False)
    op.create_unique_constraint(op.f('user_signal_modes_user_id_key'), 'user_signal_modes', ['user_id'], postgresql_nulls_not_distinct=False)
    op.alter_column('user_signal_modes', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('user_scanner_results', 'generated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.create_index(op.f('ix_user_scanner_automation_profiles_auto_enabled'), 'user_scanner_automation_profiles', ['auto_enabled'], unique=False)
    op.drop_index(op.f('ix_user_scanner_automation_configs_user_id'), table_name='user_scanner_automation_configs')
    op.create_index(op.f('ix_user_scanner_automation_configs_user_id'), 'user_scanner_automation_configs', ['user_id'], unique=False)
    op.create_unique_constraint(op.f('user_scanner_automation_configs_user_id_key'), 'user_scanner_automation_configs', ['user_id'], postgresql_nulls_not_distinct=False)
    op.create_index(op.f('ix_user_scanner_automation_configs_auto_enabled'), 'user_scanner_automation_configs', ['auto_enabled'], unique=False)
    op.create_unique_constraint(op.f('user_risk_settings_user_id_key'), 'user_risk_settings', ['user_id'], postgresql_nulls_not_distinct=False)
    op.alter_column('user_indicator_watchlist', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('user_indicator_saved_queries', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('user_indicator_saved_queries', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.drop_index(op.f('ix_user_execution_intents_intent_id'), table_name='user_execution_intents')
    op.drop_index(op.f('ix_user_execution_intents_idempotency_key'), table_name='user_execution_intents')
    op.drop_index(op.f('ix_user_execution_intents_intent_token'), table_name='user_execution_intents')
    op.create_index(op.f('ix_user_execution_intents_intent_token'), 'user_execution_intents', ['intent_token'], unique=False)
    op.create_unique_constraint(op.f('user_execution_intents_intent_token_key'), 'user_execution_intents', ['intent_token'], postgresql_nulls_not_distinct=False)
    op.create_unique_constraint(op.f('unique_user_execution_intent_intent_id'), 'user_execution_intents', ['intent_id'], postgresql_nulls_not_distinct=False)
    op.create_unique_constraint(op.f('unique_user_execution_intent_idempotency_key'), 'user_execution_intents', ['idempotency_key'], postgresql_nulls_not_distinct=False)
    op.alter_column('user_execution_intents', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('user_execution_intents', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.create_unique_constraint(op.f('user_exchange_settings_user_id_key'), 'user_exchange_settings', ['user_id'], postgresql_nulls_not_distinct=False)
    op.drop_index(op.f('ix_user_decision_traces_trace_scope'), table_name='user_decision_traces')
    op.drop_index(op.f('ix_user_decision_traces_strategy_code'), table_name='user_decision_traces')
    op.drop_index(op.f('ix_user_decision_traces_decision_status'), table_name='user_decision_traces')
    op.create_index(op.f('ix_user_decision_traces_strategy'), 'user_decision_traces', ['strategy_code'], unique=False)
    op.create_index(op.f('ix_user_decision_traces_scope'), 'user_decision_traces', ['trace_scope'], unique=False)
    op.create_index(op.f('ix_user_decision_traces_decision'), 'user_decision_traces', ['decision_status'], unique=False)
    op.alter_column('user_decision_traces', 'expires_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('user_decision_traces', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.create_index(op.f('ix_system_alerts_next_retry_at'), 'system_alerts', ['next_retry_at'], unique=False)
    op.create_index(op.f('ix_system_alerts_delivery_provider'), 'system_alerts', ['delivery_provider'], unique=False)
    op.create_index(op.f('ix_strategy_templates_strategy_type'), 'strategy_templates', ['strategy_type'], unique=False)
    op.drop_constraint(None, 'strategy_observability_events', type_='foreignkey')
    op.drop_constraint(None, 'strategy_observability_events', type_='foreignkey')
    op.alter_column('strategy_allocations', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.drop_index(op.f('ix_strategy_allocation_approval_requests_source_request_id'), table_name='strategy_allocation_approval_requests')
    op.drop_index(op.f('ix_strategy_allocation_approval_requests_reverted_by'), table_name='strategy_allocation_approval_requests')
    op.drop_index(op.f('ix_strategy_allocation_approval_requests_linked_revert_request_id'), table_name='strategy_allocation_approval_requests')
    op.create_index(op.f('ix_alloc_appr_src_req'), 'strategy_allocation_approval_requests', ['source_request_id'], unique=False)
    op.create_index(op.f('ix_alloc_appr_reverted_by'), 'strategy_allocation_approval_requests', ['reverted_by'], unique=False)
    op.create_index(op.f('ix_alloc_appr_lnk_rev'), 'strategy_allocation_approval_requests', ['linked_revert_request_id'], unique=False)
    op.drop_index(op.f('ix_signal_governance_decisions_acted_at'), table_name='signal_governance_decisions')
    op.drop_column('risk_orchestrator_policies', 'policy_version')
    op.drop_index(op.f('ix_risk_exposure_groups_name'), table_name='risk_exposure_groups')
    op.create_unique_constraint(op.f('risk_exposure_groups_name_key'), 'risk_exposure_groups', ['name'], postgresql_nulls_not_distinct=False)
    op.alter_column('risk_clusters', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('risk_clusters', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('positions', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('positions', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('portfolio_exposure_snapshot', 'timestamp',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.drop_constraint(None, 'playbook_execution_runs', type_='foreignkey')
    op.create_index(op.f('ix_playbook_execution_runs_retry_attempt'), 'playbook_execution_runs', ['retry_attempt'], unique=False)
    op.drop_constraint(None, 'pending_signals', type_='foreignkey')
    op.drop_constraint(None, 'pending_signals', type_='foreignkey')
    op.drop_constraint(None, 'pending_signals', type_='foreignkey')
    op.alter_column('pending_signals', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('manual_override_log', 'timestamp',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.drop_index(op.f('ix_learning_recommendations_recommendation_type'), table_name='learning_recommendations')
    op.create_index(op.f('ix_learning_recommendations_type'), 'learning_recommendations', ['recommendation_type'], unique=False)
    op.drop_constraint(None, 'learning_decision_events', type_='foreignkey')
    op.drop_index(op.f('ix_learning_decision_events_user_id'), table_name='learning_decision_events')
    op.drop_index(op.f('ix_learning_decision_events_strategy_id'), table_name='learning_decision_events')
    op.drop_index(op.f('ix_learning_decision_events_strategy_family'), table_name='learning_decision_events')
    op.drop_index(op.f('ix_learning_decision_events_scanner_result_id'), table_name='learning_decision_events')
    op.drop_index(op.f('ix_learning_decision_events_position_id'), table_name='learning_decision_events')
    op.drop_index(op.f('ix_learning_decision_events_pending_signal_id'), table_name='learning_decision_events')
    op.drop_index(op.f('ix_learning_decision_events_closed_at'), table_name='learning_decision_events')
    op.create_unique_constraint(op.f('learning_decision_events_scanner_result_id_key'), 'learning_decision_events', ['scanner_result_id'], postgresql_nulls_not_distinct=False)
    op.create_unique_constraint(op.f('learning_decision_events_pending_signal_id_key'), 'learning_decision_events', ['pending_signal_id'], postgresql_nulls_not_distinct=False)
    op.drop_index(op.f('ix_idempotency_collisions_status'), table_name='idempotency_collisions')
    op.drop_index(op.f('ix_idempotency_collisions_intent_id'), table_name='idempotency_collisions')
    op.drop_index(op.f('ix_idempotency_collisions_idempotency_key'), table_name='idempotency_collisions')
    op.drop_index(op.f('ix_idempotency_collisions_correlation_id'), table_name='idempotency_collisions')
    op.create_index(op.f('ix_idemp_collisions_status'), 'idempotency_collisions', ['status'], unique=False)
    op.create_index(op.f('ix_idemp_collisions_key'), 'idempotency_collisions', ['idempotency_key'], unique=False)
    op.create_index(op.f('ix_idemp_collisions_intent'), 'idempotency_collisions', ['intent_id'], unique=False)
    op.create_index(op.f('ix_idemp_collisions_corr'), 'idempotency_collisions', ['correlation_id'], unique=False)
    op.drop_index(op.f('ix_failed_events_event_type'), table_name='failed_events')
    op.drop_index(op.f('ix_failed_events_entity_id'), table_name='failed_events')
    op.drop_index(op.f('ix_execution_trace_index_stage'), table_name='execution_trace_index')
    op.drop_index(op.f('ix_execution_trace_index_intent_id'), table_name='execution_trace_index')
    op.drop_index(op.f('ix_execution_trace_index_execution_event_id'), table_name='execution_trace_index')
    op.drop_index(op.f('ix_execution_trace_index_correlation_id'), table_name='execution_trace_index')
    op.create_index(op.f('ix_exec_trace_stage'), 'execution_trace_index', ['stage'], unique=False)
    op.create_index(op.f('ix_exec_trace_intent'), 'execution_trace_index', ['intent_id'], unique=False)
    op.create_index(op.f('ix_exec_trace_event'), 'execution_trace_index', ['execution_event_id'], unique=False)
    op.create_index(op.f('ix_exec_trace_corr'), 'execution_trace_index', ['correlation_id'], unique=False)
    op.drop_constraint(None, 'execution_state_transitions', type_='foreignkey')
    op.drop_index(op.f('ix_execution_state_transitions_source_type'), table_name='execution_state_transitions')
    op.drop_index(op.f('ix_execution_state_transitions_environment'), table_name='execution_state_transitions')
    op.drop_index(op.f('ix_execution_state_transitions_correlation_id'), table_name='execution_state_transitions')
    op.create_index(op.f('ix_exec_trans_source'), 'execution_state_transitions', ['source_type'], unique=False)
    op.create_index(op.f('ix_exec_trans_env'), 'execution_state_transitions', ['environment'], unique=False)
    op.create_index(op.f('ix_exec_trans_corr'), 'execution_state_transitions', ['correlation_id'], unique=False)
    op.drop_index(op.f('ix_execution_policies_strategy_type'), table_name='execution_policies')
    op.create_unique_constraint(op.f('execution_policies_strategy_type_key'), 'execution_policies', ['strategy_type'], postgresql_nulls_not_distinct=False)
    op.drop_index(op.f('ix_execution_manual_actions_requested_by'), table_name='execution_manual_actions')
    op.drop_index(op.f('ix_execution_manual_actions_execution_event_id'), table_name='execution_manual_actions')
    op.drop_index(op.f('ix_execution_manual_actions_correlation_id'), table_name='execution_manual_actions')
    op.drop_index(op.f('ix_execution_manual_actions_action_type'), table_name='execution_manual_actions')
    op.create_index(op.f('ix_exec_manual_type'), 'execution_manual_actions', ['action_type'], unique=False)
    op.create_index(op.f('ix_exec_manual_event'), 'execution_manual_actions', ['execution_event_id'], unique=False)
    op.create_index(op.f('ix_exec_manual_corr'), 'execution_manual_actions', ['correlation_id'], unique=False)
    op.create_unique_constraint(op.f('unique_intent'), 'execution_intents', ['intent_id'], postgresql_nulls_not_distinct=False)
    op.create_unique_constraint(op.f('execution_intents_intent_hash_key'), 'execution_intents', ['intent_hash'], postgresql_nulls_not_distinct=False)
    op.create_index(op.f('ix_execution_alert_delivery_attempts_status'), 'execution_alert_delivery_attempts', ['status'], unique=False)
    op.create_index(op.f('ix_execution_alert_delivery_attempts_request_timestamp'), 'execution_alert_delivery_attempts', ['request_timestamp'], unique=False)
    op.create_index(op.f('ix_execution_alert_delivery_attempts_next_retry_at'), 'execution_alert_delivery_attempts', ['next_retry_at'], unique=False)
    op.create_unique_constraint(op.f('exchange_registry_exchange_code_key'), 'exchange_registry', ['exchange_code'], postgresql_nulls_not_distinct=False)
    op.drop_index(op.f('ix_canonical_strategy_registry_strategy_family'), table_name='canonical_strategy_registry')
    op.create_index(op.f('ix_canonical_strategy_registry_family'), 'canonical_strategy_registry', ['strategy_family'], unique=False)
    op.create_index(op.f('ix_canonical_strategy_registry_enabled'), 'canonical_strategy_registry', ['is_enabled'], unique=False)
    op.drop_index(op.f('ix_backtest_result_cards_strategy_type'), table_name='backtest_result_cards')
    op.alter_column('alert_channel_configs', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.drop_index(op.f('ix_escalation_center_items_state'), table_name='escalation_center_items')
    op.drop_index(op.f('ix_escalation_center_items_resolved_by'), table_name='escalation_center_items')
    op.drop_index(op.f('ix_escalation_center_items_linked_simulation_run_id'), table_name='escalation_center_items')
    op.drop_index(op.f('ix_escalation_center_items_linked_request_id'), table_name='escalation_center_items')
    op.drop_index(op.f('ix_escalation_center_items_current_owner'), table_name='escalation_center_items')
    op.drop_index(op.f('ix_escalation_center_items_created_at'), table_name='escalation_center_items')
    op.drop_index(op.f('ix_escalation_center_items_ack_by'), table_name='escalation_center_items')
    op.drop_table('escalation_center_items')
    op.drop_index(op.f('ix_simulation_scenario_items_symbol'), table_name='simulation_scenario_items')
    op.drop_index(op.f('ix_simulation_scenario_items_run_id'), table_name='simulation_scenario_items')
    op.drop_index(op.f('ix_simulation_scenario_items_created_at'), table_name='simulation_scenario_items')
    op.drop_table('simulation_scenario_items')
    op.drop_index(op.f('ix_decision_approval_requests_target_type'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_target_id'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_status'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_source_request_id'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_simulation_run_id'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_reverted_by'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_requested_by'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_request_type'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_linked_revert_request_id'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_expires_at'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_created_at'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_assigned_to'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_approved_by'), table_name='decision_approval_requests')
    op.drop_index(op.f('ix_decision_approval_requests_ack_by'), table_name='decision_approval_requests')
    op.drop_table('decision_approval_requests')
    op.drop_index(op.f('ix_user_mfa_backup_codes_user_id'), table_name='user_mfa_backup_codes')
    op.drop_index(op.f('ix_user_mfa_backup_codes_code_hash'), table_name='user_mfa_backup_codes')
    op.drop_table('user_mfa_backup_codes')
    op.drop_index(op.f('ix_universe_export_jobs_trace_id'), table_name='universe_export_jobs')
    op.drop_index(op.f('ix_universe_export_jobs_status'), table_name='universe_export_jobs')
    op.drop_index(op.f('ix_universe_export_jobs_created_by'), table_name='universe_export_jobs')
    op.drop_index(op.f('ix_universe_export_jobs_created_at'), table_name='universe_export_jobs')
    op.drop_table('universe_export_jobs')
    op.drop_index(op.f('ix_simulation_runs_summary_hash'), table_name='simulation_runs')
    op.drop_index(op.f('ix_simulation_runs_status'), table_name='simulation_runs')
    op.drop_index(op.f('ix_simulation_runs_scope'), table_name='simulation_runs')
    op.drop_index(op.f('ix_simulation_runs_created_at'), table_name='simulation_runs')
    op.drop_index(op.f('ix_simulation_runs_approval_request_id'), table_name='simulation_runs')
    op.drop_index(op.f('ix_simulation_runs_actor_role'), table_name='simulation_runs')
    op.drop_index(op.f('ix_simulation_runs_actor_id'), table_name='simulation_runs')
    op.drop_table('simulation_runs')
    op.drop_index(op.f('ix_risk_orchestrator_policy_versions_version_no'), table_name='risk_orchestrator_policy_versions')
    op.drop_index(op.f('ix_risk_orchestrator_policy_versions_simulation_id'), table_name='risk_orchestrator_policy_versions')
    op.drop_index(op.f('ix_risk_orchestrator_policy_versions_reverted_from_version_id'), table_name='risk_orchestrator_policy_versions')
    op.drop_index(op.f('ix_risk_orchestrator_policy_versions_created_at'), table_name='risk_orchestrator_policy_versions')
    op.drop_index(op.f('ix_risk_orchestrator_policy_versions_changed_by'), table_name='risk_orchestrator_policy_versions')
    op.drop_index(op.f('ix_risk_orchestrator_policy_versions_approval_request_id'), table_name='risk_orchestrator_policy_versions')
    op.drop_table('risk_orchestrator_policy_versions')
    op.drop_index(op.f('ix_risk_orchestrator_policy_simulations_result_status'), table_name='risk_orchestrator_policy_simulations')
    op.drop_index(op.f('ix_risk_orchestrator_policy_simulations_created_at'), table_name='risk_orchestrator_policy_simulations')
    op.drop_index(op.f('ix_risk_orchestrator_policy_simulations_actor_id'), table_name='risk_orchestrator_policy_simulations')
    op.drop_table('risk_orchestrator_policy_simulations')
    op.drop_index(op.f('ix_risk_orchestrator_policy_change_requests_status'), table_name='risk_orchestrator_policy_change_requests')
    op.drop_index(op.f('ix_risk_orchestrator_policy_change_requests_simulation_id'), table_name='risk_orchestrator_policy_change_requests')
    op.drop_index(op.f('ix_risk_orchestrator_policy_change_requests_requested_by'), table_name='risk_orchestrator_policy_change_requests')
    op.drop_index(op.f('ix_risk_orchestrator_policy_change_requests_created_at'), table_name='risk_orchestrator_policy_change_requests')
    op.drop_index(op.f('ix_risk_orchestrator_policy_change_requests_approved_by'), table_name='risk_orchestrator_policy_change_requests')
    op.drop_table('risk_orchestrator_policy_change_requests')
    op.drop_index(op.f('ix_risk_orchestrator_manual_overrides_target_key'), table_name='risk_orchestrator_manual_overrides')
    op.drop_index(op.f('ix_risk_orchestrator_manual_overrides_status'), table_name='risk_orchestrator_manual_overrides')
    op.drop_index(op.f('ix_risk_orchestrator_manual_overrides_override_type'), table_name='risk_orchestrator_manual_overrides')
    op.drop_index(op.f('ix_risk_orchestrator_manual_overrides_expires_at'), table_name='risk_orchestrator_manual_overrides')
    op.drop_index(op.f('ix_risk_orchestrator_manual_overrides_created_at'), table_name='risk_orchestrator_manual_overrides')
    op.drop_index(op.f('ix_risk_orchestrator_manual_overrides_actor_id'), table_name='risk_orchestrator_manual_overrides')
    op.drop_table('risk_orchestrator_manual_overrides')
    op.drop_index(op.f('ix_risk_orchestrator_intervention_logs_status'), table_name='risk_orchestrator_intervention_logs')
    op.drop_index(op.f('ix_risk_orchestrator_intervention_logs_intent_id'), table_name='risk_orchestrator_intervention_logs')
    op.drop_index(op.f('ix_risk_orchestrator_intervention_logs_created_at'), table_name='risk_orchestrator_intervention_logs')
    op.drop_index(op.f('ix_risk_orchestrator_intervention_logs_actor_id'), table_name='risk_orchestrator_intervention_logs')
    op.drop_index(op.f('ix_risk_orchestrator_intervention_logs_action_type'), table_name='risk_orchestrator_intervention_logs')
    op.drop_table('risk_orchestrator_intervention_logs')
    op.drop_index(op.f('ix_risk_orchestrator_auto_trigger_logs_target_key'), table_name='risk_orchestrator_auto_trigger_logs')
    op.drop_index(op.f('ix_risk_orchestrator_auto_trigger_logs_severity'), table_name='risk_orchestrator_auto_trigger_logs')
    op.drop_index(op.f('ix_risk_orchestrator_auto_trigger_logs_created_at'), table_name='risk_orchestrator_auto_trigger_logs')
    op.drop_index(op.f('ix_risk_orchestrator_auto_trigger_logs_breach_type'), table_name='risk_orchestrator_auto_trigger_logs')
    op.drop_index(op.f('ix_risk_orchestrator_auto_trigger_logs_acknowledged_by'), table_name='risk_orchestrator_auto_trigger_logs')
    op.drop_table('risk_orchestrator_auto_trigger_logs')
    # ### end Alembic commands ###