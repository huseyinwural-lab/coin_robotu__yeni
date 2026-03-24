import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdentityRolePolicy(Base):
    __tablename__ = "identity_role_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    role_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_privileged: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserRoleBinding(Base):
    __tablename__ = "user_role_bindings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_role_bindings_user_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    role_policy_id: Mapped[str | None] = mapped_column(String, ForeignKey("identity_role_policies.id"), nullable=True, index=True)
    extra_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    denied_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginHistoryEvent(Base):
    __tablename__ = "login_history_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    endpoint_scope: Mapped[str] = mapped_column(String(80), default="login")
    outcome: Mapped[str] = mapped_column(String(40), default="FAILED", index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    lock_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ApprovalPolicyConfig(Base):
    __tablename__ = "approval_policy_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    action_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    requester_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    approver_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    override_allowed_for_super_admin: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IdentityApprovalRequest(Base):
    __tablename__ = "identity_approval_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    action_key: Mapped[str] = mapped_column(String(120), index=True)
    target_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    request_reason: Mapped[str] = mapped_column(Text, default="")
    approval_note: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    rejected_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    approval_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserIdentityProfile(Base):
    __tablename__ = "user_identity_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_identity_profiles_user_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    capital_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, default=False)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    non_compliant_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    live_trading_eligible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    eligible_for_login: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    eligible_for_ops: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    compliance_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    policy_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    soft_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    delete_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delete_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    hard_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    hard_delete_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_seen_device: Mapped[str | None] = mapped_column(String(160), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserStrategyScope(Base):
    __tablename__ = "user_strategy_scopes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    strategy_code: Mapped[str] = mapped_column(String(120), index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserBotScope(Base):
    __tablename__ = "user_bot_scopes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    bot_profile_id: Mapped[str] = mapped_column(String, ForeignKey("bot_profiles.id"), index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserInviteToken(Base):
    __tablename__ = "user_invite_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    invited_role: Mapped[str] = mapped_column(String(40), default="user")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    invite_delivery_status: Mapped[str] = mapped_column(String(40), default="MOCKED_SENT")
    invite_preview_token: Mapped[str | None] = mapped_column(String(180), nullable=True)
    invited_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    resend_count: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
