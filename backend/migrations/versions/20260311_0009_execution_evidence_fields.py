"""execution evidence fields and lifecycle events

Revision ID: 20260311_0009
Revises: 20260311_0008
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0009"
down_revision = "20260311_0008"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_exchange_settings") and not _column_exists(bind, "user_exchange_settings", "validation_snapshot_id"):
        op.add_column("user_exchange_settings", sa.Column("validation_snapshot_id", sa.String(length=120), nullable=True))

    if _table_exists(bind, "execution_metrics"):
        columns_to_add = [
            ("client_order_id", sa.Column("client_order_id", sa.String(length=120), nullable=True)),
            ("final_status", sa.Column("final_status", sa.String(length=30), nullable=True)),
            ("failure_code", sa.Column("failure_code", sa.String(length=40), nullable=True)),
            ("submitted_at", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)),
            ("ack_at", sa.Column("ack_at", sa.DateTime(timezone=True), nullable=True)),
            ("final_at", sa.Column("final_at", sa.DateTime(timezone=True), nullable=True)),
            ("validation_snapshot_id", sa.Column("validation_snapshot_id", sa.String(length=120), nullable=True)),
            ("raw_exchange_status", sa.Column("raw_exchange_status", sa.JSON(), nullable=True)),
        ]
        for name, column in columns_to_add:
            if not _column_exists(bind, "execution_metrics", name):
                op.add_column("execution_metrics", column)

        op.execute(sa.text("UPDATE execution_metrics SET client_order_id = '' WHERE client_order_id IS NULL"))
        op.execute(sa.text("UPDATE execution_metrics SET final_status = status WHERE final_status IS NULL"))
        op.execute(sa.text("UPDATE execution_metrics SET raw_exchange_status = '{}' WHERE raw_exchange_status IS NULL"))

        op.alter_column("execution_metrics", "client_order_id", existing_type=sa.String(length=120), nullable=False, server_default="")
        op.alter_column("execution_metrics", "final_status", existing_type=sa.String(length=30), nullable=False, server_default="NEW")
        op.alter_column("execution_metrics", "raw_exchange_status", existing_type=sa.JSON(), nullable=False)

    if not _table_exists(bind, "execution_lifecycle_events"):
        op.create_table(
            "execution_lifecycle_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("execution_metric_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("event_name", sa.String(length=40), nullable=False),
            sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["execution_metric_id"], ["execution_metrics.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_execution_lifecycle_events_execution_metric_id", "execution_lifecycle_events", ["execution_metric_id"], unique=False)
        op.create_index("ix_execution_lifecycle_events_user_id", "execution_lifecycle_events", ["user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_lifecycle_events"):
        op.drop_index("ix_execution_lifecycle_events_user_id", table_name="execution_lifecycle_events")
        op.drop_index("ix_execution_lifecycle_events_execution_metric_id", table_name="execution_lifecycle_events")
        op.drop_table("execution_lifecycle_events")

    if _table_exists(bind, "execution_metrics"):
        if _column_exists(bind, "execution_metrics", "raw_exchange_status"):
            op.drop_column("execution_metrics", "raw_exchange_status")
        if _column_exists(bind, "execution_metrics", "validation_snapshot_id"):
            op.drop_column("execution_metrics", "validation_snapshot_id")
        if _column_exists(bind, "execution_metrics", "final_at"):
            op.drop_column("execution_metrics", "final_at")
        if _column_exists(bind, "execution_metrics", "ack_at"):
            op.drop_column("execution_metrics", "ack_at")
        if _column_exists(bind, "execution_metrics", "submitted_at"):
            op.drop_column("execution_metrics", "submitted_at")
        if _column_exists(bind, "execution_metrics", "failure_code"):
            op.drop_column("execution_metrics", "failure_code")
        if _column_exists(bind, "execution_metrics", "final_status"):
            op.drop_column("execution_metrics", "final_status")
        if _column_exists(bind, "execution_metrics", "client_order_id"):
            op.drop_column("execution_metrics", "client_order_id")

    if _table_exists(bind, "user_exchange_settings") and _column_exists(bind, "user_exchange_settings", "validation_snapshot_id"):
        op.drop_column("user_exchange_settings", "validation_snapshot_id")