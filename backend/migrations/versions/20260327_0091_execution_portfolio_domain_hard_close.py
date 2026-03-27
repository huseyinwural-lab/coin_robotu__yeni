"""execution portfolio domain hard close

Revision ID: 20260327_0091
Revises: 20260327_0090
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0091"
down_revision = "20260327_0090"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _has_index(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "execution_portfolios"):
        op.create_table(
            "execution_portfolios",
            sa.Column("portfolio_id", sa.String(length=120), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False, server_default="default"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("exposure", sa.Float(), nullable=False, server_default="0"),
            sa.Column("gross_exposure", sa.Float(), nullable=False, server_default="0"),
            sa.Column("net_exposure", sa.Float(), nullable=False, server_default="0"),
            sa.Column("concentration", sa.Float(), nullable=False, server_default="0"),
            sa.Column("drawdown", sa.Float(), nullable=False, server_default="0"),
            sa.Column("limits", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("risk_profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_execution_portfolios_user_id", "execution_portfolios", ["user_id"], unique=False)
        op.create_index("ix_execution_portfolios_is_default", "execution_portfolios", ["is_default"], unique=False)

    if _has_table(bind, "execution_policy_decision_logs"):
        if not _has_column(bind, "execution_policy_decision_logs", "violation_id"):
            op.add_column("execution_policy_decision_logs", sa.Column("violation_id", sa.String(length=120), nullable=True))
        if not _has_column(bind, "execution_policy_decision_logs", "triggered_policy"):
            op.add_column("execution_policy_decision_logs", sa.Column("triggered_policy", sa.String(length=120), nullable=True))
        if not _has_column(bind, "execution_policy_decision_logs", "triggered_rule"):
            op.add_column("execution_policy_decision_logs", sa.Column("triggered_rule", sa.String(length=120), nullable=True))
        if not _has_column(bind, "execution_policy_decision_logs", "metrics_snapshot"):
            op.add_column("execution_policy_decision_logs", sa.Column("metrics_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))

        if not _has_index(bind, "execution_policy_decision_logs", "ix_execution_policy_logs_violation_id"):
            op.create_index("ix_execution_policy_logs_violation_id", "execution_policy_decision_logs", ["violation_id"], unique=False)
        if not _has_index(bind, "execution_policy_decision_logs", "ix_execution_policy_logs_triggered_policy"):
            op.create_index("ix_execution_policy_logs_triggered_policy", "execution_policy_decision_logs", ["triggered_policy"], unique=False)
        if not _has_index(bind, "execution_policy_decision_logs", "ix_execution_policy_logs_triggered_rule"):
            op.create_index("ix_execution_policy_logs_triggered_rule", "execution_policy_decision_logs", ["triggered_rule"], unique=False)

    op.execute(
        sa.text(
            """
            INSERT INTO execution_portfolios (
                portfolio_id, user_id, name, is_default, exposure, gross_exposure, net_exposure,
                concentration, drawdown, limits, risk_profile, created_at, updated_at
            )
            SELECT
                CONCAT('default:', u.id) AS portfolio_id,
                u.id AS user_id,
                'default' AS name,
                true AS is_default,
                0 AS exposure,
                0 AS gross_exposure,
                0 AS net_exposure,
                0 AS concentration,
                0 AS drawdown,
                '{"max_portfolio_exposure": 300000, "max_drawdown_pct": 25}'::json AS limits,
                '{"version": "portfolio_v1"}'::json AS risk_profile,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM execution_portfolios ep
                WHERE ep.user_id = u.id AND ep.is_default = true
            )
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "execution_portfolios"):
        op.drop_table("execution_portfolios")
