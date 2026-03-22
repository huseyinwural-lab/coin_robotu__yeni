"""revert and explainability columns for governance requests

Revision ID: 20260322_0060
Revises: 20260322_0059
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260322_0060"
down_revision = "20260322_0059"
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


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    if _column_exists(bind, table_name, column_name):
        op.drop_column(table_name, column_name)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "decision_approval_requests"):
        _add_column_if_missing("decision_approval_requests", sa.Column("target_type", sa.String(length=80), nullable=True))
        _add_column_if_missing("decision_approval_requests", sa.Column("target_id", sa.String(length=160), nullable=True))
        _add_column_if_missing("decision_approval_requests", sa.Column("explanation_summary", sa.Text(), nullable=False, server_default=""))
        _add_column_if_missing("decision_approval_requests", sa.Column("decision_factors", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        _add_column_if_missing("decision_approval_requests", sa.Column("previous_state_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        _add_column_if_missing("decision_approval_requests", sa.Column("source_request_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("decision_approval_requests", sa.Column("linked_revert_request_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("decision_approval_requests", sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("decision_approval_requests", sa.Column("reverted_by", sa.String(length=120), nullable=True))
        _add_column_if_missing("decision_approval_requests", sa.Column("revert_reason", sa.Text(), nullable=True))

        _create_index_if_missing("decision_approval_requests", "ix_decision_approval_requests_target_type", ["target_type"])
        _create_index_if_missing("decision_approval_requests", "ix_decision_approval_requests_target_id", ["target_id"])
        _create_index_if_missing("decision_approval_requests", "ix_decision_approval_requests_source_request_id", ["source_request_id"])
        _create_index_if_missing("decision_approval_requests", "ix_decision_approval_requests_linked_revert_request_id", ["linked_revert_request_id"])
        _create_index_if_missing("decision_approval_requests", "ix_decision_approval_requests_reverted_by", ["reverted_by"])

    if _table_exists(bind, "strategy_allocation_approval_requests"):
        _add_column_if_missing("strategy_allocation_approval_requests", sa.Column("explanation_summary", sa.Text(), nullable=False, server_default=""))
        _add_column_if_missing("strategy_allocation_approval_requests", sa.Column("decision_factors", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        _add_column_if_missing("strategy_allocation_approval_requests", sa.Column("previous_state_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        _add_column_if_missing("strategy_allocation_approval_requests", sa.Column("source_request_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("strategy_allocation_approval_requests", sa.Column("linked_revert_request_id", sa.String(length=120), nullable=True))
        _add_column_if_missing("strategy_allocation_approval_requests", sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing("strategy_allocation_approval_requests", sa.Column("reverted_by", sa.String(length=120), nullable=True))
        _add_column_if_missing("strategy_allocation_approval_requests", sa.Column("revert_reason", sa.Text(), nullable=True))

        _create_index_if_missing("strategy_allocation_approval_requests", "ix_alloc_appr_src_req", ["source_request_id"])
        _create_index_if_missing("strategy_allocation_approval_requests", "ix_alloc_appr_lnk_rev", ["linked_revert_request_id"])
        _create_index_if_missing("strategy_allocation_approval_requests", "ix_alloc_appr_reverted_by", ["reverted_by"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "strategy_allocation_approval_requests"):
        _drop_column_if_exists("strategy_allocation_approval_requests", "revert_reason")
        _drop_column_if_exists("strategy_allocation_approval_requests", "reverted_by")
        _drop_column_if_exists("strategy_allocation_approval_requests", "reverted_at")
        _drop_column_if_exists("strategy_allocation_approval_requests", "linked_revert_request_id")
        _drop_column_if_exists("strategy_allocation_approval_requests", "source_request_id")
        _drop_column_if_exists("strategy_allocation_approval_requests", "previous_state_snapshot")
        _drop_column_if_exists("strategy_allocation_approval_requests", "decision_factors")
        _drop_column_if_exists("strategy_allocation_approval_requests", "explanation_summary")

    if _table_exists(bind, "decision_approval_requests"):
        _drop_column_if_exists("decision_approval_requests", "revert_reason")
        _drop_column_if_exists("decision_approval_requests", "reverted_by")
        _drop_column_if_exists("decision_approval_requests", "reverted_at")
        _drop_column_if_exists("decision_approval_requests", "linked_revert_request_id")
        _drop_column_if_exists("decision_approval_requests", "source_request_id")
        _drop_column_if_exists("decision_approval_requests", "previous_state_snapshot")
        _drop_column_if_exists("decision_approval_requests", "decision_factors")
        _drop_column_if_exists("decision_approval_requests", "explanation_summary")
        _drop_column_if_exists("decision_approval_requests", "target_id")
        _drop_column_if_exists("decision_approval_requests", "target_type")
