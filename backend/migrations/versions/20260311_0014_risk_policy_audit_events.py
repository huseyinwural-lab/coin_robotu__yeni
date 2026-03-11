"""risk policy audit events table

Revision ID: 20260311_0014
Revises: 20260311_0013
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0014"
down_revision = "20260311_0013"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "risk_policy_audit_events"):
        return

    op.create_table(
        "risk_policy_audit_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("replay_run_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("strategy_version", sa.String(length=120), nullable=False),
        sa.Column("regime_bucket", sa.String(length=40), nullable=False),
        sa.Column("drawdown", sa.Float(), nullable=False),
        sa.Column("exposure_breach", sa.Integer(), nullable=False),
        sa.Column("reject_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["replay_run_id"], ["replay_runs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_policy_audit_events_replay_run_id", "risk_policy_audit_events", ["replay_run_id"], unique=False)
    op.create_index("ix_risk_policy_audit_events_user_id", "risk_policy_audit_events", ["user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "risk_policy_audit_events"):
        return

    op.drop_index("ix_risk_policy_audit_events_user_id", table_name="risk_policy_audit_events")
    op.drop_index("ix_risk_policy_audit_events_replay_run_id", table_name="risk_policy_audit_events")
    op.drop_table("risk_policy_audit_events")
