"""canonical strategy extra contract fields

Revision ID: 20260313_0038
Revises: 20260313_0037
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0038"
down_revision = "20260313_0037"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    names = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in names


def upgrade() -> None:
    bind = op.get_bind()
    table_name = "canonical_strategy_registry"
    if not _table_exists(bind, table_name):
        return

    for column_name in ["stop_loss", "take_profit", "invalidation", "signal_score"]:
        if not _column_exists(bind, table_name, column_name):
            op.add_column(table_name, sa.Column(column_name, sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    bind = op.get_bind()
    table_name = "canonical_strategy_registry"
    if not _table_exists(bind, table_name):
        return

    for column_name in ["signal_score", "invalidation", "take_profit", "stop_loss"]:
        if _column_exists(bind, table_name, column_name):
            op.drop_column(table_name, column_name)
