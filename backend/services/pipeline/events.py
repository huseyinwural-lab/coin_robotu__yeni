from datetime import datetime

from pydantic import BaseModel


class CandleClosedEvent(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime


class SignalDecision(BaseModel):
    signal: str
    symbol: str
    direction: str
    confidence: float
    strategy_id: str
    reason_codes: list[str]
    proposed_entry: float
    proposed_stop: float
    proposed_take_profit: float
    timestamp: datetime


class RiskDecision(BaseModel):
    approved: bool
    size: float
    leverage: int
    stop: float
    take_profit: float
    risk_tags: list[str]