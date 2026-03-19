"""phase3 execution safety controls

Revision ID: 20260319_0054
Revises: 20260319_0053
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260319_0054"
down_revision = "20260319_0053"
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

    if not _has_column(bind, "live_activation_config", "trading_enabled"):
        op.add_column(
            "live_activation_config",
            sa.Column("trading_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if not _has_column(bind, "live_activation_config", "max_total_exposure"):
        op.add_column(
            "live_activation_config",
            sa.Column("max_total_exposure", sa.Float(), nullable=False, server_default="150"),
        )

    if not _has_column(bind, "live_activation_config", "max_active_positions"):
        op.add_column(
            "live_activation_config",
            sa.Column("max_active_positions", sa.Integer(), nullable=False, server_default="3"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "live_activation_config"):
        return

    if _has_column(bind, "live_activation_config", "max_active_positions"):
        op.drop_column("live_activation_config", "max_active_positions")

    if _has_column(bind, "live_activation_config", "max_total_exposure"):
        op.drop_column("live_activation_config", "max_total_exposure")

    if _has_column(bind, "live_activation_config", "trading_enabled"):
        op.drop_column("live_activation_config", "trading_enabled")
