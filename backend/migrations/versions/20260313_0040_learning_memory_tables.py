"""learning memory tables

Revision ID: 20260313_0040
Revises: 20260313_0039
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0040"
down_revision = "20260313_0039"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "learning_decision_events"):
        op.create_table(
            "learning_decision_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("decision", sa.String(length=20), nullable=False, server_default="NO_TRADE"),
            sa.Column("source_strategies", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("family_scores", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("regime_snapshot", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("risk_snapshot", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("entry_price", sa.Float(), nullable=True),
            sa.Column("exit_price", sa.Float(), nullable=True),
            sa.Column("max_favorable_excursion", sa.Float(), nullable=False, server_default="0"),
            sa.Column("max_adverse_excursion", sa.Float(), nullable=False, server_default="0"),
            sa.Column("hold_duration_minutes", sa.Float(), nullable=False, server_default="0"),
            sa.Column("outcome_label", sa.String(length=20), nullable=False, server_default="OPEN"),
            sa.Column("pnl_normalized", sa.Float(), nullable=False, server_default="0"),
            sa.Column("stop_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("tp_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("timed_exit", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("invalidated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("strategy_id", sa.String(length=120), nullable=True),
            sa.Column("strategy_family", sa.String(length=40), nullable=True),
            sa.Column("scanner_result_id", sa.String(), nullable=True),
            sa.Column("pending_signal_id", sa.String(), nullable=True),
            sa.Column("position_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["scanner_result_id"], ["user_scanner_results.id"]),
            sa.ForeignKeyConstraint(["pending_signal_id"], ["pending_signals.id"]),
            sa.ForeignKeyConstraint(["position_id"], ["paper_positions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("scanner_result_id"),
            sa.UniqueConstraint("pending_signal_id"),
        )
        op.create_index("ix_learning_decision_events_symbol", "learning_decision_events", ["symbol"])
        op.create_index("ix_learning_decision_events_decision", "learning_decision_events", ["decision"])
        op.create_index("ix_learning_decision_events_outcome_label", "learning_decision_events", ["outcome_label"])
        op.create_index("ix_learning_decision_events_created_at", "learning_decision_events", ["created_at"])

    if not _table_exists(bind, "strategy_outcome_memory"):
        op.create_table(
            "strategy_outcome_memory",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("strategy_id", sa.String(length=120), nullable=False),
            sa.Column("direction", sa.String(length=10), nullable=False, server_default="both"),
            sa.Column("regime", sa.String(length=30), nullable=False, server_default="any"),
            sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("hit_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_return", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_mfe", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_mae", sa.Float(), nullable=False, server_default="0"),
            sa.Column("false_allow_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("false_reject_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("recent_rolling_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("decay_adjusted_quality_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_strategy_outcome_memory_strategy_id", "strategy_outcome_memory", ["strategy_id"])

    if not _table_exists(bind, "family_outcome_memory"):
        op.create_table(
            "family_outcome_memory",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("family", sa.String(length=30), nullable=False),
            sa.Column("regime", sa.String(length=30), nullable=False, server_default="any"),
            sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("hit_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_return", sa.Float(), nullable=False, server_default="0"),
            sa.Column("volatility_success", sa.Float(), nullable=False, server_default="0"),
            sa.Column("conflict_success", sa.Float(), nullable=False, server_default="0"),
            sa.Column("solo_vs_combo_success", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_family_outcome_memory_family", "family_outcome_memory", ["family"])

    if not _table_exists(bind, "learning_recommendations"):
        op.create_table(
            "learning_recommendations",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("strategy_id", sa.String(length=120), nullable=True),
            sa.Column("family", sa.String(length=30), nullable=True),
            sa.Column("recommendation_type", sa.String(length=30), nullable=False),
            sa.Column("recommendation_value", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("note", sa.String(length=280), nullable=False, server_default=""),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="medium"),
            sa.Column("is_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_learning_recommendations_strategy_id", "learning_recommendations", ["strategy_id"])
        op.create_index("ix_learning_recommendations_family", "learning_recommendations", ["family"])
        op.create_index("ix_learning_recommendations_type", "learning_recommendations", ["recommendation_type"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "learning_recommendations"):
        for index_name in [
            "ix_learning_recommendations_type",
            "ix_learning_recommendations_family",
            "ix_learning_recommendations_strategy_id",
        ]:
            try:
                op.drop_index(index_name, table_name="learning_recommendations")
            except Exception:
                pass
        op.drop_table("learning_recommendations")

    if _table_exists(bind, "family_outcome_memory"):
        try:
            op.drop_index("ix_family_outcome_memory_family", table_name="family_outcome_memory")
        except Exception:
            pass
        op.drop_table("family_outcome_memory")

    if _table_exists(bind, "strategy_outcome_memory"):
        try:
            op.drop_index("ix_strategy_outcome_memory_strategy_id", table_name="strategy_outcome_memory")
        except Exception:
            pass
        op.drop_table("strategy_outcome_memory")

    if _table_exists(bind, "learning_decision_events"):
        for index_name in [
            "ix_learning_decision_events_created_at",
            "ix_learning_decision_events_outcome_label",
            "ix_learning_decision_events_decision",
            "ix_learning_decision_events_symbol",
        ]:
            try:
                op.drop_index(index_name, table_name="learning_decision_events")
            except Exception:
                pass
        op.drop_table("learning_decision_events")
