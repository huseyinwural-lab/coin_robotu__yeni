"""regime classifier tables

Revision ID: 20260311_0017
Revises: 20260311_0016
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0017"
down_revision = "20260311_0016"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "strategy_regime_bindings"):
        op.create_table(
            "strategy_regime_bindings",
            sa.Column("binding_id", sa.String(), nullable=False),
            sa.Column("strategy_version_id", sa.String(), nullable=False),
            sa.Column("allowed_regimes", sa.JSON(), nullable=False),
            sa.Column("blocked_regimes", sa.JSON(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("gating_policy_version", sa.String(length=30), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_versions.version_id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("binding_id"),
        )
        op.create_index("ix_strategy_regime_bindings_strategy_version_id", "strategy_regime_bindings", ["strategy_version_id"], unique=False)
        op.create_index("ix_strategy_regime_bindings_created_by", "strategy_regime_bindings", ["created_by"], unique=False)

    if not _table_exists(bind, "regime_snapshots"):
        op.create_table(
            "regime_snapshots",
            sa.Column("regime_snapshot_id", sa.String(), nullable=False),
            sa.Column("timestamp_utc", sa.String(length=40), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("timeframe", sa.String(length=10), nullable=False),
            sa.Column("strategy_version_id", sa.String(), nullable=False),
            sa.Column("volatility_regime", sa.String(length=40), nullable=False),
            sa.Column("trend_regime", sa.String(length=40), nullable=False),
            sa.Column("liquidity_regime", sa.String(length=40), nullable=False),
            sa.Column("market_state_features", sa.JSON(), nullable=False),
            sa.Column("feature_set_version", sa.String(length=30), nullable=False),
            sa.Column("regime_score", sa.Float(), nullable=False),
            sa.Column("regime_label", sa.String(length=50), nullable=False),
            sa.Column("regime_hash", sa.String(length=128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_versions.version_id"]),
            sa.PrimaryKeyConstraint("regime_snapshot_id"),
        )
        op.create_index("ix_regime_snapshots_timestamp_utc", "regime_snapshots", ["timestamp_utc"], unique=False)
        op.create_index("ix_regime_snapshots_symbol", "regime_snapshots", ["symbol"], unique=False)
        op.create_index("ix_regime_snapshots_timeframe", "regime_snapshots", ["timeframe"], unique=False)
        op.create_index("ix_regime_snapshots_strategy_version_id", "regime_snapshots", ["strategy_version_id"], unique=False)
        op.create_index("ix_regime_snapshots_regime_label", "regime_snapshots", ["regime_label"], unique=False)
        op.create_index("ix_regime_snapshots_regime_hash", "regime_snapshots", ["regime_hash"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "regime_snapshots"):
        op.drop_index("ix_regime_snapshots_regime_hash", table_name="regime_snapshots")
        op.drop_index("ix_regime_snapshots_regime_label", table_name="regime_snapshots")
        op.drop_index("ix_regime_snapshots_strategy_version_id", table_name="regime_snapshots")
        op.drop_index("ix_regime_snapshots_timeframe", table_name="regime_snapshots")
        op.drop_index("ix_regime_snapshots_symbol", table_name="regime_snapshots")
        op.drop_index("ix_regime_snapshots_timestamp_utc", table_name="regime_snapshots")
        op.drop_table("regime_snapshots")

    if _table_exists(bind, "strategy_regime_bindings"):
        op.drop_index("ix_strategy_regime_bindings_created_by", table_name="strategy_regime_bindings")
        op.drop_index("ix_strategy_regime_bindings_strategy_version_id", table_name="strategy_regime_bindings")
        op.drop_table("strategy_regime_bindings")
