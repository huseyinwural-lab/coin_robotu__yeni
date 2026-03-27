from __future__ import annotations

from datetime import datetime, timezone

import requests


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _binance_base(market_type: str, environment: str) -> str:
    market = str(market_type or "spot").lower()
    env = str(environment or "testnet").lower()
    if market == "futures":
        return "https://testnet.binancefuture.com" if env == "testnet" else "https://fapi.binance.com"
    return "https://testnet.binance.vision" if env == "testnet" else "https://api.binance.com"


def _build_symbol_capability(symbol: str, market_type: str, base_support: dict) -> dict:
    market = str(market_type or "spot").lower()
    leverage = market == "futures"
    reduce_only = market == "futures"
    hedge_mode = market == "futures"
    margin_mode = market == "futures"
    support_level = "full" if base_support.get("supports_test_order", False) else "partial"
    if market != "futures":
        support_level = "partial"
    return {
        "symbol": symbol,
        "supports_leverage": leverage,
        "supports_reduce_only": reduce_only,
        "supports_hedge_mode": hedge_mode,
        "supports_margin_mode": margin_mode,
        "support_level": support_level,
    }


def discover_exchange_capabilities(
    *,
    exchange_code: str,
    market_type: str,
    environment: str,
    symbols: list[str] | None = None,
) -> dict:
    exchange = str(exchange_code or "").lower()
    market = str(market_type or "spot").lower()
    env = str(environment or "testnet").lower()

    base_support = {
        "supports_spot": market == "spot",
        "supports_futures": market == "futures",
        "supports_test_order": True,
        "supports_quote_qty": True,
        "supports_reduce_only": market == "futures",
        "supports_leverage": market == "futures",
        "supports_margin_mode": market == "futures",
        "supports_hedge_mode": market == "futures",
    }

    discovered_symbols: list[str] = []
    reason_codes: list[str] = []

    if exchange == "binance":
        try:
            base_url = _binance_base(market, env)
            endpoint = "/fapi/v1/exchangeInfo" if market == "futures" else "/api/v3/exchangeInfo"
            response = requests.get(f"{base_url}{endpoint}", timeout=8)
            response.raise_for_status()
            body = response.json() if response.content else {}
            discovered_symbols = [item.get("symbol") for item in (body.get("symbols") or []) if item.get("symbol")]
        except Exception:  # noqa: BLE001
            reason_codes.append("capability_discovery_partial")

    if not discovered_symbols:
        discovered_symbols = list(symbols or [])
    if symbols:
        discovered_symbols = [symbol for symbol in discovered_symbols if symbol in set(symbols)] or list(symbols)

    if not discovered_symbols:
        discovered_symbols = ["BTCUSDT", "ETHUSDT"]
        reason_codes.append("symbol_fallback_used")

    symbol_capabilities = [_build_symbol_capability(symbol, market, base_support) for symbol in discovered_symbols[:200]]

    if exchange not in {"binance"}:
        reason_codes.append("adapter_capability_partial_support")
        for item in symbol_capabilities:
            item["support_level"] = "partial"

    return {
        "exchange_code": exchange,
        "market_type": market,
        "environment": env,
        "discovered_at": _now_iso(),
        "base_capabilities": base_support,
        "symbol_capabilities": symbol_capabilities,
        "reason_codes": sorted(set(reason_codes)),
    }
