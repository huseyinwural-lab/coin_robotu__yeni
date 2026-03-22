"""strategy allocation revision audit fields

Revision ID: 20260322_0057
Revises: 20260320_0056
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260322_0057"
down_revision = "20260320_0056"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "strategy_allocations"):
        return

    if not _has_column(bind, "strategy_allocations", "revision_id"):
        op.add_column(
            "strategy_allocations",
            sa.Column("revision_id", sa.Integer(), nullable=False, server_default="1"),
        )

    if not _has_column(bind, "strategy_allocations", "updated_by"):
        op.add_column(
            "strategy_allocations",
            sa.Column("updated_by", sa.String(length=120), nullable=False, server_default="system"),
        )

    if not _has_column(bind, "strategy_allocations", "change_reason"):
        op.add_column(
            "strategy_allocations",
            sa.Column("change_reason", sa.Text(), nullable=False, server_default="manual_update"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "strategy_allocations"):
        return

    if _has_column(bind, "strategy_allocations", "change_reason"):
        op.drop_column("strategy_allocations", "change_reason")

    if _has_column(bind, "strategy_allocations", "updated_by"):
        op.drop_column("strategy_allocations", "updated_by")

    if _has_column(bind, "strategy_allocations", "revision_id"):
        op.drop_column("strategy_allocations", "revision_id")
