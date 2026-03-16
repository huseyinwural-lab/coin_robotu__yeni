"""release gate override and validation snapshot

Revision ID: 20260311_0008
Revises: 20260311_0007
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0008"
down_revision = "20260311_0007"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "user_exchange_settings"):
        if not _column_exists(bind, "user_exchange_settings", "last_validation_success"):
            op.add_column("user_exchange_settings", sa.Column("last_validation_success", sa.Boolean(), nullable=True))
        if not _column_exists(bind, "user_exchange_settings", "last_reason_codes"):
            op.add_column("user_exchange_settings", sa.Column("last_reason_codes", sa.JSON(), nullable=True))
            op.execute(sa.text("UPDATE user_exchange_settings SET last_reason_codes = '[]' WHERE last_reason_codes IS NULL"))
            op.alter_column("user_exchange_settings", "last_reason_codes", existing_type=sa.JSON(), nullable=False)

    if not _table_exists(bind, "release_gate_overrides"):
        op.create_table(
            "release_gate_overrides",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("admin_user_id", sa.String(), nullable=False),
            sa.Column("reason_code", sa.String(length=40), nullable=False),
            sa.Column("reason_note", sa.Text(), nullable=False),
            sa.Column("release_gate_snapshot", sa.JSON(), nullable=False),
            sa.Column("deploy_context", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("used_deploy_count", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_release_gate_overrides_admin_user_id", "release_gate_overrides", ["admin_user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "release_gate_overrides"):
        op.drop_index("ix_release_gate_overrides_admin_user_id", table_name="release_gate_overrides")
        op.drop_table("release_gate_overrides")

    if _table_exists(bind, "user_exchange_settings"):
        if _column_exists(bind, "user_exchange_settings", "last_reason_codes"):
            op.drop_column("user_exchange_settings", "last_reason_codes")
        if _column_exists(bind, "user_exchange_settings", "last_validation_success"):
            op.drop_column("user_exchange_settings", "last_validation_success")