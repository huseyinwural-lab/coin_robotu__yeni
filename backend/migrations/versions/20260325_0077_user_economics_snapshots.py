"""user economics snapshots table

Revision ID: 20260325_0077
Revises: 20260325_0076
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260325_0077"
down_revision = "20260325_0076"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "user_economics_snapshots"):
        return

    op.create_table(
        "user_economics_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("snapshot_type", sa.String(length=20), nullable=False, server_default="daily"),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("ltv_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("revenue_contribution_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("realized_pnl_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("inactive_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("churned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cohort_month", sa.String(length=20), nullable=True),
        sa.Column("segment", sa.String(length=40), nullable=False, server_default="low_activity_low_revenue"),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("snapshot_type", "snapshot_date", "environment", "user_id", name="uq_user_econ_snapshot_key"),
    )

    for name, cols in [
        ("ix_user_economics_snapshots_snapshot_type", ["snapshot_type"]),
        ("ix_user_economics_snapshots_snapshot_date", ["snapshot_date"]),
        ("ix_user_economics_snapshots_environment", ["environment"]),
        ("ix_user_economics_snapshots_user_id", ["user_id"]),
        ("ix_user_economics_snapshots_user_email", ["user_email"]),
        ("ix_user_economics_snapshots_segment", ["segment"]),
    ]:
        op.create_index(name, "user_economics_snapshots", cols)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "user_economics_snapshots"):
        op.drop_table("user_economics_snapshots")
