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
