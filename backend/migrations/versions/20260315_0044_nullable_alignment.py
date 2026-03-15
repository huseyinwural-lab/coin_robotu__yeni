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

    if _table_exists(bind, "bot_profiles") and _column_exists(bind, "bot_profiles", "is_running"):
        with op.batch_alter_table("bot_profiles") as batch_op:
            batch_op.alter_column("is_running", existing_type=sa.Boolean(), nullable=False)

    if _table_exists(bind, "strategy_observability_events") and _column_exists(bind, "strategy_observability_events", "created_at"):
        with op.batch_alter_table("strategy_observability_events") as batch_op:
            batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    if _table_exists(bind, "users") and _column_exists(bind, "users", "updated_at"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "users") and _column_exists(bind, "users", "updated_at"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=True)

    if _table_exists(bind, "strategy_observability_events") and _column_exists(bind, "strategy_observability_events", "created_at"):
        with op.batch_alter_table("strategy_observability_events") as batch_op:
            batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=True)

    if _table_exists(bind, "bot_profiles") and _column_exists(bind, "bot_profiles", "is_running"):
        with op.batch_alter_table("bot_profiles") as batch_op:
            batch_op.alter_column("is_running", existing_type=sa.Boolean(), nullable=True)
