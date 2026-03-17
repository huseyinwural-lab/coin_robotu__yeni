"""bot profiles soft delete columns

Revision ID: 20260317_0050
Revises: 20260317_0049
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260317_0050"
down_revision = "20260317_0049"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any((col.get("name") or "") == column_name for col in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any((idx.get("name") or "") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "bot_profiles"):
        return

    if not _column_exists(bind, "bot_profiles", "is_deleted"):
        op.add_column("bot_profiles", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.execute(sa.text("UPDATE bot_profiles SET is_deleted = FALSE WHERE is_deleted IS NULL"))

    if not _column_exists(bind, "bot_profiles", "deleted_at"):
        op.add_column("bot_profiles", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    if not _index_exists(bind, "bot_profiles", "ix_bot_profiles_is_deleted"):
        op.create_index("ix_bot_profiles_is_deleted", "bot_profiles", ["is_deleted"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "bot_profiles"):
        return

    if _index_exists(bind, "bot_profiles", "ix_bot_profiles_is_deleted"):
        op.drop_index("ix_bot_profiles_is_deleted", table_name="bot_profiles")
    if _column_exists(bind, "bot_profiles", "deleted_at"):
        op.drop_column("bot_profiles", "deleted_at")
    if _column_exists(bind, "bot_profiles", "is_deleted"):
        op.drop_column("bot_profiles", "is_deleted")
