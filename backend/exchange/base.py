from abc import ABC, abstractmethod
from typing import TypedDict


class AdapterExecutionResult(TypedDict):
    exchange_order_id: str
    status: str
    symbol: str
    side: str
    quantity: float
    mock_price: float
    mode: str


class ExchangeAdapter(ABC):
    name: str

    @abstractmethod
    def healthcheck(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def execute_mock_order(self, symbol: str, side: str, quantity: float) -> AdapterExecutionResult:
        raise NotImplementedError