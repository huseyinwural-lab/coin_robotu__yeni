from pydantic import BaseModel, Field, field_validator

from services.quote_asset_policy import normalize_quote_symbol


class FuturesExecutionRequest(BaseModel):
    symbol: str = Field(min_length=5, max_length=20)
    side: str = Field(pattern="^(BUY|SELL)$")
    order_type: str = Field(pattern="^(MARKET|LIMIT)$")
    quantity: float = Field(gt=0)
    leverage: float = Field(gt=0)
    reduce_only: bool = False
    client_order_id: str = Field(min_length=6, max_length=120)
    decision_trace_id: str = Field(min_length=6, max_length=120)
    strategy: str = Field(min_length=3, max_length=80)
    reason_context: dict = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return normalize_quote_symbol(value)


class FuturesExecutionResponse(BaseModel):
    accepted: bool
    environment: str = "live"
    reason_code: str
    exchange_order_id: str | None = None
    client_order_id: str
    status: str
    order_payload: dict = Field(default_factory=dict)
