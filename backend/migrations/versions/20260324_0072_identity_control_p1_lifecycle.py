"""identity control p1 lifecycle columns

Revision ID: 20260324_0072
Revises: 20260324_0071
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260324_0072"
down_revision = "20260324_0071"
branch_labels = None
depends_on = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = [item.get("name") for item in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "identity_role_policies", "is_active"):
        op.add_column("identity_role_policies", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    if not _has_column(bind, "identity_role_policies", "archived_at"):
        op.add_column("identity_role_policies", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    if not _has_column(bind, "user_invite_tokens", "resend_count"):
        op.add_column("user_invite_tokens", sa.Column("resend_count", sa.Integer(), nullable=False, server_default="0"))
    if not _has_column(bind, "user_invite_tokens", "last_sent_at"):
        op.add_column("user_invite_tokens", sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column(bind, "user_invite_tokens", "cancelled_at"):
        op.add_column("user_invite_tokens", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for table, col in [
        ("user_invite_tokens", "cancelled_at"),
        ("user_invite_tokens", "last_sent_at"),
        ("user_invite_tokens", "resend_count"),
        ("identity_role_policies", "archived_at"),
        ("identity_role_policies", "is_active"),
    ]:
        if _has_column(bind, table, col):
            op.drop_column(table, col)
