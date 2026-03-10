import random
import uuid
from datetime import datetime, timezone

from exchange.base import AdapterExecutionResult, ExchangeAdapter


class BinanceMockAdapter(ExchangeAdapter):
    name = "binance"

    def __init__(self, redis_client):
        self.redis_client = redis_client

    def healthcheck(self) -> dict:
        self.redis_client.set("exchange:binance:mock:last_ping", datetime.now(timezone.utc).isoformat())
        return {
            "exchange": self.name,
            "connection": "ready",
            "mode": "mock",
            "last_ping": self.redis_client.get("exchange:binance:mock:last_ping"),
        }

    def execute_mock_order(self, symbol: str, side: str, quantity: float) -> AdapterExecutionResult:
        base_price = random.uniform(95, 105)
        drift = random.uniform(-1.2, 1.2)
        simulated_price = round(base_price + drift, 4)

        payload: AdapterExecutionResult = {
            "exchange_order_id": f"MOCK-{uuid.uuid4().hex[:12].upper()}",
            "status": "filled",
            "symbol": symbol.upper(),
            "side": side.lower(),
            "quantity": quantity,
            "mock_price": simulated_price,
            "mode": "mock",
        }
        self.redis_client.set("exchange:binance:mock:last_order", str(payload))
        return payload