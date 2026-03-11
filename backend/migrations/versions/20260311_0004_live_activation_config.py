"""phase4 live activation config

Revision ID: 20260311_0004
Revises: 20260311_0003
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0004"
down_revision = "20260311_0003"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "live_activation_config"):
        op.create_table(
            "live_activation_config",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("exchange", sa.String(length=30), nullable=False),
            sa.Column("market_type", sa.String(length=20), nullable=False),
            sa.Column("safe_mode_enabled", sa.Boolean(), nullable=False),
            sa.Column("live_mode_enabled", sa.Boolean(), nullable=False),
            sa.Column("symbol_whitelist", sa.JSON(), nullable=False),
            sa.Column("max_position_pct", sa.Float(), nullable=False),
            sa.Column("leverage_cap", sa.Integer(), nullable=False),
            sa.Column("max_trades_per_hour", sa.Integer(), nullable=False),
            sa.Column("max_notional_exposure", sa.Float(), nullable=False),
            sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False),
            sa.Column("disable_futures", sa.Boolean(), nullable=False),
            sa.Column("ip_whitelist_ready", sa.Boolean(), nullable=False),
            sa.Column("trading_permission_ready", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "live_activation_config"):
        op.drop_table("live_activation_config")