"""identity control plane tables

Revision ID: 20260324_0070
Revises: 20260324_0069
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260324_0070"
down_revision = "20260324_0069"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "identity_role_policies"):
        op.create_table(
            "identity_role_policies",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("role_key", sa.String(length=80), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_privileged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("permissions", sa.JSON(), nullable=False),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("role_key", name="uq_identity_role_policies_role_key"),
        )

    if not _table_exists(bind, "user_role_bindings"):
        op.create_table(
            "user_role_bindings",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role_policy_id", sa.String(), sa.ForeignKey("identity_role_policies.id"), nullable=True),
            sa.Column("extra_permissions", sa.JSON(), nullable=False),
            sa.Column("denied_permissions", sa.JSON(), nullable=False),
            sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_user_role_bindings_user_id"),
        )

    if not _table_exists(bind, "auth_sessions"):
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("ip_address", sa.String(length=120), nullable=True),
            sa.Column("user_agent", sa.String(length=300), nullable=True),
            sa.Column("device_fingerprint", sa.String(length=160), nullable=True),
            sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("revoked_reason", sa.String(length=255), nullable=True),
            sa.Column("revoked_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        )

    if not _table_exists(bind, "login_history_events"):
        op.create_table(
            "login_history_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("endpoint_scope", sa.String(length=80), nullable=False, server_default="login"),
            sa.Column("outcome", sa.String(length=40), nullable=False, server_default="FAILED"),
            sa.Column("failure_reason", sa.String(length=120), nullable=True),
            sa.Column("ip_address", sa.String(length=120), nullable=True),
            sa.Column("user_agent", sa.String(length=300), nullable=True),
            sa.Column("device_fingerprint", sa.String(length=160), nullable=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("lock_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists(bind, "approval_policy_configs"):
        op.create_table(
            "approval_policy_configs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("action_key", sa.String(length=120), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("requester_roles", sa.JSON(), nullable=False),
            sa.Column("approver_roles", sa.JSON(), nullable=False),
            sa.Column("override_allowed_for_super_admin", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("action_key", name="uq_approval_policy_configs_action_key"),
        )

    if not _table_exists(bind, "identity_approval_requests"):
        op.create_table(
            "identity_approval_requests",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("action_key", sa.String(length=120), nullable=False),
            sa.Column("target_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("request_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("approval_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("requested_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("approved_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("rejected_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("approval_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists(bind, "user_identity_profiles"):
        op.create_table(
            "user_identity_profiles",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("capital_limit", sa.Float(), nullable=True),
            sa.Column("trading_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("kill_switch_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("non_compliant_since", sa.DateTime(timezone=True), nullable=True),
            sa.Column("live_trading_eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("compliance_snapshot", sa.JSON(), nullable=False),
            sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("password_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("soft_deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_ip", sa.String(length=120), nullable=True),
            sa.Column("last_seen_device", sa.String(length=160), nullable=True),
            sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_user_identity_profiles_user_id"),
        )

    if not _table_exists(bind, "user_strategy_scopes"):
        op.create_table(
            "user_strategy_scopes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("strategy_code", sa.String(length=120), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists(bind, "user_bot_scopes"):
        op.create_table(
            "user_bot_scopes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("bot_profile_id", sa.String(), sa.ForeignKey("bot_profiles.id"), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists(bind, "user_invite_tokens"):
        op.create_table(
            "user_invite_tokens",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("invited_role", sa.String(length=40), nullable=False, server_default="user"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("invite_delivery_status", sa.String(length=40), nullable=False, server_default="MOCKED_SENT"),
            sa.Column("invite_preview_token", sa.String(length=180), nullable=True),
            sa.Column("invited_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("token_hash", name="uq_user_invite_tokens_token_hash"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = [
        "user_invite_tokens",
        "user_bot_scopes",
        "user_strategy_scopes",
        "user_identity_profiles",
        "identity_approval_requests",
        "approval_policy_configs",
        "login_history_events",
        "auth_sessions",
        "user_role_bindings",
        "identity_role_policies",
    ]
    for table_name in tables:
        if _table_exists(bind, table_name):
            op.drop_table(table_name)
