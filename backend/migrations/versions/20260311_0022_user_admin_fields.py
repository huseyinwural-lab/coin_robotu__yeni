"""user admin fields

Revision ID: 20260311_0022
Revises: 20260311_0021
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "20260311_0022"
down_revision = "20260311_0021"
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns(table_name)}
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "users", "disabled_at"):
        op.add_column("users", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists(bind, "users", "updated_at"):
        op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "users", "updated_at"):
        op.drop_column("users", "updated_at")
    if _column_exists(bind, "users", "disabled_at"):
        op.drop_column("users", "disabled_at")
