import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow


class UserMfaPreference(Base):
    __tablename__ = "user_mfa_preferences"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    totp_secret: Mapped[str | None] = mapped_column(String(120), nullable=True)
    totp_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_otp_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthMfaChallenge(Base):
    __tablename__ = "auth_mfa_challenges"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    challenge_token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    allowed_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    email_otp_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email_delivery_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserMfaBackupCode(Base):
    __tablename__ = "user_mfa_backup_codes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserMfaSecurityState(Base):
    __tablename__ = "user_mfa_security_state"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    mfa_grace_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_grace_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_totp_code_hash: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_totp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuthRiskEvent(Base):
    __tablename__ = "auth_risk_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    action_name: Mapped[str] = mapped_column(String(120), default="login", index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", index=True)
    risk_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    requires_step_up: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_iso: Mapped[str | None] = mapped_column(String(10), nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(160), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SuspiciousActivityAlert(Base):
    __tablename__ = "suspicious_activity_alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    risk_event_id: Mapped[str | None] = mapped_column(String, ForeignKey("auth_risk_events.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(80), default="risk_event")
    severity: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    title: Mapped[str] = mapped_column(String(180), default="suspicious_activity")
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    assigned_to_ops_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    resolved_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MfaRecoveryRequest(Base):
    __tablename__ = "mfa_recovery_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    required_approvals: Mapped[int] = mapped_column(default=2)
    approval_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    ready_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MfaRecoveryApprovalVote(Base):
    __tablename__ = "mfa_recovery_approval_votes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    recovery_request_id: Mapped[str] = mapped_column(String, ForeignKey("mfa_recovery_requests.id"), index=True)
    approver_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(20), default="approved")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecretProviderBinding(Base):
    __tablename__ = "secret_provider_bindings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_name: Mapped[str] = mapped_column(String(40), index=True)
    provider_version: Mapped[str] = mapped_column(String(40), default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BrandSetting(Base):
    __tablename__ = "brand_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    app_name: Mapped[str] = mapped_column(String(120), default="XILO User Trading Engine")
    logo_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_mime_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    logo_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_storage_note: Mapped[str] = mapped_column(Text, default="db_blob")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
