import hashlib
import hmac
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from db import redis_client


RATE_LIMIT_KEY = "incident:binance:live_action_counter"
LIVE_ACTION_LIMIT = 3


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _credentials() -> tuple[str, str, str, str]:
    api_key = str(os.environ.get("BINANCE_API_KEY") or "").strip()
    api_secret = str(os.environ.get("BINANCE_API_SECRET") or "").strip()
    base_url = str(os.environ.get("BINANCE_FUTURES_LIVE_BASE_URL") or "").strip().rstrip("/")
    proxy_token = str(os.environ.get("BINANCE_FUTURES_LIVE_PROXY_TOKEN") or "").strip()
    if not api_key or not api_secret:
        raise ValueError("binance_live_credentials_missing")
    if not base_url or not proxy_token:
        raise ValueError("binance_live_proxy_missing")
    return api_key, api_secret, base_url, proxy_token


def _signed_query(params: dict, api_secret: str) -> str:
    payload = dict(params or {})
    payload["timestamp"] = int(time.time() * 1000)
    payload["recvWindow"] = 10000
    query = urlencode(sorted(payload.items()), doseq=True)
    signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    return f"{query}&signature={signature}"


def _rate_limit_guard() -> None:
    current = int(redis_client.incr(RATE_LIMIT_KEY, 1))
    if hasattr(redis_client, "expire"):
        redis_client.expire(RATE_LIMIT_KEY, 300)
    if current > LIVE_ACTION_LIMIT:
        raise ValueError("binance_live_action_rate_limited")


def _request(method: str, endpoint: str, *, params: dict | None = None) -> dict | list:
    api_key, api_secret, base_url, proxy_token = _credentials()
    query = _signed_query(params or {}, api_secret)
    url = f"{base_url}{endpoint}?{query}"
    response = httpx.request(method, url, headers={"X-MBX-APIKEY": api_key, "X-Proxy-Token": proxy_token}, timeout=30.0)
    response.raise_for_status()
    payload = response.json() if response.content else {}
    return payload if isinstance(payload, (dict, list)) else {}


def preview_cancel_all_open_orders() -> dict:
    rows = _request("GET", "/fapi/v1/openOrders")
    orders = list(rows or []) if isinstance(rows, list) else []
    grouped = defaultdict(int)
    for row in orders:
        grouped[str(row.get("symbol") or "UNKNOWN").upper()] += 1
    return {
        "mode": "dry_run",
        "open_order_count": len(orders),
        "orders_by_symbol": dict(grouped),
        "preview_generated_at": datetime.now(timezone.utc).isoformat(),
    }


def execute_cancel_all_open_orders_live() -> dict:
    _rate_limit_guard()
    rows = _request("GET", "/fapi/v1/openOrders")
    orders = list(rows or []) if isinstance(rows, list) else []
    symbols = sorted({str(row.get("symbol") or "").upper() for row in orders if str(row.get("symbol") or "").strip()})
    responses = []
    for symbol in symbols:
        responses.append({"symbol": symbol, "result": _request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": symbol})})
    return {
        "mode": "live",
        "open_order_count": len(orders),
        "symbols_cancelled": symbols,
        "responses": responses,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


def preview_reduce_leverage(symbol: str, target_leverage: float) -> dict:
    return {
        "mode": "dry_run",
        "symbol": str(symbol or "").upper(),
        "target_leverage": int(_safe_float(target_leverage, 1)),
        "preview_generated_at": datetime.now(timezone.utc).isoformat(),
    }


def execute_reduce_leverage_live(symbol: str, target_leverage: float) -> dict:
    _rate_limit_guard()
    return {
        "mode": "live",
        "result": _request("POST", "/fapi/v1/leverage", params={"symbol": str(symbol or "").upper(), "leverage": int(_safe_float(target_leverage, 1))}),
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
