"""scanner observability tables repair

Revision ID: 20260317_0048
Revises: 20260317_0047
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260317_0048"
down_revision = "20260317_0047"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any((index.get("name") or "") == index_name for index in inspector.get_indexes(table_name))


def _ensure_indicator_computation_cache(bind) -> None:
    if not _table_exists(bind, "indicator_computation_cache"):
        op.create_table(
            "indicator_computation_cache",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("cache_key", sa.String(length=280), nullable=False),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("timeframe", sa.String(length=12), nullable=False),
            sa.Column("bar_close_time", sa.String(length=64), nullable=False),
            sa.Column("indicator_name", sa.String(length=80), nullable=False),
            sa.Column("params_version", sa.String(length=40), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cache_key", name="uq_indicator_computation_cache_key"),
        )

    if not _index_exists(bind, "indicator_computation_cache", "ix_indicator_computation_cache_cache_key"):
        op.create_index("ix_indicator_computation_cache_cache_key", "indicator_computation_cache", ["cache_key"])
    if not _index_exists(bind, "indicator_computation_cache", "ix_indicator_computation_cache_symbol"):
        op.create_index("ix_indicator_computation_cache_symbol", "indicator_computation_cache", ["symbol"])
    if not _index_exists(bind, "indicator_computation_cache", "ix_indicator_computation_cache_timeframe"):
        op.create_index("ix_indicator_computation_cache_timeframe", "indicator_computation_cache", ["timeframe"])
    if not _index_exists(bind, "indicator_computation_cache", "ix_indicator_computation_cache_bar_close_time"):
        op.create_index("ix_indicator_computation_cache_bar_close_time", "indicator_computation_cache", ["bar_close_time"])
    if not _index_exists(bind, "indicator_computation_cache", "ix_indicator_computation_cache_indicator_name"):
        op.create_index("ix_indicator_computation_cache_indicator_name", "indicator_computation_cache", ["indicator_name"])
    if not _index_exists(bind, "indicator_computation_cache", "ix_indicator_computation_cache_params_version"):
        op.create_index("ix_indicator_computation_cache_params_version", "indicator_computation_cache", ["params_version"])
    if not _index_exists(bind, "indicator_computation_cache", "ix_indicator_computation_cache_expires_at"):
        op.create_index("ix_indicator_computation_cache_expires_at", "indicator_computation_cache", ["expires_at"])

def _ensure_scanner_performance_snapshots(bind) -> None:
    if not _table_exists(bind, "scanner_performance_snapshots"):
        op.create_table(
            "scanner_performance_snapshots",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("run_id", sa.String(length=120), nullable=True),
            sa.Column("stage", sa.String(length=40), nullable=False, server_default="top_volume_subset"),
            sa.Column("metrics", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(bind, "scanner_performance_snapshots", "ix_scanner_performance_snapshots_user_id"):
        op.create_index("ix_scanner_performance_snapshots_user_id", "scanner_performance_snapshots", ["user_id"])
    if not _index_exists(bind, "scanner_performance_snapshots", "ix_scanner_performance_snapshots_run_id"):
        op.create_index("ix_scanner_performance_snapshots_run_id", "scanner_performance_snapshots", ["run_id"])
    if not _index_exists(bind, "scanner_performance_snapshots", "ix_scanner_performance_snapshots_stage"):
        op.create_index("ix_scanner_performance_snapshots_stage", "scanner_performance_snapshots", ["stage"])
    if not _index_exists(bind, "scanner_performance_snapshots", "ix_scanner_performance_snapshots_created_at"):
        op.create_index("ix_scanner_performance_snapshots_created_at", "scanner_performance_snapshots", ["created_at"])


def _ensure_universe_rollout_state(bind) -> None:
    if not _table_exists(bind, "universe_rollout_state"):
        op.create_table(
            "universe_rollout_state",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("current_stage", sa.String(length=40), nullable=False, server_default="full_market"),
            sa.Column("recommended_stage", sa.String(length=40), nullable=True),
            sa.Column("recommendation_payload", sa.JSON(), nullable=False),
            sa.Column("requires_admin_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("approved_by", sa.String(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def _ensure_scanner_fallback_events(bind) -> None:
    if not _table_exists(bind, "scanner_fallback_events"):
        op.create_table(
            "scanner_fallback_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("run_id", sa.String(length=120), nullable=True),
            sa.Column("event_type", sa.String(length=20), nullable=False),
            sa.Column("requested_mode", sa.String(length=40), nullable=False, server_default="all_market_symbols"),
            sa.Column("effective_mode", sa.String(length=40), nullable=False, server_default="all_market_symbols"),
            sa.Column("trigger_metric", sa.String(length=80), nullable=True),
            sa.Column("threshold_breach", sa.JSON(), nullable=False),
            sa.Column("exit_reason", sa.String(length=120), nullable=True),
            sa.Column("cycle_snapshot", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(bind, "scanner_fallback_events", "ix_scanner_fallback_events_run_id"):
        op.create_index("ix_scanner_fallback_events_run_id", "scanner_fallback_events", ["run_id"])
    if not _index_exists(bind, "scanner_fallback_events", "ix_scanner_fallback_events_event_type"):
        op.create_index("ix_scanner_fallback_events_event_type", "scanner_fallback_events", ["event_type"])
    if not _index_exists(bind, "scanner_fallback_events", "ix_scanner_fallback_events_created_at"):
        op.create_index("ix_scanner_fallback_events_created_at", "scanner_fallback_events", ["created_at"])


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_indicator_computation_cache(bind)
    _ensure_scanner_performance_snapshots(bind)
    _ensure_universe_rollout_state(bind)
    _ensure_scanner_fallback_events(bind)


def downgrade() -> None:
    # Repair migration intentionally non-destructive on downgrade.
    pass
