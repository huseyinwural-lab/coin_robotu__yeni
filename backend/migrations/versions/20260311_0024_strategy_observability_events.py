"""strategy observability events

Revision ID: 20260311_0024
Revises: 20260311_0023
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "20260311_0024"
down_revision = "20260311_0023"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "strategy_observability_events"):
        op.create_table(
            "strategy_observability_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("selection_cycle_id", sa.String(length=120), nullable=False),
            sa.Column("audit_log_id", sa.String(), nullable=True),
            sa.Column("bot_profile_id", sa.String(), nullable=True),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("strategy_id", sa.String(length=80), nullable=False),
            sa.Column("strategy_name", sa.String(length=120), nullable=False, server_default="SPOT_TREND_PULLBACK"),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("market_regime", sa.String(length=30), nullable=False, server_default="RANGING"),
            sa.Column("multiplier_version", sa.String(length=20), nullable=False, server_default="v1"),
            sa.Column("multiplier_set", sa.JSON(), nullable=False),
            sa.Column("base_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("adjusted_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("score_delta", sa.Float(), nullable=False, server_default="0"),
            sa.Column("selection_rank", sa.Integer(), nullable=True),
            sa.Column("trend_strength", sa.String(length=20), nullable=True),
            sa.Column("relative_volume", sa.Float(), nullable=True),
            sa.Column("hard_gate_pass", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("threshold_pass", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("rejection_reason", sa.String(length=120), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["audit_log_id"], ["audit_logs.id"]),
            sa.ForeignKeyConstraint(["bot_profile_id"], ["bot_profiles.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_strategy_observability_events_selection_cycle_id", "strategy_observability_events", ["selection_cycle_id"])
        op.create_index("ix_strategy_observability_events_audit_log_id", "strategy_observability_events", ["audit_log_id"])
        op.create_index("ix_strategy_observability_events_bot_profile_id", "strategy_observability_events", ["bot_profile_id"])
        op.create_index("ix_strategy_observability_events_user_id", "strategy_observability_events", ["user_id"])
        op.create_index("ix_strategy_observability_events_symbol", "strategy_observability_events", ["symbol"])
        op.create_index("ix_strategy_observability_events_strategy_id", "strategy_observability_events", ["strategy_id"])
        op.create_index("ix_strategy_observability_events_event_type", "strategy_observability_events", ["event_type"])
        op.create_index("ix_strategy_observability_events_market_regime", "strategy_observability_events", ["market_regime"])
        op.create_index("ix_strategy_observability_events_rejection_reason", "strategy_observability_events", ["rejection_reason"])
        op.create_index("ix_strategy_observability_events_created_at", "strategy_observability_events", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "strategy_observability_events"):
        op.drop_index("ix_strategy_observability_events_created_at", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_rejection_reason", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_market_regime", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_event_type", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_strategy_id", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_symbol", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_user_id", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_bot_profile_id", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_audit_log_id", table_name="strategy_observability_events")
        op.drop_index("ix_strategy_observability_events_selection_cycle_id", table_name="strategy_observability_events")
        op.drop_table("strategy_observability_events")
