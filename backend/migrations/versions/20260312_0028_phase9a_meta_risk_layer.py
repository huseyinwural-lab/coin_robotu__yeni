"""phase9a meta strategy and portfolio risk layer

Revision ID: 20260312_0028
Revises: 20260312_0027
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20260312_0028"
down_revision = "20260312_0027"
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

    if _table_exists(bind, "pending_signals"):
        if not _column_exists(bind, "pending_signals", "strategy_weight"):
            op.add_column("pending_signals", sa.Column("strategy_weight", sa.Float(), nullable=False, server_default="1"))
        if not _column_exists(bind, "pending_signals", "allocation_source"):
            op.add_column(
                "pending_signals",
                sa.Column("allocation_source", sa.String(length=40), nullable=False, server_default="default_allocation"),
            )
        if not _column_exists(bind, "pending_signals", "meta_engine_decision"):
            op.add_column(
                "pending_signals",
                sa.Column("meta_engine_decision", sa.String(length=30), nullable=False, server_default="ALLOW"),
            )

    if _table_exists(bind, "user_execution_intents"):
        if not _column_exists(bind, "user_execution_intents", "risk_score"):
            op.add_column("user_execution_intents", sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"))
        if not _column_exists(bind, "user_execution_intents", "gate_decision"):
            op.add_column(
                "user_execution_intents",
                sa.Column("gate_decision", sa.String(length=30), nullable=False, server_default="ALLOW"),
            )
        if not _column_exists(bind, "user_execution_intents", "meta_engine_decision"):
            op.add_column(
                "user_execution_intents",
                sa.Column("meta_engine_decision", sa.String(length=30), nullable=False, server_default="ALLOW"),
            )
        if not _column_exists(bind, "user_execution_intents", "cluster_id"):
            op.add_column("user_execution_intents", sa.Column("cluster_id", sa.String(length=40), nullable=True))

    if _table_exists(bind, "user_decision_traces"):
        if not _column_exists(bind, "user_decision_traces", "portfolio_risk_score"):
            op.add_column("user_decision_traces", sa.Column("portfolio_risk_score", sa.Float(), nullable=True))
        if not _column_exists(bind, "user_decision_traces", "strategy_allocation_reason"):
            op.add_column("user_decision_traces", sa.Column("strategy_allocation_reason", sa.String(length=120), nullable=True))
        if not _column_exists(bind, "user_decision_traces", "cluster_risk_flag"):
            op.add_column("user_decision_traces", sa.Column("cluster_risk_flag", sa.String(length=80), nullable=True))
        if not _column_exists(bind, "user_decision_traces", "meta_engine_decision"):
            op.add_column("user_decision_traces", sa.Column("meta_engine_decision", sa.String(length=30), nullable=True))

    if not _table_exists(bind, "risk_clusters"):
        op.create_table(
            "risk_clusters",
            sa.Column("cluster_id", sa.String(length=40), nullable=False),
            sa.Column("symbols", sa.JSON(), nullable=False),
            sa.Column("cluster_type", sa.String(length=60), nullable=False, server_default="custom"),
            sa.Column("correlation_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("risk_weight", sa.Float(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("cluster_id"),
        )

    if not _table_exists(bind, "portfolio_exposure_snapshot"):
        op.create_table(
            "portfolio_exposure_snapshot",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("position_size", sa.Float(), nullable=False, server_default="0"),
            sa.Column("notional", sa.Float(), nullable=False, server_default="0"),
            sa.Column("strategy_id", sa.String(length=80), nullable=True),
            sa.Column("cluster_id", sa.String(length=40), nullable=True),
            sa.Column("exposure_weight", sa.Float(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_portfolio_exposure_snapshot_timestamp", "portfolio_exposure_snapshot", ["timestamp"])
        op.create_index("ix_portfolio_exposure_snapshot_user_id", "portfolio_exposure_snapshot", ["user_id"])
        op.create_index("ix_portfolio_exposure_snapshot_symbol", "portfolio_exposure_snapshot", ["symbol"])
        op.create_index("ix_portfolio_exposure_snapshot_strategy_id", "portfolio_exposure_snapshot", ["strategy_id"])
        op.create_index("ix_portfolio_exposure_snapshot_cluster_id", "portfolio_exposure_snapshot", ["cluster_id"])

    if not _table_exists(bind, "strategy_allocations"):
        op.create_table(
            "strategy_allocations",
            sa.Column("strategy_id", sa.String(length=80), nullable=False),
            sa.Column("capital_weight", sa.Float(), nullable=False, server_default="1"),
            sa.Column("max_capital", sa.Float(), nullable=False, server_default="10000"),
            sa.Column("current_capital", sa.Float(), nullable=False, server_default="0"),
            sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("performance_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("state", sa.String(length=20), nullable=False, server_default="ACTIVE"),
            sa.Column("expected_return", sa.Float(), nullable=False, server_default="0"),
            sa.Column("realized_return", sa.Float(), nullable=False, server_default="0"),
            sa.Column("signal_decay", sa.Float(), nullable=False, server_default="0"),
            sa.Column("execution_quality_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("strategy_id"),
        )
        op.create_index("ix_strategy_allocations_state", "strategy_allocations", ["state"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "strategy_allocations"):
        op.drop_index("ix_strategy_allocations_state", table_name="strategy_allocations")
        op.drop_table("strategy_allocations")

    if _table_exists(bind, "portfolio_exposure_snapshot"):
        op.drop_index("ix_portfolio_exposure_snapshot_cluster_id", table_name="portfolio_exposure_snapshot")
        op.drop_index("ix_portfolio_exposure_snapshot_strategy_id", table_name="portfolio_exposure_snapshot")
        op.drop_index("ix_portfolio_exposure_snapshot_symbol", table_name="portfolio_exposure_snapshot")
        op.drop_index("ix_portfolio_exposure_snapshot_user_id", table_name="portfolio_exposure_snapshot")
        op.drop_index("ix_portfolio_exposure_snapshot_timestamp", table_name="portfolio_exposure_snapshot")
        op.drop_table("portfolio_exposure_snapshot")

    if _table_exists(bind, "risk_clusters"):
        op.drop_table("risk_clusters")

    if _table_exists(bind, "user_decision_traces"):
        if _column_exists(bind, "user_decision_traces", "meta_engine_decision"):
            op.drop_column("user_decision_traces", "meta_engine_decision")
        if _column_exists(bind, "user_decision_traces", "cluster_risk_flag"):
            op.drop_column("user_decision_traces", "cluster_risk_flag")
        if _column_exists(bind, "user_decision_traces", "strategy_allocation_reason"):
            op.drop_column("user_decision_traces", "strategy_allocation_reason")
        if _column_exists(bind, "user_decision_traces", "portfolio_risk_score"):
            op.drop_column("user_decision_traces", "portfolio_risk_score")

    if _table_exists(bind, "user_execution_intents"):
        if _column_exists(bind, "user_execution_intents", "cluster_id"):
            op.drop_column("user_execution_intents", "cluster_id")
        if _column_exists(bind, "user_execution_intents", "meta_engine_decision"):
            op.drop_column("user_execution_intents", "meta_engine_decision")
        if _column_exists(bind, "user_execution_intents", "gate_decision"):
            op.drop_column("user_execution_intents", "gate_decision")
        if _column_exists(bind, "user_execution_intents", "risk_score"):
            op.drop_column("user_execution_intents", "risk_score")

    if _table_exists(bind, "pending_signals"):
        if _column_exists(bind, "pending_signals", "meta_engine_decision"):
            op.drop_column("pending_signals", "meta_engine_decision")
        if _column_exists(bind, "pending_signals", "allocation_source"):
            op.drop_column("pending_signals", "allocation_source")
        if _column_exists(bind, "pending_signals", "strategy_weight"):
            op.drop_column("pending_signals", "strategy_weight")
