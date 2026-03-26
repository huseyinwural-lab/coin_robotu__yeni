"""commercial ops backoffice domains

Revision ID: 20260326_0082
Revises: 20260326_0081
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0082"
down_revision = "20260326_0081"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "commercial_subscription_profiles"):
        op.create_table(
            "commercial_subscription_profiles",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
            sa.Column("subscription_status", sa.String(length=30), nullable=False, server_default="inactive"),
            sa.Column("tier_code", sa.String(length=40), nullable=False, server_default="free"),
            sa.Column("billing_cycle", sa.String(length=20), nullable=False, server_default="monthly"),
            sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("renewal_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("subscription_fee_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("profit_share_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("user_id", "environment", name="uq_commercial_sub_profile_user_env"),
        )
        op.create_index("ix_commercial_sub_profile_user_id", "commercial_subscription_profiles", ["user_id"])
        op.create_index("ix_commercial_sub_profile_environment", "commercial_subscription_profiles", ["environment"])

    if not _has_table(bind, "commercial_usage_events"):
        op.create_table(
            "commercial_usage_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
            sa.Column("event_type", sa.String(length=30), nullable=False, server_default="api_call"),
            sa.Column("endpoint", sa.String(length=160), nullable=False, server_default="/api/admin/commercial/overview"),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_commercial_usage_events_created_at", "commercial_usage_events", ["created_at"])
        op.create_index("ix_commercial_usage_events_event_type", "commercial_usage_events", ["event_type"])
        op.create_index("ix_commercial_usage_events_endpoint", "commercial_usage_events", ["endpoint"])

    if not _has_table(bind, "commercial_export_manifests"):
        op.create_table(
            "commercial_export_manifests",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("export_type", sa.String(length=40), nullable=False),
            sa.Column("schema_version", sa.String(length=20), nullable=False, server_default="v1"),
            sa.Column("requested_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("filters_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("column_mapping", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("output_format", sa.String(length=20), nullable=False, server_default="csv"),
            sa.Column("checksum", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("file_hash", sa.String(length=128), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        )
        op.create_index("ix_commercial_export_manifests_export_type", "commercial_export_manifests", ["export_type"])

    if not _has_table(bind, "commercial_export_schedules"):
        op.create_table(
            "commercial_export_schedules",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("export_type", sa.String(length=40), nullable=False),
            sa.Column("schedule_period", sa.String(length=20), nullable=False, server_default="daily"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("output_format", sa.String(length=20), nullable=False, server_default="csv"),
            sa.Column("requested_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("filters_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_status", sa.String(length=20), nullable=False, server_default="never"),
            sa.Column("last_output_ref", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_commercial_export_schedules_export_type", "commercial_export_schedules", ["export_type"])
        op.create_index("ix_commercial_export_schedules_schedule_period", "commercial_export_schedules", ["schedule_period"])

    if not _has_table(bind, "commercial_export_audits"):
        op.create_table(
            "commercial_export_audits",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("export_id", sa.String(), nullable=False),
            sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("actor_email", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("export_type", sa.String(length=40), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("filters_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("file_hash", sa.String(length=128), nullable=True),
            sa.Column("reason_note", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_commercial_export_audits_export_id", "commercial_export_audits", ["export_id"])

    if not _has_table(bind, "commercial_operational_control_states"):
        op.create_table(
            "commercial_operational_control_states",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, unique=True),
            sa.Column("trading_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("capital_frozen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("withdraw_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("emergency_stop", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("reason_note", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_commercial_operational_control_states_user_id", "commercial_operational_control_states", ["user_id"])

    if not _has_table(bind, "commercial_operational_control_transitions"):
        op.create_table(
            "commercial_operational_control_transitions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("actor_email", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("previous_state", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("next_state", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("reason_note", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_commercial_operational_control_transitions_user_id", "commercial_operational_control_transitions", ["user_id"])

    if not _has_table(bind, "commercial_alert_events"):
        op.create_table(
            "commercial_alert_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("alert_type", sa.String(length=80), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
            sa.Column("source", sa.String(length=60), nullable=False, server_default="commercial_overview"),
            sa.Column("entity_type", sa.String(length=40), nullable=False, server_default="system"),
            sa.Column("entity_id", sa.String(length=120), nullable=False, server_default="global"),
            sa.Column("title", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("message", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("suggested_action", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_commercial_alert_events_alert_type", "commercial_alert_events", ["alert_type"])
        op.create_index("ix_commercial_alert_events_created_at", "commercial_alert_events", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in [
        "commercial_alert_events",
        "commercial_operational_control_transitions",
        "commercial_operational_control_states",
        "commercial_export_audits",
        "commercial_export_schedules",
        "commercial_export_manifests",
        "commercial_usage_events",
        "commercial_subscription_profiles",
    ]:
        if _has_table(bind, table_name):
            op.drop_table(table_name)
