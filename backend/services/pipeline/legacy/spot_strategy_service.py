import json
import random
from pathlib import Path
from statistics import fmean
from datetime import date, datetime, timezone

import requests
from sqlalchemy.orm import Session

from models import PaperPosition, PositionLedgerEvent
from services.pipeline.cache_store import get_json, set_json, utc_now_iso

BINANCE_TICKER_24H_URL = "https://api.binance.com/api/v3/ticker/24hr"
BINANCE_BOOK_TICKER_URL = "https://api.binance.com/api/v3/ticker/bookTicker"
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

UNIVERSE_MIN_VOLUME_USDT = 20_000_000
UNIVERSE_MAX_SPREAD_PCT = 0.3
UNIVERSE_MIN_SYMBOLS = 30
UNIVERSE_MAX_SYMBOLS = 50
MIN_15M_CANDLES = 500

ARTIFACTS_DIR = Path("/app/backend/artifacts")
UNIVERSE_FILE_PATH = ARTIFACTS_DIR / "spot_universe.json"
DAILY_REPORT_FILE_PATH = ARTIFACTS_DIR / "daily_strategy_report.json"


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _ema(series: list[float], period: int) -> float:
    if not series:
        return 0.0
    alpha = 2 / (period + 1)
    value = series[0]
    for price in series[1:]:
        value = (price * alpha) + (value * (1 - alpha))
    return float(value)


def _rsi(series: list[float], period: int = 14) -> float:
    if len(series) < period + 1:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for idx in range(-period, 0):
        delta = series[idx] - series[idx - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_gain = fmean(gains) if gains else 0.0
    avg_loss = fmean(losses) if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr(candles: list[dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    true_ranges: list[float] = []
    for idx in range(len(candles) - period, len(candles)):
        high = _safe_float(candles[idx].get("high"))
        low = _safe_float(candles[idx].get("low"))
        prev_close = _safe_float(candles[idx - 1].get("close"))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(max(tr, 0.0))
    return fmean(true_ranges) if true_ranges else 0.0


def _vwap(candles: list[dict], period: int = 50) -> float:
    subset = candles[-period:] if len(candles) >= period else candles
    if not subset:
        return 0.0
    cumulative_pv = 0.0
    cumulative_volume = 0.0
    for candle in subset:
        high = _safe_float(candle.get("high"))
        low = _safe_float(candle.get("low"))
        close = _safe_float(candle.get("close"))
        volume = _safe_float(candle.get("volume"))
        typical_price = (high + low + close) / 3
        cumulative_pv += typical_price * volume
        cumulative_volume += volume
    return cumulative_pv / cumulative_volume if cumulative_volume else 0.0


def calculate_indicator_snapshot(candles: list[dict]) -> dict:
    closes = [_safe_float(candle.get("close")) for candle in candles]
    volumes = [_safe_float(candle.get("volume")) for candle in candles]
    close = closes[-1] if closes else 0.0
    ema50 = _ema(closes[-120:], 50) if len(closes) >= 50 else 0.0
    ema200 = _ema(closes[-240:], 200) if len(closes) >= 200 else 0.0
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(candles, 14)
    vwap_value = _vwap(candles, 50)
    avg_volume_20 = fmean(volumes[-20:]) if len(volumes) >= 20 else (fmean(volumes) if volumes else 0.0)
    current_volume = volumes[-1] if volumes else 0.0
    relative_volume = current_volume / avg_volume_20 if avg_volume_20 else 0.0
    atr_pct = (atr14 / close) if close else 0.0
    return {
        "close": close,
        "ema50": ema50,
        "ema200": ema200,
        "rsi14": rsi14,
        "atr14": atr14,
        "vwap": vwap_value,
        "atr_pct": atr_pct,
        "current_volume": current_volume,
        "avg_volume_20": avg_volume_20,
        "relative_volume": relative_volume,
        "updated_at": utc_now_iso(),
    }


def _trend_strength(candles: list[dict], indicators: dict) -> str:
    ema50 = indicators.get("ema50", 0.0)
    ema200 = indicators.get("ema200", 0.0)
    if ema50 <= 0 or ema200 <= 0:
        return "weak"
    spread_ratio = ((ema50 - ema200) / ema200) * 100
    closes = [_safe_float(candle.get("close")) for candle in candles[-5:]]
    closes_above_ema = sum(1 for close in closes if close >= ema50)

    if spread_ratio > 1.2 and closes_above_ema >= 4:
        return "strong"
    if spread_ratio > 0.5 and closes_above_ema >= 3:
        return "medium"
    return "weak"


def _pullback_quality(candles: list[dict], indicators: dict) -> str:
    if len(candles) < 3:
        return "low"
    ema50 = indicators.get("ema50", 0.0)
    if ema50 <= 0:
        return "low"

    last = candles[-1]
    prev = candles[-2]
    prev2 = candles[-3]
    current_close = _safe_float(last.get("close"))
    current_open = _safe_float(last.get("open"))
    prev_open = _safe_float(prev.get("open"))
    prev_close = _safe_float(prev.get("close"))
    prev2_open = _safe_float(prev2.get("open"))
    prev2_close = _safe_float(prev2.get("close"))

    bearish_last_two = (prev_close < prev_open) and (prev2_close < prev2_open)
    recovery_bullish = current_close > current_open
    pullback_depth_pct = ((ema50 - current_close) / ema50) * 100

    if bearish_last_two and not recovery_bullish:
        return "low"
    if pullback_depth_pct <= 1.8 and recovery_bullish:
        return "strong"
    if pullback_depth_pct <= 2.4:
        return "acceptable"
    return "low"


def _btc_regime(btc_candles: list[dict]) -> str:
    if len(btc_candles) < 60:
        return "neutral"
    btc_indicators = calculate_indicator_snapshot(btc_candles)
    btc_close = btc_indicators["close"]
    btc_ema50 = btc_indicators["ema50"]
    btc_rsi = btc_indicators["rsi14"]

    recent = btc_candles[-4:]
    breakdown = False
    for candle in recent:
        open_price = _safe_float(candle.get("open"))
        close_price = _safe_float(candle.get("close"))
        move_pct = ((close_price - open_price) / open_price) * 100 if open_price else 0.0
        if move_pct <= -1.5:
            breakdown = True
            break

    if btc_close > btc_ema50 and btc_rsi >= 48 and not breakdown:
        return "supportive"
    if breakdown:
        return "hostile"
    return "neutral"


def evaluate_spot_pullback_candidate(symbol: str, candles: list[dict], btc_candles: list[dict]) -> dict:
    if len(candles) < 220:
        return {
            "signal": "none",
            "direction": "none",
            "reason_codes": ["insufficient_data"],
            "signal_strength": 0.0,
            "signal_score": 0.0,
            "metadata": {},
        }

    indicators = calculate_indicator_snapshot(candles)
    close = indicators["close"]
    trend = "bullish" if indicators["ema50"] > indicators["ema200"] else "bearish"
    trend_strength = _trend_strength(candles, indicators)
    btc_regime = _btc_regime(btc_candles)
    pullback_quality = _pullback_quality(candles, indicators)
    relative_volume = indicators["relative_volume"]
    volume_quality = "strong" if relative_volume >= 1.8 else "acceptable" if relative_volume >= 1.2 else "low"

    reasons: list[str] = []
    if trend != "bullish":
        reasons.append("trend_not_bullish")
    if close > indicators["ema50"]:
        reasons.append("price_above_ema50")
    if indicators["rsi14"] >= 45:
        reasons.append("rsi_not_ready")
    if relative_volume < 1.05:
        reasons.append("volume_spike_missing")
    if indicators["atr_pct"] <= 0.008:
        reasons.append("volatility_too_low")

    trend_score_map = {"weak": 20, "medium": 70, "strong": 95}
    pullback_score_map = {"low": 25, "acceptable": 65, "strong": 92}
    btc_score_map = {"hostile": 0, "neutral": 55, "supportive": 90}
    vol_score = min(max(indicators["atr_pct"] * 1000, 10), 95)
    relative_volume_score = min(max(relative_volume * 45, 10), 95)

    signal_score = (
        trend_score_map[trend_strength] * 0.30
        + relative_volume_score * 0.25
        + pullback_score_map[pullback_quality] * 0.20
        + vol_score * 0.15
        + btc_score_map[btc_regime] * 0.10
    )

    executable = len(reasons) == 0
    signal = "long" if executable else "none"
    direction = "long" if executable else "none"
    signal_strength = round(signal_score / 100, 4)

    return {
        "signal": signal,
        "direction": direction,
        "reason_codes": reasons or ["spot_pullback_ready"],
        "signal_strength": signal_strength,
        "signal_score": round(signal_score, 2),
        "metadata": {
            "symbol": symbol,
            "trend": trend,
            "trend_strength": trend_strength,
            "btc_regime": btc_regime,
            "pullback_quality": pullback_quality,
            "relative_volume": round(relative_volume, 4),
            "volume_quality": volume_quality,
            "atr_pct": round(indicators["atr_pct"], 6),
            "ema50": round(indicators["ema50"], 6),
            "ema200": round(indicators["ema200"], 6),
            "rsi14": round(indicators["rsi14"], 4),
            "vwap": round(indicators["vwap"], 6),
        },
        "entry": round(close, 6),
        "stop": round(close * 0.99, 6),
        "take_profit": round(close * 1.02, 6),
        "indicators": indicators,
    }


def get_spot_tradable_universe(cache) -> dict:
    payload = get_json(cache, "universe:spot:tradable")
    return payload or {"symbols": [], "rows": [], "generated_at": utc_now_iso(), "source": "empty"}


def refresh_spot_tradable_universe(cache) -> dict:
    try:
        tickers = requests.get(BINANCE_TICKER_24H_URL, timeout=12).json()
        books = requests.get(BINANCE_BOOK_TICKER_URL, timeout=12).json()
        book_map = {item.get("symbol", "").upper(): item for item in books if item.get("symbol")}
    except Exception:
        tickers = []
        book_map = {}

    rows: list[dict] = []
    for ticker in tickers:
        symbol = str(ticker.get("symbol", "")).upper()
        if not symbol.endswith("USDT"):
            continue
        quote_volume = _safe_float(ticker.get("quoteVolume"))
        book = book_map.get(symbol, {})
        bid = _safe_float(book.get("bidPrice"))
        ask = _safe_float(book.get("askPrice"))
        spread_pct = ((ask - bid) / ask * 100) if ask else 99.0
        is_tradable = quote_volume > UNIVERSE_MIN_VOLUME_USDT and spread_pct < UNIVERSE_MAX_SPREAD_PCT
        rows.append(
            {
                "symbol": symbol,
                "24h_volume": round(quote_volume, 2),
                "spread": round(spread_pct, 5),
                "status": "active" if is_tradable else "filtered_out",
            }
        )

    tradable = [row for row in rows if row["status"] == "active"]
    tradable.sort(key=lambda item: item["24h_volume"], reverse=True)

    if len(tradable) < UNIVERSE_MIN_SYMBOLS:
        fallbacks = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "TRXUSDT",
            "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT", "UNIUSDT", "MATICUSDT", "ATOMUSDT",
            "AAVEUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "INJUSDT", "ETCUSDT",
            "FILUSDT", "RUNEUSDT", "ICPUSDT", "SEIUSDT", "XLMUSDT", "HBARUSDT",
        ]
        present = {item["symbol"] for item in tradable}
        for fallback_symbol in fallbacks:
            if fallback_symbol in present:
                continue
            tradable.append(
                {
                    "symbol": fallback_symbol,
                    "24h_volume": 0.0,
                    "spread": 0.0,
                    "status": "fallback",
                }
            )
            if len(tradable) >= UNIVERSE_MIN_SYMBOLS:
                break

    universe_rows = tradable[:UNIVERSE_MAX_SYMBOLS]
    payload = {
        "generated_at": utc_now_iso(),
        "filters": {
            "min_24h_volume_usdt": UNIVERSE_MIN_VOLUME_USDT,
            "max_spread_pct": UNIVERSE_MAX_SPREAD_PCT,
            "quote_asset": "USDT",
        },
        "symbols": [item["symbol"] for item in universe_rows],
        "rows": universe_rows,
        "count": len(universe_rows),
        "source": "binance_spot",
    }
    set_json(cache, "universe:spot:tradable", payload)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    UNIVERSE_FILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _fetch_15m_klines(symbol: str, limit: int = MIN_15M_CANDLES) -> list[dict]:
    try:
        response = requests.get(
            BINANCE_KLINES_URL,
            params={"symbol": symbol.upper(), "interval": "15m", "limit": limit},
            timeout=12,
        )
        response.raise_for_status()
        rows = response.json()
    except Exception:
        return []

    candles: list[dict] = []
    for item in rows:
        candles.append(
            {
                "open": _safe_float(item[1]),
                "high": _safe_float(item[2]),
                "low": _safe_float(item[3]),
                "close": _safe_float(item[4]),
                "volume": _safe_float(item[5]),
                "quote_volume": _safe_float(item[7]),
                "start": int(item[0]),
                "end": int(item[6]),
                "is_closed": True,
            }
        )
    return candles


def _synthetic_15m_klines(symbol: str, limit: int = MIN_15M_CANDLES, start_price: float = 100.0) -> list[dict]:
    rng = random.Random(symbol)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    step_ms = 15 * 60 * 1000
    candles: list[dict] = []
    price = max(start_price, 0.0001)
    start_time = now_ms - (limit * step_ms)
    for idx in range(limit):
        drift = rng.uniform(-0.008, 0.01)
        open_price = max(price, 0.0001)
        close_price = max(open_price * (1 + drift), 0.0001)
        high = max(open_price, close_price) * (1 + rng.uniform(0.0005, 0.005))
        low = min(open_price, close_price) * (1 - rng.uniform(0.0005, 0.005))
        volume = abs(rng.gauss(8000, 2500))
        candles.append(
            {
                "open": round(open_price, 6),
                "high": round(high, 6),
                "low": round(max(low, 0.0001), 6),
                "close": round(close_price, 6),
                "volume": round(volume, 6),
                "quote_volume": round(volume * close_price, 6),
                "start": start_time + (idx * step_ms),
                "end": start_time + ((idx + 1) * step_ms) - 1,
                "is_closed": True,
            }
        )
        price = close_price
    return candles


def bootstrap_market_data_store(cache, symbols: list[str], min_candles: int = MIN_15M_CANDLES) -> dict:
    symbols = sorted({symbol.upper() for symbol in symbols if symbol})
    seeded = 0
    seeded_synthetic = 0
    skipped = 0
    failed: list[str] = []
    for symbol in symbols:
        key = f"market_data_store:{symbol}:15m"
        existing = get_json(cache, key) or []
        if len(existing) >= min_candles:
            skipped += 1
            continue

        candles = _fetch_15m_klines(symbol, min_candles)
        if not candles:
            ticker_payload = get_json(cache, f"market:ticker:{symbol}") or {}
            start_price = _safe_float(ticker_payload.get("last_price"), 100.0)
            candles = _synthetic_15m_klines(symbol, min_candles, start_price=start_price)
            seeded_synthetic += 1

        set_json(cache, key, candles)
        set_json(cache, f"market:candles:{symbol}:15m", candles)
        seeded += 1
    payload = {
        "seeded": seeded,
        "seeded_synthetic": seeded_synthetic,
        "skipped": skipped,
        "failed": failed,
        "symbol_count": len(symbols),
        "min_candles": min_candles,
        "updated_at": utc_now_iso(),
    }
    set_json(cache, "market_data_store:bootstrap:last", payload)
    return payload


def update_indicator_cache(cache, symbol: str, candles: list[dict]) -> dict:
    indicators = calculate_indicator_snapshot(candles)
    set_json(cache, f"indicators:spot:{symbol.upper()}:15m", indicators)
    return indicators


def scan_spot_universe_for_signals(cache, max_symbols: int = 50) -> dict:
    universe = get_spot_tradable_universe(cache)
    symbols = [symbol.upper() for symbol in universe.get("symbols", [])][:max_symbols]
    btc_candles = get_json(cache, "market_data_store:BTCUSDT:15m") or get_json(cache, "market:candles:BTCUSDT:15m") or []

    rows: list[dict] = []
    for symbol in symbols:
        candles = get_json(cache, f"market_data_store:{symbol}:15m") or get_json(cache, f"market:candles:{symbol}:15m") or []
        if len(candles) < 220:
            rows.append(
                {
                    "symbol": symbol,
                    "signal": "none",
                    "reason_codes": ["insufficient_data"],
                    "signal_score": 0.0,
                    "trend_strength": "weak",
                    "btc_regime": "neutral",
                }
            )
            continue

        candidate = evaluate_spot_pullback_candidate(symbol, candles[-500:], btc_candles[-500:])
        metadata = candidate.get("metadata", {})
        rows.append(
            {
                "symbol": symbol,
                "signal": candidate.get("signal"),
                "reason_codes": candidate.get("reason_codes", []),
                "signal_score": candidate.get("signal_score", 0.0),
                "signal_strength": candidate.get("signal_strength", 0.0),
                "trend_strength": metadata.get("trend_strength", "weak"),
                "btc_regime": metadata.get("btc_regime", "neutral"),
                "relative_volume": metadata.get("relative_volume", 0.0),
                "pullback_quality": metadata.get("pullback_quality", "low"),
                "entry": candidate.get("entry", 0.0),
                "stop": candidate.get("stop", 0.0),
                "take_profit": candidate.get("take_profit", 0.0),
            }
        )

    rows.sort(key=lambda item: item.get("signal_score", 0.0), reverse=True)
    executable = [item for item in rows if item.get("signal") == "long"]
    payload = {
        "generated_at": utc_now_iso(),
        "symbol_count": len(rows),
        "executable_count": len(executable),
        "top_executable": executable[:10],
        "top_ranked": rows[:20],
    }
    set_json(cache, "spot_strategy:last_scan", payload)
    return payload


def _extract_spot_strategy_position_ids(db: Session) -> set[str]:
    events = db.query(PositionLedgerEvent).filter(PositionLedgerEvent.event_type == "trade_open").all()
    result: set[str] = set()
    for event in events:
        payload = event.payload or {}
        if payload.get("strategy_id") in {
            "spot_pullback",
            "spot_pullback_v1",
            "spot_range_reversion",
            "spot_range_reversion_v1",
        }:
            result.add(event.position_id)
    return result


def generate_daily_strategy_report(db: Session, cache, report_day: date | None = None) -> dict:
    target_day = report_day or datetime.now(timezone.utc).date()
    strategy_position_ids = _extract_spot_strategy_position_ids(db)
    positions: list[PaperPosition] = []
    if strategy_position_ids:
        positions = db.query(PaperPosition).filter(PaperPosition.id.in_(list(strategy_position_ids))).all()

    closed_today = [position for position in positions if position.closed_at and position.closed_at.date() == target_day]
    returns: list[float] = []
    positive = 0.0
    negative = 0.0
    winners = 0

    for position in closed_today:
        notional = max(position.entry_price * position.quantity, 0.0001)
        trade_return = position.realized_pnl / notional
        returns.append(trade_return)
        if trade_return >= 0:
            winners += 1
            positive += trade_return
        else:
            negative += trade_return

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for item in returns:
        cumulative += item
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)

    win_rate = (winners / len(returns) * 100) if returns else 0.0
    profit_factor = (positive / abs(negative)) if negative < 0 else (positive if positive > 0 else 0.0)
    avg_trade_return = fmean(returns) if returns else 0.0
    daily_trades = len(closed_today)

    multiplier_contract = get_json(cache, "spot_strategy:multiplier_contract") or {}
    last_scan = get_json(cache, "spot_strategy:last_scan") or {}

    metrics = {
        "signals_total": int(cache.get("spot_strategy:signals_total:day") or 0),
        "signals_after_hard_gate": int(cache.get("spot_strategy:signals_after_hard_gate:day") or 0),
        "signals_above_threshold": int(cache.get("spot_strategy:signals_above_threshold:day") or 0),
        "signals_selected": int(cache.get("spot_strategy:signals_selected:day") or 0),
        "signals_selected_for_execution": int(cache.get("spot_strategy:signals_selected:day") or 0),
        "signals_rejected_trend_strength": int(cache.get("spot_strategy:rejected:trend_strength_weak") or 0),
        "signals_rejected_market_bias": int(cache.get("spot_strategy:rejected:market_bias_hostile") or 0),
        "signals_rejected_market_stress": int(cache.get("spot_strategy:rejected:market_stress_guard") or 0),
        "signals_rejected_btc_regime": int(cache.get("spot_strategy:rejected:market_bias_hostile") or 0),
        "signals_rejected_freeze_guard": int(cache.get("spot_strategy:rejected:market_stress_guard") or 0),
        "signals_rejected_threshold": int(cache.get("spot_strategy:rejected:threshold") or 0),
        "executed_signals": int(cache.get("spot_strategy:executed_signals:day") or 0),
        "avg_signal_score": _safe_float(cache.get("spot_strategy:avg_signal_score:day"), 0.0),
    }

    report = {
        "date": target_day.isoformat(),
        "strategy": "spot_multi_regime_v1",
        "market_regime": last_scan.get("market_regime", "RANGING"),
        "multiplier_version": multiplier_contract.get("multiplier_version", "v1"),
        "multiplier_set": multiplier_contract.get("multiplier_set", {}),
        "base_score": round(_safe_float((last_scan.get("selected") or [{}])[0].get("base_score"), 0.0), 4) if last_scan.get("selected") else 0.0,
        "adjusted_score": round(_safe_float((last_scan.get("selected") or [{}])[0].get("adjusted_score"), 0.0), 4) if last_scan.get("selected") else 0.0,
        "score_delta": round(_safe_float((last_scan.get("selected") or [{}])[0].get("score_delta"), 0.0), 4) if last_scan.get("selected") else 0.0,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 6),
        "avg_trade_return": round(avg_trade_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "daily_trades": daily_trades,
        "positions_closed": len(closed_today),
        "metrics": metrics,
        "generated_at": utc_now_iso(),
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_REPORT_FILE_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    set_json(cache, "spot_strategy:daily_report", report)
    return report
