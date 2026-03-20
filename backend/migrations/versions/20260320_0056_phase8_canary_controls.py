"""phase8 canary controls

Revision ID: 20260320_0056
Revises: 20260319_0055
Create Date: 2026-03-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260320_0056"
down_revision = "20260319_0055"
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
    if not _table_exists(bind, "live_activation_config"):
        return

    if not _has_column(bind, "live_activation_config", "canary_enabled"):
        op.add_column(
            "live_activation_config",
            sa.Column("canary_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if not _has_column(bind, "live_activation_config", "canary_symbols"):
        op.add_column(
            "live_activation_config",
            sa.Column("canary_symbols", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        )

    if not _has_column(bind, "live_activation_config", "canary_max_capital_usdt"):
        op.add_column(
            "live_activation_config",
            sa.Column("canary_max_capital_usdt", sa.Float(), nullable=False, server_default="50"),
        )

    if not _has_column(bind, "live_activation_config", "canary_max_positions"):
        op.add_column(
            "live_activation_config",
            sa.Column("canary_max_positions", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "live_activation_config"):
        return

    if _has_column(bind, "live_activation_config", "canary_max_positions"):
        op.drop_column("live_activation_config", "canary_max_positions")

    if _has_column(bind, "live_activation_config", "canary_max_capital_usdt"):
        op.drop_column("live_activation_config", "canary_max_capital_usdt")

    if _has_column(bind, "live_activation_config", "canary_symbols"):
        op.drop_column("live_activation_config", "canary_symbols")

    if _has_column(bind, "live_activation_config", "canary_enabled"):
        op.drop_column("live_activation_config", "canary_enabled")
