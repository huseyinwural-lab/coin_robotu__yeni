import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import statistics

import httpx

from models import PaperPosition, UserExchangeConnection, UserRiskSetting
from services.pipeline.cache_store import get_json, set_json


SUPPORTED_VENUES = ("binance", "bybit")
VENUE_PRIORITY = {"binance": 0, "bybit": 1}
SNAPSHOT_KEY = "execution:microstructure:snapshot:{venue}:{symbol}"
BUFFER_KEY = "execution:microstructure:buffer:{venue}:{symbol}"
REPLAY_FILE = Path("/app/artifacts/manifests/execution_microstructure_replay.jsonl")


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None = None) -> str:
    return (value or _utcnow()).isoformat()


def _env_bool(key: str, default: bool) -> bool:
    value = str(os.environ.get(key, str(default))).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _tracked_symbols() -> list[str]:
    raw = str(os.environ.get("MICROSTRUCTURE_TRACKED_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT"))
    symbols = [item.strip().upper() for item in raw.split(",") if item.strip()]
    return list(dict.fromkeys(symbols))[:12] or ["BTCUSDT", "ETHUSDT"]


def _stale_after_ms() -> int:
    return max(1000, _env_int("MICROSTRUCTURE_STALE_AFTER_MS", 15000))


def _buffer_size() -> int:
    return max(10, _env_int("MICROSTRUCTURE_BUFFER_SIZE", 120))


def _depth_levels() -> int:
    return max(5, _env_int("MICROSTRUCTURE_DEPTH_LEVELS", 20))


def _invalid_snapshot(venue: str, symbol: str, reason: str, *, error: str | None = None) -> dict:
    return {
        "venue": venue,
        "symbol": symbol.upper(),
        "data_state": "INVALID",
        "venue_readiness": "INVALID",
        "reason": reason,
        "error": error,
        "collected_at": _utc_iso(),
        "quote_age_ms": _stale_after_ms() + 1,
        "best_bid": 0.0,
        "best_ask": 0.0,
        "mid_price": 0.0,
        "spread_abs": 0.0,
        "spread_bps": 0.0,
        "top_of_book_bid_qty": 0.0,
        "top_of_book_ask_qty": 0.0,
        "visible_bid_depth_qty": 0.0,
        "visible_ask_depth_qty": 0.0,
        "visible_bid_depth_notional": 0.0,
        "visible_ask_depth_notional": 0.0,
        "l2_bids": [],
        "l2_asks": [],
        "recent_trades": [],
        "trade_flow": {"buy_notional": 0.0, "sell_notional": 0.0, "aggression_side": "UNKNOWN"},
        "fast_market": False,
    }


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _age_ms(value) -> int:
    parsed = _parse_ts(value)
    if parsed is None:
        return _stale_after_ms() + 1
    return max(int((_utcnow() - parsed).total_seconds() * 1000), 0)


def _append_buffer(cache, key: str, payload: dict) -> None:
    if cache is None:
        return
    rows = get_json(cache, key) or []
    rows.append(payload)
    set_json(cache, key, rows[-_buffer_size() :])


def _book_notional(rows: list[list[float]]) -> float:
    return round(sum(_safe_float(price) * _safe_float(qty) for price, qty in rows), 8)


def _stddev(values: list[float]) -> float:
    clean = [float(item) for item in values if isinstance(item, (int, float))]
    if len(clean) < 2:
        return 0.0
    return float(statistics.pstdev(clean))


def _volatility_from_trades(trades: list[dict]) -> float:
    prices = [_safe_float(item.get("price"), 0.0) for item in trades if _safe_float(item.get("price"), 0.0) > 0]
    if len(prices) < 3:
        return 0.0
    returns = []
    for idx in range(1, len(prices)):
        prev = prices[idx - 1]
        curr = prices[idx]
        if prev <= 0:
            continue
        returns.append(abs((curr - prev) / prev))
    if not returns:
        return 0.0
    return round(sum(returns) / len(returns), 8)


def _trade_flow(trades: list[dict]) -> dict:
    buy_notional = 0.0
    sell_notional = 0.0
    for item in trades:
        notional = _safe_float(item.get("price"), 0.0) * _safe_float(item.get("qty"), 0.0)
        if str(item.get("aggression_side") or "").upper() == "BUY":
            buy_notional += notional
        else:
            sell_notional += notional
    aggression_side = "BUY" if buy_notional > sell_notional else "SELL" if sell_notional > buy_notional else "BALANCED"
    total = buy_notional + sell_notional
    return {
        "buy_notional": round(buy_notional, 8),
        "sell_notional": round(sell_notional, 8),
        "buy_share": round(buy_notional / total, 6) if total > 0 else 0.5,
        "aggression_side": aggression_side,
    }


def _buffer_spread_expansion(cache, venue: str, symbol: str, latest_spread_bps: float) -> bool:
    rows = get_json(cache, BUFFER_KEY.format(venue=venue, symbol=symbol.upper())) or []
    spreads = [_safe_float(item.get("spread_bps"), 0.0) for item in rows[-5:] if _safe_float(item.get("spread_bps"), 0.0) > 0]
    if not spreads:
        return False
    baseline = sum(spreads) / len(spreads)
    return latest_spread_bps >= max(baseline * 1.8, _env_float("MICROSTRUCTURE_FAST_MARKET_SPREAD_BPS", 18.0))


def _update_legacy_cache(cache, snapshot: dict) -> None:
    if cache is None:
        return
    symbol = str(snapshot.get("symbol") or "").upper()
    if not symbol or str(snapshot.get("venue") or "") != "binance":
        return

    spread_payload = {
        "symbol": symbol,
        "top_bid": _safe_float(snapshot.get("best_bid"), 0.0),
        "top_ask": _safe_float(snapshot.get("best_ask"), 0.0),
        "spread_bps": _safe_float(snapshot.get("spread_bps"), 0.0),
        "updated_at": snapshot.get("collected_at"),
    }
    orderbook_payload = {
        "symbol": symbol,
        "best_bid": _safe_float(snapshot.get("best_bid"), 0.0),
        "best_ask": _safe_float(snapshot.get("best_ask"), 0.0),
        "bid_depth_top_n": _safe_float(snapshot.get("visible_bid_depth_qty"), 0.0),
        "ask_depth_top_n": _safe_float(snapshot.get("visible_ask_depth_qty"), 0.0),
        "top_of_book_size": round(
            min(_safe_float(snapshot.get("top_of_book_bid_qty"), 0.0), _safe_float(snapshot.get("top_of_book_ask_qty"), 0.0)),
            8,
        ),
        "updated_at": snapshot.get("collected_at"),
    }
    recent_trades = list(snapshot.get("recent_trades") or [])
    trade_payload = {
        "symbol": symbol,
        "recent_trade_volume": round(sum(_safe_float(item.get("qty"), 0.0) * _safe_float(item.get("price"), 0.0) for item in recent_trades), 8),
        "recent_trade_count": len(recent_trades),
        "short_window_volatility": _volatility_from_trades(recent_trades),
        "quote_update_rate": len(recent_trades),
        "updated_at": snapshot.get("collected_at"),
    }
    ticker_payload = {
        "symbol": symbol,
        "last_price": _safe_float(snapshot.get("mid_price"), 0.0),
        "quote_volume": trade_payload["recent_trade_volume"],
        "updated_at": snapshot.get("collected_at"),
    }

    set_json(cache, f"market:spread:{symbol}", spread_payload)
    set_json(cache, f"futures:orderbook:{symbol}", orderbook_payload)
    set_json(cache, f"futures:trade-stats:{symbol}", trade_payload)
    set_json(cache, f"market:ticker:{symbol}", ticker_payload)


def _append_replay_row(snapshot: dict) -> None:
    row = {
        "captured_at": snapshot.get("collected_at"),
        "venue": snapshot.get("venue"),
        "symbol": snapshot.get("symbol"),
        "data_state": snapshot.get("data_state"),
        "mid_price": snapshot.get("mid_price"),
        "spread_bps": snapshot.get("spread_bps"),
        "visible_bid_depth_notional": snapshot.get("visible_bid_depth_notional"),
        "visible_ask_depth_notional": snapshot.get("visible_ask_depth_notional"),
        "fast_market": snapshot.get("fast_market"),
        "transport_latency_ms": snapshot.get("transport_latency_ms"),
        "trade_flow": snapshot.get("trade_flow") or {},
    }
    REPLAY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _buffer_rows(cache, venue: str, symbol: str, *, limit: int = 30) -> list[dict]:
    if cache is None:
        return []
    rows = get_json(cache, BUFFER_KEY.format(venue=venue, symbol=symbol.upper())) or []
    return list(rows)[-max(1, limit) :]


def _market_regime(snapshot: dict, buffer_rows: list[dict]) -> dict:
    prices = [_safe_float(item.get("mid_price"), 0.0) for item in buffer_rows if _safe_float(item.get("mid_price"), 0.0) > 0]
    current_price = _safe_float(snapshot.get("mid_price"), 0.0)
    if current_price > 0:
        prices.append(current_price)
    start_price = prices[0] if prices else current_price
    end_price = prices[-1] if prices else current_price
    momentum_pct = ((end_price - start_price) / start_price) if start_price > 0 else 0.0
    trend_regime = "bull" if momentum_pct >= 0.0015 else "bear" if momentum_pct <= -0.0015 else "chop"

    depth_notional = min(
        _safe_float(snapshot.get("visible_bid_depth_notional"), 0.0),
        _safe_float(snapshot.get("visible_ask_depth_notional"), 0.0),
    )
    liquidity_regime = "high_liquidity" if depth_notional >= _env_float("MICROSTRUCTURE_HIGH_LIQUIDITY_NOTIONAL", 150000.0) else "low_liquidity"
    market_speed = "fast" if bool(snapshot.get("fast_market")) else "normal"
    return {
        "trend": trend_regime,
        "liquidity": liquidity_regime,
        "market_speed": market_speed,
        "momentum_pct": round(momentum_pct, 6),
    }


def _venue_health(snapshot: dict, buffer_rows: list[dict]) -> dict:
    latency_values = [_safe_float(item.get("transport_latency_ms"), 0.0) for item in buffer_rows if _safe_float(item.get("transport_latency_ms"), 0.0) > 0]
    spread_values = [_safe_float(item.get("spread_bps"), 0.0) for item in buffer_rows if _safe_float(item.get("spread_bps"), 0.0) >= 0]
    depth_values = [
        min(_safe_float(item.get("visible_bid_depth_notional"), 0.0), _safe_float(item.get("visible_ask_depth_notional"), 0.0))
        for item in buffer_rows
        if isinstance(item, dict)
    ]
    retry_ratio = 0.0
    if buffer_rows:
        invalid_count = len([item for item in buffer_rows if str(item.get("data_state") or "").upper() != "VALID"])
        retry_ratio = invalid_count / len(buffer_rows)
    spread_instability = _stddev(spread_values)
    depth_instability = _stddev(depth_values)
    avg_latency = (sum(latency_values) / len(latency_values)) if latency_values else 0.0

    latency_penalty = min(avg_latency / 10.0, 25.0)
    retry_penalty = retry_ratio * 35.0
    spread_penalty = min(spread_instability * 3.5, 20.0)
    depth_penalty = min((depth_instability / max(sum(depth_values) / len(depth_values), 1.0)) * 40.0 if depth_values else 0.0, 20.0)
    venue_health_score = max(0.0, min(100.0, 100.0 - latency_penalty - retry_penalty - spread_penalty - depth_penalty))
    liquidity_stress_score = max(
        0.0,
        min(
            100.0,
            (_safe_float(snapshot.get("spread_bps"), 0.0) * 1.5)
            + spread_penalty
            + depth_penalty
            + (20.0 if bool(snapshot.get("fast_market")) else 0.0),
        ),
    )
    return {
        "venue_health_score": round(venue_health_score, 4),
        "liquidity_stress_score": round(liquidity_stress_score, 4),
        "latency_score": round(max(0.0, 100.0 - latency_penalty), 4),
        "retry_score": round(max(0.0, 100.0 - retry_penalty), 4),
        "spread_instability": round(spread_instability, 6),
        "depth_instability": round(depth_instability, 6),
        "avg_transport_latency_ms": round(avg_latency, 4),
        "retry_ratio": round(retry_ratio, 6),
    }


def _execution_recommendation(
    *,
    state: str,
    regime: dict,
    venue_health: dict,
    selected_venue: str,
    snapshots: dict,
    capacity: dict,
) -> dict:
    recommendations: list[str] = []
    primary = "passive"
    if state == "BLOCK":
        primary = "reduce-size"
        recommendations.append("reduce-size")
    elif capacity.get("state") == "REDUCE_SIZE" or state == "REDUCE_SIZE":
        primary = "reduce-size"
        recommendations.append("reduce-size")

    if regime.get("market_speed") == "fast" or _safe_float(venue_health.get("liquidity_stress_score"), 0.0) >= 55.0:
        recommendations.append("slice")
    if regime.get("trend") == "bull" and regime.get("liquidity") == "high_liquidity" and regime.get("market_speed") == "normal":
        recommendations.append("aggressive")
    else:
        recommendations.append("passive")

    current_health = _safe_float(venue_health.get("venue_health_score"), 0.0)
    alternative_candidates = []
    for venue, snapshot in snapshots.items():
        if venue == selected_venue or str(snapshot.get("data_state") or "") != "VALID":
            continue
        other_health = _venue_health(snapshot, [])
        if _safe_float(other_health.get("venue_health_score"), 0.0) >= current_health + 12.0:
            alternative_candidates.append(venue)
    if alternative_candidates:
        recommendations.append("venue-switch-candidate")

    ordered = list(dict.fromkeys(recommendations))
    if primary not in ordered:
        primary = ordered[0] if ordered else primary
    return {
        "primary": primary,
        "all": ordered,
        "venue_switch_candidates": alternative_candidates,
    }


def get_microstructure_replay(*, venue: str | None = None, symbol: str | None = None, limit: int = 100) -> dict:
    if not REPLAY_FILE.exists():
        return {"items": []}
    items = []
    venue_filter = str(venue or "").lower().strip()
    symbol_filter = str(symbol or "").upper().strip()
    for raw in REPLAY_FILE.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if venue_filter and str(row.get("venue") or "").lower() != venue_filter:
            continue
        if symbol_filter and str(row.get("symbol") or "").upper() != symbol_filter:
            continue
        items.append(row)
    return {"items": items[-max(1, min(limit, 500)) :]}


def build_latest_execution_replay(db, *, symbol: str | None = None) -> dict:
    from models import ExecutionMetric

    query = db.query(ExecutionMetric)
    if symbol:
        query = query.filter(ExecutionMetric.symbol == str(symbol).upper())
    metric = query.order_by(ExecutionMetric.created_at.desc()).first()
    if metric is None:
        return {"status": "empty", "reason": "execution_metric_missing"}

    raw_status = dict(metric.raw_exchange_status or {})
    guard_payload = dict(raw_status.get("microstructure_guard") or {})
    replay_rows = get_microstructure_replay(
        venue=str(guard_payload.get("selected_venue") or metric.exchange or "binance"),
        symbol=str(metric.symbol or ""),
        limit=25,
    ).get("items") or []
    predicted_bps = _safe_float(raw_status.get("predicted_slippage_bps"), 0.0)
    realized_bps = _safe_float(raw_status.get("realized_slippage_bps"), abs(_safe_float(metric.slippage_pct)) * 100)
    error_bps = _safe_float(raw_status.get("slippage_error_bps"), abs(realized_bps - predicted_bps))
    root_cause = "timing_delay"
    if error_bps <= 1.0:
        root_cause = "prediction_match"
    elif _safe_float(((guard_payload.get("slippage_decomposition") or {}).get("impact_bps")), 0.0) >= max(
        _safe_float(((guard_payload.get("slippage_decomposition") or {}).get("spread_bps")), 0.0),
        _safe_float(((guard_payload.get("slippage_decomposition") or {}).get("timing_bps")), 0.0),
    ):
        root_cause = "market_impact"
    elif any(bool(item.get("fast_market")) for item in replay_rows[-5:]):
        root_cause = "fast_market"
    return {
        "status": "ok",
        "symbol": metric.symbol,
        "order_id": metric.order_id,
        "exchange": metric.exchange,
        "predicted_slippage_bps": round(predicted_bps, 6),
        "realized_slippage_bps": round(realized_bps, 6),
        "slippage_error_bps": round(error_bps, 6),
        "root_cause": root_cause,
        "pre_trade_guard": guard_payload,
        "replay_rows": replay_rows,
    }


async def _fetch_json(client: httpx.AsyncClient, url: str, *, headers: dict | None = None, params: dict | None = None) -> dict | list:
    response = await client.get(url, headers=headers or {}, params=params or {})
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, (dict, list)) else {}


async def _fetch_binance_snapshot(client: httpx.AsyncClient, symbol: str) -> dict:
    base_url = str(os.environ.get("BINANCE_FUTURES_LIVE_BASE_URL") or "").strip().rstrip("/")
    proxy_token = str(os.environ.get("BINANCE_FUTURES_LIVE_PROXY_TOKEN") or "").strip()
    if not base_url or not proxy_token:
        return _invalid_snapshot("binance", symbol, "binance_market_data_env_missing")

    headers = {"X-Proxy-Token": proxy_token}
    started = asyncio.get_running_loop().time()
    try:
        depth_payload, trades_payload = await asyncio.gather(
            _fetch_json(client, f"{base_url}/fapi/v1/depth", headers=headers, params={"symbol": symbol, "limit": _depth_levels()}),
            _fetch_json(client, f"{base_url}/fapi/v1/trades", headers=headers, params={"symbol": symbol, "limit": 20}),
        )
    except Exception as exc:  # noqa: BLE001
        return _invalid_snapshot("binance", symbol, "binance_market_data_unreachable", error=str(exc)[:240])

    transport_latency_ms = round((asyncio.get_running_loop().time() - started) * 1000, 4)
    bids_raw = list((depth_payload or {}).get("bids") or [])[: _depth_levels()]
    asks_raw = list((depth_payload or {}).get("asks") or [])[: _depth_levels()]
    if not bids_raw or not asks_raw:
        return _invalid_snapshot("binance", symbol, "binance_orderbook_missing")

    bids = [[_safe_float(price), _safe_float(qty)] for price, qty in bids_raw]
    asks = [[_safe_float(price), _safe_float(qty)] for price, qty in asks_raw]
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    spread_abs = max(best_ask - best_bid, 0.0)
    spread_bps = (spread_abs / best_ask) * 10000 if best_ask > 0 else 0.0
    trades = []
    for item in list(trades_payload or [])[:20]:
        trades.append(
            {
                "price": _safe_float(item.get("price"), 0.0),
                "qty": _safe_float(item.get("qty"), 0.0),
                "trade_id": str(item.get("id") or ""),
                "timestamp": _safe_int(item.get("time"), 0),
                "aggression_side": "SELL" if bool(item.get("isBuyerMaker")) else "BUY",
            }
        )

    snapshot = {
        "venue": "binance",
        "symbol": symbol.upper(),
        "data_state": "VALID",
        "venue_readiness": "READY",
        "collected_at": _utc_iso(),
        "source_timestamp": _utc_iso(),
        "quote_age_ms": 0,
        "best_bid": round(best_bid, 8),
        "best_ask": round(best_ask, 8),
        "mid_price": round((best_bid + best_ask) / 2, 8),
        "spread_abs": round(spread_abs, 8),
        "spread_bps": round(spread_bps, 6),
        "top_of_book_bid_qty": round(bids[0][1], 8),
        "top_of_book_ask_qty": round(asks[0][1], 8),
        "visible_bid_depth_qty": round(sum(qty for _, qty in bids), 8),
        "visible_ask_depth_qty": round(sum(qty for _, qty in asks), 8),
        "visible_bid_depth_notional": round(_book_notional(bids), 8),
        "visible_ask_depth_notional": round(_book_notional(asks), 8),
        "l2_bids": bids,
        "l2_asks": asks,
        "recent_trades": trades,
        "trade_flow": _trade_flow(trades),
        "fast_market": False,
        "transport_latency_ms": transport_latency_ms,
    }
    return snapshot


async def _fetch_bybit_snapshot(client: httpx.AsyncClient, symbol: str) -> dict:
    base_url = str(os.environ.get("BYBIT_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        return _invalid_snapshot("bybit", symbol, "bybit_market_data_env_missing")

    started = asyncio.get_running_loop().time()
    try:
        orderbook_payload, trades_payload = await asyncio.gather(
            _fetch_json(client, f"{base_url}/v5/market/orderbook", params={"category": "linear", "symbol": symbol, "limit": _depth_levels()}),
            _fetch_json(client, f"{base_url}/v5/market/recent-trade", params={"category": "linear", "symbol": symbol, "limit": 20}),
        )
    except Exception as exc:  # noqa: BLE001
        return _invalid_snapshot("bybit", symbol, "bybit_market_data_unreachable", error=str(exc)[:240])

    result = dict((orderbook_payload or {}).get("result") or {})
    transport_latency_ms = round((asyncio.get_running_loop().time() - started) * 1000, 4)
    bids_raw = list(result.get("b") or [])[: _depth_levels()]
    asks_raw = list(result.get("a") or [])[: _depth_levels()]
    if not bids_raw or not asks_raw:
        return _invalid_snapshot("bybit", symbol, "bybit_orderbook_missing")

    bids = [[_safe_float(price), _safe_float(qty)] for price, qty in bids_raw]
    asks = [[_safe_float(price), _safe_float(qty)] for price, qty in asks_raw]
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    spread_abs = max(best_ask - best_bid, 0.0)
    spread_bps = (spread_abs / best_ask) * 10000 if best_ask > 0 else 0.0
    recent_trade_rows = []
    for item in list(((trades_payload or {}).get("result") or {}).get("list") or [])[:20]:
        recent_trade_rows.append(
            {
                "price": _safe_float(item.get("price"), 0.0),
                "qty": _safe_float(item.get("size"), 0.0),
                "trade_id": str(item.get("execId") or ""),
                "timestamp": _safe_int(item.get("time"), 0),
                "aggression_side": str(item.get("side") or "UNKNOWN").upper(),
            }
        )

    snapshot = {
        "venue": "bybit",
        "symbol": symbol.upper(),
        "data_state": "VALID",
        "venue_readiness": "READY",
        "collected_at": _utc_iso(),
        "source_timestamp": _utc_iso(_parse_ts(result.get("ts")) or _utcnow()),
        "quote_age_ms": 0,
        "best_bid": round(best_bid, 8),
        "best_ask": round(best_ask, 8),
        "mid_price": round((best_bid + best_ask) / 2, 8),
        "spread_abs": round(spread_abs, 8),
        "spread_bps": round(spread_bps, 6),
        "top_of_book_bid_qty": round(bids[0][1], 8),
        "top_of_book_ask_qty": round(asks[0][1], 8),
        "visible_bid_depth_qty": round(sum(qty for _, qty in bids), 8),
        "visible_ask_depth_qty": round(sum(qty for _, qty in asks), 8),
        "visible_bid_depth_notional": round(_book_notional(bids), 8),
        "visible_ask_depth_notional": round(_book_notional(asks), 8),
        "l2_bids": bids,
        "l2_asks": asks,
        "recent_trades": recent_trade_rows,
        "trade_flow": _trade_flow(recent_trade_rows),
        "fast_market": False,
        "transport_latency_ms": transport_latency_ms,
    }
    return snapshot


class ExecutionMicrostructureRuntime:
    def __init__(self, cache):
        self.cache = cache
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="execution-microstructure-runtime")

    async def stop(self):
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        poll_interval = max(1.0, _env_float("MICROSTRUCTURE_POLL_INTERVAL_SECONDS", 3.0))
        async with httpx.AsyncClient(timeout=10.0) as client:
            while not self._stop_event.is_set():
                symbols = _tracked_symbols()
                tasks = []
                if _env_bool("MICROSTRUCTURE_BINANCE_ENABLED", True):
                    tasks.extend(self._refresh_symbol(client, "binance", symbol) for symbol in symbols)
                if _env_bool("MICROSTRUCTURE_BYBIT_ENABLED", True):
                    tasks.extend(self._refresh_symbol(client, "bybit", symbol) for symbol in symbols)
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(poll_interval)

    async def _refresh_symbol(self, client: httpx.AsyncClient, venue: str, symbol: str):
        if venue == "binance":
            snapshot = await _fetch_binance_snapshot(client, symbol)
        else:
            snapshot = await _fetch_bybit_snapshot(client, symbol)

        snapshot["quote_age_ms"] = _age_ms(snapshot.get("source_timestamp") or snapshot.get("collected_at"))
        snapshot["fast_market"] = bool(snapshot.get("fast_market")) or _buffer_spread_expansion(
            self.cache,
            venue,
            symbol,
            _safe_float(snapshot.get("spread_bps"), 0.0),
        ) or len(snapshot.get("recent_trades") or []) >= _env_int("MICROSTRUCTURE_FAST_MARKET_TRADE_BURST", 15)

        set_json(self.cache, SNAPSHOT_KEY.format(venue=venue, symbol=symbol.upper()), snapshot)
        _append_buffer(
            self.cache,
            BUFFER_KEY.format(venue=venue, symbol=symbol.upper()),
            {
                "collected_at": snapshot.get("collected_at"),
                "spread_bps": snapshot.get("spread_bps"),
                "mid_price": snapshot.get("mid_price"),
                "data_state": snapshot.get("data_state"),
                "fast_market": snapshot.get("fast_market"),
                "visible_bid_depth_notional": snapshot.get("visible_bid_depth_notional"),
                "visible_ask_depth_notional": snapshot.get("visible_ask_depth_notional"),
                "transport_latency_ms": snapshot.get("transport_latency_ms"),
            },
        )
        _append_replay_row(snapshot)
        if str(snapshot.get("data_state") or "") == "VALID":
            _update_legacy_cache(self.cache, snapshot)


def get_venue_snapshot(cache, venue: str, symbol: str) -> dict:
    venue_code = str(venue or "").lower().strip()
    symbol_code = str(symbol or "").upper().strip()
    if cache is None:
        return _invalid_snapshot(venue_code, symbol_code, "microstructure_cache_unavailable")
    snapshot = get_json(cache, SNAPSHOT_KEY.format(venue=venue_code, symbol=symbol_code))
    if not snapshot:
        return _invalid_snapshot(venue_code, symbol_code, "snapshot_missing")
    current = dict(snapshot)
    current["quote_age_ms"] = _age_ms(current.get("source_timestamp") or current.get("collected_at"))
    if current["quote_age_ms"] > _stale_after_ms() and current.get("data_state") == "VALID":
        current["data_state"] = "INVALID"
        current["venue_readiness"] = "INVALID"
        current["reason"] = "quote_stale"
    return current


def build_microstructure_venue_summary(cache, symbols: list[str] | None = None) -> dict:
    tracked = symbols or _tracked_symbols()
    venues = {}
    for venue in SUPPORTED_VENUES:
        rows = [get_venue_snapshot(cache, venue, symbol) for symbol in tracked]
        ready_count = len([row for row in rows if row.get("data_state") == "VALID"])
        health_rows = [_venue_health(row, _buffer_rows(cache, venue, row.get("symbol") or "")) for row in rows]
        venues[venue] = {
            "venue": venue,
            "ready_count": ready_count,
            "invalid_count": len(rows) - ready_count,
            "status": "READY" if ready_count > 0 else "INVALID",
            "venue_health_score": round((sum(_safe_float(item.get("venue_health_score"), 0.0) for item in health_rows) / len(health_rows)) if health_rows else 0.0, 4),
            "liquidity_stress_score": round((sum(_safe_float(item.get("liquidity_stress_score"), 0.0) for item in health_rows) / len(health_rows)) if health_rows else 0.0, 4),
            "symbols": [
                {
                    "symbol": row.get("symbol"),
                    "data_state": row.get("data_state"),
                    "quote_age_ms": row.get("quote_age_ms"),
                    "spread_bps": row.get("spread_bps"),
                    "fast_market": row.get("fast_market"),
                    "reason": row.get("reason"),
                    "venue_health": _venue_health(row, _buffer_rows(cache, venue, row.get("symbol") or "")),
                }
                for row in rows
            ],
        }
    return {"tracked_symbols": tracked, "venues": venues, "updated_at": _utc_iso()}


def _resolve_preferred_venue(db, user_id: str, explicit_venue: str | None = None) -> str:
    if explicit_venue:
        return str(explicit_venue).lower().strip()
    row = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == user_id)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )
    return str(row.exchange or "binance").lower().strip() if row else "binance"


def _capacity_assessment(db, *, user_id: str, symbol: str, price: float, requested_size: float, strategy_binding: str | None, snapshot: dict) -> dict:
    requested_notional = max(price, 0.0) * max(requested_size, 0.0)
    risk_setting = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()
    base_capital = _safe_float(getattr(risk_setting, "base_capital", None), 10000.0)
    allocation_pct = _safe_float(getattr(risk_setting, "allocation_pct", None), 20.0)
    max_deployable_capital = max(base_capital * (allocation_pct / 100.0), 0.0)
    open_positions = db.query(PaperPosition).filter(PaperPosition.user_id == user_id, PaperPosition.status == "open").all()
    open_exposure = sum(abs(_safe_float(row.entry_price) * _safe_float(row.quantity)) for row in open_positions)
    remaining_capital = max(max_deployable_capital - open_exposure, 0.0)
    symbol_capacity_notional = min(
        _safe_float(snapshot.get("visible_bid_depth_notional"), 0.0),
        _safe_float(snapshot.get("visible_ask_depth_notional"), 0.0),
    ) * _env_float("MICROSTRUCTURE_SYMBOL_CAPACITY_PARTICIPATION", 0.20)
    strategy_multiplier = _env_float("MICROSTRUCTURE_STRATEGY_CAPACITY_RATIO", 0.60) if strategy_binding else 1.0
    strategy_capacity_notional = remaining_capital * strategy_multiplier
    allowed_notional = max(min(remaining_capital, symbol_capacity_notional or remaining_capital, strategy_capacity_notional), 0.0)
    adjusted_size = (allowed_notional / price) if price > 0 else 0.0
    state = "ALLOW"
    reasons = []
    if requested_notional > max(allowed_notional, 0.0):
        state = "REDUCE_SIZE" if adjusted_size >= _env_float("MICROSTRUCTURE_MIN_SIZE", 0.001) else "BLOCK"
        reasons.append("capacity_limit_exceeded")
    return {
        "state": state,
        "requested_notional": round(requested_notional, 8),
        "symbol_capacity_notional": round(symbol_capacity_notional, 8),
        "strategy_capacity_notional": round(strategy_capacity_notional, 8),
        "max_deployable_capital": round(max_deployable_capital, 8),
        "remaining_capital": round(remaining_capital, 8),
        "allowed_notional": round(allowed_notional, 8),
        "adjusted_size": round(max(adjusted_size, 0.0), 8),
        "reasons": reasons,
    }


def build_order_microstructure_assessment(
    db,
    cache,
    *,
    user_id: str,
    symbol: str,
    side: str,
    price: float,
    size: float,
    order_type: str,
    strategy_binding: str | None = None,
    preferred_venue: str | None = None,
) -> dict:
    symbol_code = str(symbol or "").upper().strip()
    selected_venue = _resolve_preferred_venue(db, user_id, explicit_venue=preferred_venue)
    snapshots = {venue: get_venue_snapshot(cache, venue, symbol_code) for venue in SUPPORTED_VENUES}
    snapshot = snapshots.get(selected_venue) or next(
        (snapshots[venue] for venue in sorted(SUPPORTED_VENUES, key=lambda item: VENUE_PRIORITY.get(item, 99))),
        _invalid_snapshot(selected_venue, symbol_code, "snapshot_missing"),
    )

    requested_price = max(_safe_float(price), _safe_float(snapshot.get("mid_price"), 0.0), 0.0)
    requested_size = max(_safe_float(size), 0.0)
    requested_notional = requested_price * requested_size
    side_code = str(side or "buy").upper()
    visible_depth_notional = _safe_float(
        snapshot.get("visible_ask_depth_notional") if side_code == "BUY" else snapshot.get("visible_bid_depth_notional"),
        0.0,
    )
    spread_bps = _safe_float(snapshot.get("spread_bps"), 0.0)
    quote_age_ms = _safe_int(snapshot.get("quote_age_ms"), _stale_after_ms() + 1)
    depth_ratio = (requested_notional / max(visible_depth_notional, 1e-6)) if requested_notional > 0 else 0.0
    spread_cost_bps = spread_bps
    depth_impact_bps = round(max(depth_ratio, 0.0) * _env_float("MICROSTRUCTURE_DEPTH_IMPACT_FACTOR_BPS", 12.0), 6)
    latency_penalty_bps = round((quote_age_ms / 1000.0) * _env_float("MICROSTRUCTURE_LATENCY_PENALTY_BPS_PER_SEC", 0.8), 6)
    buffer_rows = _buffer_rows(cache, selected_venue, symbol_code)
    regime = _market_regime(snapshot, buffer_rows)
    venue_health = _venue_health(snapshot, buffer_rows)
    retry_cost_bps = round(_safe_float(venue_health.get("retry_ratio"), 0.0) * _env_float("MICROSTRUCTURE_RETRY_COST_FACTOR_BPS", 6.0), 6)
    if bool(snapshot.get("fast_market")):
        latency_penalty_bps += _env_float("MICROSTRUCTURE_FAST_MARKET_LATENCY_BPS", 4.0)

    reasons: list[str] = []
    state = "ALLOW"
    adjusted_size = requested_size
    recommended_order_type = str(order_type or "market").upper()
    if str(snapshot.get("data_state") or "INVALID") != "VALID":
        state = "BLOCK"
        reasons.append(str(snapshot.get("reason") or "microstructure_invalid"))
    elif quote_age_ms > _stale_after_ms():
        state = "BLOCK"
        reasons.append("quote_stale")
    elif spread_bps >= _env_float("MICROSTRUCTURE_BLOCK_SPREAD_BPS", 25.0):
        state = "BLOCK"
        reasons.append("spread_unsuitable")
    elif visible_depth_notional <= 0:
        state = "BLOCK"
        reasons.append("visible_depth_missing")
    elif depth_ratio >= _env_float("MICROSTRUCTURE_BLOCK_DEPTH_RATIO", 0.35):
        state = "BLOCK"
        reasons.append("visible_depth_too_thin")
    elif bool(snapshot.get("fast_market")) or spread_bps >= _env_float("MICROSTRUCTURE_SWITCH_SPREAD_BPS", 12.0):
        state = "SWITCH_EXECUTION_MODE"
        recommended_order_type = "LIMIT"
        reasons.append("fast_market_execution_mode_switch")
    elif depth_ratio >= _env_float("MICROSTRUCTURE_REDUCE_DEPTH_RATIO", 0.20):
        state = "REDUCE_SIZE"
        adjusted_size = round(requested_size * _env_float("MICROSTRUCTURE_DEPTH_REDUCE_RATIO", 0.60), 8)
        reasons.append("visible_depth_requires_reduction")

    capacity = _capacity_assessment(
        db,
        user_id=user_id,
        symbol=symbol_code,
        price=requested_price,
        requested_size=requested_size,
        strategy_binding=strategy_binding,
        snapshot=snapshot,
    )
    if capacity.get("state") == "BLOCK":
        state = "BLOCK"
        reasons.extend(capacity.get("reasons") or [])
        adjusted_size = 0.0
    elif capacity.get("state") == "REDUCE_SIZE":
        adjusted_size = min(adjusted_size, _safe_float(capacity.get("adjusted_size"), adjusted_size))
        if state != "BLOCK":
            state = "REDUCE_SIZE"
        reasons.extend(capacity.get("reasons") or [])

    adjusted_size = round(max(adjusted_size, 0.0), 8)
    recommendation = _execution_recommendation(
        state=state,
        regime=regime,
        venue_health=venue_health,
        selected_venue=selected_venue,
        snapshots=snapshots,
        capacity=capacity,
    )
    return {
        "state": state,
        "selected_venue": selected_venue,
        "symbol": symbol_code,
        "side": side_code,
        "requested_size": round(requested_size, 8),
        "adjusted_size": adjusted_size,
        "requested_notional": round(requested_notional, 8),
        "adjusted_notional": round(adjusted_size * requested_price, 8),
        "recommended_order_type": recommended_order_type,
        "reasons": sorted(set(reasons)),
        "slippage_prediction": {
            "spread_cost_bps": round(spread_cost_bps, 6),
            "depth_impact_bps": round(depth_impact_bps, 6),
            "latency_penalty_bps": round(latency_penalty_bps, 6),
            "retry_cost_bps": round(retry_cost_bps, 6),
            "expected_slippage_bps": round(spread_cost_bps + depth_impact_bps + latency_penalty_bps + retry_cost_bps, 6),
        },
        "slippage_decomposition": {
            "spread_bps": round(spread_cost_bps, 6),
            "impact_bps": round(depth_impact_bps, 6),
            "timing_bps": round(latency_penalty_bps, 6),
            "retry_cost_bps": round(retry_cost_bps, 6),
        },
        "market_regime": regime,
        "venue_health": venue_health,
        "execution_recommendation": recommendation,
        "market_snapshot": {
            "data_state": snapshot.get("data_state"),
            "venue_readiness": snapshot.get("venue_readiness"),
            "best_bid": snapshot.get("best_bid"),
            "best_ask": snapshot.get("best_ask"),
            "mid_price": snapshot.get("mid_price"),
            "spread_bps": snapshot.get("spread_bps"),
            "quote_age_ms": quote_age_ms,
            "visible_depth_notional": round(visible_depth_notional, 8),
            "fast_market": bool(snapshot.get("fast_market")),
        },
        "capacity": capacity,
        "venue_snapshots": {
            venue: {
                "data_state": row.get("data_state"),
                "venue_readiness": row.get("venue_readiness"),
                "spread_bps": row.get("spread_bps"),
                "quote_age_ms": row.get("quote_age_ms"),
                "reason": row.get("reason"),
                "venue_health": _venue_health(row, _buffer_rows(cache, venue, symbol_code)),
            }
            for venue, row in snapshots.items()
        },
        "generated_at": _utc_iso(),
    }
