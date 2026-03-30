"""add bot runtime/source fields

Revision ID: 20260330_1900_bot_runtime_fields
Revises: 20260317_0050_bot_profiles_soft_delete
Create Date: 2026-03-30 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260330_1900_bot_runtime_fields"
down_revision = "20260329_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bot_profiles", sa.Column("symbol_source_type", sa.String(length=20), nullable=False, server_default="manual"))
    op.add_column("bot_profiles", sa.Column("scanner_id", sa.String(length=120), nullable=True))
    op.add_column("bot_profiles", sa.Column("symbol_resolution_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("bot_profiles", sa.Column("strategy_template_id", sa.String(length=120), nullable=True))
    op.create_index("ix_bot_profiles_scanner_id", "bot_profiles", ["scanner_id"], unique=False)
    op.create_index("ix_bot_profiles_strategy_template_id", "bot_profiles", ["strategy_template_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bot_profiles_strategy_template_id", table_name="bot_profiles")
    op.drop_index("ix_bot_profiles_scanner_id", table_name="bot_profiles")
    op.drop_column("bot_profiles", "strategy_template_id")
    op.drop_column("bot_profiles", "symbol_resolution_snapshot")
    op.drop_column("bot_profiles", "scanner_id")
    op.drop_column("bot_profiles", "symbol_source_type")
