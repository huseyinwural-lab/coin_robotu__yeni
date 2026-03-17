"""strategy templates repair

Revision ID: 20260317_0047
Revises: 20260316_0046
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260317_0047"
down_revision = "20260316_0046"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any((index.get("name") or "") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "strategy_templates"):
        op.create_table(
            "strategy_templates",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("strategy_type", sa.String(length=50), nullable=False),
            sa.Column("parameters", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if not _index_exists(bind, "strategy_templates", "ix_strategy_templates_strategy_type"):
        op.create_index("ix_strategy_templates_strategy_type", "strategy_templates", ["strategy_type"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "strategy_templates"):
        return

    if _index_exists(bind, "strategy_templates", "ix_strategy_templates_strategy_type"):
        op.drop_index("ix_strategy_templates_strategy_type", table_name="strategy_templates")
    op.drop_table("strategy_templates")
