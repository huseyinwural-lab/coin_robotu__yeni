from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import UserIndicatorSavedQuery, UserIndicatorWatchlist
from services.indicator_screener.indicator_calculation_service import IndicatorCalculationError, calculate_query_indicator_values
from services.indicator_screener.market_data_provider import ALLOWED_TIMEFRAMES, BinanceMarketDataProvider, MarketDataProviderError
from services.indicator_screener.query_parser import QueryParseError, collect_query_fields, evaluate_query_ast, parse_query_expression


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_RESULT_LIMIT = 50
MAX_RESULT_LIMIT = 300
MAX_WORKERS = 12

DEFAULT_FILTERS = {
    "symbol_source": "crypto",
    "symbol_universe_mode": "all_tradable",
    "symbol_search": "",
    "symbol_whitelist": [],
    "saved_query_id": None,
    "universe_top_n": 200,
    "sort_by": "symbol",
    "sort_direction": "asc",
    "min_24h_volume": 100_000.0,
    "max_24h_volume": None,
    "quote_asset_filter": "ALL",
    "only_tradable_pairs": True,
    "only_margin_eligible": False,
    "only_futures_eligible": False,
    "spread_threshold_pct": None,
    "market_participation": "spot_only",
    "pair_mode": "all",
    "exclude_leveraged_tokens": True,
    "exclude_stablecoin_stablecoin_pairs": True,
    "min_signal_score": None,
    "min_confidence": None,
    "min_rr_estimate": None,
    "only_executable": False,
    "only_fresh_data": False,
    "last_candle_freshness_minutes": 180,
}

SORTABLE_FIELDS = {
    "symbol",
    "market_type",
    "volume_24h",
    "close",
    "rsi14",
    "rsi7",
    "signal_score",
    "confidence",
    "rr_estimate",
    "updated_at",
}


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize_universe_mode(raw_mode: str | None) -> str:
    candidate = (raw_mode or "").strip().lower()
    mapping = {
        "all": "all_tradable",
        "all_exchange": "all_tradable",
        "all_tradable": "all_tradable",
        "top": "top_by_volume",
        "top_active_50": "top_by_volume",
        "top_active_100": "top_by_volume",
        "top_by_volume": "top_by_volume",
        "whitelist": "whitelist_only",
        "custom_list": "whitelist_only",
        "whitelist_only": "whitelist_only",
        "watchlist": "watchlist_only",
        "watchlist_only": "watchlist_only",
        "saved": "saved_universe",
        "saved_universe": "saved_universe",
        "futures_eligible": "futures_only_eligible_universe",
        "futures_only_eligible_universe": "futures_only_eligible_universe",
    }
    return mapping.get(candidate, "all_tradable")


def _normalize_market_participation(default_market_type: str, raw_value: str | None) -> str:
    candidate = (raw_value or "").strip().lower()
    if candidate in {"spot_only", "futures_only", "both"}:
        return candidate
    if (default_market_type or "spot").strip().lower() == "futures":
        return "futures_only"
    return "spot_only"


def _build_filter_payload(symbol_universe, raw_filter_payload: dict, market_type: str, limit: int) -> dict:
    payload = {**DEFAULT_FILTERS}
    if isinstance(raw_filter_payload, dict):
        payload.update(raw_filter_payload)

    payload["symbol_universe_mode"] = _normalize_universe_mode(payload.get("symbol_universe_mode"))
    payload["symbol_source"] = str(payload.get("symbol_source") or "crypto").strip().lower()
    payload["market_participation"] = _normalize_market_participation(market_type, payload.get("market_participation"))
    payload["sort_direction"] = str(payload.get("sort_direction") or "asc").lower()
    payload["sort_by"] = str(payload.get("sort_by") or "symbol").lower()
    payload["quote_asset_filter"] = str(payload.get("quote_asset_filter") or "ALL").upper()
    payload["pair_mode"] = str(payload.get("pair_mode") or "all").lower()
    payload["symbol_search"] = str(payload.get("symbol_search") or "").strip().upper()
    payload["last_candle_freshness_minutes"] = int(payload.get("last_candle_freshness_minutes") or 180)
    payload["universe_top_n"] = int(payload.get("universe_top_n") or max(limit * 5, 200))

    whitelist_raw = payload.get("symbol_whitelist")
    if isinstance(whitelist_raw, list):
        payload["symbol_whitelist"] = sorted({str(item).strip().upper() for item in whitelist_raw if str(item).strip()})
    elif isinstance(whitelist_raw, str):
        payload["symbol_whitelist"] = sorted({part.strip().upper() for part in whitelist_raw.split(",") if part.strip()})
    else:
        payload["symbol_whitelist"] = []

    if symbol_universe is not None:
        if isinstance(symbol_universe, list) and symbol_universe:
            payload["symbol_universe_mode"] = "whitelist_only"
            payload["symbol_whitelist"] = sorted({str(item).strip().upper() for item in symbol_universe if str(item).strip()})
        elif isinstance(symbol_universe, str) and symbol_universe.strip().lower() not in {"", "all"}:
            payload["symbol_universe_mode"] = "whitelist_only"
            payload["symbol_whitelist"] = sorted(
                {part.strip().upper() for part in symbol_universe.split(",") if part.strip()}
            )

    return payload


def _validate_filter_payload(payload: dict) -> str | None:
    if payload.get("symbol_source") != "crypto":
        return "stock_symbol_source_not_supported_in_indicator_engine"

    if payload.get("sort_by") not in SORTABLE_FIELDS:
        return f"Geçersiz sort_by: {payload.get('sort_by')}"
    if payload.get("sort_direction") not in {"asc", "desc"}:
        return "sort_direction yalnızca 'asc' veya 'desc' olabilir"

    min_vol = payload.get("min_24h_volume")
    max_vol = payload.get("max_24h_volume")
    if min_vol is not None and max_vol is not None and _safe_float(min_vol) > _safe_float(max_vol):
        return "min_24h_volume, max_24h_volume değerinden büyük olamaz"

    if payload.get("symbol_universe_mode") == "top_by_volume" and payload.get("symbol_whitelist"):
        return "top_by_volume ile whitelist aynı anda kullanılamaz"

    if payload.get("only_fresh_data") and int(payload.get("last_candle_freshness_minutes") or 0) <= 0:
        return "only_fresh_data açıkken last_candle_freshness_minutes > 0 olmalı"

    if int(payload.get("universe_top_n") or 0) <= 0:
        return "universe_top_n 1 veya daha büyük olmalı"

    if payload.get("pair_mode") not in {"all", "usdt_only", "btc_only"}:
        return "pair_mode yalnızca all/usdt_only/btc_only olabilir"

    if payload.get("symbol_universe_mode") == "whitelist_only" and not payload.get("symbol_whitelist"):
        return "whitelist_only seçildiğinde whitelist boş olamaz"

    return None


def _build_active_filter_chips(payload: dict) -> list[dict]:
    chips: list[dict] = []
    if payload.get("market_participation") != "spot_only":
        chips.append({"key": "market_participation", "label": "Market", "value": payload.get("market_participation")})
    if payload.get("symbol_universe_mode") != "all_tradable":
        chips.append({"key": "symbol_universe_mode", "label": "Universe", "value": payload.get("symbol_universe_mode")})
    if payload.get("symbol_source") != "crypto":
        chips.append({"key": "symbol_source", "label": "Source", "value": payload.get("symbol_source")})
    if payload.get("symbol_search"):
        chips.append({"key": "symbol_search", "label": "Search", "value": payload.get("symbol_search")})
    if payload.get("min_24h_volume"):
        chips.append({"key": "min_24h_volume", "label": "Min 24h Vol", "value": payload.get("min_24h_volume")})
    if payload.get("max_24h_volume"):
        chips.append({"key": "max_24h_volume", "label": "Max 24h Vol", "value": payload.get("max_24h_volume")})
    if payload.get("quote_asset_filter") not in {"ALL", ""}:
        chips.append({"key": "quote_asset_filter", "label": "Quote", "value": payload.get("quote_asset_filter")})
    if payload.get("pair_mode") != "all":
        chips.append({"key": "pair_mode", "label": "Pair Mode", "value": payload.get("pair_mode")})
    if payload.get("only_fresh_data"):
        chips.append({"key": "fresh", "label": "Fresh Only", "value": payload.get("last_candle_freshness_minutes")})
    if payload.get("only_executable"):
        chips.append({"key": "exec", "label": "Only Executable", "value": True})
    if payload.get("min_signal_score") is not None:
        chips.append({"key": "min_signal_score", "label": "Min Score", "value": payload.get("min_signal_score")})
    return chips


def _participation_modes(payload: dict) -> list[str]:
    mode = payload.get("market_participation")
    if mode == "both":
        return ["spot", "futures"]
    if mode == "futures_only":
        return ["futures"]
    return ["spot"]


def _load_saved_universe_symbols(db: Session, user_id: str, payload: dict) -> tuple[list[str], str | None]:
    saved_query_id = payload.get("saved_query_id")
    query = db.query(UserIndicatorSavedQuery).filter(UserIndicatorSavedQuery.user_id == user_id)
    if saved_query_id:
        query = query.filter(UserIndicatorSavedQuery.id == saved_query_id)
    row = query.order_by(UserIndicatorSavedQuery.updated_at.desc()).first()
    if row is None:
        return [], "saved_universe_not_found"
    return sorted({str(symbol).strip().upper() for symbol in (row.symbol_universe or []) if str(symbol).strip()}), None


def _select_symbols_for_market(
    *,
    db: Session,
    user_id: str,
    provider: BinanceMarketDataProvider,
    exchange: str,
    market_mode: str,
    payload: dict,
    warnings: list[str],
) -> list[dict]:
    universe_payload = provider.get_tradable_symbols(exchange=exchange, market_type=market_mode)
    rows = universe_payload.get("rows", [])

    if payload.get("only_tradable_pairs"):
        rows = [item for item in rows if bool(item.get("is_tradable", False))]

    if payload.get("quote_asset_filter") not in {"ALL", ""}:
        quote_asset = payload.get("quote_asset_filter")
        rows = [item for item in rows if str(item.get("quote_asset", "")).upper() == quote_asset]

    pair_mode = payload.get("pair_mode")
    if pair_mode == "usdt_only":
        rows = [item for item in rows if str(item.get("quote_asset", "")).upper() == "USDT"]
    elif pair_mode == "btc_only":
        rows = [item for item in rows if str(item.get("quote_asset", "")).upper() == "BTC"]

    if payload.get("exclude_leveraged_tokens"):
        rows = [item for item in rows if not bool(item.get("leveraged_token", False))]

    if payload.get("exclude_stablecoin_stablecoin_pairs"):
        rows = [item for item in rows if not bool(item.get("stablecoin_pair", False))]

    min_vol = payload.get("min_24h_volume")
    if min_vol is not None:
        rows = [
            item
            for item in rows
            if item.get("volume_24h") is None or _safe_float(item.get("volume_24h")) >= _safe_float(min_vol)
        ]

    max_vol = payload.get("max_24h_volume")
    if max_vol is not None:
        rows = [
            item
            for item in rows
            if item.get("volume_24h") is None or _safe_float(item.get("volume_24h")) <= _safe_float(max_vol)
        ]

    spread_threshold = payload.get("spread_threshold_pct")
    if spread_threshold is not None:
        rows = [
            item
            for item in rows
            if item.get("spread_pct_24h") is None or _safe_float(item.get("spread_pct_24h")) <= _safe_float(spread_threshold)
        ]

    if payload.get("only_margin_eligible"):
        rows = [item for item in rows if bool(item.get("margin_eligible", False))]

    if payload.get("only_futures_eligible"):
        if market_mode == "futures":
            rows = [item for item in rows if bool(item.get("futures_eligible", False))]
        else:
            futures_symbols_payload = provider.get_tradable_symbols(exchange=exchange, market_type="futures")
            futures_symbols = set(futures_symbols_payload.get("symbols", []))
            rows = [item for item in rows if item.get("symbol") in futures_symbols]

    symbol_search = payload.get("symbol_search")
    if symbol_search:
        rows = [item for item in rows if symbol_search in str(item.get("symbol", ""))]

    mode = payload.get("symbol_universe_mode")
    if mode == "whitelist_only":
        whitelist = set(payload.get("symbol_whitelist") or [])
        rows = [item for item in rows if item.get("symbol") in whitelist]
    elif mode == "watchlist_only":
        watchlist = (
            db.query(UserIndicatorWatchlist)
            .filter(UserIndicatorWatchlist.user_id == user_id)
            .all()
        )
        watch_symbols = {row.symbol for row in watchlist}
        rows = [item for item in rows if item.get("symbol") in watch_symbols]
    elif mode == "saved_universe":
        saved_symbols, error = _load_saved_universe_symbols(db, user_id, payload)
        if error:
            warnings.append(error)
            rows = []
        else:
            rows = [item for item in rows if item.get("symbol") in set(saved_symbols)]
    elif mode == "futures_only_eligible_universe":
        futures_symbols_payload = provider.get_tradable_symbols(exchange=exchange, market_type="futures")
        futures_symbols = set(futures_symbols_payload.get("symbols", []))
        rows = [item for item in rows if item.get("symbol") in futures_symbols]

    rows.sort(key=lambda item: (-_safe_float(item.get("volume_24h")), item.get("symbol")))
    if mode == "top_by_volume":
        rows = rows[: max(1, int(payload.get("universe_top_n") or 200))]
    else:
        rows = rows[: max(1, int(payload.get("universe_top_n") or 200))]

    for row in rows:
        row["market_type"] = market_mode
    return rows


def _freshness_minutes(last_candle_time: str | None) -> float | None:
    if not last_candle_time:
        return None
    try:
        parsed = datetime.fromisoformat(last_candle_time)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max((now - parsed).total_seconds() / 60.0, 0.0)


def _score_row(indicator_values: dict, metadata: dict) -> tuple[float, float, float]:
    rsi14 = _safe_float(indicator_values.get("rsi14"), 50)
    rsi7 = _safe_float(indicator_values.get("rsi7"), 50)
    close = max(_safe_float(indicator_values.get("close"), 0.0), 1e-9)
    ema20 = _safe_float(indicator_values.get("ema20"), close)
    ema50 = _safe_float(indicator_values.get("ema50"), close)
    fibo_127_2 = _safe_float(indicator_values.get("fibo_127_2"), close)
    fibo_78_6 = _safe_float(indicator_values.get("fibo_78_6"), close)
    volume_24h = _safe_float(metadata.get("volume_24h"), 0.0)

    oversold_component = max(0.0, 50.0 - rsi14) + max(0.0, 50.0 - rsi7)
    trend_component = min(abs(ema20 - ema50) / close * 120, 20.0)
    volume_component = min(volume_24h / 10_000_000, 20.0)
    signal_score = min(100.0, oversold_component * 1.2 + trend_component + volume_component)

    confidence = min(100.0, signal_score * 0.85 + min(volume_component, 10.0))
    downside = max(close - fibo_78_6, 1e-9)
    upside = max(fibo_127_2 - close, 0.0)
    rr_estimate = round(upside / downside, 6)
    return round(signal_score, 6), round(confidence, 6), rr_estimate


def _row_sort_key(row: dict, sort_by: str):
    if sort_by == "updated_at":
        return row.get("updated_at") or ""
    value = row.get(sort_by)
    if isinstance(value, (int, float)):
        return float(value)
    return str(value or "")


def _build_result_row(
    *,
    index: int,
    exchange: str,
    timeframe: str,
    symbol: str,
    indicator_values: dict,
    matched_rules: list[str],
    matched_fields: list[str],
    market_payload: dict,
    metadata: dict,
    signal_score: float,
    confidence: float,
    rr_estimate: float,
    executable: bool,
    executable_reasons: list[str],
    stale_data: bool,
    query_fields: set[str],
) -> dict:
    condition_metric_values: dict[str, float] = {}
    for field in sorted(set(query_fields or set())):
        if field in indicator_values:
            condition_metric_values[field] = round(_safe_float(indicator_values.get(field), 0.0), 8)
        elif field == "last_price":
            condition_metric_values[field] = round(_safe_float(metadata.get("last_price"), _safe_float(indicator_values.get("close"), 0.0)), 8)

    return {
        "index": index,
        "exchange": exchange,
        "market_type": metadata.get("market_type") or market_payload.get("market_type"),
        "symbol": symbol,
        "timeframe": timeframe,
        "open": round(float(indicator_values["open"]), 8),
        "high": round(float(indicator_values["high"]), 8),
        "low": round(float(indicator_values["low"]), 8),
        "close": round(float(indicator_values["close"]), 8),
        "scan_price": round(float(indicator_values["close"]), 8),
        "last_price": round(_safe_float(metadata.get("last_price"), _safe_float(indicator_values.get("close"), 0.0)), 8),
        "volume": round(float(indicator_values["volume"]), 8),
        "rsi14": round(float(indicator_values["rsi14"]), 6),
        "rsi7": round(float(indicator_values["rsi7"]), 6),
        "ema21": round(float(indicator_values["ema21"]), 8),
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
        "condition_metric_values": condition_metric_values,
        "updated_at": market_payload.get("last_candle_time"),
        "evaluated_at": market_payload.get("evaluated_at"),
        "data_source": market_payload.get("data_source"),
        "cache_hit": bool(market_payload.get("cache_hit", False)),
        "fresh_fetch": bool(market_payload.get("fresh_fetch", False)),
        "last_candle_time": market_payload.get("last_candle_time"),
        "volume_24h": None if metadata.get("volume_24h") is None else _safe_float(metadata.get("volume_24h"), 0.0),
        "spread_pct_24h": metadata.get("spread_pct_24h"),
        "quote_asset": metadata.get("quote_asset"),
        "is_tradable": bool(metadata.get("is_tradable", True)),
        "margin_eligible": bool(metadata.get("margin_eligible", False)),
        "futures_eligible": bool(metadata.get("futures_eligible", False)),
        "leveraged_token": bool(metadata.get("leveraged_token", False)),
        "stablecoin_pair": bool(metadata.get("stablecoin_pair", False)),
        "signal_score": signal_score,
        "confidence": confidence,
        "rr_estimate": rr_estimate,
        "executable": executable,
        "executable_reasons": executable_reasons,
        "stale_data": stale_data,
    }


def run_indicator_query_engine(
    *,
    db: Session,
    user_id: str,
    exchange: str,
    market_type: str,
    timeframe: str,
    query_expression: str,
    symbol_universe,
    limit: int,
    filter_payload: dict,
) -> dict:
    calculation_timestamp = _utc_now_iso()
    safe_limit = max(1, min(int(limit or DEFAULT_RESULT_LIMIT), MAX_RESULT_LIMIT))
    normalized_exchange = (exchange or "binance").strip().lower()
    normalized_timeframe = (timeframe or "15m").strip().lower()

    if normalized_timeframe not in ALLOWED_TIMEFRAMES:
        return {
            "matched_symbols": [],
            "evaluated_count": 0,
            "match_count": 0,
            "query_valid": False,
            "query_error": f"unsupported_timeframe:{normalized_timeframe}",
            "calculation_timestamp": calculation_timestamp,
            "rows": [],
            "evaluated_symbols": [],
            "skipped_symbols": [],
            "limit": safe_limit,
            "universe_mode": "all_tradable",
            "universe_count": 0,
            "exchange": normalized_exchange,
            "market_type": (market_type or "spot").strip().lower(),
            "timeframe": normalized_timeframe,
            "applied_filters": {},
            "active_filter_chips": [],
            "result_state": "invalid_timeframe",
            "filter_error": None,
            "warnings": [],
        }

    payload = _build_filter_payload(symbol_universe, filter_payload, market_type, safe_limit)
    filter_error = _validate_filter_payload(payload)
    active_filter_chips = _build_active_filter_chips(payload)

    if filter_error:
        return {
            "matched_symbols": [],
            "evaluated_count": 0,
            "match_count": 0,
            "query_valid": True,
            "query_error": None,
            "calculation_timestamp": calculation_timestamp,
            "rows": [],
            "evaluated_symbols": [],
            "skipped_symbols": [],
            "limit": safe_limit,
            "universe_mode": payload.get("symbol_universe_mode"),
            "universe_count": 0,
            "exchange": normalized_exchange,
            "market_type": payload.get("market_participation"),
            "timeframe": normalized_timeframe,
            "applied_filters": payload,
            "active_filter_chips": active_filter_chips,
            "result_state": "invalid_filter_combination",
            "filter_error": filter_error,
            "warnings": [],
        }

    query_ast = None
    query_fields: set[str] = set()
    query_valid = True
    query_error = None
    stripped_query = (query_expression or "").strip()
    if stripped_query:
        try:
            query_ast = parse_query_expression(stripped_query)
            query_fields = collect_query_fields(query_ast)
        except QueryParseError as exc:
            query_valid = False
            query_error = str(exc)

    if not query_valid:
        return {
            "matched_symbols": [],
            "evaluated_count": 0,
            "match_count": 0,
            "query_valid": False,
            "query_error": query_error,
            "calculation_timestamp": calculation_timestamp,
            "rows": [],
            "evaluated_symbols": [],
            "skipped_symbols": [],
            "limit": safe_limit,
            "universe_mode": payload.get("symbol_universe_mode"),
            "universe_count": 0,
            "exchange": normalized_exchange,
            "market_type": payload.get("market_participation"),
            "timeframe": normalized_timeframe,
            "applied_filters": payload,
            "active_filter_chips": active_filter_chips,
            "result_state": "invalid_query",
            "filter_error": None,
            "warnings": [],
        }

    provider = BinanceMarketDataProvider()
    warnings: list[str] = []
    candidate_rows: list[dict] = []
    backend_errors: list[str] = []

    for market_mode in _participation_modes(payload):
        try:
            selected = _select_symbols_for_market(
                db=db,
                user_id=user_id,
                provider=provider,
                exchange=normalized_exchange,
                market_mode=market_mode,
                payload=payload,
                warnings=warnings,
            )
            candidate_rows.extend(selected)
        except MarketDataProviderError as exc:
            backend_errors.append(str(exc))

    if backend_errors and not candidate_rows:
        lowered = " ".join(backend_errors).lower()
        result_state = "rate_limit_throttled" if "429" in lowered or "rate" in lowered else "backend_unavailable"
        return {
            "matched_symbols": [],
            "evaluated_count": 0,
            "match_count": 0,
            "query_valid": True,
            "query_error": None,
            "calculation_timestamp": calculation_timestamp,
            "rows": [],
            "evaluated_symbols": [],
            "skipped_symbols": [],
            "limit": safe_limit,
            "universe_mode": payload.get("symbol_universe_mode"),
            "universe_count": 0,
            "exchange": normalized_exchange,
            "market_type": payload.get("market_participation"),
            "timeframe": normalized_timeframe,
            "applied_filters": payload,
            "active_filter_chips": active_filter_chips,
            "result_state": result_state,
            "filter_error": None,
            "warnings": backend_errors,
        }

    dedup: dict[tuple[str, str], dict] = {}
    for row in candidate_rows:
        key = (row.get("symbol"), row.get("market_type"))
        if key not in dedup:
            dedup[key] = row
    candidate_rows = list(dedup.values())
    candidate_rows.sort(key=lambda item: (-_safe_float(item.get("volume_24h")), item.get("symbol"), item.get("market_type")))

    if not candidate_rows:
        return {
            "matched_symbols": [],
            "evaluated_count": 0,
            "match_count": 0,
            "query_valid": True,
            "query_error": None,
            "calculation_timestamp": calculation_timestamp,
            "rows": [],
            "evaluated_symbols": [],
            "skipped_symbols": [],
            "limit": safe_limit,
            "universe_mode": payload.get("symbol_universe_mode"),
            "universe_count": 0,
            "exchange": normalized_exchange,
            "market_type": payload.get("market_participation"),
            "timeframe": normalized_timeframe,
            "applied_filters": payload,
            "active_filter_chips": active_filter_chips,
            "result_state": "empty_universe",
            "filter_error": None,
            "warnings": warnings,
        }

    matched_rows: list[dict] = []
    evaluated_symbols: list[str] = []
    skipped_symbols: list[str] = []

    def evaluate_candidate(metadata: dict):
        market_payload = provider.fetch_candles(
            exchange=normalized_exchange,
            market_type=metadata.get("market_type"),
            symbol=metadata.get("symbol"),
            timeframe=normalized_timeframe,
            candle_limit=90,
        )
        indicator_values = calculate_query_indicator_values(market_payload.get("candles", []), query_fields)
        query_values = dict(indicator_values)
        query_values["last_price"] = _safe_float(metadata.get("last_price"), _safe_float(indicator_values.get("close"), 0.0))
        if query_ast is None:
            query_match, matched_rules, matched_fields = True, [], []
        else:
            query_match, matched_rules, matched_fields = evaluate_query_ast(query_ast, query_values)

        signal_score, confidence, rr_estimate = _score_row(indicator_values, metadata)
        freshness_mins = _freshness_minutes(market_payload.get("last_candle_time"))
        stale_data = freshness_mins is None or freshness_mins > int(payload.get("last_candle_freshness_minutes") or 180)

        executable_reasons: list[str] = []
        if not metadata.get("is_tradable", True):
            executable_reasons.append("not_tradable")
        if stale_data:
            executable_reasons.append("stale_data")
        if _safe_float(metadata.get("volume_24h"), 0.0) < _safe_float(payload.get("min_24h_volume"), 0.0):
            executable_reasons.append("low_volume")
        spread_threshold = payload.get("spread_threshold_pct")
        if spread_threshold is not None and metadata.get("spread_pct_24h") is not None:
            if _safe_float(metadata.get("spread_pct_24h")) > _safe_float(spread_threshold):
                executable_reasons.append("high_spread")

        executable = len(executable_reasons) == 0

        if payload.get("min_signal_score") is not None and signal_score < _safe_float(payload.get("min_signal_score")):
            query_match = False
        if payload.get("min_confidence") is not None and confidence < _safe_float(payload.get("min_confidence")):
            query_match = False
        if payload.get("min_rr_estimate") is not None and rr_estimate < _safe_float(payload.get("min_rr_estimate")):
            query_match = False
        if payload.get("only_executable") and not executable:
            query_match = False
        if payload.get("only_fresh_data") and stale_data:
            query_match = False

        return {
            "symbol": metadata.get("symbol"),
            "market_type": metadata.get("market_type"),
            "query_match": query_match,
            "matched_rules": matched_rules,
            "matched_fields": matched_fields,
            "indicator_values": indicator_values,
            "market_payload": market_payload,
            "metadata": metadata,
            "signal_score": signal_score,
            "confidence": confidence,
            "rr_estimate": rr_estimate,
            "executable": executable,
            "executable_reasons": executable_reasons,
            "stale_data": stale_data,
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(evaluate_candidate, row): row for row in candidate_rows}
        for future in as_completed(future_map):
            metadata = future_map[future]
            symbol_key = f"{metadata.get('symbol')}:{metadata.get('market_type')}"
            try:
                result = future.result()
                evaluated_symbols.append(symbol_key)
                if result["query_match"]:
                    matched_rows.append(
                        _build_result_row(
                            index=0,
                            exchange=normalized_exchange,
                            timeframe=normalized_timeframe,
                            symbol=result["symbol"],
                            indicator_values=result["indicator_values"],
                            matched_rules=result["matched_rules"],
                            matched_fields=result["matched_fields"],
                            market_payload=result["market_payload"],
                            metadata=result["metadata"],
                            signal_score=result["signal_score"],
                            confidence=result["confidence"],
                            rr_estimate=result["rr_estimate"],
                            executable=result["executable"],
                            executable_reasons=result["executable_reasons"],
                            stale_data=result["stale_data"],
                            query_fields=query_fields,
                        )
                    )
            except (MarketDataProviderError, IndicatorCalculationError, QueryParseError):
                skipped_symbols.append(symbol_key)
            except Exception:
                skipped_symbols.append(symbol_key)

    reverse = payload.get("sort_direction") == "desc"
    sort_by = payload.get("sort_by")
    matched_rows.sort(key=lambda row: (_row_sort_key(row, sort_by), row.get("symbol"), row.get("market_type")), reverse=reverse)

    for idx, row in enumerate(matched_rows, start=1):
        row["index"] = idx

    limited_rows = matched_rows[:safe_limit]
    if len(limited_rows) == 0:
        result_state = "no_match"
    else:
        result_state = "success"

    return {
        "matched_symbols": [f"{row['symbol']}:{row['market_type']}" for row in limited_rows],
        "evaluated_count": len(evaluated_symbols),
        "match_count": len(matched_rows),
        "query_valid": True,
        "query_error": None,
        "calculation_timestamp": calculation_timestamp,
        "rows": limited_rows,
        "evaluated_symbols": sorted(evaluated_symbols),
        "skipped_symbols": sorted(set(skipped_symbols)),
        "limit": safe_limit,
        "universe_mode": payload.get("symbol_universe_mode"),
        "universe_count": len(candidate_rows),
        "exchange": normalized_exchange,
        "market_type": payload.get("market_participation"),
        "timeframe": normalized_timeframe,
        "applied_filters": payload,
        "active_filter_chips": active_filter_chips,
        "result_state": result_state,
        "filter_error": None,
        "warnings": warnings + backend_errors,
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
