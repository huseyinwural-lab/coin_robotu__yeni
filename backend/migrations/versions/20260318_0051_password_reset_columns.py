"""password reset columns on user onboarding profiles

Revision ID: 20260318_0051
Revises: 20260317_0050
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_0051"
down_revision = "20260317_0050"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any((col.get("name") or "") == column_name for col in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any((idx.get("name") or "") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    table_name = "user_onboarding_profiles"
    if not _table_exists(bind, table_name):
        return

    if not _column_exists(bind, table_name, "password_reset_token_hash"):
        op.add_column(table_name, sa.Column("password_reset_token_hash", sa.String(length=128), nullable=True))
    if not _column_exists(bind, table_name, "password_reset_expires_at"):
        op.add_column(table_name, sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists(bind, table_name, "password_reset_requested_at"):
        op.add_column(table_name, sa.Column("password_reset_requested_at", sa.DateTime(timezone=True), nullable=True))

    index_name = "ix_user_onboarding_profiles_password_reset_token_hash"
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, ["password_reset_token_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    table_name = "user_onboarding_profiles"
    if not _table_exists(bind, table_name):
        return

    index_name = "ix_user_onboarding_profiles_password_reset_token_hash"
    if _index_exists(bind, table_name, index_name):
        op.drop_index(index_name, table_name=table_name)

    if _column_exists(bind, table_name, "password_reset_requested_at"):
        op.drop_column(table_name, "password_reset_requested_at")
    if _column_exists(bind, table_name, "password_reset_expires_at"):
        op.drop_column(table_name, "password_reset_expires_at")
    if _column_exists(bind, table_name, "password_reset_token_hash"):
        op.drop_column(table_name, "password_reset_token_hash")
