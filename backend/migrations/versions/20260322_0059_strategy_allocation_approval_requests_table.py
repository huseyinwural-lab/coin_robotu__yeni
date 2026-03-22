"""strategy allocation approval requests table

Revision ID: 20260322_0059
Revises: 20260322_0058
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260322_0059"
down_revision = "20260322_0058"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "strategy_allocation_approval_requests"):
        return

    op.create_table(
        "strategy_allocation_approval_requests",
        sa.Column("request_id", sa.String(length=120), primary_key=True),
        sa.Column("request_type", sa.String(length=100), nullable=False, server_default="strategy_allocation"),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False, server_default="unknown"),
        sa.Column("target_id", sa.String(length=160), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_role", sa.String(length=80), nullable=True),
        sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("revision_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("stale_state", sa.String(length=40), nullable=True),
        sa.Column("stale_reason_code", sa.String(length=120), nullable=True),
        sa.Column("stale_conflicts", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejected_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_strategy_allocation_approval_requests_action_type", "strategy_allocation_approval_requests", ["action_type"])
    op.create_index("ix_strategy_allocation_approval_requests_status", "strategy_allocation_approval_requests", ["status"])
    op.create_index("ix_strategy_allocation_approval_requests_requested_by", "strategy_allocation_approval_requests", ["requested_by"])
    op.create_index("ix_strategy_allocation_approval_requests_created_at", "strategy_allocation_approval_requests", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "strategy_allocation_approval_requests"):
        return

    op.drop_index("ix_strategy_allocation_approval_requests_created_at", table_name="strategy_allocation_approval_requests")
    op.drop_index("ix_strategy_allocation_approval_requests_requested_by", table_name="strategy_allocation_approval_requests")
    op.drop_index("ix_strategy_allocation_approval_requests_status", table_name="strategy_allocation_approval_requests")
    op.drop_index("ix_strategy_allocation_approval_requests_action_type", table_name="strategy_allocation_approval_requests")
    op.drop_table("strategy_allocation_approval_requests")
