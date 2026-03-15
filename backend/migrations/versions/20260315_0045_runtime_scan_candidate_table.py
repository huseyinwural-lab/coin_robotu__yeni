"""runtime scan candidate table

Revision ID: 20260315_0045
Revises: 20260315_0044
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0045"
down_revision = "20260315_0044"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "runtime_scan_candidates"):
        return

    op.create_table(
        "runtime_scan_candidates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("market_type", sa.String(length=20), nullable=False),
        sa.Column("scan_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_signal", sa.String(length=20), nullable=False, server_default="PASS"),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("decision", sa.String(length=10), nullable=False, server_default="PASS"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_scan_candidates_symbol", "runtime_scan_candidates", ["symbol"])
    op.create_index("ix_runtime_scan_candidates_market_type", "runtime_scan_candidates", ["market_type"])
    op.create_index("ix_runtime_scan_candidates_scan_timestamp", "runtime_scan_candidates", ["scan_timestamp"])
    op.create_index("ix_runtime_scan_candidates_decision", "runtime_scan_candidates", ["decision"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "runtime_scan_candidates"):
        return

    op.drop_index("ix_runtime_scan_candidates_decision", table_name="runtime_scan_candidates")
    op.drop_index("ix_runtime_scan_candidates_scan_timestamp", table_name="runtime_scan_candidates")
    op.drop_index("ix_runtime_scan_candidates_market_type", table_name="runtime_scan_candidates")
    op.drop_index("ix_runtime_scan_candidates_symbol", table_name="runtime_scan_candidates")
    op.drop_table("runtime_scan_candidates")
