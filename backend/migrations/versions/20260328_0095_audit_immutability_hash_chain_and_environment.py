"""audit immutability, hash-chain signature, and environment columns

Revision ID: 20260328_0095
Revises: 20260328_0094
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_0095"
down_revision = "20260328_0094"
branch_labels = None
depends_on = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = [item["name"] for item in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "audit_logs", "environment"):
        op.add_column("audit_logs", sa.Column("environment", sa.String(length=20), nullable=False, server_default="prod"))
        op.create_index("ix_audit_logs_environment", "audit_logs", ["environment"], unique=False)

    if not _has_column(bind, "audit_logs", "is_test_event"):
        op.add_column("audit_logs", sa.Column("is_test_event", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        op.create_index("ix_audit_logs_is_test_event", "audit_logs", ["is_test_event"], unique=False)

    if not _has_column(bind, "audit_logs", "previous_event_hash"):
        op.add_column("audit_logs", sa.Column("previous_event_hash", sa.String(length=64), nullable=True))

    if not _has_column(bind, "audit_logs", "event_hash"):
        op.add_column("audit_logs", sa.Column("event_hash", sa.String(length=64), nullable=True))
        op.create_index("ix_audit_logs_event_hash", "audit_logs", ["event_hash"], unique=False)

    if not _has_column(bind, "audit_logs", "signature_version"):
        op.add_column("audit_logs", sa.Column("signature_version", sa.String(length=20), nullable=False, server_default="v1"))

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_logs_update_delete()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_audit_logs_no_update'
            ) THEN
                CREATE TRIGGER trg_audit_logs_no_update
                BEFORE UPDATE ON audit_logs
                FOR EACH ROW EXECUTE FUNCTION prevent_audit_logs_update_delete();
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_audit_logs_no_delete'
            ) THEN
                CREATE TRIGGER trg_audit_logs_no_delete
                BEFORE DELETE ON audit_logs
                FOR EACH ROW EXECUTE FUNCTION prevent_audit_logs_update_delete();
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_logs_update_delete")

    bind = op.get_bind()
    if _has_column(bind, "audit_logs", "signature_version"):
        op.drop_column("audit_logs", "signature_version")
    if _has_column(bind, "audit_logs", "event_hash"):
        op.drop_index("ix_audit_logs_event_hash", table_name="audit_logs")
        op.drop_column("audit_logs", "event_hash")
    if _has_column(bind, "audit_logs", "previous_event_hash"):
        op.drop_column("audit_logs", "previous_event_hash")
    if _has_column(bind, "audit_logs", "is_test_event"):
        op.drop_index("ix_audit_logs_is_test_event", table_name="audit_logs")
        op.drop_column("audit_logs", "is_test_event")
    if _has_column(bind, "audit_logs", "environment"):
        op.drop_index("ix_audit_logs_environment", table_name="audit_logs")
        op.drop_column("audit_logs", "environment")
