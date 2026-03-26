import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow


class RuntimeSmokeRun(Base):
    __tablename__ = "runtime_smoke_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(40), default="PASS", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[dict] = mapped_column(JSON, default=dict)
    trigger_source: Mapped[str] = mapped_column(String(40), default="manual")
    report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
