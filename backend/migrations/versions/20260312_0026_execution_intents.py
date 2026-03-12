"""execution intents queue model

Revision ID: 20260312_0026
Revises: 20260312_0025
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20260312_0026"
down_revision = "20260312_0025"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "user_execution_intents"):
        return

    op.create_table(
        "user_execution_intents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("source_ref_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PREVIEWED"),
        sa.Column("intent_token", sa.String(length=120), nullable=False),
        sa.Column("preview_hash", sa.String(length=120), nullable=False),
        sa.Column("queue_mode", sa.String(length=20), nullable=False, server_default="ASSISTED"),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("market_type", sa.String(length=20), nullable=False, server_default="spot"),
        sa.Column("side", sa.String(length=10), nullable=False, server_default="buy"),
        sa.Column("notional", sa.Float(), nullable=False, server_default="0"),
        sa.Column("normalized_order_payload", sa.JSON(), nullable=False),
        sa.Column("reject_reason_codes", sa.JSON(), nullable=False),
        sa.Column("risk_flags", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_user_id", sa.String(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intent_token"),
    )

    op.create_index("ix_user_execution_intents_user_id", "user_execution_intents", ["user_id"])
    op.create_index("ix_user_execution_intents_status", "user_execution_intents", ["status"])
    op.create_index("ix_user_execution_intents_intent_token", "user_execution_intents", ["intent_token"])
    op.create_index("ix_user_execution_intents_preview_hash", "user_execution_intents", ["preview_hash"])
    op.create_index("ix_user_execution_intents_symbol", "user_execution_intents", ["symbol"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "user_execution_intents"):
        return

    op.drop_index("ix_user_execution_intents_symbol", table_name="user_execution_intents")
    op.drop_index("ix_user_execution_intents_preview_hash", table_name="user_execution_intents")
    op.drop_index("ix_user_execution_intents_intent_token", table_name="user_execution_intents")
    op.drop_index("ix_user_execution_intents_status", table_name="user_execution_intents")
    op.drop_index("ix_user_execution_intents_user_id", table_name="user_execution_intents")
    op.drop_table("user_execution_intents")
