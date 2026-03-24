"""strategy lifecycle production gate

Revision ID: 20260324_0068
Revises: 20260323_0067
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260324_0068"
down_revision = "20260323_0067"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    for item in inspector.get_indexes(table_name):
        if item.get("name") == index_name:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "strategy_version_lifecycle"):
        op.create_table(
            "strategy_version_lifecycle",
            sa.Column("lifecycle_id", sa.String(), primary_key=True, nullable=False),
            sa.Column("strategy_id", sa.String(), sa.ForeignKey("strategy_definitions.strategy_id"), nullable=False),
            sa.Column("strategy_version_id", sa.String(), sa.ForeignKey("strategy_versions.version_id"), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_production", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("lifecycle_state", sa.String(length=30), nullable=False, server_default="draft"),
            sa.Column("validation_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("validation_errors_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("compatibility_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("compatibility_report_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("dry_run_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("dry_run_report_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("rollout_stage", sa.String(length=20), nullable=True),
            sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rolled_back_from_version_id", sa.String(), nullable=True),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("strategy_version_id", name="uq_strategy_version_lifecycle_version"),
        )

    if not _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_strategy_id"):
        op.create_index("ix_strategy_version_lifecycle_strategy_id", "strategy_version_lifecycle", ["strategy_id"], unique=False)
    if not _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_strategy_version_id"):
        op.create_index("ix_strategy_version_lifecycle_strategy_version_id", "strategy_version_lifecycle", ["strategy_version_id"], unique=False)
    if not _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_is_active"):
        op.create_index("ix_strategy_version_lifecycle_is_active", "strategy_version_lifecycle", ["is_active"], unique=False)
    if not _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_is_production"):
        op.create_index("ix_strategy_version_lifecycle_is_production", "strategy_version_lifecycle", ["is_production"], unique=False)
    if not _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_lifecycle_state"):
        op.create_index("ix_strategy_version_lifecycle_lifecycle_state", "strategy_version_lifecycle", ["lifecycle_state"], unique=False)

    op.execute(
        """
        INSERT INTO strategy_version_lifecycle (
            lifecycle_id,
            strategy_id,
            strategy_version_id,
            is_active,
            is_production,
            lifecycle_state,
            validation_status,
            validation_errors_json,
            compatibility_status,
            compatibility_report_json,
            dry_run_status,
            dry_run_report_json,
            rollout_stage,
            promoted_at,
            rolled_back_from_version_id,
            created_by,
            created_at,
            updated_at
        )
        SELECT
            sv.version_id,
            sv.strategy_id,
            sv.version_id,
            CASE WHEN sd.active_version_id = sv.version_id THEN true ELSE false END,
            false,
            CASE WHEN sd.active_version_id = sv.version_id THEN 'validated' ELSE 'draft' END,
            CASE WHEN sd.active_version_id = sv.version_id THEN 'PASS' ELSE 'pending' END,
            '[]'::json,
            CASE WHEN sd.active_version_id = sv.version_id THEN 'PASS' ELSE 'pending' END,
            '{}'::json,
            CASE WHEN sd.active_version_id = sv.version_id THEN 'PASS' ELSE 'pending' END,
            '{}'::json,
            NULL,
            NULL,
            NULL,
            sv.created_by,
            sv.created_at,
            sv.created_at
        FROM strategy_versions sv
        JOIN strategy_definitions sd ON sd.strategy_id = sv.strategy_id
        LEFT JOIN strategy_version_lifecycle sl ON sl.strategy_version_id = sv.version_id
        WHERE sl.strategy_version_id IS NULL
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_lifecycle_active_per_strategy
        ON strategy_version_lifecycle (strategy_id)
        WHERE is_active = true
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_lifecycle_production_per_strategy
        ON strategy_version_lifecycle (strategy_id)
        WHERE is_production = true
        """
    )

    if not _table_exists(bind, "strategy_promotion_requests"):
        op.create_table(
            "strategy_promotion_requests",
            sa.Column("request_id", sa.String(), primary_key=True, nullable=False),
            sa.Column("strategy_id", sa.String(), sa.ForeignKey("strategy_definitions.strategy_id"), nullable=False),
            sa.Column("strategy_version_id", sa.String(), sa.ForeignKey("strategy_versions.version_id"), nullable=False),
            sa.Column("requested_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("requested_role", sa.String(length=40), nullable=False, server_default="admin"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("request_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("approval_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("require_validation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("require_dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("requested_stage", sa.String(length=20), nullable=True),
            sa.Column("approved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("rejected_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_strategy_id"):
        op.create_index("ix_strategy_promotion_requests_strategy_id", "strategy_promotion_requests", ["strategy_id"], unique=False)
    if not _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_strategy_version_id"):
        op.create_index(
            "ix_strategy_promotion_requests_strategy_version_id",
            "strategy_promotion_requests",
            ["strategy_version_id"],
            unique=False,
        )
    if not _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_requested_by"):
        op.create_index("ix_strategy_promotion_requests_requested_by", "strategy_promotion_requests", ["requested_by"], unique=False)
    if not _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_status"):
        op.create_index("ix_strategy_promotion_requests_status", "strategy_promotion_requests", ["status"], unique=False)
    if not _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_created_at"):
        op.create_index("ix_strategy_promotion_requests_created_at", "strategy_promotion_requests", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "strategy_promotion_requests"):
        if _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_created_at"):
            op.drop_index("ix_strategy_promotion_requests_created_at", table_name="strategy_promotion_requests")
        if _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_status"):
            op.drop_index("ix_strategy_promotion_requests_status", table_name="strategy_promotion_requests")
        if _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_requested_by"):
            op.drop_index("ix_strategy_promotion_requests_requested_by", table_name="strategy_promotion_requests")
        if _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_strategy_version_id"):
            op.drop_index("ix_strategy_promotion_requests_strategy_version_id", table_name="strategy_promotion_requests")
        if _index_exists(bind, "strategy_promotion_requests", "ix_strategy_promotion_requests_strategy_id"):
            op.drop_index("ix_strategy_promotion_requests_strategy_id", table_name="strategy_promotion_requests")
        op.drop_table("strategy_promotion_requests")

    if _table_exists(bind, "strategy_version_lifecycle"):
        op.execute("DROP INDEX IF EXISTS uq_strategy_lifecycle_production_per_strategy")
        op.execute("DROP INDEX IF EXISTS uq_strategy_lifecycle_active_per_strategy")
        if _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_lifecycle_state"):
            op.drop_index("ix_strategy_version_lifecycle_lifecycle_state", table_name="strategy_version_lifecycle")
        if _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_is_production"):
            op.drop_index("ix_strategy_version_lifecycle_is_production", table_name="strategy_version_lifecycle")
        if _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_is_active"):
            op.drop_index("ix_strategy_version_lifecycle_is_active", table_name="strategy_version_lifecycle")
        if _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_strategy_version_id"):
            op.drop_index("ix_strategy_version_lifecycle_strategy_version_id", table_name="strategy_version_lifecycle")
        if _index_exists(bind, "strategy_version_lifecycle", "ix_strategy_version_lifecycle_strategy_id"):
            op.drop_index("ix_strategy_version_lifecycle_strategy_id", table_name="strategy_version_lifecycle")
        op.drop_table("strategy_version_lifecycle")
