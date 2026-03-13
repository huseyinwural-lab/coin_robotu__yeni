"""scanner automation profiles and actionable counter

Revision ID: 20260313_0036
Revises: 20260313_0035
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "20260313_0036"
down_revision = "20260313_0035"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_scanner_automation_configs") and not _column_exists(
        bind,
        "user_scanner_automation_configs",
        "last_actionable_count",
    ):
        op.add_column(
            "user_scanner_automation_configs",
            sa.Column("last_actionable_count", sa.Integer(), nullable=False, server_default="0"),
        )

    if not _table_exists(bind, "user_scanner_automation_profiles"):
        op.create_table(
            "user_scanner_automation_profiles",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False, server_default="default"),
            sa.Column("auto_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="180"),
            sa.Column("max_results", sa.Integer(), nullable=False, server_default="25"),
            sa.Column("symbol_source", sa.String(length=20), nullable=False, server_default="crypto"),
            sa.Column("symbol_selection_mode", sa.String(length=40), nullable=False, server_default="top_active_50"),
            sa.Column("selected_symbols", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("last_run_id", sa.String(length=120), nullable=True),
            sa.Column("last_run_status", sa.String(length=20), nullable=False, server_default="idle"),
            sa.Column("last_actionable_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_run_error", sa.String(length=240), nullable=True),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_scanner_automation_profiles_user_id", "user_scanner_automation_profiles", ["user_id"])
        op.create_index("ix_user_scanner_automation_profiles_name", "user_scanner_automation_profiles", ["name"])
        op.create_index(
            "ix_user_scanner_automation_profiles_auto_enabled",
            "user_scanner_automation_profiles",
            ["auto_enabled"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_scanner_automation_profiles"):
        for index_name in [
            "ix_user_scanner_automation_profiles_auto_enabled",
            "ix_user_scanner_automation_profiles_name",
            "ix_user_scanner_automation_profiles_user_id",
        ]:
            try:
                op.drop_index(index_name, table_name="user_scanner_automation_profiles")
            except Exception:
                pass
        op.drop_table("user_scanner_automation_profiles")

    if _table_exists(bind, "user_scanner_automation_configs") and _column_exists(
        bind,
        "user_scanner_automation_configs",
        "last_actionable_count",
    ):
        op.drop_column("user_scanner_automation_configs", "last_actionable_count")
