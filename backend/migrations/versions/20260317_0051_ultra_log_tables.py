"""ultra log tables

Revision ID: 20260317_0051
Revises: 20260317_0050
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260317_0051"
down_revision = "20260317_0050"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any((idx.get("name") or "") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "ultra_log_configs"):
        op.create_table(
            "ultra_log_configs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("duration_option", sa.String(length=20), nullable=False, server_default="1h"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("max_normal_log_mb", sa.Integer(), nullable=False, server_default="1024"),
            sa.Column("max_ultra_log_mb", sa.Integer(), nullable=False, server_default="512"),
            sa.Column("ultra_log_dir", sa.Text(), nullable=False, server_default=""),
            sa.Column("auto_shutdown_reason", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("updated_by_user_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists(bind, "ultra_log_events"):
        op.create_table(
            "ultra_log_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("category", sa.String(length=40), nullable=False),
            sa.Column("event_name", sa.String(length=120), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
            sa.Column("request_id", sa.String(length=120), nullable=True),
            sa.Column("session_id", sa.String(length=120), nullable=True),
            sa.Column("path", sa.String(length=255), nullable=True),
            sa.Column("method", sa.String(length=20), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Float(), nullable=True),
            sa.Column("client_ip", sa.String(length=64), nullable=True),
            sa.Column("actor_user_id", sa.String(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    for table_name, index_name, columns in [
        ("ultra_log_events", "ix_ultra_log_events_category", ["category"]),
        ("ultra_log_events", "ix_ultra_log_events_event_name", ["event_name"]),
        ("ultra_log_events", "ix_ultra_log_events_request_id", ["request_id"]),
        ("ultra_log_events", "ix_ultra_log_events_session_id", ["session_id"]),
        ("ultra_log_events", "ix_ultra_log_events_created_at", ["created_at"]),
    ]:
        if not _index_exists(bind, table_name, index_name):
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "ultra_log_events"):
        for idx in [
            "ix_ultra_log_events_created_at",
            "ix_ultra_log_events_session_id",
            "ix_ultra_log_events_request_id",
            "ix_ultra_log_events_event_name",
            "ix_ultra_log_events_category",
        ]:
            if _index_exists(bind, "ultra_log_events", idx):
                op.drop_index(idx, table_name="ultra_log_events")
        op.drop_table("ultra_log_events")

    if _table_exists(bind, "ultra_log_configs"):
        op.drop_table("ultra_log_configs")
