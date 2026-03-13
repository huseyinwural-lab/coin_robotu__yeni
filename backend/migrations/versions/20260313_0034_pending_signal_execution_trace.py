"""pending signal execution trace fields

Revision ID: 20260313_0034
Revises: 20260313_0033
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0034"
down_revision = "20260313_0033"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "pending_signals"):
        return

    additions = [
        ("previous_state", sa.Column("previous_state", sa.String(length=40), nullable=False, server_default="DETECTED")),
        ("current_state", sa.Column("current_state", sa.String(length=40), nullable=False, server_default="DETECTED")),
        ("blocked_reason_code", sa.Column("blocked_reason_code", sa.String(length=60), nullable=False, server_default="")),
        ("blocked_reason_message", sa.Column("blocked_reason_message", sa.String(length=220), nullable=False, server_default="")),
        ("blocked_solution_hint", sa.Column("blocked_solution_hint", sa.String(length=240), nullable=False, server_default="")),
        ("requires_manual_approval", sa.Column("requires_manual_approval", sa.Boolean(), nullable=False, server_default=sa.true())),
        ("execution_eligible", sa.Column("execution_eligible", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("bot_profile_id", sa.Column("bot_profile_id", sa.String(), nullable=True)),
        ("risk_policy_id", sa.Column("risk_policy_id", sa.String(), nullable=True)),
        ("exchange_connection_id", sa.Column("exchange_connection_id", sa.String(), nullable=True)),
        ("created_order_intent_id", sa.Column("created_order_intent_id", sa.String(), nullable=True)),
        ("runtime_owner", sa.Column("runtime_owner", sa.String(length=120), nullable=False, server_default="")),
        ("last_eligibility_check_at", sa.Column("last_eligibility_check_at", sa.DateTime(timezone=True), nullable=True)),
        ("last_transition_at", sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=True)),
    ]

    for column_name, column in additions:
        if not _column_exists(bind, "pending_signals", column_name):
            op.add_column("pending_signals", column)

    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("pending_signals")}
    if "ix_pending_signals_current_state" not in existing_indexes:
        op.create_index("ix_pending_signals_current_state", "pending_signals", ["current_state"])
    if "ix_pending_signals_bot_profile_id" not in existing_indexes:
        op.create_index("ix_pending_signals_bot_profile_id", "pending_signals", ["bot_profile_id"])
    if "ix_pending_signals_risk_policy_id" not in existing_indexes:
        op.create_index("ix_pending_signals_risk_policy_id", "pending_signals", ["risk_policy_id"])
    if "ix_pending_signals_exchange_connection_id" not in existing_indexes:
        op.create_index("ix_pending_signals_exchange_connection_id", "pending_signals", ["exchange_connection_id"])
    if "ix_pending_signals_created_order_intent_id" not in existing_indexes:
        op.create_index("ix_pending_signals_created_order_intent_id", "pending_signals", ["created_order_intent_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "pending_signals"):
        return

    for index_name in [
        "ix_pending_signals_created_order_intent_id",
        "ix_pending_signals_exchange_connection_id",
        "ix_pending_signals_risk_policy_id",
        "ix_pending_signals_bot_profile_id",
        "ix_pending_signals_current_state",
    ]:
        try:
            op.drop_index(index_name, table_name="pending_signals")
        except Exception:
            pass

    for column_name in [
        "last_transition_at",
        "last_eligibility_check_at",
        "runtime_owner",
        "created_order_intent_id",
        "exchange_connection_id",
        "risk_policy_id",
        "bot_profile_id",
        "execution_eligible",
        "requires_manual_approval",
        "blocked_solution_hint",
        "blocked_reason_message",
        "blocked_reason_code",
        "current_state",
        "previous_state",
    ]:
        if _column_exists(bind, "pending_signals", column_name):
            op.drop_column("pending_signals", column_name)
