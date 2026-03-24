"""strategy ops and observability extensions

Revision ID: 20260324_0069
Revises: 20260324_0068
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260324_0069"
down_revision = "20260324_0068"
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    cols = inspector.get_columns(table_name)
    return any(col.get("name") == column_name for col in cols)


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists(bind, "strategy_definitions", "owner_user_id"):
        op.add_column("strategy_definitions", sa.Column("owner_user_id", sa.String(), nullable=True))
        op.create_foreign_key(
            "fk_strategy_definitions_owner_user_id",
            "strategy_definitions",
            "users",
            ["owner_user_id"],
            ["id"],
        )
    if not _column_exists(bind, "strategy_definitions", "owner_name"):
        op.add_column("strategy_definitions", sa.Column("owner_name", sa.String(length=120), nullable=False, server_default="ops"))
    if not _column_exists(bind, "strategy_definitions", "category"):
        op.add_column("strategy_definitions", sa.Column("category", sa.String(length=80), nullable=False, server_default="general"))
    if not _column_exists(bind, "strategy_definitions", "tags"):
        op.add_column("strategy_definitions", sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    if not _column_exists(bind, "strategy_definitions", "archived_at"):
        op.add_column("strategy_definitions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists(bind, "strategy_definitions", "last_reviewed_at"):
        op.add_column("strategy_definitions", sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True))

    if not _index_exists(bind, "strategy_definitions", "ix_strategy_definitions_owner_user_id"):
        op.create_index("ix_strategy_definitions_owner_user_id", "strategy_definitions", ["owner_user_id"], unique=False)
    if not _index_exists(bind, "strategy_definitions", "ix_strategy_definitions_category"):
        op.create_index("ix_strategy_definitions_category", "strategy_definitions", ["category"], unique=False)
    if not _index_exists(bind, "strategy_definitions", "ix_strategy_definitions_archived_at"):
        op.create_index("ix_strategy_definitions_archived_at", "strategy_definitions", ["archived_at"], unique=False)

    op.execute(
        """
        UPDATE strategy_definitions
        SET owner_user_id = created_by
        WHERE owner_user_id IS NULL
        """
    )

    if not _column_exists(bind, "strategy_observability_events", "strategy_version_id"):
        op.add_column("strategy_observability_events", sa.Column("strategy_version_id", sa.String(), nullable=True))
        op.create_foreign_key(
            "fk_strategy_observability_events_strategy_version_id",
            "strategy_observability_events",
            "strategy_versions",
            ["strategy_version_id"],
            ["version_id"],
        )
    if not _index_exists(bind, "strategy_observability_events", "ix_strategy_observability_events_strategy_version_id"):
        op.create_index(
            "ix_strategy_observability_events_strategy_version_id",
            "strategy_observability_events",
            ["strategy_version_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _index_exists(bind, "strategy_observability_events", "ix_strategy_observability_events_strategy_version_id"):
        op.drop_index("ix_strategy_observability_events_strategy_version_id", table_name="strategy_observability_events")
    if _column_exists(bind, "strategy_observability_events", "strategy_version_id"):
        op.drop_constraint(
            "fk_strategy_observability_events_strategy_version_id",
            "strategy_observability_events",
            type_="foreignkey",
        )
        op.drop_column("strategy_observability_events", "strategy_version_id")

    if _index_exists(bind, "strategy_definitions", "ix_strategy_definitions_archived_at"):
        op.drop_index("ix_strategy_definitions_archived_at", table_name="strategy_definitions")
    if _index_exists(bind, "strategy_definitions", "ix_strategy_definitions_category"):
        op.drop_index("ix_strategy_definitions_category", table_name="strategy_definitions")
    if _index_exists(bind, "strategy_definitions", "ix_strategy_definitions_owner_user_id"):
        op.drop_index("ix_strategy_definitions_owner_user_id", table_name="strategy_definitions")

    if _column_exists(bind, "strategy_definitions", "last_reviewed_at"):
        op.drop_column("strategy_definitions", "last_reviewed_at")
    if _column_exists(bind, "strategy_definitions", "archived_at"):
        op.drop_column("strategy_definitions", "archived_at")
    if _column_exists(bind, "strategy_definitions", "tags"):
        op.drop_column("strategy_definitions", "tags")
    if _column_exists(bind, "strategy_definitions", "category"):
        op.drop_column("strategy_definitions", "category")
    if _column_exists(bind, "strategy_definitions", "owner_name"):
        op.drop_column("strategy_definitions", "owner_name")
    if _column_exists(bind, "strategy_definitions", "owner_user_id"):
        op.drop_constraint("fk_strategy_definitions_owner_user_id", "strategy_definitions", type_="foreignkey")
        op.drop_column("strategy_definitions", "owner_user_id")
