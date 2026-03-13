from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from services.indicator_screener.indicator_calculation_service import IndicatorCalculationError, calculate_indicator_values
from services.indicator_screener.market_data_provider import BinanceMarketDataProvider, MarketDataProviderError
from services.indicator_screener.query_parser import QueryParseError, evaluate_query_ast, parse_query_expression


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_RESULT_LIMIT = 50
MAX_RESULT_LIMIT = 300
MAX_WORKERS = 12


def _normalize_symbol_universe(symbol_universe, all_symbols: list[str]) -> tuple[list[str], str]:
    if symbol_universe is None:
        return sorted(all_symbols), "all"

    if isinstance(symbol_universe, str):
        candidate = symbol_universe.strip().lower()
        if candidate in {"", "all"}:
            return sorted(all_symbols), "all"
        requested = [part.strip().upper() for part in symbol_universe.split(",") if part.strip()]
    elif isinstance(symbol_universe, list):
        requested = [str(part).strip().upper() for part in symbol_universe if str(part).strip()]
    else:
        raise QueryParseError("symbol_universe yalnızca 'all' veya sembol listesi olabilir")

    if not requested:
        raise QueryParseError("symbol_universe listesi boş olamaz")

    allowed = set(all_symbols)
    selected = sorted({symbol for symbol in requested if symbol in allowed})
    if not selected:
        raise QueryParseError("Whitelist içindeki semboller Binance tradable listesinde bulunamadı")
    return selected, "whitelist"


def _build_result_row(
    *,
    index: int,
    exchange: str,
    market_type: str,
    timeframe: str,
    symbol: str,
    indicator_values: dict,
    matched_rules: list[str],
    matched_fields: list[str],
    market_payload: dict,
) -> dict:
    return {
        "index": index,
        "exchange": exchange,
        "market_type": market_type,
        "symbol": symbol,
        "timeframe": timeframe,
        "open": round(float(indicator_values["open"]), 8),
        "high": round(float(indicator_values["high"]), 8),
        "low": round(float(indicator_values["low"]), 8),
        "close": round(float(indicator_values["close"]), 8),
        "volume": round(float(indicator_values["volume"]), 8),
        "rsi14": round(float(indicator_values["rsi14"]), 6),
        "rsi7": round(float(indicator_values["rsi7"]), 6),
        "ema20": round(float(indicator_values["ema20"]), 8),
        "ema50": round(float(indicator_values["ema50"]), 8),
        "sma20": round(float(indicator_values["sma20"]), 8),
        "sma50": round(float(indicator_values["sma50"]), 8),
        "fibo_161_8": round(float(indicator_values["fibo_161_8"]), 8),
        "fibo_127_2": round(float(indicator_values["fibo_127_2"]), 8),
        "fibo_100": round(float(indicator_values["fibo_100"]), 8),
        "fibo_78_6": round(float(indicator_values["fibo_78_6"]), 8),
        "matched_rules": matched_rules,
        "matched_fields": sorted(set(matched_fields)),
        "updated_at": market_payload.get("last_candle_time"),
        "evaluated_at": market_payload.get("evaluated_at"),
        "data_source": market_payload.get("data_source"),
        "cache_hit": bool(market_payload.get("cache_hit", False)),
        "fresh_fetch": bool(market_payload.get("fresh_fetch", False)),
        "last_candle_time": market_payload.get("last_candle_time"),
    }


def run_indicator_query_engine(
    *,
    exchange: str,
    market_type: str,
    timeframe: str,
    query_expression: str,
    symbol_universe,
    limit: int,
) -> dict:
    calculation_timestamp = _utc_now_iso()
    safe_limit = max(1, min(int(limit or DEFAULT_RESULT_LIMIT), MAX_RESULT_LIMIT))
    normalized_exchange = (exchange or "binance").strip().lower()
    normalized_market_type = (market_type or "spot").strip().lower()
    normalized_timeframe = (timeframe or "15m").strip().lower()

    try:
        query_ast = parse_query_expression(query_expression)
    except QueryParseError as exc:
        return {
            "matched_symbols": [],
            "evaluated_count": 0,
            "match_count": 0,
            "query_valid": False,
            "query_error": str(exc),
            "calculation_timestamp": calculation_timestamp,
            "rows": [],
            "evaluated_symbols": [],
            "skipped_symbols": [],
            "limit": safe_limit,
        }

    provider = BinanceMarketDataProvider()
    try:
        universe_payload = provider.get_tradable_symbols(exchange=normalized_exchange, market_type=normalized_market_type)
    except MarketDataProviderError as exc:
        return {
            "matched_symbols": [],
            "evaluated_count": 0,
            "match_count": 0,
            "query_valid": False,
            "query_error": str(exc),
            "calculation_timestamp": calculation_timestamp,
            "rows": [],
            "evaluated_symbols": [],
            "skipped_symbols": [],
            "limit": safe_limit,
        }

    all_symbols = universe_payload.get("symbols", [])
    try:
        selected_symbols, universe_mode = _normalize_symbol_universe(symbol_universe, all_symbols)
    except QueryParseError as exc:
        return {
            "matched_symbols": [],
            "evaluated_count": 0,
            "match_count": 0,
            "query_valid": False,
            "query_error": str(exc),
            "calculation_timestamp": calculation_timestamp,
            "rows": [],
            "evaluated_symbols": [],
            "skipped_symbols": [],
            "limit": safe_limit,
        }

    matched_rows: list[dict] = []
    evaluated_symbols: list[str] = []
    skipped_symbols: list[str] = []

    def evaluate_symbol(symbol: str):
        market_payload = provider.fetch_candles(
            exchange=normalized_exchange,
            market_type=normalized_market_type,
            symbol=symbol,
            timeframe=normalized_timeframe,
            candle_limit=90,
        )
        indicator_values = calculate_indicator_values(market_payload.get("candles", []))
        is_match, matched_rules, matched_fields = evaluate_query_ast(query_ast, indicator_values)
        return {
            "symbol": symbol,
            "is_match": is_match,
            "matched_rules": matched_rules,
            "matched_fields": matched_fields,
            "indicator_values": indicator_values,
            "market_payload": market_payload,
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(evaluate_symbol, symbol): symbol for symbol in selected_symbols}
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                result = future.result()
                evaluated_symbols.append(symbol)
                if result["is_match"]:
                    matched_rows.append(
                        _build_result_row(
                            index=0,
                            exchange=normalized_exchange,
                            market_type=normalized_market_type,
                            timeframe=normalized_timeframe,
                            symbol=symbol,
                            indicator_values=result["indicator_values"],
                            matched_rules=result["matched_rules"],
                            matched_fields=result["matched_fields"],
                            market_payload=result["market_payload"],
                        )
                    )
            except (MarketDataProviderError, IndicatorCalculationError, QueryParseError):
                skipped_symbols.append(symbol)
            except Exception:
                skipped_symbols.append(symbol)

    matched_rows.sort(key=lambda row: row["symbol"])
    for idx, row in enumerate(matched_rows, start=1):
        row["index"] = idx

    limited_rows = matched_rows[:safe_limit]
    return {
        "matched_symbols": [row["symbol"] for row in limited_rows],
        "evaluated_count": len(evaluated_symbols),
        "match_count": len(matched_rows),
        "query_valid": True,
        "query_error": None,
        "calculation_timestamp": calculation_timestamp,
        "rows": limited_rows,
        "evaluated_symbols": sorted(evaluated_symbols),
        "skipped_symbols": sorted(set(skipped_symbols)),
        "limit": safe_limit,
        "universe_mode": universe_mode,
        "universe_count": len(selected_symbols),
        "exchange": normalized_exchange,
        "market_type": normalized_market_type,
        "timeframe": normalized_timeframe,
    }


def indicator_screener_presets() -> list[dict]:
    return [
        {
            "preset_key": "oversold_rsi14",
            "title": "Oversold RSI14",
            "query_expression": "rsi14 < 30",
        },
        {
            "preset_key": "oversold_rsi7",
            "title": "Oversold RSI7",
            "query_expression": "rsi7 < 30",
        },
        {
            "preset_key": "double_oversold",
            "title": "Double Oversold",
            "query_expression": "rsi14 < 30 AND rsi7 < 30",
        },
        {
            "preset_key": "rsi_recovery",
            "title": "RSI Recovery",
            "query_expression": "rsi14 < 35 AND rsi7 > 30",
        },
        {
            "preset_key": "high_volume_oversold",
            "title": "High Volume Oversold",
            "query_expression": "rsi14 < 30 AND volume > 1000000",
        },
    ]
