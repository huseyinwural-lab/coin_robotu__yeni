"""playbook execution state machine columns

Revision ID: 20260323_0063
Revises: 20260323_0062
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260323_0063"
down_revision = "20260323_0062"
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


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "playbook_execution_runs"):
        return

    _add_column_if_missing("playbook_execution_runs", sa.Column("step_index", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("playbook_execution_runs", sa.Column("total_steps", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("playbook_execution_runs", sa.Column("failure_reason", sa.Text(), nullable=True))
    _add_column_if_missing("playbook_execution_runs", sa.Column("parent_run_id", sa.String(), nullable=True))
    _add_column_if_missing("playbook_execution_runs", sa.Column("retry_attempt", sa.Integer(), nullable=False, server_default="0"))

    _create_index_if_missing("playbook_execution_runs", "ix_playbook_execution_runs_parent_run_id", ["parent_run_id"])
    _create_index_if_missing("playbook_execution_runs", "ix_playbook_execution_runs_retry_attempt", ["retry_attempt"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "playbook_execution_runs"):
        return

    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("playbook_execution_runs")}

    if _index_exists(bind, "playbook_execution_runs", "ix_playbook_execution_runs_retry_attempt"):
        op.drop_index("ix_playbook_execution_runs_retry_attempt", table_name="playbook_execution_runs")
    if _index_exists(bind, "playbook_execution_runs", "ix_playbook_execution_runs_parent_run_id"):
        op.drop_index("ix_playbook_execution_runs_parent_run_id", table_name="playbook_execution_runs")

    for column_name in ["retry_attempt", "parent_run_id", "failure_reason", "total_steps", "step_index"]:
        if column_name in existing_columns:
            op.drop_column("playbook_execution_runs", column_name)
