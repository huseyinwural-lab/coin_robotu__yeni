from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import AdminControl
from services.indicator_screener.market_data_provider import BinanceMarketDataProvider, MarketDataProviderError
from services.pipeline.cache_store import get_json, set_json
from services.pipeline.spot_strategy_service import get_spot_tradable_universe
from services.quote_asset_policy import ALLOWED_QUOTE_ASSETS, filter_allowed_quote_symbols


def _normalize_symbols(symbols: list[str]) -> list[str]:
    return filter_allowed_quote_symbols([str(symbol or "").strip().upper() for symbol in symbols])


def _within_filters(symbol: str, cache, min_volume: float, max_spread_bps: int) -> bool:
    ticker_key = f"market:ticker:{symbol}"
    spread_key = f"market:spread:{symbol}"
    ticker = get_json(cache, ticker_key) or {}
    spread = get_json(cache, spread_key) or {}
    quote_volume = float(ticker.get("quote_volume", 0))
    spread_bps = float(spread.get("spread_bps", 9999))
    return quote_volume >= min_volume and spread_bps <= max_spread_bps


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _market_rows(market_type: str) -> list[dict]:
    provider = BinanceMarketDataProvider()
    try:
        payload = provider.get_tradable_symbols(exchange="binance", market_type=market_type)
    except MarketDataProviderError:
        return []
    rows: list[dict] = []
    for row in payload.get("rows", []):
        if not bool(row.get("is_tradable", False)):
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        quote_asset = str(row.get("quote_asset") or "").upper()
        if quote_asset not in ALLOWED_QUOTE_ASSETS:
            continue
        rows.append(
            {
                "symbol": symbol,
                "quote_asset": quote_asset,
                "volume_24h": _safe_float(row.get("volume_24h"), 0.0),
            }
        )
    return rows


def _cache_volume(symbol: str, cache) -> float:
    ticker = get_json(cache, f"market:ticker:{symbol}") or {}
    return _safe_float(ticker.get("quote_volume"), 0.0)


def _cache_spread_bps(symbol: str, cache) -> float:
    spread = get_json(cache, f"market:spread:{symbol}") or {}
    spread_bps = _safe_float(spread.get("spread_bps"), 0.0)
    if spread_bps > 0:
        return spread_bps
    ticker = get_json(cache, f"market:ticker:{symbol}") or {}
    bid = _safe_float(ticker.get("bid"), 0.0)
    ask = _safe_float(ticker.get("ask"), 0.0)
    if ask > 0 and bid > 0:
        mid = (ask + bid) / 2
        if mid > 0:
            return abs(ask - bid) / mid * 10000
    return 0.0


def _liquidity_advisory(symbol: str, *, cache, minimum_volume_usd: float, max_spread_bps: int) -> dict:
    quote_volume = _cache_volume(symbol, cache)
    spread_bps = _cache_spread_bps(symbol, cache)
    has_ticker = bool(get_json(cache, f"market:ticker:{symbol}"))
    volume_gap_ratio = 0.0
    if minimum_volume_usd > 0:
        volume_gap_ratio = max(0.0, (minimum_volume_usd - quote_volume) / minimum_volume_usd)
    volume_low = minimum_volume_usd > 0 and quote_volume < minimum_volume_usd
    spread_high = max_spread_bps > 0 and spread_bps > max_spread_bps

    confidence_penalty = 0.0
    risk_score_bonus = 0.0
    if volume_low or spread_high:
        confidence_penalty = min(0.35, (spread_bps / 1000.0 if spread_high else 0.0) + (volume_gap_ratio * 0.25))
        risk_score_bonus = min(0.30, (spread_bps / 1200.0 if spread_high else 0.0) + (volume_gap_ratio * 0.20))

    advisory_state = "clear"
    if not has_ticker:
        advisory_state = "data_unavailable"
    elif volume_low or spread_high:
        advisory_state = "advisory"

    return {
        "symbol": symbol,
        "data_available": bool(has_ticker),
        "quote_volume": round(quote_volume, 6),
        "spread_bps": round(spread_bps, 6),
        "volume_low": bool(volume_low),
        "spread_high": bool(spread_high),
        "volume_gap_ratio": round(volume_gap_ratio, 6),
        "confidence_penalty": round(confidence_penalty, 6),
        "risk_score_bonus": round(risk_score_bonus, 6),
        "advisory_state": advisory_state,
    }


def _volume_map(symbols: list[str], cache, market_rows: list[dict]) -> dict[str, float]:
    market_lookup = {str(item.get("symbol") or "").upper(): _safe_float(item.get("volume_24h"), 0.0) for item in market_rows}
    payload: dict[str, float] = {}
    for symbol in symbols:
        cache_volume = _cache_volume(symbol, cache)
        payload[symbol] = cache_volume if cache_volume > 0 else market_lookup.get(symbol, 0.0)
    return payload


SCANNER_MODE_ALIASES = {
    "all_market_symbols": "ALL_MARKET_SYMBOLS",
    "all_exchange": "ALL_MARKET_SYMBOLS",
    "top_volume": "TOP_VOLUME",
    "top_active_50": "TOP_VOLUME",
    "top_active_100": "TOP_VOLUME",
    "manual_selection": "MANUAL_SELECTION",
    "custom_list": "MANUAL_SELECTION",
    "bot_scope": "MANUAL_SELECTION",
}


def normalize_scanner_mode(mode: str | None) -> str:
    candidate = str(mode or "ALL_MARKET_SYMBOLS").strip().lower()
    return SCANNER_MODE_ALIASES.get(candidate, "ALL_MARKET_SYMBOLS")


def apply_scanner_mode(
    symbols: list[str],
    *,
    mode: str,
    selected_symbols: list[str] | None,
    top_n: int,
    volume_map: dict[str, float] | None,
) -> list[str]:
    normalized_symbols = _normalize_symbols(symbols)
    normalized_selected = _normalize_symbols(selected_symbols or [])
    normalized_mode = normalize_scanner_mode(mode)

    if normalized_mode == "MANUAL_SELECTION":
        if not normalized_selected:
            return []
        selected_set = set(normalized_selected)
        return [symbol for symbol in normalized_symbols if symbol in selected_set]

    if normalized_mode == "TOP_VOLUME":
        volume_lookup = volume_map or {}
        ranked = sorted(normalized_symbols, key=lambda item: (float(volume_lookup.get(item, 0.0)), item), reverse=True)
        return ranked[: max(1, min(int(top_n or 100), 1000))]

    return normalized_symbols


def build_effective_universe(db: Session, cache):
    dynamic_universe = get_spot_tradable_universe(cache)
    dynamic_spot_symbols = _normalize_symbols(dynamic_universe.get("symbols", []))
    market_spot_rows = _market_rows("spot")
    market_futures_rows = _market_rows("futures")
    market_spot_symbols = _normalize_symbols([row["symbol"] for row in market_spot_rows if row.get("quote_asset") in ALLOWED_QUOTE_ASSETS])
    market_futures_symbols = _normalize_symbols([row["symbol"] for row in market_futures_rows if row.get("quote_asset") in ALLOWED_QUOTE_ASSETS])
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control is None:
        advisory_map = {symbol: _liquidity_advisory(symbol, cache=cache, minimum_volume_usd=0, max_spread_bps=0) for symbol in dynamic_spot_symbols}
        return {
            "spot_symbols": dynamic_spot_symbols,
            "futures_symbols": market_futures_symbols,
            "filters": {
                "minimum_volume_usd": dynamic_universe.get("filters", {}).get("min_24h_volume_usdt"),
                "max_spread_pct": dynamic_universe.get("filters", {}).get("max_spread_pct"),
                "quote_assets": sorted(ALLOWED_QUOTE_ASSETS),
                "advisory_only": True,
            },
            "liquidity_advisory": {"spot": advisory_map, "futures": {}},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    configured_spot_override = _normalize_symbols(control.spot_universe)
    configured_futures_override = _normalize_symbols(control.futures_universe)
    spot_symbols = configured_spot_override or market_spot_symbols or dynamic_spot_symbols
    futures_symbols = configured_futures_override or market_futures_symbols
    whitelist = _normalize_symbols(control.whitelist)
    blacklist = set(_normalize_symbols(control.blacklist))

    if whitelist:
        whitelist_set = set(whitelist)
        spot_symbols = [symbol for symbol in spot_symbols if symbol in whitelist_set]
        futures_symbols = [symbol for symbol in futures_symbols if symbol in whitelist_set]

    spot_symbols = [symbol for symbol in spot_symbols if symbol not in blacklist]
    futures_symbols = [symbol for symbol in futures_symbols if symbol not in blacklist]

    spot_advisory = {
        symbol: _liquidity_advisory(
            symbol,
            cache=cache,
            minimum_volume_usd=float(control.minimum_volume_usd or 0),
            max_spread_bps=int(control.max_spread_bps or 0),
        )
        for symbol in spot_symbols
    }
    futures_advisory = {
        symbol: _liquidity_advisory(
            symbol,
            cache=cache,
            minimum_volume_usd=float(control.minimum_volume_usd or 0),
            max_spread_bps=int(control.max_spread_bps or 0),
        )
        for symbol in futures_symbols
    }

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
            "allow_all": len(whitelist) == 0,
            "spot_override_active": len(configured_spot_override) > 0,
            "futures_override_active": len(configured_futures_override) > 0,
            "liquidity_filter_mode": "advisory_only",
            "disable_futures": control.disable_futures,
            "emergency_mode": control.emergency_mode,
        },
        "liquidity_advisory": {
            "spot": spot_advisory,
            "futures": futures_advisory,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_json(cache, "universe:effective", payload)
    set_json(cache, "universe:effective:spot", {"symbols": spot_symbols, "generated_at": payload["generated_at"]})
    set_json(cache, "universe:effective:futures", {"symbols": futures_symbols, "generated_at": payload["generated_at"]})
    return payload


def debug_effective_universe(
    db: Session,
    cache,
    *,
    market_type: str = "spot",
    scanner_mode: str = "ALL_MARKET_SYMBOLS",
    selected_symbols: list[str] | None = None,
    top_n: int = 100,
) -> dict:
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    normalized_market = str(market_type or "spot").strip().lower()
    if normalized_market not in {"spot", "futures"}:
        normalized_market = "spot"

    market_rows = _market_rows(normalized_market)
    market_symbols = _normalize_symbols([row.get("symbol") for row in market_rows if row.get("quote_asset") in ALLOWED_QUOTE_ASSETS])
    blacklist = set(_normalize_symbols((control.blacklist if control else []) or []))
    whitelist = _normalize_symbols((control.whitelist if control else []) or [])

    after_blacklist_symbols = [symbol for symbol in market_symbols if symbol not in blacklist]
    permission_symbols = after_blacklist_symbols
    if whitelist:
        allowed = set(whitelist)
        permission_symbols = [symbol for symbol in after_blacklist_symbols if symbol in allowed]

    volume_map = _volume_map(permission_symbols, cache, market_rows)
    after_scanner_mode_symbols = apply_scanner_mode(
        permission_symbols,
        mode=scanner_mode,
        selected_symbols=selected_symbols,
        top_n=top_n,
        volume_map=volume_map,
    )

    liquidity_advisory = {
        symbol: _liquidity_advisory(
            symbol,
            cache=cache,
            minimum_volume_usd=float(control.minimum_volume_usd if control else 0),
            max_spread_bps=int(control.max_spread_bps if control else 0),
        )
        for symbol in after_scanner_mode_symbols
    }

    return {
        "market_type": normalized_market,
        "scanner_mode": normalize_scanner_mode(scanner_mode),
        "market_symbols_count": len(market_symbols),
        "after_blacklist": len(after_blacklist_symbols),
        "after_scanner_mode": len(after_scanner_mode_symbols),
        "after_liquidity": len(after_scanner_mode_symbols),
        "after_liquidity_filter": len(after_scanner_mode_symbols),
        "final_symbols": after_scanner_mode_symbols,
        "after_permission_rules": len(permission_symbols),
        "liquidity_advisory_summary": {
            "advisory_count": sum(1 for item in liquidity_advisory.values() if item.get("advisory_state") == "advisory"),
            "data_unavailable_count": sum(1 for item in liquidity_advisory.values() if item.get("advisory_state") == "data_unavailable"),
        },
        "filters": {
            "whitelist": whitelist,
            "blacklist": sorted(blacklist),
            "allow_all": len(whitelist) == 0,
            "minimum_volume_usd": float(control.minimum_volume_usd if control else 0),
            "max_spread_bps": int(control.max_spread_bps if control else 0),
            "liquidity_filter_mode": "advisory_only",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }