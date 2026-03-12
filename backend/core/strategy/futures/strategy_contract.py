from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StrategySignal:
    symbol: str
    side: str
    confidence: float
    regime: str
    reason: str


class FuturesStrategy(ABC):
    @abstractmethod
    def generate_signal(self, market_state: dict) -> StrategySignal:
        raise NotImplementedError
