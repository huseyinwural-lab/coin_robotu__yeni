"""alert channel configs

Revision ID: 20260311_0023
Revises: 20260311_0022
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "20260311_0023"
down_revision = "20260311_0022"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "alert_channel_configs"):
        op.create_table(
            "alert_channel_configs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("resend_api_key_encrypted", sa.Text(), nullable=False, server_default=""),
            sa.Column("alert_from", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("alert_to", sa.Text(), nullable=False, server_default=""),
            sa.Column("slack_webhook_url_encrypted", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "alert_channel_configs"):
        op.drop_table("alert_channel_configs")
