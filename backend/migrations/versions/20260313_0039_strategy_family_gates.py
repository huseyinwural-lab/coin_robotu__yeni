"""strategy family gates

Revision ID: 20260313_0039
Revises: 20260313_0038
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0039"
down_revision = "20260313_0038"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "strategy_family_gates"):
        return

    op.create_table(
        "strategy_family_gates",
        sa.Column("family", sa.String(length=30), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("long_threshold", sa.Float(), nullable=False, server_default="5"),
        sa.Column("short_threshold", sa.Float(), nullable=False, server_default="5"),
        sa.Column("min_strategy_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_conflict_score", sa.Float(), nullable=False, server_default="2"),
        sa.Column("regime_match_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("risk_clear_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reversal_extra_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("family"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "strategy_family_gates"):
        return
    op.drop_table("strategy_family_gates")
