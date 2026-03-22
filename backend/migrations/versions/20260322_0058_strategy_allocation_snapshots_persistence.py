"""strategy allocation snapshots persistence

Revision ID: 20260322_0058
Revises: 20260322_0057
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260322_0058"
down_revision = "20260322_0057"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "strategy_allocation_snapshots"):
        return

    op.create_table(
        "strategy_allocation_snapshots",
        sa.Column("snapshot_id", sa.String(length=120), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("strategy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_capital", sa.Float(), nullable=False, server_default="0"),
        sa.Column("used_capital", sa.Float(), nullable=False, server_default="0"),
        sa.Column("summary_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("rows_payload", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("revision_map", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("source_request_id", sa.String(length=120), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_index("ix_strategy_allocation_snapshots_created_at", "strategy_allocation_snapshots", ["created_at"])
    op.create_index("ix_strategy_allocation_snapshots_created_by", "strategy_allocation_snapshots", ["created_by"])
    op.create_index("ix_strategy_allocation_snapshots_source_request_id", "strategy_allocation_snapshots", ["source_request_id"])
    op.create_index("ix_strategy_allocation_snapshots_restored_by", "strategy_allocation_snapshots", ["restored_by"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "strategy_allocation_snapshots"):
        return

    op.drop_index("ix_strategy_allocation_snapshots_restored_by", table_name="strategy_allocation_snapshots")
    op.drop_index("ix_strategy_allocation_snapshots_source_request_id", table_name="strategy_allocation_snapshots")
    op.drop_index("ix_strategy_allocation_snapshots_created_by", table_name="strategy_allocation_snapshots")
    op.drop_index("ix_strategy_allocation_snapshots_created_at", table_name="strategy_allocation_snapshots")
    op.drop_table("strategy_allocation_snapshots")
