"""scheduler hardening and alert operations columns

Revision ID: 20260326_0084
Revises: 20260326_0083
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0084"
down_revision = "20260326_0083"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "commercial_export_manifests"):
        for column_name, column in [
            ("idempotency_key", sa.Column("idempotency_key", sa.String(length=160), nullable=True)),
            ("retention_expires_at", sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True)),
            ("retention_state", sa.Column("retention_state", sa.String(length=20), nullable=False, server_default="active")),
            ("downloadable_state", sa.Column("downloadable_state", sa.String(length=20), nullable=False, server_default="ready")),
            ("signed_download_url", sa.Column("signed_download_url", sa.String(length=500), nullable=True)),
        ]:
            if not _has_column(bind, "commercial_export_manifests", column_name):
                op.add_column("commercial_export_manifests", column)

    if _has_table(bind, "commercial_export_schedules"):
        schedule_columns = [
            ("running_started_at", sa.Column("running_started_at", sa.DateTime(timezone=True), nullable=True)),
            ("claim_token", sa.Column("claim_token", sa.String(length=120), nullable=True)),
            ("claim_expires_at", sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True)),
            ("retry_count", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")),
            ("next_retry_at", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True)),
            ("last_failure_reason", sa.Column("last_failure_reason", sa.String(length=500), nullable=True)),
            ("max_retry", sa.Column("max_retry", sa.Integer(), nullable=False, server_default="3")),
            ("last_execution_window", sa.Column("last_execution_window", sa.String(length=80), nullable=True)),
            ("stale_run_flag", sa.Column("stale_run_flag", sa.Boolean(), nullable=False, server_default=sa.text("false"))),
        ]
        for column_name, column in schedule_columns:
            if not _has_column(bind, "commercial_export_schedules", column_name):
                op.add_column("commercial_export_schedules", column)

    if _has_table(bind, "commercial_alert_events"):
        alert_columns = [
            ("assigned_to_user_id", sa.Column("assigned_to_user_id", sa.String(), nullable=True)),
            ("assigned_to_email", sa.Column("assigned_to_email", sa.String(length=255), nullable=True)),
            ("assigned_at", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True)),
            ("assignment_note", sa.Column("assignment_note", sa.String(length=500), nullable=True)),
            ("age_seconds", sa.Column("age_seconds", sa.Integer(), nullable=False, server_default="0")),
            ("sla_state", sa.Column("sla_state", sa.String(length=20), nullable=False, server_default="within_sla")),
            ("auto_escalated", sa.Column("auto_escalated", sa.Boolean(), nullable=False, server_default=sa.text("false"))),
            ("auto_escalated_at", sa.Column("auto_escalated_at", sa.DateTime(timezone=True), nullable=True)),
        ]
        for column_name, column in alert_columns:
            if not _has_column(bind, "commercial_alert_events", column_name):
                op.add_column("commercial_alert_events", column)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "commercial_alert_events"):
        for column_name in [
            "auto_escalated_at",
            "auto_escalated",
            "sla_state",
            "age_seconds",
            "assignment_note",
            "assigned_at",
            "assigned_to_email",
            "assigned_to_user_id",
        ]:
            if _has_column(bind, "commercial_alert_events", column_name):
                op.drop_column("commercial_alert_events", column_name)

    if _has_table(bind, "commercial_export_schedules"):
        for column_name in [
            "stale_run_flag",
            "last_execution_window",
            "max_retry",
            "last_failure_reason",
            "next_retry_at",
            "retry_count",
            "claim_expires_at",
            "claim_token",
            "running_started_at",
        ]:
            if _has_column(bind, "commercial_export_schedules", column_name):
                op.drop_column("commercial_export_schedules", column_name)

    if _has_table(bind, "commercial_export_manifests"):
        for column_name in [
            "signed_download_url",
            "downloadable_state",
            "retention_state",
            "retention_expires_at",
            "idempotency_key",
        ]:
            if _has_column(bind, "commercial_export_manifests", column_name):
                op.drop_column("commercial_export_manifests", column_name)
