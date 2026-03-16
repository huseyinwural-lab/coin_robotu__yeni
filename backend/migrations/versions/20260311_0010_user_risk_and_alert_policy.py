"""user risk settings and alert policy

Revision ID: 20260311_0010
Revises: 20260311_0009
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0010"
down_revision = "20260311_0009"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "user_risk_settings"):
        op.create_table(
            "user_risk_settings",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("allocation_pct", sa.Float(), nullable=False),
            sa.Column("trade_risk_pct", sa.Float(), nullable=False),
            sa.Column("daily_loss_limit_pct", sa.Float(), nullable=False),
            sa.Column("compounding_enabled", sa.Boolean(), nullable=False),
            sa.Column("base_capital", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index("ix_user_risk_settings_user_id", "user_risk_settings", ["user_id"], unique=True)

    if not _table_exists(bind, "alert_policies"):
        op.create_table(
            "alert_policies",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("admin_notification_enabled", sa.Boolean(), nullable=False),
            sa.Column("ops_webhook_url", sa.Text(), nullable=False),
            sa.Column("monitoring_alert_log_enabled", sa.Boolean(), nullable=False),
            sa.Column("execution_quality_warning_threshold", sa.Float(), nullable=False),
            sa.Column("execution_quality_critical_threshold", sa.Float(), nullable=False),
            sa.Column("permission_drift_warning_per_day", sa.Integer(), nullable=False),
            sa.Column("permission_drift_critical_per_day", sa.Integer(), nullable=False),
            sa.Column("gate_override_warning_per_day", sa.Integer(), nullable=False),
            sa.Column("gate_override_critical_per_day", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.execute(
            sa.text(
                """
                INSERT INTO alert_policies (
                    id, admin_notification_enabled, ops_webhook_url, monitoring_alert_log_enabled,
                    execution_quality_warning_threshold, execution_quality_critical_threshold,
                    permission_drift_warning_per_day, permission_drift_critical_per_day,
                    gate_override_warning_per_day, gate_override_critical_per_day, updated_at
                ) VALUES (
                    'global', TRUE, '', TRUE,
                    60, 40,
                    2, 5,
                    2, 5, CURRENT_TIMESTAMP
                )
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "alert_policies"):
        op.drop_table("alert_policies")
    if _table_exists(bind, "user_risk_settings"):
        op.drop_index("ix_user_risk_settings_user_id", table_name="user_risk_settings")
        op.drop_table("user_risk_settings")