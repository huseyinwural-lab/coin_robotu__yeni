import hashlib
import hmac
import os
import time
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode

import httpx

from core.exchanges.base_adapter import BaseExecutionAdapter


def _is_true(value: str | None) -> bool:
    return str(value or "false").strip().lower() == "true"


class BinanceExecutionAdapter(BaseExecutionAdapter):
    adapter_name = "binance"

    def __init__(self, *, mode: str = "live"):
        self.mode = str(mode or "live").strip().lower()
        self.api_key = str(os.environ.get("BINANCE_LIVE_API_KEY") or "").strip()
        self.api_secret = str(os.environ.get("BINANCE_LIVE_API_SECRET") or "").strip()

        if self.mode == "live":
            spot_override = os.environ.get("BINANCE_SPOT_LIVE_BASE_URL") or os.environ.get("BINANCE_SPOT_BASE_URL")
            futures_override = os.environ.get("BINANCE_FUTURES_LIVE_BASE_URL") or os.environ.get("BINANCE_FUTURES_BASE_URL")
            spot_mode_proxy_token = os.environ.get("BINANCE_SPOT_LIVE_PROXY_TOKEN") or os.environ.get("BINANCE_SPOT_PROXY_TOKEN")
            futures_mode_proxy_token = os.environ.get("BINANCE_FUTURES_LIVE_PROXY_TOKEN") or os.environ.get("BINANCE_FUTURES_PROXY_TOKEN")
            default_spot_base_url = "https://api.binance.com"
            default_futures_base_url = "https://fapi.binance.com"
        else:
            spot_override = os.environ.get("BINANCE_SPOT_LIVE_BASE_URL") or os.environ.get("BINANCE_SPOT_BASE_URL")
            futures_override = os.environ.get("BINANCE_FUTURES_LIVE_BASE_URL") or os.environ.get("BINANCE_FUTURES_BASE_URL")
            spot_mode_proxy_token = os.environ.get("BINANCE_SPOT_LIVE_PROXY_TOKEN") or os.environ.get("BINANCE_SPOT_PROXY_TOKEN")
            futures_mode_proxy_token = os.environ.get("BINANCE_FUTURES_LIVE_PROXY_TOKEN") or os.environ.get("BINANCE_FUTURES_PROXY_TOKEN")
            default_spot_base_url = "https://api.binance.com"
            default_futures_base_url = "https://fapi.binance.com"

        self.spot_base_url = str(spot_override or default_spot_base_url).strip().rstrip("/")
        self.futures_base_url = str(futures_override or default_futures_base_url).strip().rstrip("/")
        self.base_url = self.spot_base_url
        generic_proxy_token = os.environ.get("BINANCE_PROXY_TOKEN")
        self.spot_proxy_token = str(
            spot_mode_proxy_token or generic_proxy_token or self._token_from_proxy_base_url(self.spot_base_url) or ""
        ).strip()
        self.futures_proxy_token = str(
            futures_mode_proxy_token or generic_proxy_token or self._token_from_proxy_base_url(self.futures_base_url) or ""
        ).strip()
        self.proxy_token = self.spot_proxy_token

        self.execution_market_type = str(
            os.environ.get("BINANCE_EXECUTION_MARKET_TYPE")
            or os.environ.get("BINANCE_LIVE_MARKET_TYPE")
            or ("futures" if self.mode == "live" else "spot")
        ).strip().lower()
        if self.execution_market_type not in {"spot", "futures"}:
            self.execution_market_type = "futures" if self.mode == "live" else "spot"

        try:
            timeout_seconds = float(os.environ.get("BINANCE_ADAPTER_TIMEOUT_SECONDS") or 20.0)
        except ValueError:
            timeout_seconds = 20.0
        try:
            max_retries = int(os.environ.get("BINANCE_ADAPTER_MAX_RETRIES") or 3)
        except ValueError:
            max_retries = 3

        self.timeout_seconds = max(3.0, timeout_seconds)
        self.max_retries = max(1, min(max_retries, 6))
        self._symbol_rules_cache: dict[str, dict] = {}

    @staticmethod
    def _token_from_proxy_base_url(base_url: str) -> str:
        normalized = str(base_url or "")
        marker = "/p/"
        if marker not in normalized:
            return ""
        tail = normalized.split(marker, 1)[1]
        return str(tail.split("/", 1)[0]).strip()

    def _active_market(self) -> str:
        return "futures" if self.execution_market_type == "futures" else "spot"

    def _active_base_url(self) -> str:
        return self.futures_base_url if self._active_market() == "futures" else self.spot_base_url

    def _order_endpoint(self) -> str:
        return "/fapi/v1/order" if self._active_market() == "futures" else "/api/v3/order"

    def _account_endpoint(self) -> str:
        return "/fapi/v2/account" if self._active_market() == "futures" else "/api/v3/account"

    def _exchange_info_endpoint(self) -> str:
        return "/fapi/v1/exchangeInfo" if self._active_market() == "futures" else "/api/v3/exchangeInfo"

    def _proxy_token_for_base_url(self, *, base_url: str) -> str:
        normalized = str(base_url or "").rstrip("/")
        if normalized == self.futures_base_url:
            return self.futures_proxy_token
        if normalized == self.spot_base_url:
            return self.spot_proxy_token
        inferred = self._token_from_proxy_base_url(normalized)
        return inferred or self.spot_proxy_token or self.futures_proxy_token

    def _resolve_base_url_for_endpoint(self, *, endpoint: str, explicit_base_url: str | None = None) -> str:
        if explicit_base_url:
            return str(explicit_base_url).rstrip("/")
        normalized_endpoint = str(endpoint or "")
        if normalized_endpoint.startswith("/fapi/"):
            return self.futures_base_url
        if normalized_endpoint.startswith("/api/"):
            return self.spot_base_url
        return self._active_base_url()

    def _request_headers(self, *, include_api_key: bool, base_url: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if include_api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        token = self._proxy_token_for_base_url(base_url=base_url or self._active_base_url())
        if token:
            headers["X-Proxy-Token"] = token
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

    def _symbol_rules(self, *, symbol: str) -> dict:
        normalized_symbol = str(symbol or "").upper()
        if normalized_symbol in self._symbol_rules_cache:
            return self._symbol_rules_cache[normalized_symbol]

        payload = self._public_request(
            "GET",
            self._exchange_info_endpoint(),
            params={"symbol": normalized_symbol},
            base_url=self._active_base_url(),
        )

        symbols = payload.get("symbols") if isinstance(payload, dict) else []
        for row in symbols or []:
            if str(row.get("symbol") or "").upper() != normalized_symbol:
                continue
            lot_size_filter = next(
                (item for item in (row.get("filters") or []) if str(item.get("filterType") or "") == "LOT_SIZE"),
                {},
            )
            price_filter = next(
                (item for item in (row.get("filters") or []) if str(item.get("filterType") or "") == "PRICE_FILTER"),
                {},
            )
            step_size = str(lot_size_filter.get("stepSize") or "0.000001")
            min_qty = str(lot_size_filter.get("minQty") or "0")
            tick_size = str(price_filter.get("tickSize") or "0.01")
            min_price = str(price_filter.get("minPrice") or "0")
            max_price = str(price_filter.get("maxPrice") or "0")
            rules = {
                "step_size": step_size,
                "min_qty": min_qty,
                "tick_size": tick_size,
                "min_price": min_price,
                "max_price": max_price,
            }
            self._symbol_rules_cache[normalized_symbol] = rules
            return rules

        fallback = {
            "step_size": "0.000001",
            "min_qty": "0.000001",
            "tick_size": "0.01",
            "min_price": "0",
            "max_price": "0",
        }
        self._symbol_rules_cache[normalized_symbol] = fallback
        return fallback

    def _normalize_quantity(self, *, symbol: str, quantity: float) -> float:
        rules = self._symbol_rules(symbol=symbol)
        try:
            raw_qty = Decimal(str(quantity))
            step = Decimal(str(rules.get("step_size") or "0.000001"))
            min_qty = Decimal(str(rules.get("min_qty") or "0"))
            if raw_qty < min_qty:
                raw_qty = min_qty
            if step > 0:
                steps = (raw_qty / step).to_integral_value(rounding=ROUND_DOWN)
                normalized = steps * step
            else:
                normalized = raw_qty
            if normalized < min_qty:
                normalized = min_qty
            return float(normalized)
        except Exception:  # noqa: BLE001
            return max(float(quantity), 0.0)

    def _normalize_price(self, *, symbol: str, price: float) -> float:
        rules = self._symbol_rules(symbol=symbol)
        try:
            raw_price = Decimal(str(price))
            tick = Decimal(str(rules.get("tick_size") or "0.01"))
            min_price = Decimal(str(rules.get("min_price") or "0"))
            max_price = Decimal(str(rules.get("max_price") or "0"))
            if raw_price < min_price:
                raw_price = min_price
            if max_price > 0 and raw_price > max_price:
                raw_price = max_price
            if tick > 0:
                steps = (raw_price / tick).to_integral_value(rounding=ROUND_DOWN)
                normalized = steps * tick
            else:
                normalized = raw_price
            if normalized < min_price:
                normalized = min_price
            return float(normalized)
        except Exception:  # noqa: BLE001
            return max(float(price), 0.0)

    def _public_request(self, method: str, endpoint: str, params: dict | None = None, *, base_url: str | None = None) -> dict | list:
        resolved_base_url = self._resolve_base_url_for_endpoint(endpoint=endpoint, explicit_base_url=base_url)
        query = urlencode(params or {}, doseq=True)
        url = f"{resolved_base_url}{endpoint}"
        if query:
            url = f"{url}?{query}"

        for attempt in range(self.max_retries):
            try:
                response = httpx.request(
                    method,
                    url,
                    headers=self._request_headers(include_api_key=False, base_url=resolved_base_url),
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                if attempt >= self.max_retries - 1:
                    raise RuntimeError("timeout") from exc
                time.sleep(0.4 * (attempt + 1))
                continue
            except httpx.RequestError as exc:
                if attempt >= self.max_retries - 1:
                    raise RuntimeError("network_error") from exc
                time.sleep(0.4 * (attempt + 1))
                continue

            payload = self._response_payload(response)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries - 1:
                time.sleep(0.4 * (attempt + 1))
                continue
            if response.status_code >= 400:
                message = payload.get("msg") if isinstance(payload, dict) else "exchange_error"
                raise RuntimeError(f"exchange_reject:{response.status_code}:{message}")
            return payload

        raise RuntimeError("exchange_reject:unknown:request_failed")

    def _guard(self) -> None:
        execution_mode = str(os.environ.get("EXECUTION_MODE") or "sim").strip().lower()
        live_enabled = _is_true(os.environ.get("LIVE_TRADING_ENABLED"))
        live_enabled = _is_true(os.environ.get("LIVE_TRADING_ENABLED"))
        live_route_approved = _is_true(os.environ.get("LIVE_ROUTE_APPROVED"))

        if execution_mode == "live":
            if not (live_enabled and live_route_approved):
                raise RuntimeError("live_guard_blocked")
            raise RuntimeError("live_route_not_implemented")

        if execution_mode != "live":
            raise RuntimeError("invalid_binance_mode")
        if not live_enabled:
            raise RuntimeError("live_guard_blocked")
        if live_enabled:
            raise RuntimeError("live_mode_invalid_live_enabled")
        if not self.api_key or not self.api_secret:
            raise RuntimeError("missing_live_credentials")

    def _signed_request(self, method: str, endpoint: str, params: dict, *, base_url: str | None = None) -> dict:
        resolved_base_url = self._resolve_base_url_for_endpoint(endpoint=endpoint, explicit_base_url=base_url)
        for attempt in range(self.max_retries):
            signed = dict(params)
            signed["timestamp"] = int(time.time() * 1000)
            signed["recvWindow"] = 10000
            query = urlencode(signed, doseq=True)
            signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            url = f"{resolved_base_url}{endpoint}?{query}&signature={signature}"

            try:
                response = httpx.request(
                    method,
                    url,
                    headers=self._request_headers(include_api_key=True, base_url=resolved_base_url),
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                if attempt >= self.max_retries - 1:
                    raise RuntimeError("timeout") from exc
                time.sleep(0.4 * (attempt + 1))
                continue
            except httpx.RequestError as exc:
                if attempt >= self.max_retries - 1:
                    raise RuntimeError("network_error") from exc
                time.sleep(0.4 * (attempt + 1))
                continue

            payload = self._response_payload(response)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries - 1:
                time.sleep(0.4 * (attempt + 1))
                continue
            if response.status_code >= 400:
                message = payload.get("msg") if isinstance(payload, dict) else "exchange_error"
                raise RuntimeError(f"exchange_reject:{response.status_code}:{message}")
            return payload if isinstance(payload, dict) else {}

        raise RuntimeError("exchange_reject:unknown:request_failed")

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
            "quantity": self._normalize_quantity(symbol=symbol, quantity=quantity),
            "newClientOrderId": str(payload.get("idempotency_key") or payload.get("execution_job_id") or "runtime-order")[:36],
        }
        params["quantity"] = format(Decimal(str(params["quantity"])).normalize(), "f")

        if self._active_market() == "futures":
            requested_leverage = int(_safe_float(payload.get("leverage"), 0))
            if requested_leverage > 0:
                try:
                    self._signed_request(
                        "POST",
                        "/fapi/v1/leverage",
                        {"symbol": symbol, "leverage": max(1, min(requested_leverage, 125))},
                        base_url=self._active_base_url(),
                    )
                except RuntimeError:
                    pass

        if self._active_market() == "futures":
            mark_price = _safe_float(payload.get("mark_price"), 0.0)
            if mark_price > 0:
                rules = self._symbol_rules(symbol=symbol)
                step_size = max(_safe_float(rules.get("step_size"), 0.0), 0.0)
                if step_size > 0:
                    qty_decimal = Decimal(str(params.get("quantity") or 0.0))
                    step_decimal = Decimal(str(step_size))
                    min_notional_decimal = Decimal("100")
                    mark_price_decimal = Decimal(str(mark_price))
                    while qty_decimal * mark_price_decimal < min_notional_decimal:
                        qty_decimal += step_decimal
                    params["quantity"] = format(qty_decimal.normalize(), "f")

        if order_type == "LIMIT":
            price = float(payload.get("limit_price") or payload.get("mark_price") or 0.0)
            if price <= 0:
                raise RuntimeError("invalid_limit_price")
            params["price"] = self._normalize_price(symbol=symbol, price=price)
            params["timeInForce"] = "GTC"

        result = self._signed_request("POST", self._order_endpoint(), params, base_url=self._active_base_url())
        executed_qty = float(result.get("executedQty") or 0.0)
        cumulative_quote = float(result.get("cummulativeQuoteQty") or result.get("cumQuote") or 0.0)
        avg_fill_price = (cumulative_quote / executed_qty) if executed_qty > 0 else float(payload.get("mark_price") or 0.0)
        exchange_status = str(result.get("status") or "").upper()

        if self._active_market() == "futures" and not exchange_status:
            exchange_status = "FILLED" if executed_qty > 0 else "SENT"

        return {
            "external_order_id": str(result.get("orderId") or ""),
            "states": self._map_status_to_states(exchange_status),
            "avg_fill_price": round(avg_fill_price, 8),
            "filled_size": round(executed_qty, 8),
        }

    def get_order_status(self, *, symbol: str, order_id: str) -> dict:
        self._guard()
        result = self._signed_request(
            "GET",
            self._order_endpoint(),
            {
                "symbol": str(symbol).upper(),
                "orderId": int(float(order_id)),
            },
            base_url=self._active_base_url(),
        )
        executed_qty = float(result.get("executedQty") or 0.0)
        cumulative_quote = float(result.get("cummulativeQuoteQty") or result.get("cumQuote") or 0.0)
        avg_fill_price = _safe_float(result.get("avgPrice"), 0.0) if self._active_market() == "futures" else 0.0
        if avg_fill_price <= 0 and executed_qty > 0:
            avg_fill_price = cumulative_quote / executed_qty
        return {
            "status": str(result.get("status") or "").upper(),
            "executed_qty": round(executed_qty, 8),
            "avg_fill_price": round(avg_fill_price, 8),
        }

    def cancel_order(self, *, symbol: str, order_id: str) -> dict:
        self._guard()
        result = self._signed_request(
            "DELETE",
            self._order_endpoint(),
            {
                "symbol": str(symbol).upper(),
                "orderId": int(float(order_id)),
            },
            base_url=self._active_base_url(),
        )
        return {
            "status": str(result.get("status") or "").upper(),
            "order_id": str(result.get("orderId") or order_id),
        }

    def get_available_balance(self, *, asset: str = "USDT") -> float:
        self._guard()
        account = self._signed_request("GET", self._account_endpoint(), {}, base_url=self._active_base_url())
        if self._active_market() == "futures":
            assets = account.get("assets") if isinstance(account, dict) else []
            for row in assets or []:
                if str(row.get("asset") or "").upper() == str(asset).upper():
                    return float(row.get("availableBalance") or row.get("walletBalance") or 0.0)
            return float(account.get("availableBalance") or 0.0)

        balances = account.get("balances") if isinstance(account, dict) else []
        for row in balances or []:
            if str(row.get("asset") or "").upper() == str(asset).upper():
                return float(row.get("free") or 0.0)
        return 0.0


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
