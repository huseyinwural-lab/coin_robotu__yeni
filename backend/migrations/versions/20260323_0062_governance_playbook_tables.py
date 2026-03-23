"""governance and playbook execution tables

Revision ID: 20260323_0062
Revises: 20260322_0061
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260323_0062"
down_revision = "20260322_0061"
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


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _create_signal_governance_decisions(bind) -> None:
    if _table_exists(bind, "signal_governance_decisions"):
        _add_column_if_missing("signal_governance_decisions", sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"))
        _add_column_if_missing("signal_governance_decisions", sa.Column("reason", sa.Text(), nullable=True))
        _add_column_if_missing("signal_governance_decisions", sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        _add_column_if_missing("signal_governance_decisions", sa.Column("actor_id", sa.String(), nullable=True))
        _add_column_if_missing("signal_governance_decisions", sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("signal_governance_decisions", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("signal_governance_decisions", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    else:
        op.create_table(
            "signal_governance_decisions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("signal_id", sa.String(), sa.ForeignKey("strategy_observability_events.id"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("actor_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    _create_index_if_missing("signal_governance_decisions", "ix_signal_governance_decisions_signal_id", ["signal_id"], unique=True)
    _create_index_if_missing("signal_governance_decisions", "ix_signal_governance_decisions_status", ["status"])
    _create_index_if_missing("signal_governance_decisions", "ix_signal_governance_decisions_actor_id", ["actor_id"])


def _create_playbook_execution_runs(bind) -> None:
    if _table_exists(bind, "playbook_execution_runs"):
        _add_column_if_missing("playbook_execution_runs", sa.Column("preview_token", sa.String(length=120), nullable=True))
        _add_column_if_missing("playbook_execution_runs", sa.Column("chain_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("playbook_execution_runs", sa.Column("execution_state", sa.String(length=30), nullable=False, server_default="preview"))
        _add_column_if_missing("playbook_execution_runs", sa.Column("steps", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
        _add_column_if_missing("playbook_execution_runs", sa.Column("scope_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        _add_column_if_missing("playbook_execution_runs", sa.Column("approved_by", sa.String(), nullable=True))
        _add_column_if_missing("playbook_execution_runs", sa.Column("executed_by", sa.String(), nullable=True))
        _add_column_if_missing("playbook_execution_runs", sa.Column("created_by", sa.String(), nullable=True))
        _add_column_if_missing("playbook_execution_runs", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("playbook_execution_runs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    else:
        op.create_table(
            "playbook_execution_runs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("preview_token", sa.String(length=120), nullable=False),
            sa.Column("chain_id", sa.String(length=120), nullable=False),
            sa.Column("execution_state", sa.String(length=30), nullable=False, server_default="preview"),
            sa.Column("steps", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("scope_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("approved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("executed_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    _create_index_if_missing("playbook_execution_runs", "ix_playbook_execution_runs_preview_token", ["preview_token"], unique=True)
    _create_index_if_missing("playbook_execution_runs", "ix_playbook_execution_runs_chain_id", ["chain_id"])
    _create_index_if_missing("playbook_execution_runs", "ix_playbook_execution_runs_execution_state", ["execution_state"])
    _create_index_if_missing("playbook_execution_runs", "ix_playbook_execution_runs_created_by", ["created_by"])
    _create_index_if_missing("playbook_execution_runs", "ix_playbook_execution_runs_approved_by", ["approved_by"])
    _create_index_if_missing("playbook_execution_runs", "ix_playbook_execution_runs_executed_by", ["executed_by"])


def _create_playbook_rollback_markers(bind) -> None:
    if _table_exists(bind, "playbook_rollback_markers"):
        _add_column_if_missing("playbook_rollback_markers", sa.Column("playbook_run_id", sa.String(), nullable=True))
        _add_column_if_missing("playbook_rollback_markers", sa.Column("chain_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("playbook_rollback_markers", sa.Column("execution_state", sa.String(length=30), nullable=False, server_default="planned"))
        _add_column_if_missing("playbook_rollback_markers", sa.Column("rollback_state", sa.String(length=30), nullable=False, server_default="ready"))
        _add_column_if_missing("playbook_rollback_markers", sa.Column("rollback_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        _add_column_if_missing("playbook_rollback_markers", sa.Column("created_by", sa.String(), nullable=True))
        _add_column_if_missing("playbook_rollback_markers", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("playbook_rollback_markers", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    else:
        op.create_table(
            "playbook_rollback_markers",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("playbook_run_id", sa.String(), sa.ForeignKey("playbook_execution_runs.id"), nullable=False),
            sa.Column("chain_id", sa.String(length=120), nullable=False),
            sa.Column("execution_state", sa.String(length=30), nullable=False, server_default="planned"),
            sa.Column("rollback_state", sa.String(length=30), nullable=False, server_default="ready"),
            sa.Column("rollback_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    _create_index_if_missing("playbook_rollback_markers", "ix_playbook_rollback_markers_playbook_run_id", ["playbook_run_id"])
    _create_index_if_missing("playbook_rollback_markers", "ix_playbook_rollback_markers_chain_id", ["chain_id"])
    _create_index_if_missing("playbook_rollback_markers", "ix_playbook_rollback_markers_execution_state", ["execution_state"])
    _create_index_if_missing("playbook_rollback_markers", "ix_playbook_rollback_markers_rollback_state", ["rollback_state"])
    _create_index_if_missing("playbook_rollback_markers", "ix_playbook_rollback_markers_created_by", ["created_by"])


def upgrade() -> None:
    bind = op.get_bind()
    _create_signal_governance_decisions(bind)
    _create_playbook_execution_runs(bind)
    _create_playbook_rollback_markers(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "playbook_rollback_markers"):
        op.drop_table("playbook_rollback_markers")
    if _table_exists(bind, "playbook_execution_runs"):
        op.drop_table("playbook_execution_runs")
    if _table_exists(bind, "signal_governance_decisions"):
        op.drop_table("signal_governance_decisions")