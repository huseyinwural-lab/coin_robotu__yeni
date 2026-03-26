from __future__ import annotations

from abc import ABC, abstractmethod


class BaseExecutionAdapter(ABC):
    adapter_name: str = "base"

    @abstractmethod
    def submit_order(self, payload: dict) -> dict:
        raise NotImplementedError
