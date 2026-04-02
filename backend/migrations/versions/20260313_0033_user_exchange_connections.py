"""user exchange connections multi-account model

Revision ID: 20260313_0033
Revises: 20260313_0032
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0033"
down_revision = "20260313_0032"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "user_exchange_connections"):
        return

    op.create_table(
        "user_exchange_connections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("account_label", sa.String(length=80), nullable=False, server_default="default"),
        sa.Column("exchange", sa.String(length=30), nullable=False, server_default="binance"),
        sa.Column("market_type", sa.String(length=20), nullable=False, server_default="spot"),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("readiness_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("permission_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("api_secret_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_exchange_connections_user_id", "user_exchange_connections", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "user_exchange_connections"):
        return

    op.drop_index("ix_user_exchange_connections_user_id", table_name="user_exchange_connections")
    op.drop_table("user_exchange_connections")
