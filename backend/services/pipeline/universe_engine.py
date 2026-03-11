from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import AdminControl
from services.pipeline.cache_store import get_json, set_json
from services.pipeline.spot_strategy_service import get_spot_tradable_universe


def _normalize_symbols(symbols: list[str]) -> list[str]:
    return sorted({symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()})


def _within_filters(symbol: str, cache, min_volume: float, max_spread_bps: int) -> bool:
    ticker_key = f"market:ticker:{symbol}"
    spread_key = f"market:spread:{symbol}"
    ticker = get_json(cache, ticker_key) or {}
    spread = get_json(cache, spread_key) or {}
    quote_volume = float(ticker.get("quote_volume", 0))
    spread_bps = float(spread.get("spread_bps", 9999))
    return quote_volume >= min_volume and spread_bps <= max_spread_bps


def build_effective_universe(db: Session, cache):
    dynamic_universe = get_spot_tradable_universe(cache)
    dynamic_spot_symbols = _normalize_symbols(dynamic_universe.get("symbols", []))
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control is None:
        return {
            "spot_symbols": dynamic_spot_symbols,
            "futures_symbols": [],
            "filters": {
                "minimum_volume_usd": dynamic_universe.get("filters", {}).get("min_24h_volume_usdt"),
                "max_spread_pct": dynamic_universe.get("filters", {}).get("max_spread_pct"),
                "quote_asset": "USDT",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    spot_symbols = dynamic_spot_symbols or _normalize_symbols(control.spot_universe)
    futures_symbols = _normalize_symbols(control.futures_universe)
    whitelist = _normalize_symbols(control.whitelist)
    blacklist = set(_normalize_symbols(control.blacklist))

    if whitelist:
        whitelist_set = set(whitelist)
        spot_symbols = [symbol for symbol in spot_symbols if symbol in whitelist_set]
        futures_symbols = [symbol for symbol in futures_symbols if symbol in whitelist_set]

    spot_symbols = [symbol for symbol in spot_symbols if symbol not in blacklist]
    futures_symbols = [symbol for symbol in futures_symbols if symbol not in blacklist]

    spot_symbols = [
        symbol
        for symbol in spot_symbols
        if _within_filters(symbol, cache, control.minimum_volume_usd, control.max_spread_bps)
        or not get_json(cache, f"market:ticker:{symbol}")
    ]
    futures_symbols = [
        symbol
        for symbol in futures_symbols
        if _within_filters(symbol, cache, control.minimum_volume_usd, control.max_spread_bps)
        or not get_json(cache, f"market:ticker:{symbol}")
    ]

    if control.disable_futures:
        futures_symbols = []

    payload = {
        "spot_symbols": spot_symbols,
        "futures_symbols": futures_symbols,
        "filters": {
            "minimum_volume_usd": control.minimum_volume_usd,
            "max_spread_bps": control.max_spread_bps,
            "blacklist": list(blacklist),
            "whitelist": whitelist,
            "disable_futures": control.disable_futures,
            "emergency_mode": control.emergency_mode,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_json(cache, "universe:effective", payload)
    set_json(cache, "universe:effective:spot", {"symbols": spot_symbols, "generated_at": payload["generated_at"]})
    set_json(cache, "universe:effective:futures", {"symbols": futures_symbols, "generated_at": payload["generated_at"]})
    return payload