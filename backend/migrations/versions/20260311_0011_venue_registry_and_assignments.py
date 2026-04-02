"""venue registry and assignment domain

Revision ID: 20260311_0011
Revises: 20260311_0010
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0011"
down_revision = "20260311_0010"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "exchange_registry"):
        op.create_table(
            "exchange_registry",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("exchange_code", sa.String(length=40), nullable=False),
            sa.Column("exchange_name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("supported_market_types", sa.JSON(), nullable=False),
            sa.Column("supports_live", sa.Boolean(), nullable=False),
            sa.Column("health_status", sa.String(length=20), nullable=False),
            sa.Column("rate_limit_status", sa.String(length=20), nullable=False),
            sa.Column("adapter_version", sa.String(length=40), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("exchange_code"),
        )
        op.create_index("ix_exchange_registry_exchange_code", "exchange_registry", ["exchange_code"], unique=True)

    if not _table_exists(bind, "exchange_capabilities"):
        op.create_table(
            "exchange_capabilities",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("exchange_code", sa.String(length=40), nullable=False),
            sa.Column("market_type", sa.String(length=20), nullable=False),
            sa.Column("supports_spot", sa.Boolean(), nullable=False),
            sa.Column("supports_futures", sa.Boolean(), nullable=False),
            sa.Column("supports_test_order", sa.Boolean(), nullable=False),
            sa.Column("supports_quote_qty", sa.Boolean(), nullable=False),
            sa.Column("supports_reduce_only", sa.Boolean(), nullable=False),
            sa.Column("supports_leverage", sa.Boolean(), nullable=False),
            sa.Column("supports_margin_mode", sa.Boolean(), nullable=False),
            sa.Column("supports_hedge_mode", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_exchange_capabilities_exchange_code", "exchange_capabilities", ["exchange_code"], unique=False)

    if not _table_exists(bind, "allowed_markets"):
        op.create_table(
            "allowed_markets",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("exchange_code", sa.String(length=40), nullable=False),
            sa.Column("market_type", sa.String(length=20), nullable=False),
            sa.Column("environment", sa.String(length=20), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_allowed_markets_exchange_code", "allowed_markets", ["exchange_code"], unique=False)

    if not _table_exists(bind, "user_venue_assignments"):
        op.create_table(
            "user_venue_assignments",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("exchange_code", sa.String(length=40), nullable=False),
            sa.Column("spot_allowed", sa.Boolean(), nullable=False),
            sa.Column("futures_allowed", sa.Boolean(), nullable=False),
            sa.Column("live_allowed", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_venue_assignments_user_id", "user_venue_assignments", ["user_id"], unique=False)
        op.create_index("ix_user_venue_assignments_exchange_code", "user_venue_assignments", ["exchange_code"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "user_venue_assignments"):
        op.drop_index("ix_user_venue_assignments_exchange_code", table_name="user_venue_assignments")
        op.drop_index("ix_user_venue_assignments_user_id", table_name="user_venue_assignments")
        op.drop_table("user_venue_assignments")

    if _table_exists(bind, "allowed_markets"):
        op.drop_index("ix_allowed_markets_exchange_code", table_name="allowed_markets")
        op.drop_table("allowed_markets")

    if _table_exists(bind, "exchange_capabilities"):
        op.drop_index("ix_exchange_capabilities_exchange_code", table_name="exchange_capabilities")
        op.drop_table("exchange_capabilities")

    if _table_exists(bind, "exchange_registry"):
        op.drop_index("ix_exchange_registry_exchange_code", table_name="exchange_registry")
        op.drop_table("exchange_registry")