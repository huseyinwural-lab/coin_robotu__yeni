import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow


class RuntimeScanCandidate(Base):
    __tablename__ = "runtime_scan_candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market_type: Mapped[str] = mapped_column(String(20), index=True)
    scan_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=utcnow)
    strategy_signal: Mapped[str] = mapped_column(String(20), default="PASS")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    decision: Mapped[str] = mapped_column(String(10), index=True, default="PASS")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    def to_learning_seed(self) -> dict:
        return {
            "symbol": self.symbol,
            "decision": self.decision,
            "decision_timestamp": self.scan_timestamp.isoformat() if self.scan_timestamp else None,
            "outcome_placeholder": None,
            "strategy_attribution": self.strategy_signal,
            "filter_attribution": "risk_filter" if float(self.risk_score or 0) > 0 else None,
            "confidence": float(self.confidence or 0),
        }
