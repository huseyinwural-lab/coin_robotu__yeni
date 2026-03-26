"""commercial ops enforcement and lifecycle columns

Revision ID: 20260326_0083
Revises: 20260326_0082
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0083"
down_revision = "20260326_0082"
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
        if not _has_column(bind, "commercial_export_manifests", "artifact_ref"):
            op.add_column("commercial_export_manifests", sa.Column("artifact_ref", sa.String(length=255), nullable=True))
        if not _has_column(bind, "commercial_export_manifests", "delivery_status"):
            op.add_column(
                "commercial_export_manifests",
                sa.Column("delivery_status", sa.String(length=20), nullable=False, server_default="pending"),
            )
        if not _has_column(bind, "commercial_export_manifests", "failure_reason"):
            op.add_column("commercial_export_manifests", sa.Column("failure_reason", sa.String(length=500), nullable=True))

    if _has_table(bind, "commercial_export_audits"):
        if not _has_column(bind, "commercial_export_audits", "artifact_ref"):
            op.add_column("commercial_export_audits", sa.Column("artifact_ref", sa.String(length=255), nullable=True))
        if not _has_column(bind, "commercial_export_audits", "delivery_status"):
            op.add_column(
                "commercial_export_audits",
                sa.Column("delivery_status", sa.String(length=20), nullable=False, server_default="pending"),
            )

    if _has_table(bind, "commercial_operational_control_transitions"):
        if not _has_column(bind, "commercial_operational_control_transitions", "previous_state_snapshot"):
            op.add_column(
                "commercial_operational_control_transitions",
                sa.Column("previous_state_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            )
        if not _has_column(bind, "commercial_operational_control_transitions", "new_state_snapshot"):
            op.add_column(
                "commercial_operational_control_transitions",
                sa.Column("new_state_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            )
        if not _has_column(bind, "commercial_operational_control_transitions", "changed_fields"):
            op.add_column(
                "commercial_operational_control_transitions",
                sa.Column("changed_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            )

    if _has_table(bind, "commercial_alert_events"):
        if not _has_column(bind, "commercial_alert_events", "triage_status"):
            op.add_column(
                "commercial_alert_events",
                sa.Column("triage_status", sa.String(length=20), nullable=False, server_default="new"),
            )
        if not _has_column(bind, "commercial_alert_events", "escalation_level"):
            op.add_column(
                "commercial_alert_events",
                sa.Column("escalation_level", sa.String(length=20), nullable=False, server_default="none"),
            )
        if not _has_column(bind, "commercial_alert_events", "acknowledged_by"):
            op.add_column("commercial_alert_events", sa.Column("acknowledged_by", sa.String(), nullable=True))
        if not _has_column(bind, "commercial_alert_events", "acknowledged_at"):
            op.add_column("commercial_alert_events", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
        if not _has_column(bind, "commercial_alert_events", "resolution_note"):
            op.add_column("commercial_alert_events", sa.Column("resolution_note", sa.String(length=500), nullable=True))
        if not _has_column(bind, "commercial_alert_events", "resolution_at"):
            op.add_column("commercial_alert_events", sa.Column("resolution_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "commercial_alert_events"):
        for column_name in ["resolution_at", "resolution_note", "acknowledged_at", "acknowledged_by", "escalation_level", "triage_status"]:
            if _has_column(bind, "commercial_alert_events", column_name):
                op.drop_column("commercial_alert_events", column_name)
    if _has_table(bind, "commercial_operational_control_transitions"):
        for column_name in ["changed_fields", "new_state_snapshot", "previous_state_snapshot"]:
            if _has_column(bind, "commercial_operational_control_transitions", column_name):
                op.drop_column("commercial_operational_control_transitions", column_name)
    if _has_table(bind, "commercial_export_audits"):
        for column_name in ["delivery_status", "artifact_ref"]:
            if _has_column(bind, "commercial_export_audits", column_name):
                op.drop_column("commercial_export_audits", column_name)
    if _has_table(bind, "commercial_export_manifests"):
        for column_name in ["failure_reason", "delivery_status", "artifact_ref"]:
            if _has_column(bind, "commercial_export_manifests", column_name):
                op.drop_column("commercial_export_manifests", column_name)
