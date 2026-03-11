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
    signal_strength: float = 0.0
    signal_score: float = 0.0
    metadata: dict = {}


class RiskDecision(BaseModel):
    approved: bool
    size: float
    leverage: int
    stop: float
    take_profit: float
    risk_tags: list[str]
    equity: float = 0
    trade_allocation_usdt: float = 0
    risk_amount_usdt: float = 0
    strategy_drawdown_pct: float = 0
    portfolio_drawdown_pct: float = 0
    open_risk_pct: float = 0
    capital_allocation: dict = {}