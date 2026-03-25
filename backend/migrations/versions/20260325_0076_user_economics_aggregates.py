"""user economics aggregates table

Revision ID: 20260325_0076
Revises: 20260325_0075
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260325_0076"
down_revision = "20260325_0075"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "user_economics_aggregates"):
        return

    op.create_table(
        "user_economics_aggregates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
        sa.Column("user_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("ltv_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("revenue_contribution_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("realized_pnl_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("first_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inactive_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("churned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cohort_month", sa.String(length=20), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "environment", name="uq_user_econ_user_env"),
    )

    for name, cols in [
        ("ix_user_economics_aggregates_user_id", ["user_id"]),
        ("ix_user_economics_aggregates_environment", ["environment"]),
        ("ix_user_economics_aggregates_user_email", ["user_email"]),
        ("ix_user_economics_aggregates_ltv_usd", ["ltv_usd"]),
        ("ix_user_economics_aggregates_revenue_contribution_usd", ["revenue_contribution_usd"]),
        ("ix_user_economics_aggregates_last_activity_at", ["last_activity_at"]),
        ("ix_user_economics_aggregates_inactive_days", ["inactive_days"]),
        ("ix_user_economics_aggregates_churned", ["churned"]),
        ("ix_user_economics_aggregates_cohort_month", ["cohort_month"]),
    ]:
        op.create_index(name, "user_economics_aggregates", cols)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "user_economics_aggregates"):
        op.drop_table("user_economics_aggregates")
