"""add testnet_allowed to user venue assignments

Revision ID: 20260405_2101_user_venue_assignment_testnet_allowed
Revises: 20260330_2100_strategy_template_lifecycle
Create Date: 2026-04-05 21:01:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260405_2101_user_venue_assignment_testnet_allowed"
down_revision = "20260330_2100_strategy_template_lifecycle"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        cols = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(str(col.get("name")) == column_name for col in cols)


def upgrade() -> None:
    if not _has_column("user_venue_assignments", "testnet_allowed"):
        op.add_column(
            "user_venue_assignments",
            sa.Column("testnet_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    if _has_column("user_venue_assignments", "testnet_allowed"):
        op.drop_column("user_venue_assignments", "testnet_allowed")
