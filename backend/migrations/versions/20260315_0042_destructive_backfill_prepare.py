"""destructive drift backfill prepare

Revision ID: 20260315_0042
Revises: 20260315_0041
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0042"
down_revision = "20260315_0041"
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
        op.execute(sa.text("UPDATE bot_profiles SET is_running = 0 WHERE is_running IS NULL"))

    if _table_exists(bind, "strategy_observability_events") and _column_exists(bind, "strategy_observability_events", "created_at"):
        op.execute(sa.text("UPDATE strategy_observability_events SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

    if _table_exists(bind, "users"):
        if _column_exists(bind, "users", "updated_at"):
            op.execute(
                sa.text(
                    """
                    UPDATE users
                    SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)
                    WHERE updated_at IS NULL
                    """
                )
            )

        if _column_exists(bind, "users", "role"):
            op.execute(sa.text("UPDATE users SET role = 'user' WHERE role IS NULL"))
            op.execute(sa.text("UPDATE users SET role = 'super_admin' WHERE LOWER(role) = 'super_admin'"))
            op.execute(sa.text("UPDATE users SET role = 'admin' WHERE LOWER(role) = 'admin'"))
            op.execute(sa.text("UPDATE users SET role = 'ops' WHERE LOWER(role) = 'ops'"))
            op.execute(sa.text("UPDATE users SET role = 'user' WHERE LOWER(role) = 'user'"))
            op.execute(
                sa.text(
                    """
                    UPDATE users
                    SET role = 'user'
                    WHERE LOWER(role) NOT IN ('super_admin', 'admin', 'ops', 'user')
                    """
                )
            )


def downgrade() -> None:
    pass
