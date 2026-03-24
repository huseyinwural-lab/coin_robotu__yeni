"""identity control delete lifecycle fields

Revision ID: 20260324_0071
Revises: 20260324_0070
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260324_0071"
down_revision = "20260324_0070"
branch_labels = None
depends_on = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = [item.get("name") for item in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()
    table = "user_identity_profiles"
    if not _has_column(bind, table, "eligible_for_login"):
        op.add_column(table, sa.Column("eligible_for_login", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    if not _has_column(bind, table, "eligible_for_ops"):
        op.add_column(table, sa.Column("eligible_for_ops", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if not _has_column(bind, table, "policy_locked_until"):
        op.add_column(table, sa.Column("policy_locked_until", sa.DateTime(timezone=True), nullable=True))
    if not _has_column(bind, table, "deleted_at"):
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column(bind, table, "deleted_by"):
        op.add_column(table, sa.Column("deleted_by", sa.String(), sa.ForeignKey("users.id"), nullable=True))
    if not _has_column(bind, table, "delete_reason"):
        op.add_column(table, sa.Column("delete_reason", sa.String(length=500), nullable=True))
    if not _has_column(bind, table, "delete_request_id"):
        op.add_column(table, sa.Column("delete_request_id", sa.String(), nullable=True))
    if not _has_column(bind, table, "hard_deleted_at"):
        op.add_column(table, sa.Column("hard_deleted_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column(bind, table, "hard_delete_request_id"):
        op.add_column(table, sa.Column("hard_delete_request_id", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    table = "user_identity_profiles"
    for col in [
        "hard_delete_request_id",
        "hard_deleted_at",
        "delete_request_id",
        "delete_reason",
        "deleted_by",
        "deleted_at",
        "policy_locked_until",
        "eligible_for_ops",
        "eligible_for_login",
    ]:
        if _has_column(bind, table, col):
            op.drop_column(table, col)
