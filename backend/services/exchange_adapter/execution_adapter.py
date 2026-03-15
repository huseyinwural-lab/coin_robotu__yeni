from datetime import datetime, timezone
import os

from services.exchange_adapter.precision_normalizer import normalize_order_values
from services.exchange_adapter.symbol_mapper import to_exchange_symbol


class ExchangeExecutionAdapter:
    def __init__(self):
        self.credentials = {
            "bybit": {
                "api_key": os.environ.get("BYBIT_API_KEY", "").strip(),
                "api_secret": os.environ.get("BYBIT_API_SECRET", "").strip(),
            },
            "okx": {
                "api_key": os.environ.get("OKX_API_KEY", "").strip(),
                "api_secret": os.environ.get("OKX_API_SECRET", "").strip(),
                "passphrase": os.environ.get("OKX_API_PASSPHRASE", "").strip(),
            },
        }

    def submit_order(
        self,
        *,
        exchange: str,
        symbol: str,
        side: str,
        price: float,
        qty: float,
        leverage: int,
    ) -> dict:
        exchange_code = str(exchange or "").lower().strip()
        normalized = normalize_order_values(exchange_code, price=price, qty=qty, leverage=leverage)
        exchange_symbol = to_exchange_symbol(exchange_code, symbol)
        creds = self.credentials.get(exchange_code) or {}
        has_creds = bool(creds.get("api_key") and creds.get("api_secret"))

        if not has_creds:
            return {
                "exchange": exchange_code,
                "symbol": exchange_symbol,
                "status": "MOCKED",
                "mocked": True,
                "side": str(side or "buy").lower(),
                "normalized": normalized,
                "reason": "missing_exchange_credentials",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "exchange": exchange_code,
            "symbol": exchange_symbol,
            "status": "SUBMITTED",
            "mocked": False,
            "side": str(side or "buy").lower(),
            "normalized": normalized,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
