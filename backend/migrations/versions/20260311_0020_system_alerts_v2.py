"""system alerts v2

Revision ID: 20260311_0020
Revises: 20260311_0019
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "20260311_0020"
down_revision = "20260311_0019"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns(table_name)}
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "system_alerts"):
        if not _column_exists(bind, "system_alerts", "fingerprint"):
            op.add_column("system_alerts", sa.Column("fingerprint", sa.String(length=128), nullable=True))
            op.create_index("ix_system_alerts_fingerprint", "system_alerts", ["fingerprint"], unique=False)
        if not _column_exists(bind, "system_alerts", "entity_key"):
            op.add_column("system_alerts", sa.Column("entity_key", sa.String(length=120), nullable=True))
            op.create_index("ix_system_alerts_entity_key", "system_alerts", ["entity_key"], unique=False)
        if not _column_exists(bind, "system_alerts", "root_cause_code"):
            op.add_column("system_alerts", sa.Column("root_cause_code", sa.String(length=80), nullable=True))
        if not _column_exists(bind, "system_alerts", "state_key"):
            op.add_column("system_alerts", sa.Column("state_key", sa.String(length=120), nullable=True))
        if not _column_exists(bind, "system_alerts", "delivery_status"):
            op.add_column("system_alerts", sa.Column("delivery_status", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "system_alerts"):
        if _column_exists(bind, "system_alerts", "delivery_status"):
            op.drop_column("system_alerts", "delivery_status")
        if _column_exists(bind, "system_alerts", "state_key"):
            op.drop_column("system_alerts", "state_key")
        if _column_exists(bind, "system_alerts", "root_cause_code"):
            op.drop_column("system_alerts", "root_cause_code")
        if _column_exists(bind, "system_alerts", "entity_key"):
            op.drop_index("ix_system_alerts_entity_key", table_name="system_alerts")
            op.drop_column("system_alerts", "entity_key")
        if _column_exists(bind, "system_alerts", "fingerprint"):
            op.drop_index("ix_system_alerts_fingerprint", table_name="system_alerts")
            op.drop_column("system_alerts", "fingerprint")
