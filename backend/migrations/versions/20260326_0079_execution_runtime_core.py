"""execution runtime core tables

Revision ID: 20260326_0079
Revises: 20260325_0078
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0079"
down_revision = "20260325_0078"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "execution_jobs"):
        op.create_table(
            "execution_jobs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("idempotency_key", sa.String(length=160), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("side", sa.String(length=10), nullable=False),
            sa.Column("size", sa.Float(), nullable=False, server_default="0"),
            sa.Column("strategy_name", sa.String(length=80), nullable=False, server_default="runtime_strategy"),
            sa.Column("state", sa.String(length=30), nullable=False, server_default="CREATED"),
            sa.Column("reject_reason", sa.Text(), nullable=True),
            sa.Column("fail_reason", sa.Text(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_retry", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("queue_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("meta_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_state_transition_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("idempotency_key", name="uq_execution_jobs_idempotency_key"),
        )
        op.create_index("ix_execution_jobs_idempotency_key", "execution_jobs", ["idempotency_key"])
        op.create_index("ix_execution_jobs_user_id", "execution_jobs", ["user_id"])
        op.create_index("ix_execution_jobs_state", "execution_jobs", ["state"])
        op.create_index("ix_execution_jobs_user_state", "execution_jobs", ["user_id", "state"])

    if not _has_table(bind, "orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("execution_job_id", sa.String(), sa.ForeignKey("execution_jobs.id"), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("side", sa.String(length=10), nullable=False),
            sa.Column("size", sa.Float(), nullable=False, server_default="0"),
            sa.Column("state", sa.String(length=30), nullable=False, server_default="CREATED"),
            sa.Column("external_order_id", sa.String(length=120), nullable=True),
            sa.Column("avg_fill_price", sa.Float(), nullable=True),
            sa.Column("filled_size", sa.Float(), nullable=False, server_default="0"),
            sa.Column("reject_reason", sa.Text(), nullable=True),
            sa.Column("fail_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("partial_filled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_state_transition_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("external_order_id", name="uq_orders_external_order_id"),
        )
        op.create_index("ix_orders_execution_job_id", "orders", ["execution_job_id"])
        op.create_index("ix_orders_user_id", "orders", ["user_id"])
        op.create_index("ix_orders_state", "orders", ["state"])
        op.create_index("ix_orders_external_order_id", "orders", ["external_order_id"])
        op.create_index("ix_orders_user_state", "orders", ["user_id", "state"])

    if _has_table(bind, "positions"):
        for col_name, col in [
            ("external_order_id", sa.Column("external_order_id", sa.String(length=120), nullable=True)),
            ("last_state_transition_at", sa.Column("last_state_transition_at", sa.DateTime(timezone=True), nullable=True)),
            ("reject_reason", sa.Column("reject_reason", sa.Text(), nullable=True)),
            ("fail_reason", sa.Column("fail_reason", sa.Text(), nullable=True)),
        ]:
            if not _has_column(bind, "positions", col_name):
                op.add_column("positions", col)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "orders"):
        op.drop_table("orders")
    if _has_table(bind, "execution_jobs"):
        op.drop_table("execution_jobs")
