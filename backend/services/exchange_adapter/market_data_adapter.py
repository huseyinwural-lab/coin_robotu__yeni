from datetime import datetime, timezone

import httpx

from services.exchange_adapter.retry_handler import with_retry
from services.exchange_adapter.symbol_mapper import to_exchange_symbol


class ExchangeMarketDataAdapter:
    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds

    def fetch_ticker(self, *, exchange: str, symbol: str) -> dict:
        exchange_code = str(exchange or "").lower().strip()
        symbol_code = to_exchange_symbol(exchange_code, symbol)

        if exchange_code == "bybit":
            return self._fetch_bybit(symbol_code)
        if exchange_code == "okx":
            return self._fetch_okx(symbol_code)
        raise ValueError("unsupported_exchange")

    def _fetch_bybit(self, symbol: str) -> dict:
        def _request():
            response = httpx.get(
                "https://api.bybit.com/v5/market/tickers",
                params={"category": "linear", "symbol": symbol},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            rows = ((payload or {}).get("result") or {}).get("list") or []
            if not rows:
                raise ValueError("bybit_ticker_missing")
            row = rows[0]
            return {
                "exchange": "bybit",
                "symbol": symbol,
                "last_price": float(row.get("lastPrice") or 0.0),
                "bid_price": float(row.get("bid1Price") or 0.0),
                "ask_price": float(row.get("ask1Price") or 0.0),
                "spread_bps": self._spread_bps(float(row.get("bid1Price") or 0.0), float(row.get("ask1Price") or 0.0)),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

        return with_retry(_request)

    def _fetch_okx(self, symbol: str) -> dict:
        def _request():
            response = httpx.get(
                "https://www.okx.com/api/v5/market/ticker",
                params={"instId": symbol},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            rows = (payload or {}).get("data") or []
            if not rows:
                raise ValueError("okx_ticker_missing")
            row = rows[0]
            return {
                "exchange": "okx",
                "symbol": symbol,
                "last_price": float(row.get("last") or 0.0),
                "bid_price": float(row.get("bidPx") or 0.0),
                "ask_price": float(row.get("askPx") or 0.0),
                "spread_bps": self._spread_bps(float(row.get("bidPx") or 0.0), float(row.get("askPx") or 0.0)),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

        return with_retry(_request)

    def fetch_funding_rate(self, *, exchange: str, symbol: str) -> dict:
        exchange_code = str(exchange or "").lower().strip()
        symbol_code = to_exchange_symbol(exchange_code, symbol)
        if exchange_code == "bybit":
            return with_retry(lambda: self._fetch_bybit_funding(symbol_code))
        if exchange_code == "okx":
            return with_retry(lambda: self._fetch_okx_funding(symbol_code))
        raise ValueError("unsupported_exchange")

    def _fetch_bybit_funding(self, symbol: str) -> dict:
        response = httpx.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        rows = ((payload or {}).get("result") or {}).get("list") or []
        if not rows:
            raise ValueError("bybit_funding_missing")
        row = rows[0]
        return {
            "exchange": "bybit",
            "symbol": symbol,
            "funding_rate": float(row.get("fundingRate") or 0.0),
            "next_funding_time": row.get("nextFundingTime"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _fetch_okx_funding(self, symbol: str) -> dict:
        response = httpx.get(
            "https://www.okx.com/api/v5/public/funding-rate",
            params={"instId": symbol.replace("USDT", "-USDT-SWAP") if "-SWAP" not in symbol else symbol},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        rows = (payload or {}).get("data") or []
        if not rows:
            raise ValueError("okx_funding_missing")
        row = rows[0]
        return {
            "exchange": "okx",
            "symbol": symbol,
            "funding_rate": float(row.get("fundingRate") or 0.0),
            "next_funding_time": row.get("nextFundingTime"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _spread_bps(bid_price: float, ask_price: float) -> float:
        midpoint = (bid_price + ask_price) / 2.0 if (bid_price > 0 and ask_price > 0) else 0.0
        if midpoint <= 0:
            return 0.0
        return ((ask_price - bid_price) / midpoint) * 10000.0
