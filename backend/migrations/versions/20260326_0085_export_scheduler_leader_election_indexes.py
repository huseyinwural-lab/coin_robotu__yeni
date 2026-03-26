"""export scheduler leader-election indexes and idempotency uniqueness

Revision ID: 20260326_0085
Revises: 20260326_0084
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0085"
down_revision = "20260326_0084"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "commercial_export_manifests"):
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_commercial_export_manifests_idempotency_key
            ON commercial_export_manifests (idempotency_key)
            WHERE idempotency_key IS NOT NULL
            """
        )

    if _has_table(bind, "commercial_export_schedules"):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_commercial_export_schedules_claim_recovery
            ON commercial_export_schedules (is_active, last_status, claim_expires_at, next_retry_at, last_run_at)
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_commercial_export_schedules_claim_recovery")
    op.execute("DROP INDEX IF EXISTS uq_commercial_export_manifests_idempotency_key")
