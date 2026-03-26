import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPS = "ops"
    USER = "user"

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="approved")
    approval_requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @property
    def status(self) -> str:
        return "active" if self.is_active else "disabled"

class UserOnboardingProfile(Base):
    __tablename__ = "user_onboarding_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    kyc_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    aml_flag: Mapped[str] = mapped_column(String(30), default="clear", index=True)
    aml_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_validity: Mapped[str] = mapped_column(String(20), default="unknown")
    balance_usd: Mapped[float] = mapped_column(Float, default=0.0)
    first_funding_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    region_compliance_status: Mapped[str] = mapped_column(String(20), default="unknown")
    leverage_permission: Mapped[bool] = mapped_column(Boolean, default=False)
    futures_capability: Mapped[bool] = mapped_column(Boolean, default=False)
    spot_capability: Mapped[bool] = mapped_column(Boolean, default=True)
    trading_eligibility: Mapped[bool] = mapped_column(Boolean, default=False)
    precheck_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    verification_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserKycDocument(Base):
    __tablename__ = "user_kyc_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    storage_ref: Mapped[str] = mapped_column(Text)
    upload_status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OnboardingAmlDenylist(Base):
    __tablename__ = "onboarding_aml_denylist"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    match_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    match_type: Mapped[str] = mapped_column(String(30), default="email")
    reason: Mapped[str] = mapped_column(Text, default="aml_internal_denylist")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserOnboardingDecisionLog(Base):
    __tablename__ = "user_onboarding_decision_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(30), index=True)
    decision_source: Mapped[str] = mapped_column(String(30), default="manual")
    actor_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class UserOnboardingWorkflowCase(Base):
    __tablename__ = "user_onboarding_workflow_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    workflow_status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    current_step: Mapped[str] = mapped_column(String(20), default="ops", index=True)
    assigned_admin_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalation_count: Mapped[int] = mapped_column(default=0)
    supervisor_queue: Mapped[bool] = mapped_column(Boolean, default=False)
    workflow_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserOnboardingWorkflowStepLog(Base):
    __tablename__ = "user_onboarding_workflow_step_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_case_id: Mapped[str] = mapped_column(String, ForeignKey("user_onboarding_workflow_cases.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    step_name: Mapped[str] = mapped_column(String(20), index=True)
    step_status: Mapped[str] = mapped_column(String(20), default="completed")
    actor_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class UserActivationEvent(Base):
    __tablename__ = "user_activation_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
