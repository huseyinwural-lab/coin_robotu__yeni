"""indicator screener filter context columns

Revision ID: 20260313_0032
Revises: 20260312_0031
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0032"
down_revision = "20260312_0031"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_indicator_saved_queries"):
        if not _column_exists(bind, "user_indicator_saved_queries", "filter_snapshot"):
            op.add_column(
                "user_indicator_saved_queries",
                sa.Column("filter_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            )
        if not _column_exists(bind, "user_indicator_saved_queries", "schema_version"):
            op.add_column(
                "user_indicator_saved_queries",
                sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
            )

    if _table_exists(bind, "user_indicator_watchlist"):
        if not _column_exists(bind, "user_indicator_watchlist", "context_snapshot"):
            op.add_column(
                "user_indicator_watchlist",
                sa.Column("context_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            )


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_indicator_watchlist") and _column_exists(bind, "user_indicator_watchlist", "context_snapshot"):
        op.drop_column("user_indicator_watchlist", "context_snapshot")

    if _table_exists(bind, "user_indicator_saved_queries") and _column_exists(bind, "user_indicator_saved_queries", "schema_version"):
        op.drop_column("user_indicator_saved_queries", "schema_version")

    if _table_exists(bind, "user_indicator_saved_queries") and _column_exists(bind, "user_indicator_saved_queries", "filter_snapshot"):
        op.drop_column("user_indicator_saved_queries", "filter_snapshot")
