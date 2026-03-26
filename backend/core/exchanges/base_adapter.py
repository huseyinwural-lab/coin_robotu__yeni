from __future__ import annotations

from abc import ABC, abstractmethod


class BaseExecutionAdapter(ABC):
    adapter_name: str = "base"

    @abstractmethod
    def submit_order(self, payload: dict) -> dict:
        raise NotImplementedError

    def get_order_status(self, *, symbol: str, order_id: str) -> dict:
        raise NotImplementedError

    def cancel_order(self, *, symbol: str, order_id: str) -> dict:
        raise NotImplementedError

    def get_available_balance(self, *, asset: str = "USDT") -> float:
        return 0.0
