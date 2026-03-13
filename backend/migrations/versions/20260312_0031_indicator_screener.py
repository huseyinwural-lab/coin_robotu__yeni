"""indicator screener schema

Revision ID: 20260312_0031
Revises: 20260312_0030
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20260312_0031"
down_revision = "20260312_0030"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "user_indicator_saved_queries"):
        op.create_table(
            "user_indicator_saved_queries",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("exchange", sa.String(length=30), nullable=False, server_default="binance"),
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="spot"),
            sa.Column("timeframe", sa.String(length=10), nullable=False, server_default="15m"),
            sa.Column("query_expression", sa.Text(), nullable=False, server_default=""),
            sa.Column("symbol_universe", sa.JSON(), nullable=False),
            sa.Column("result_limit", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_indicator_saved_queries_user_id", "user_indicator_saved_queries", ["user_id"])

    if not _table_exists(bind, "user_indicator_watchlist"):
        op.create_table(
            "user_indicator_watchlist",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("exchange", sa.String(length=30), nullable=False, server_default="binance"),
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="spot"),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "exchange", "market_type", "symbol", name="uq_user_indicator_watchlist_symbol"),
        )
        op.create_index("ix_user_indicator_watchlist_user_id", "user_indicator_watchlist", ["user_id"])
        op.create_index("ix_user_indicator_watchlist_symbol", "user_indicator_watchlist", ["symbol"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_indicator_watchlist"):
        op.drop_index("ix_user_indicator_watchlist_symbol", table_name="user_indicator_watchlist")
        op.drop_index("ix_user_indicator_watchlist_user_id", table_name="user_indicator_watchlist")
        op.drop_table("user_indicator_watchlist")

    if _table_exists(bind, "user_indicator_saved_queries"):
        op.drop_index("ix_user_indicator_saved_queries_user_id", table_name="user_indicator_saved_queries")
        op.drop_table("user_indicator_saved_queries")
