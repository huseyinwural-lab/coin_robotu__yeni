"""user approval workflow columns

Revision ID: 20260311_0005
Revises: 20260311_0004
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0005"
down_revision = "20260311_0004"
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
    if not _table_exists(bind, "users"):
        return

    if not _column_exists(bind, "users", "approval_status"):
        op.add_column("users", sa.Column("approval_status", sa.String(length=20), nullable=True))
    if not _column_exists(bind, "users", "approval_requested_at"):
        op.add_column("users", sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists(bind, "users", "approved_at"):
        op.add_column("users", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))

    now_expr = sa.text("CURRENT_TIMESTAMP")
    op.execute(sa.text("UPDATE users SET approval_status = 'approved' WHERE approval_status IS NULL"))
    op.execute(sa.text("UPDATE users SET approval_requested_at = CURRENT_TIMESTAMP WHERE approval_requested_at IS NULL"))
    op.execute(sa.text("UPDATE users SET approved_at = CURRENT_TIMESTAMP WHERE approved_at IS NULL AND approval_status = 'approved'"))

    op.alter_column("users", "approval_status", existing_type=sa.String(length=20), nullable=False, server_default="approved")
    op.alter_column(
        "users",
        "approval_requested_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=now_expr,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "users"):
        return

    if _column_exists(bind, "users", "approved_at"):
        op.drop_column("users", "approved_at")
    if _column_exists(bind, "users", "approval_requested_at"):
        op.drop_column("users", "approval_requested_at")
    if _column_exists(bind, "users", "approval_status"):
        op.drop_column("users", "approval_status")