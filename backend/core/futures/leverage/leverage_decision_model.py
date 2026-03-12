from dataclasses import asdict, dataclass


@dataclass
class LeverageDecision:
    symbol: str
    strategy: str
    side: str
    base_leverage: float
    confidence_adjustment: float
    microstructure_adjustment: float
    liquidation_adjustment: float
    funding_adjustment: float
    final_leverage: float
    position_size_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)
