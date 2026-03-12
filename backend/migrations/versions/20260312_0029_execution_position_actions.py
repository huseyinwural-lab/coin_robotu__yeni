"""execution advanced position actions schema

Revision ID: 20260312_0029
Revises: 20260312_0028
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20260312_0029"
down_revision = "20260312_0028"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_execution_intents"):
        if not _column_exists(bind, "user_execution_intents", "intent_type"):
            op.add_column(
                "user_execution_intents",
                sa.Column("intent_type", sa.String(length=40), nullable=False, server_default="OPEN_POSITION"),
            )
        if not _column_exists(bind, "user_execution_intents", "position_id"):
            op.add_column("user_execution_intents", sa.Column("position_id", sa.String(length=120), nullable=True))
            op.create_index("ix_user_execution_intents_position_id", "user_execution_intents", ["position_id"])
        if not _column_exists(bind, "user_execution_intents", "size"):
            op.add_column("user_execution_intents", sa.Column("size", sa.Float(), nullable=False, server_default="0"))
        if not _column_exists(bind, "user_execution_intents", "reduce_only"):
            op.add_column("user_execution_intents", sa.Column("reduce_only", sa.Boolean(), nullable=False, server_default=sa.false()))
        if not _column_exists(bind, "user_execution_intents", "price"):
            op.add_column("user_execution_intents", sa.Column("price", sa.Float(), nullable=True))
        if not _column_exists(bind, "user_execution_intents", "stop_price"):
            op.add_column("user_execution_intents", sa.Column("stop_price", sa.Float(), nullable=True))
        if not _column_exists(bind, "user_execution_intents", "take_profit_price"):
            op.add_column("user_execution_intents", sa.Column("take_profit_price", sa.Float(), nullable=True))

    if _table_exists(bind, "user_decision_traces"):
        if not _column_exists(bind, "user_decision_traces", "position_action_reason"):
            op.add_column("user_decision_traces", sa.Column("position_action_reason", sa.String(length=120), nullable=True))
        if not _column_exists(bind, "user_decision_traces", "risk_adjustment_reason"):
            op.add_column("user_decision_traces", sa.Column("risk_adjustment_reason", sa.String(length=120), nullable=True))
        if not _column_exists(bind, "user_decision_traces", "strategy_override_reason"):
            op.add_column("user_decision_traces", sa.Column("strategy_override_reason", sa.String(length=120), nullable=True))

    if not _table_exists(bind, "positions"):
        op.create_table(
            "positions",
            sa.Column("position_id", sa.String(length=120), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("size", sa.Float(), nullable=False, server_default="0"),
            sa.Column("entry_price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("current_price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("unrealized_pnl", sa.Float(), nullable=False, server_default="0"),
            sa.Column("leverage", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("strategy_id", sa.String(length=80), nullable=True),
            sa.Column("cluster_id", sa.String(length=40), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("position_id"),
        )
        op.create_index("ix_positions_user_id", "positions", ["user_id"])
        op.create_index("ix_positions_symbol", "positions", ["symbol"])
        op.create_index("ix_positions_strategy_id", "positions", ["strategy_id"])
        op.create_index("ix_positions_cluster_id", "positions", ["cluster_id"])
        op.create_index("ix_positions_status", "positions", ["status"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "positions"):
        op.drop_index("ix_positions_status", table_name="positions")
        op.drop_index("ix_positions_cluster_id", table_name="positions")
        op.drop_index("ix_positions_strategy_id", table_name="positions")
        op.drop_index("ix_positions_symbol", table_name="positions")
        op.drop_index("ix_positions_user_id", table_name="positions")
        op.drop_table("positions")

    if _table_exists(bind, "user_decision_traces"):
        if _column_exists(bind, "user_decision_traces", "strategy_override_reason"):
            op.drop_column("user_decision_traces", "strategy_override_reason")
        if _column_exists(bind, "user_decision_traces", "risk_adjustment_reason"):
            op.drop_column("user_decision_traces", "risk_adjustment_reason")
        if _column_exists(bind, "user_decision_traces", "position_action_reason"):
            op.drop_column("user_decision_traces", "position_action_reason")

    if _table_exists(bind, "user_execution_intents"):
        if _column_exists(bind, "user_execution_intents", "take_profit_price"):
            op.drop_column("user_execution_intents", "take_profit_price")
        if _column_exists(bind, "user_execution_intents", "stop_price"):
            op.drop_column("user_execution_intents", "stop_price")
        if _column_exists(bind, "user_execution_intents", "price"):
            op.drop_column("user_execution_intents", "price")
        if _column_exists(bind, "user_execution_intents", "reduce_only"):
            op.drop_column("user_execution_intents", "reduce_only")
        if _column_exists(bind, "user_execution_intents", "size"):
            op.drop_column("user_execution_intents", "size")
        if _column_exists(bind, "user_execution_intents", "position_id"):
            op.drop_index("ix_user_execution_intents_position_id", table_name="user_execution_intents")
            op.drop_column("user_execution_intents", "position_id")
        if _column_exists(bind, "user_execution_intents", "intent_type"):
            op.drop_column("user_execution_intents", "intent_type")
