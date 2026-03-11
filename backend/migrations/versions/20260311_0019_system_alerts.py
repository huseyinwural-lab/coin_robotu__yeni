"""system alerts

Revision ID: 20260311_0019
Revises: 20260311_0018
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "20260311_0019"
down_revision = "20260311_0018"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "system_alerts"):
        op.create_table(
            "system_alerts",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("alert_type", sa.String(length=80), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("occurrences", sa.Integer(), nullable=False),
            sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_system_alerts_alert_type", "system_alerts", ["alert_type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "system_alerts"):
        op.drop_index("ix_system_alerts_alert_type", table_name="system_alerts")
        op.drop_table("system_alerts")
