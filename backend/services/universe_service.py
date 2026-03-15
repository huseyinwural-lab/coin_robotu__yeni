from datetime import datetime, timezone
import re

from sqlalchemy.orm import Session

from services.indicator_screener.market_data_provider import BinanceMarketDataProvider, MarketDataProviderError
from services.pipeline.cache_store import get_json
from services.pipeline.universe_engine import apply_scanner_mode, debug_effective_universe


SUPPORTED_EXCHANGES = ["binance", "bybit", "okx"]
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{2,20}USDT$")


def _normalize_symbols(symbols: list[str]) -> list[str]:
    return sorted(
        {
            str(symbol or "").strip().upper()
            for symbol in symbols
            if SYMBOL_PATTERN.match(str(symbol or "").strip().upper())
        }
    )


def _exchange_symbols(exchange: str, market_type: str) -> list[str]:
    normalized_exchange = str(exchange or "binance").strip().lower()
    normalized_market = str(market_type or "spot").strip().lower()
    if normalized_exchange != "binance":
        return []

    provider = BinanceMarketDataProvider()
    try:
        payload = provider.get_tradable_symbols(exchange=normalized_exchange, market_type=normalized_market)
    except MarketDataProviderError:
        return []

    rows = payload.get("rows") or []
    symbols = [
        str(row.get("symbol") or "").upper()
        for row in rows
        if bool(row.get("is_tradable", False)) and str(row.get("quote_asset") or "").upper() == "USDT"
    ]
    return _normalize_symbols(symbols)


def get_full_market_universe(
    db: Session,
    cache,
    *,
    scanner_mode: str = "all_market_symbols",
    selected_symbols: list[str] | None = None,
    top_n: int = 50,
) -> dict:
    runtime_state = get_json(cache, "scanner:runtime:latest:global") or {}
    runtime_metrics = runtime_state.get("runtime_metrics") or {}
    spot_debug = debug_effective_universe(
        db,
        cache,
        market_type="spot",
        scanner_mode=scanner_mode,
        selected_symbols=selected_symbols or [],
        top_n=top_n,
    )
    futures_debug = debug_effective_universe(
        db,
        cache,
        market_type="futures",
        scanner_mode=scanner_mode,
        selected_symbols=selected_symbols or [],
        top_n=top_n,
    )

    combined_symbols = _normalize_symbols(list(spot_debug.get("final_symbols") or []) + list(futures_debug.get("final_symbols") or []))
    return {
        "scanner_mode": str(scanner_mode or "all_market_symbols").lower(),
        "spot_symbols": list(spot_debug.get("final_symbols") or []),
        "futures_symbols": list(futures_debug.get("final_symbols") or []),
        "combined_symbols": combined_symbols,
        "spot_universe_size": int(spot_debug.get("after_scanner_mode") or 0),
        "futures_universe_size": int(futures_debug.get("after_scanner_mode") or 0),
        "combined_universe_size": len(combined_symbols),
        "snapshot_age_ms": float(runtime_metrics.get("snapshot_age_ms") or 0.0),
        "stale_skip_count": int(runtime_metrics.get("stale_skip_count") or 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_exchange_universe_snapshot(scanner_mode: str = "all_market_symbols", top_n: int = 50) -> dict:
    exchange_payload = {}
    warnings: list[str] = []

    for exchange in SUPPORTED_EXCHANGES:
        spot_symbols = _exchange_symbols(exchange, "spot")
        futures_symbols = _exchange_symbols(exchange, "futures")
        if exchange != "binance":
            warnings.append(f"{exchange}_adapter_not_available")

        effective_spot = apply_scanner_mode(
            spot_symbols,
            mode=scanner_mode,
            selected_symbols=[],
            top_n=top_n,
            volume_map={symbol: 0.0 for symbol in spot_symbols},
        )
        effective_futures = apply_scanner_mode(
            futures_symbols,
            mode=scanner_mode,
            selected_symbols=[],
            top_n=top_n,
            volume_map={symbol: 0.0 for symbol in futures_symbols},
        )

        exchange_payload[exchange] = {
            "spot_symbols": effective_spot,
            "futures_symbols": effective_futures,
            "spot_count": len(effective_spot),
            "futures_count": len(effective_futures),
        }

    return {
        "scanner_mode": str(scanner_mode or "all_market_symbols").lower(),
        "exchanges": exchange_payload,
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def resolve_symbol_market_type(db: Session, cache, symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return "spot"
    universe = get_full_market_universe(db, cache, scanner_mode="all_market_symbols", selected_symbols=[], top_n=50)
    futures = {str(item).upper() for item in universe.get("futures_symbols") or []}
    if normalized in futures:
        return "futures"
    return "spot"
