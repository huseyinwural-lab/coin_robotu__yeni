import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow


class SignalGovernanceDecision(Base):
    __tablename__ = "signal_governance_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    signal_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_observability_events.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    actor_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlaybookExecutionRun(Base):
    __tablename__ = "playbook_execution_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    preview_token: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    chain_id: Mapped[str] = mapped_column(String(120), index=True)
    execution_state: Mapped[str] = mapped_column(String(30), default="preview", index=True)
    steps: Mapped[list[dict]] = mapped_column(JSON, default=list)
    scope_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    executed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlaybookRollbackMarker(Base):
    __tablename__ = "playbook_rollback_markers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    playbook_run_id: Mapped[str] = mapped_column(String, ForeignKey("playbook_execution_runs.id"), index=True)
    chain_id: Mapped[str] = mapped_column(String(120), index=True)
    execution_state: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    rollback_state: Mapped[str] = mapped_column(String(30), default="ready", index=True)
    rollback_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
