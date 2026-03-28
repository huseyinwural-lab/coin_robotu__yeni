"""query engine expression indexes for advanced filtering and full-text search

Revision ID: 20260328_0096
Revises: 20260328_0095
Create Date: 2026-03-28
"""

from alembic import op


revision = "20260328_0096"
down_revision = "20260328_0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_strategy_id_expr
        ON audit_logs ((lower(COALESCE(details->>'strategy_id', ''))))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_symbol_expr
        ON audit_logs ((upper(COALESCE(details->>'symbol', ''))))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id_expr
        ON audit_logs ((COALESCE(details->>'user_id', '')))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type_expr
        ON audit_logs ((lower(COALESCE(details->>'event_type', ''))))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_correlation_expr
        ON audit_logs ((COALESCE(details->>'correlation_id', '')))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_details_tsvector
        ON audit_logs
        USING GIN (to_tsvector('simple', COALESCE(details::text, '')))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_details_tsvector")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_correlation_expr")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_event_type_expr")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_user_id_expr")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_symbol_expr")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_strategy_id_expr")
