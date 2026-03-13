"""user scanner automation config

Revision ID: 20260313_0035
Revises: 20260313_0034
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0035"
down_revision = "20260313_0034"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "user_scanner_automation_configs"):
        return

    op.create_table(
        "user_scanner_automation_configs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("auto_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("max_results", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("symbol_source", sa.String(length=20), nullable=False, server_default="crypto"),
        sa.Column("symbol_selection_mode", sa.String(length=40), nullable=False, server_default="top_active_50"),
        sa.Column("selected_symbols", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("last_run_id", sa.String(length=120), nullable=True),
        sa.Column("last_run_status", sa.String(length=20), nullable=False, server_default="idle"),
        sa.Column("last_run_error", sa.String(length=240), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_scanner_automation_configs_user_id", "user_scanner_automation_configs", ["user_id"])
    op.create_index(
        "ix_user_scanner_automation_configs_auto_enabled",
        "user_scanner_automation_configs",
        ["auto_enabled"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "user_scanner_automation_configs"):
        return

    try:
        op.drop_index("ix_user_scanner_automation_configs_auto_enabled", table_name="user_scanner_automation_configs")
    except Exception:
        pass
    try:
        op.drop_index("ix_user_scanner_automation_configs_user_id", table_name="user_scanner_automation_configs")
    except Exception:
        pass
    op.drop_table("user_scanner_automation_configs")
