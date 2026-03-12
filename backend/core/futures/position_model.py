from dataclasses import dataclass


@dataclass
class FuturesPosition:
    symbol: str
    side: str
    entry_price: float
    mark_price: float
    position_size: float
    notional_value: float
    leverage: float
    initial_margin: float
    maintenance_margin: float
    unrealized_pnl: float
    liquidation_price: float
    margin_ratio: float
    distance_to_liquidation: float

    def __post_init__(self):
        self.symbol = self.symbol.upper()
        self.side = self.side.upper()
        if self.side not in {"LONG", "SHORT"}:
            raise ValueError("invalid_side")
        if self.entry_price <= 0 or self.mark_price <= 0:
            raise ValueError("invalid_price")
        if self.position_size <= 0:
            raise ValueError("invalid_position_size")
        if self.leverage <= 0:
            raise ValueError("invalid_leverage")
