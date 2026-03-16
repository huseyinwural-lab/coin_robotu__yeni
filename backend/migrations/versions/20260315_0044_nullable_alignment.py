"""nullable alignment for destructive drift

Revision ID: 20260315_0044
Revises: 20260315_0043
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0044"
down_revision = "20260315_0043"
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

    # PostgreSQL hedefli migration akışında batch_alter_table gerekli değil.
    if _table_exists(bind, "bot_profiles") and _column_exists(bind, "bot_profiles", "is_running"):
        op.alter_column("bot_profiles", "is_running", existing_type=sa.Boolean(), nullable=False)

    if _table_exists(bind, "strategy_observability_events") and _column_exists(bind, "strategy_observability_events", "created_at"):
        op.alter_column("strategy_observability_events", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    if _table_exists(bind, "users") and _column_exists(bind, "users", "updated_at"):
        op.alter_column("users", "updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "users") and _column_exists(bind, "users", "updated_at"):
        op.alter_column("users", "updated_at", existing_type=sa.DateTime(timezone=True), nullable=True)

    if _table_exists(bind, "strategy_observability_events") and _column_exists(bind, "strategy_observability_events", "created_at"):
        op.alter_column("strategy_observability_events", "created_at", existing_type=sa.DateTime(timezone=True), nullable=True)

    if _table_exists(bind, "bot_profiles") and _column_exists(bind, "bot_profiles", "is_running"):
        op.alter_column("bot_profiles", "is_running", existing_type=sa.Boolean(), nullable=True)
