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
        self.mode = str(mode or "testnet").strip().lower()
        self.api_key = str(os.environ.get("BINANCE_TESTNET_API_KEY") or "").strip()
        self.api_secret = str(os.environ.get("BINANCE_TESTNET_API_SECRET") or "").strip()
        if self.mode == "testnet":
            base_override = os.environ.get("BINANCE_SPOT_TESTNET_BASE_URL") or os.environ.get("BINANCE_SPOT_BASE_URL")
            mode_proxy_token = os.environ.get("BINANCE_SPOT_TESTNET_PROXY_TOKEN") or os.environ.get("BINANCE_SPOT_PROXY_TOKEN")
            default_base_url = "https://testnet.binance.vision"
        else:
            base_override = os.environ.get("BINANCE_SPOT_LIVE_BASE_URL") or os.environ.get("BINANCE_SPOT_BASE_URL")
            mode_proxy_token = os.environ.get("BINANCE_SPOT_LIVE_PROXY_TOKEN") or os.environ.get("BINANCE_SPOT_PROXY_TOKEN")
            default_base_url = "https://api.binance.com"

        self.base_url = str(base_override or default_base_url).strip().rstrip("/")
        generic_proxy_token = os.environ.get("BINANCE_PROXY_TOKEN")
        self.proxy_token = str(mode_proxy_token or generic_proxy_token or self._token_from_proxy_base_url(self.base_url) or "").strip()

    @staticmethod
    def _token_from_proxy_base_url(base_url: str) -> str:
        normalized = str(base_url or "")
        marker = "/p/"
        if marker not in normalized:
            return ""
        tail = normalized.split(marker, 1)[1]
        return str(tail.split("/", 1)[0]).strip()

    def _request_headers(self, *, include_api_key: bool) -> dict[str, str]:
        headers: dict[str, str] = {}
        if include_api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        if self.proxy_token:
            headers["X-Proxy-Token"] = self.proxy_token
        return headers

    @staticmethod
    def _response_payload(response: httpx.Response) -> dict | list:
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {"msg": response.text or "exchange_error"}
        return payload if isinstance(payload, (dict, list)) else {}

    def _public_request(self, method: str, endpoint: str, params: dict | None = None) -> dict | list:
        query = urlencode(params or {}, doseq=True)
        url = f"{self.base_url}{endpoint}"
        if query:
            url = f"{url}?{query}"

        try:
            response = httpx.request(method, url, headers=self._request_headers(include_api_key=False), timeout=20.0)
        except httpx.TimeoutException as exc:
            raise RuntimeError("timeout") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("network_error") from exc

        payload = self._response_payload(response)
        if response.status_code >= 400:
            message = payload.get("msg") if isinstance(payload, dict) else "exchange_error"
            raise RuntimeError(f"exchange_reject:{response.status_code}:{message}")
        return payload

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

        try:
            response = httpx.request(method, url, headers=self._request_headers(include_api_key=True), timeout=20.0)
        except httpx.TimeoutException as exc:
            raise RuntimeError("timeout") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("network_error") from exc

        payload = self._response_payload(response)
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
