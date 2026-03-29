"""execution safety environment policy and canceled normalization

Revision ID: 20260329_0097
Revises: 20260328_0096
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260329_0097"
down_revision = "20260328_0096"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "live_activation_config") and not _column_exists(bind, "live_activation_config", "environment_policy"):
        op.add_column(
            "live_activation_config",
            sa.Column("environment_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        )

    if _table_exists(bind, "execution_intents") and _column_exists(bind, "execution_intents", "status"):
        op.execute("UPDATE execution_intents SET status='CANCELED' WHERE upper(status)='CANCELLED'")

    if _table_exists(bind, "execution_intent_events") and _column_exists(bind, "execution_intent_events", "event_status"):
        op.execute("UPDATE execution_intent_events SET event_status='CANCELED' WHERE upper(event_status)='CANCELLED'")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "execution_intent_events") and _column_exists(bind, "execution_intent_events", "event_status"):
        op.execute("UPDATE execution_intent_events SET event_status='CANCELLED' WHERE upper(event_status)='CANCELED'")

    if _table_exists(bind, "execution_intents") and _column_exists(bind, "execution_intents", "status"):
        op.execute("UPDATE execution_intents SET status='CANCELLED' WHERE upper(status)='CANCELED'")

    if _table_exists(bind, "live_activation_config") and _column_exists(bind, "live_activation_config", "environment_policy"):
        op.drop_column("live_activation_config", "environment_policy")
