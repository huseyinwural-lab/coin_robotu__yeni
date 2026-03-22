"""execution control and recovery p0 schema

Revision ID: 20260322_0061
Revises: 20260322_0060
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260322_0061"
down_revision = "20260322_0060"
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


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if not _column_exists(bind, table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def _create_idempotency_collisions_table(bind) -> None:
    if _table_exists(bind, "idempotency_collisions"):
        return
    op.create_table(
        "idempotency_collisions",
        sa.Column("collision_id", sa.String(), primary_key=True),
        sa.Column("intent_id", sa.String(length=120), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("original_request", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("duplicate_request", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("correlation_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("resolution_action", sa.String(length=80), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(length=120), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index_if_missing("idempotency_collisions", "ix_idemp_collisions_intent", ["intent_id"])
    _create_index_if_missing("idempotency_collisions", "ix_idemp_collisions_key", ["idempotency_key"])
    _create_index_if_missing("idempotency_collisions", "ix_idemp_collisions_corr", ["correlation_id"])
    _create_index_if_missing("idempotency_collisions", "ix_idemp_collisions_status", ["status"])


def _create_execution_manual_actions_table(bind) -> None:
    if _table_exists(bind, "execution_manual_actions"):
        return
    op.create_table(
        "execution_manual_actions",
        sa.Column("action_id", sa.String(), primary_key=True),
        sa.Column("execution_event_id", sa.String(length=120), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("requested_role", sa.String(length=40), nullable=False, server_default="admin"),
        sa.Column("confirmation_phrase", sa.String(length=120), nullable=True),
        sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_prod_guard_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("idempotency_checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("replay_safe_checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index_if_missing("execution_manual_actions", "ix_exec_manual_event", ["execution_event_id"])
    _create_index_if_missing("execution_manual_actions", "ix_exec_manual_corr", ["correlation_id"])
    _create_index_if_missing("execution_manual_actions", "ix_exec_manual_type", ["action_type"])


def _create_execution_trace_index_table(bind) -> None:
    if _table_exists(bind, "execution_trace_index"):
        return
    op.create_table(
        "execution_trace_index",
        sa.Column("trace_id", sa.String(), primary_key=True),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column("execution_event_id", sa.String(length=120), nullable=True),
        sa.Column("intent_id", sa.String(length=120), nullable=True),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index_if_missing("execution_trace_index", "ix_exec_trace_corr", ["correlation_id"])
    _create_index_if_missing("execution_trace_index", "ix_exec_trace_event", ["execution_event_id"])
    _create_index_if_missing("execution_trace_index", "ix_exec_trace_intent", ["intent_id"])
    _create_index_if_missing("execution_trace_index", "ix_exec_trace_stage", ["stage"])


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_events"):
        _add_column_if_missing("execution_events", sa.Column("source_type", sa.String(length=20), nullable=False, server_default="production"))
        _add_column_if_missing("execution_events", sa.Column("environment", sa.String(length=20), nullable=False, server_default="production"))
        _add_column_if_missing("execution_events", sa.Column("correlation_id", sa.String(length=120), nullable=False, server_default=""))
        _add_column_if_missing("execution_events", sa.Column("triggered_by", sa.String(length=120), nullable=False, server_default="system"))
        _add_column_if_missing("execution_events", sa.Column("parent_event_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("execution_events", sa.Column("strategy_id", sa.String(length=80), nullable=True))
        _create_index_if_missing("execution_events", "ix_execution_events_source_type", ["source_type"])
        _create_index_if_missing("execution_events", "ix_execution_events_environment", ["environment"])
        _create_index_if_missing("execution_events", "ix_execution_events_correlation_id", ["correlation_id"])
        _create_index_if_missing("execution_events", "ix_execution_events_parent_event_id", ["parent_event_id"])
        _create_index_if_missing("execution_events", "ix_execution_events_strategy_id", ["strategy_id"])

    if _table_exists(bind, "execution_state_transitions"):
        _add_column_if_missing("execution_state_transitions", sa.Column("from_state", sa.String(length=30), nullable=True))
        _add_column_if_missing("execution_state_transitions", sa.Column("to_state", sa.String(length=30), nullable=True))
        _add_column_if_missing("execution_state_transitions", sa.Column("latency_ms", sa.Float(), nullable=True))
        _add_column_if_missing("execution_state_transitions", sa.Column("correlation_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("execution_state_transitions", sa.Column("source_type", sa.String(length=20), nullable=False, server_default="production"))
        _add_column_if_missing("execution_state_transitions", sa.Column("environment", sa.String(length=20), nullable=False, server_default="production"))
        _add_column_if_missing("execution_state_transitions", sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        _create_index_if_missing("execution_state_transitions", "ix_exec_trans_corr", ["correlation_id"])
        _create_index_if_missing("execution_state_transitions", "ix_exec_trans_source", ["source_type"])
        _create_index_if_missing("execution_state_transitions", "ix_exec_trans_env", ["environment"])

    if _table_exists(bind, "failed_events"):
        _add_column_if_missing("failed_events", sa.Column("failure_class", sa.String(length=40), nullable=False, server_default="downstream_error"))
        _add_column_if_missing("failed_events", sa.Column("dead_letter_reason", sa.Text(), nullable=True))
        _add_column_if_missing("failed_events", sa.Column("last_action_by", sa.String(length=120), nullable=True))
        _add_column_if_missing("failed_events", sa.Column("correlation_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("failed_events", sa.Column("retry_reason", sa.Text(), nullable=True))
        _add_column_if_missing("failed_events", sa.Column("error_details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        _create_index_if_missing("failed_events", "ix_failed_events_failure_class", ["failure_class"])
        _create_index_if_missing("failed_events", "ix_failed_events_correlation_id", ["correlation_id"])

    _create_idempotency_collisions_table(bind)
    _create_execution_manual_actions_table(bind)
    _create_execution_trace_index_table(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "execution_trace_index"):
        op.drop_table("execution_trace_index")
    if _table_exists(bind, "execution_manual_actions"):
        op.drop_table("execution_manual_actions")
    if _table_exists(bind, "idempotency_collisions"):
        op.drop_table("idempotency_collisions")
