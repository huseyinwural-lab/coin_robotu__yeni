"""weekly report archive

Revision ID: 20260311_0021
Revises: 20260311_0020
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "20260311_0021"
down_revision = "20260311_0020"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "weekly_report_archives"):
        op.create_table(
            "weekly_report_archives",
            sa.Column("report_id", sa.String(), nullable=False),
            sa.Column("report_type", sa.String(length=40), nullable=False),
            sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("timezone", sa.String(length=40), nullable=False),
            sa.Column("filename", sa.String(length=200), nullable=False),
            sa.Column("storage_path", sa.Text(), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("trigger_source", sa.String(length=20), nullable=False),
            sa.Column("generated_by", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("report_id"),
        )
        op.create_index("ix_weekly_report_archives_generated_at", "weekly_report_archives", ["generated_at"], unique=False)
        op.create_index("ix_weekly_report_archives_report_type", "weekly_report_archives", ["report_type"], unique=False)
        op.create_index("ix_weekly_report_archives_status", "weekly_report_archives", ["status"], unique=False)
        op.create_index("ix_weekly_report_archives_trigger_source", "weekly_report_archives", ["trigger_source"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_weekly_report_archives_trigger_source", table_name="weekly_report_archives")
    op.drop_index("ix_weekly_report_archives_status", table_name="weekly_report_archives")
    op.drop_index("ix_weekly_report_archives_report_type", table_name="weekly_report_archives")
    op.drop_index("ix_weekly_report_archives_generated_at", table_name="weekly_report_archives")
    op.drop_table("weekly_report_archives")
