"""analytics snapshots table

Revision ID: 20260325_0078
Revises: 20260325_0077
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260325_0078"
down_revision = "20260325_0077"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "analytics_snapshots"):
        return

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("snapshot_type", sa.String(length=20), nullable=False, server_default="daily"),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("snapshot_type", "snapshot_date", "environment", name="uq_analytics_snapshot_key"),
    )

    for name, cols in [
        ("ix_analytics_snapshots_snapshot_type", ["snapshot_type"]),
        ("ix_analytics_snapshots_environment", ["environment"]),
        ("ix_analytics_snapshots_snapshot_date", ["snapshot_date"]),
    ]:
        op.create_index(name, "analytics_snapshots", cols)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "analytics_snapshots"):
        op.drop_table("analytics_snapshots")
