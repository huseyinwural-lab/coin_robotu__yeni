"""operational debugging acceleration layer tables and indexes

Revision ID: 20260328_0094
Revises: 20260327_0093
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_0094"
down_revision = "20260327_0093"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "lifecycle_saved_queries"):
        op.create_table(
            "lifecycle_saved_queries",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_lifecycle_saved_queries_user_id", "lifecycle_saved_queries", ["user_id"], unique=False)
        op.create_index("ix_lifecycle_saved_queries_name", "lifecycle_saved_queries", ["name"], unique=False)

    if not _has_table(bind, "debug_incidents"):
        op.create_table(
            "debug_incidents",
            sa.Column("incident_id", sa.String(), primary_key=True),
            sa.Column("title", sa.String(length=220), nullable=False, server_default="Untitled Incident"),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="CRITICAL"),
            sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("linked_correlation_id", sa.String(length=120), nullable=True),
            sa.Column("source_event_id", sa.String(length=120), nullable=True),
            sa.Column("fingerprint", sa.String(length=128), nullable=True),
            sa.Column("cluster_id", sa.String(length=80), nullable=True),
            sa.Column("root_cause", sa.String(length=160), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("auto_created", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("dedupe_window_seconds", sa.Integer(), nullable=False, server_default="300"),
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_debug_incidents_severity", "debug_incidents", ["severity"], unique=False)
        op.create_index("ix_debug_incidents_status", "debug_incidents", ["status"], unique=False)
        op.create_index("ix_debug_incidents_linked_correlation_id", "debug_incidents", ["linked_correlation_id"], unique=False)
        op.create_index("ix_debug_incidents_source_event_id", "debug_incidents", ["source_event_id"], unique=False)
        op.create_index("ix_debug_incidents_fingerprint", "debug_incidents", ["fingerprint"], unique=False)
        op.create_index("ix_debug_incidents_cluster_id", "debug_incidents", ["cluster_id"], unique=False)

    if _has_table(bind, "audit_logs"):
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_audit_logs_details_trgm
            ON audit_logs
            USING GIN ((COALESCE(details::text, '')) gin_trgm_ops)
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at_desc
            ON audit_logs (created_at DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_audit_logs_correlation_details
            ON audit_logs ((COALESCE(details->>'correlation_id', '')))
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_correlation_details")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_created_at_desc")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_details_trgm")

    bind = op.get_bind()
    if _has_table(bind, "debug_incidents"):
        op.drop_table("debug_incidents")
    if _has_table(bind, "lifecycle_saved_queries"):
        op.drop_table("lifecycle_saved_queries")
