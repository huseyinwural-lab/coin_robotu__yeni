import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow


class AdminExchangeCredential(Base):
    __tablename__ = "admin_exchange_credentials"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scope_type: Mapped[str] = mapped_column(String(20), default="global", index=True)
    scope_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    exchange: Mapped[str] = mapped_column(String(40), default="binance", index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="spot", index=True)
    purpose: Mapped[str] = mapped_column(String(40), default="market_data", index=True)
    environment: Mapped[str] = mapped_column(String(20), default="testnet", index=True)

    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_secret_encrypted: Mapped[str] = mapped_column(Text, default="")
    passphrase_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    base_url_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_binding_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)

    last_probe_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_probe_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_probe_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CredentialAssignmentRule(Base):
    __tablename__ = "credential_assignment_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    exchange: Mapped[str] = mapped_column(String(40), default="binance", index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="spot", index=True)
    environment: Mapped[str] = mapped_column(String(20), default="testnet", index=True)

    tenant_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)

    preferred_source: Mapped[str] = mapped_column(String(30), default="user")
    fallback_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
