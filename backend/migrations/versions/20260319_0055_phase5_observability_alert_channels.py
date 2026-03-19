"""phase5 observability alert channels

Revision ID: 20260319_0055
Revises: 20260319_0054
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260319_0055"
down_revision = "20260319_0054"
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
    if not _table_exists(bind, "alert_channel_configs"):
        return

    if not _has_column(bind, "alert_channel_configs", "sendgrid_api_key_encrypted"):
        op.add_column(
            "alert_channel_configs",
            sa.Column("sendgrid_api_key_encrypted", sa.Text(), nullable=False, server_default=""),
        )

    if not _has_column(bind, "alert_channel_configs", "telegram_bot_token_encrypted"):
        op.add_column(
            "alert_channel_configs",
            sa.Column("telegram_bot_token_encrypted", sa.Text(), nullable=False, server_default=""),
        )

    if not _has_column(bind, "alert_channel_configs", "telegram_chat_id"):
        op.add_column(
            "alert_channel_configs",
            sa.Column("telegram_chat_id", sa.String(length=255), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "alert_channel_configs"):
        return

    if _has_column(bind, "alert_channel_configs", "telegram_chat_id"):
        op.drop_column("alert_channel_configs", "telegram_chat_id")

    if _has_column(bind, "alert_channel_configs", "telegram_bot_token_encrypted"):
        op.drop_column("alert_channel_configs", "telegram_bot_token_encrypted")

    if _has_column(bind, "alert_channel_configs", "sendgrid_api_key_encrypted"):
        op.drop_column("alert_channel_configs", "sendgrid_api_key_encrypted")