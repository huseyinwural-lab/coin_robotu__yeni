import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import httpx

from core.exchanges.base_adapter import BaseExecutionAdapter


def _is_true(value: str | None) -> bool:
    return str(value or "false").strip().lower() == "true"


class BinanceExecutionAdapter(BaseExecutionAdapter):
    adapter_name = "binance"

    def __init__(self, *, mode: str = "testnet"):
        self.mode = mode
        self.api_key = str(os.environ.get("BINANCE_TESTNET_API_KEY") or "").strip()
        self.api_secret = str(os.environ.get("BINANCE_TESTNET_API_SECRET") or "").strip()
        self.base_url = str(os.environ.get("BINANCE_SPOT_TESTNET_BASE_URL") or "https://testnet.binance.vision").strip().rstrip("/")

    def _guard(self) -> None:
        execution_mode = str(os.environ.get("EXECUTION_MODE") or "sim").strip().lower()
        live_enabled = _is_true(os.environ.get("LIVE_TRADING_ENABLED"))
        testnet_enabled = _is_true(os.environ.get("TESTNET_TRADING_ENABLED"))
        live_route_approved = _is_true(os.environ.get("LIVE_ROUTE_APPROVED"))

        if execution_mode == "live":
            if not (live_enabled and live_route_approved):
                raise RuntimeError("live_guard_blocked")
            raise RuntimeError("live_route_not_implemented")

        if execution_mode != "testnet":
            raise RuntimeError("invalid_binance_mode")
        if not testnet_enabled:
            raise RuntimeError("testnet_guard_blocked")
        if live_enabled:
            raise RuntimeError("testnet_mode_invalid_live_enabled")
        if not self.api_key or not self.api_secret:
            raise RuntimeError("missing_testnet_credentials")

    def _signed_request(self, method: str, endpoint: str, params: dict) -> dict:
        signed = dict(params)
        signed["timestamp"] = int(time.time() * 1000)
        signed["recvWindow"] = 10000
        query = urlencode(signed, doseq=True)
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{self.base_url}{endpoint}?{query}&signature={signature}"

        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            response = httpx.request(method, url, headers=headers, timeout=20.0)
        except httpx.TimeoutException as exc:
            raise RuntimeError("timeout") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("network_error") from exc

        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            message = payload.get("msg") if isinstance(payload, dict) else "exchange_error"
            raise RuntimeError(f"exchange_reject:{response.status_code}:{message}")
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _map_status_to_states(status: str) -> list[str]:
        normalized = str(status or "").upper()
        mapping = {
            "NEW": ["SENT"],
            "PARTIALLY_FILLED": ["SENT", "PARTIALLY_FILLED"],
            "FILLED": ["SENT", "FILLED"],
            "CANCELED": ["SENT", "CANCELED"],
            "REJECTED": ["SENT", "FAILED"],
            "EXPIRED": ["SENT", "FAILED"],
        }
        return mapping.get(normalized, ["SENT"])

    def submit_order(self, payload: dict) -> dict:
        self._guard()

        symbol = str(payload.get("symbol") or "").upper()
        side = str(payload.get("side") or "BUY").upper()
        quantity = float(payload.get("size") or 0.0)
        order_type = str(payload.get("order_type") or "MARKET").upper()
        if quantity <= 0:
            raise RuntimeError("invalid_size")

        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": round(quantity, 6),
            "newClientOrderId": str(payload.get("idempotency_key") or payload.get("execution_job_id") or "runtime-order")[:36],
        }

        if order_type == "LIMIT":
            price = float(payload.get("limit_price") or payload.get("mark_price") or 0.0)
            if price <= 0:
                raise RuntimeError("invalid_limit_price")
            params["price"] = round(price, 6)
            params["timeInForce"] = "GTC"

        result = self._signed_request("POST", "/api/v3/order", params)
        executed_qty = float(result.get("executedQty") or 0.0)
        cumulative_quote = float(result.get("cummulativeQuoteQty") or 0.0)
        avg_fill_price = (cumulative_quote / executed_qty) if executed_qty > 0 else float(payload.get("mark_price") or 0.0)

        return {
            "external_order_id": str(result.get("orderId") or ""),
            "states": self._map_status_to_states(result.get("status")),
            "avg_fill_price": round(avg_fill_price, 8),
            "filled_size": round(executed_qty, 8),
        }

    def get_order_status(self, *, symbol: str, order_id: str) -> dict:
        self._guard()
        result = self._signed_request(
            "GET",
            "/api/v3/order",
            {
                "symbol": str(symbol).upper(),
                "orderId": int(float(order_id)),
            },
        )
        executed_qty = float(result.get("executedQty") or 0.0)
        cumulative_quote = float(result.get("cummulativeQuoteQty") or 0.0)
        avg_fill_price = (cumulative_quote / executed_qty) if executed_qty > 0 else 0.0
        return {
            "status": str(result.get("status") or "").upper(),
            "executed_qty": round(executed_qty, 8),
            "avg_fill_price": round(avg_fill_price, 8),
        }

    def cancel_order(self, *, symbol: str, order_id: str) -> dict:
        self._guard()
        result = self._signed_request(
            "DELETE",
            "/api/v3/order",
            {
                "symbol": str(symbol).upper(),
                "orderId": int(float(order_id)),
            },
        )
        return {
            "status": str(result.get("status") or "").upper(),
            "order_id": str(result.get("orderId") or order_id),
        }

    def get_available_balance(self, *, asset: str = "USDT") -> float:
        self._guard()
        account = self._signed_request("GET", "/api/v3/account", {})
        balances = account.get("balances") if isinstance(account, dict) else []
        for row in balances or []:
            if str(row.get("asset") or "").upper() == str(asset).upper():
                return float(row.get("free") or 0.0)
        return 0.0
