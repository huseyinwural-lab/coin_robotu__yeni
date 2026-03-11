"""strategy domain core tables

Revision ID: 20260311_0015
Revises: 20260311_0014
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0015"
down_revision = "20260311_0014"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "strategy_definitions"):
        op.create_table(
            "strategy_definitions",
            sa.Column("strategy_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("owner_type", sa.String(length=20), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("active_version_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("strategy_id"),
        )
        op.create_index("ix_strategy_definitions_code", "strategy_definitions", ["code"], unique=True)
        op.create_index("ix_strategy_definitions_name", "strategy_definitions", ["name"], unique=False)
        op.create_index("ix_strategy_definitions_created_by", "strategy_definitions", ["created_by"], unique=False)

    if not _table_exists(bind, "strategy_versions"):
        op.create_table(
            "strategy_versions",
            sa.Column("version_id", sa.String(), nullable=False),
            sa.Column("strategy_id", sa.String(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("config_json", sa.JSON(), nullable=False),
            sa.Column("config_schema_version", sa.String(length=30), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version_hash", sa.String(length=128), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["strategy_id"], ["strategy_definitions.strategy_id"]),
            sa.PrimaryKeyConstraint("version_id"),
            sa.UniqueConstraint("strategy_id", "version_number", name="uq_strategy_versions_strategy_version"),
        )
        op.create_index("ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"], unique=False)
        op.create_index("ix_strategy_versions_created_by", "strategy_versions", ["created_by"], unique=False)
        op.create_index("ix_strategy_versions_version_hash", "strategy_versions", ["version_hash"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "strategy_versions"):
        op.drop_index("ix_strategy_versions_version_hash", table_name="strategy_versions")
        op.drop_index("ix_strategy_versions_created_by", table_name="strategy_versions")
        op.drop_index("ix_strategy_versions_strategy_id", table_name="strategy_versions")
        op.drop_table("strategy_versions")

    if _table_exists(bind, "strategy_definitions"):
        op.drop_index("ix_strategy_definitions_created_by", table_name="strategy_definitions")
        op.drop_index("ix_strategy_definitions_name", table_name="strategy_definitions")
        op.drop_index("ix_strategy_definitions_code", table_name="strategy_definitions")
        op.drop_table("strategy_definitions")
