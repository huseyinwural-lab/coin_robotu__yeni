"""phase3 schema foundation

Revision ID: 20260311_0001
Revises:
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260311_0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False, server_default="USER"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if _table_exists(bind, "bot_profiles") and not _column_exists(bind, "bot_profiles", "is_running"):
        op.add_column("bot_profiles", sa.Column("is_running", sa.Boolean(), nullable=False, server_default=sa.false()))

    if not _table_exists(bind, "execution_policies"):
        op.create_table(
            "execution_policies",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("strategy_type", sa.String(length=50), nullable=False),
            sa.Column("execution_style", sa.String(length=20), nullable=False),
            sa.Column("order_preference", sa.String(length=20), nullable=False),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False),
            sa.Column("fallback_behavior", sa.String(length=30), nullable=False),
            sa.Column("partial_fill_tolerance_pct", sa.Float(), nullable=False),
            sa.Column("execution_urgency", sa.String(length=20), nullable=False),
            sa.Column("retry_limit", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("strategy_type"),
        )

    if not _table_exists(bind, "risk_exposure_groups"):
        op.create_table(
            "risk_exposure_groups",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=40), nullable=False),
            sa.Column("label", sa.String(length=120), nullable=False),
            sa.Column("symbols", sa.JSON(), nullable=False),
            sa.Column("max_group_open_positions", sa.Integer(), nullable=False),
            sa.Column("max_group_directional_positions", sa.Integer(), nullable=False),
            sa.Column("max_group_risk_pct", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if not _table_exists(bind, "failed_events"):
        op.create_table(
            "failed_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.String(length=120), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("retry_count", sa.Integer(), nullable=False),
            sa.Column("max_retry", sa.Integer(), nullable=False),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists(bind, "state_rebuild_logs"):
        op.create_table(
            "state_rebuild_logs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("rebuild_type", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("trigger_source", sa.String(length=30), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists(bind, "backtest_result_cards"):
        op.create_table(
            "backtest_result_cards",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("strategy_type", sa.String(length=50), nullable=False),
            sa.Column("market_type", sa.String(length=20), nullable=False),
            sa.Column("timeframe", sa.String(length=10), nullable=False),
            sa.Column("sample_size", sa.Integer(), nullable=False),
            sa.Column("win_rate", sa.Float(), nullable=False),
            sa.Column("max_drawdown", sa.Float(), nullable=False),
            sa.Column("profit_factor", sa.Float(), nullable=False),
            sa.Column("sharpe_like_score", sa.Float(), nullable=False),
            sa.Column("performance_summary", sa.Text(), nullable=False),
            sa.Column("risk_label", sa.String(length=20), nullable=False),
            sa.Column("period_start", sa.String(length=30), nullable=False),
            sa.Column("period_end", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "backtest_result_cards"):
        op.drop_table("backtest_result_cards")
    if _table_exists(bind, "state_rebuild_logs"):
        op.drop_table("state_rebuild_logs")
    if _table_exists(bind, "failed_events"):
        op.drop_table("failed_events")
    if _table_exists(bind, "risk_exposure_groups"):
        op.drop_table("risk_exposure_groups")
    if _table_exists(bind, "execution_policies"):
        op.drop_table("execution_policies")
    if _table_exists(bind, "users"):
        inspector = sa.inspect(bind)
        index_names = {index.get("name") for index in inspector.get_indexes("users")}
        if "ix_users_email" in index_names:
            op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")