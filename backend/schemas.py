from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class BotProfileBase(BaseModel):
    name: str
    exchange: str = "binance"
    market_type: str = "spot"
    symbols: list[str]
    strategy_type: str
    timeframe: str = "15m"
    trend_timeframe: str = "1h"
    leverage: int = Field(default=3, ge=1, le=25)
    is_enabled: bool = True


class BotProfileCreate(BotProfileBase):
    pass


class BotProfileUpdate(BaseModel):
    name: str
    exchange: str
    market_type: str
    symbols: list[str]
    strategy_type: str
    timeframe: str
    trend_timeframe: str
    leverage: int = Field(default=3, ge=1, le=25)
    is_enabled: bool


class BotProfileResponse(BotProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class RiskPolicyBase(BaseModel):
    name: str
    position_size_pct: float
    atr_stop_multiplier: float
    risk_reward_ratio: float
    daily_loss_cutoff_pct: float
    max_open_positions: int
    max_leverage: int = 3
    spread_limit_bps: int = 30
    slippage_limit_bps: int = 40
    min_liquidity_usdt: int = 100000


class RiskPolicyCreate(RiskPolicyBase):
    pass


class RiskPolicyUpdate(RiskPolicyBase):
    pass


class RiskPolicyResponse(RiskPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class StrategyTemplateBase(BaseModel):
    name: str
    strategy_type: str
    parameters: dict
    is_active: bool = True


class StrategyTemplateCreate(StrategyTemplateBase):
    pass


class StrategyTemplateUpdate(StrategyTemplateBase):
    pass


class StrategyTemplateResponse(StrategyTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_user_id: str | None
    actor_role: str
    action: str
    entity_type: str
    entity_id: str
    severity: str
    details: dict
    created_at: datetime


class MockOrderRequest(BaseModel):
    bot_profile_id: str
    symbol: str
    side: str
    quantity: float = Field(gt=0)


class ExecutionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bot_profile_id: str
    exchange: str
    symbol: str
    side: str
    quantity: float
    mock_price: float
    execution_status: str
    response_payload: dict
    note: str
    created_at: datetime