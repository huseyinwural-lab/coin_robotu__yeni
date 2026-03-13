import json

from sqlalchemy.orm import Session

from db import redis_client
from models import AdminControl
from services.pipeline.position_sizing_engine import compute_position_sizing


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _cached_json(key: str) -> dict:
    raw = redis_client.get(key)
    if not raw:
        return {}
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw) if isinstance(raw, str) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _entry_price(symbol: str, payload: dict) -> float:
    explicit_price = payload.get("price")
    if explicit_price is not None:
        return max(_safe_float(explicit_price, 0.0), 0.0)

    ticker = _cached_json(f"market:ticker:{symbol}")
    return max(_safe_float(ticker.get("last_price") or ticker.get("mid_price"), 100.0), 0.0001)


def _direction(side: str) -> str:
    return "short" if str(side or "buy").lower() in {"sell", "short"} else "long"


def _resolve_stop_price(payload: dict, entry_price: float, direction: str) -> float | None:
    if payload.get("stop_price") is not None:
        return _safe_float(payload.get("stop_price"), 0.0)

    stop_mode = str(payload.get("stop_loss_mode") or "none").lower()
    stop_value = _safe_float(payload.get("stop_loss_value"), 0.0)
    if stop_mode == "price" and stop_value > 0:
        return stop_value
    if stop_mode == "percent" and stop_value > 0:
        multiplier = (1 - stop_value / 100) if direction == "long" else (1 + stop_value / 100)
        return max(entry_price * multiplier, 0.0)
    return None


def _resolve_take_profit_price(payload: dict, entry_price: float, direction: str) -> float | None:
    if payload.get("take_profit_price") is not None:
        return _safe_float(payload.get("take_profit_price"), 0.0)

    take_profit_mode = str(payload.get("take_profit_mode") or "none").lower()
    take_profit_value = _safe_float(payload.get("take_profit_value"), 0.0)
    if take_profit_mode == "price" and take_profit_value > 0:
        return take_profit_value
    if take_profit_mode == "percent" and take_profit_value > 0:
        multiplier = (1 + take_profit_value / 100) if direction == "long" else (1 - take_profit_value / 100)
        return max(entry_price * multiplier, 0.0)
    return None


def _estimated_notional(payload: dict, account_equity: float) -> float:
    mode = str(payload.get("position_size_mode") or "fixed_notional").lower()
    value = _safe_float(payload.get("position_size_value"), 0.0)
    if mode == "risk_percent":
        return max(account_equity * (value / 100), 0.0)
    return max(value, 0.0)


def _distance_pct(entry: float, target: float | None) -> float | None:
    if target is None or entry <= 0:
        return None
    return round(abs((target - entry) / entry) * 100, 4)


def build_execution_preview_metrics(db: Session, user_id: str, payload: dict, validation: dict) -> dict:
    symbol = str((payload.get("symbol") or "BTCUSDT")).upper()
    direction = _direction(str(payload.get("side") or "buy"))

    entry_price = _entry_price(symbol, payload)
    sizing = compute_position_sizing(db, user_id, entry_price)
    account_equity = _safe_float(sizing.get("equity"), 0.0)

    stop_price = _resolve_stop_price(payload, entry_price, direction)
    take_profit_price = _resolve_take_profit_price(payload, entry_price, direction)
    stop_distance_pct = _distance_pct(entry_price, stop_price)
    take_profit_distance_pct = _distance_pct(entry_price, take_profit_price)

    rr_ratio = None
    if stop_distance_pct and stop_distance_pct > 0 and take_profit_distance_pct is not None:
        rr_ratio = round(take_profit_distance_pct / stop_distance_pct, 4)

    notional = _estimated_notional(payload, account_equity)
    estimated_quantity = round(notional / max(entry_price, 0.0001), 8)
    estimated_risk_usdt = round(notional * ((stop_distance_pct or 0.0) / 100), 4)

    spread_payload = _cached_json(f"market:spread:{symbol}")
    ticker_payload = _cached_json(f"market:ticker:{symbol}")
    spread_bps = _safe_float(spread_payload.get("spread_bps"), 0.0)
    quote_volume = _safe_float(ticker_payload.get("quote_volume"), 0.0)

    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    min_volume = _safe_float(control.minimum_volume_usd if control else 1_000_000, 1_000_000)
    max_spread = _safe_float(control.max_spread_bps if control else 40, 40)

    volume_ok = quote_volume >= min_volume
    spread_ok = spread_bps <= max_spread
    liquidity_ok = volume_ok and spread_ok

    return {
        "entry_price": round(entry_price, 8),
        "stop_price": round(stop_price, 8) if stop_price is not None else None,
        "take_profit_price": round(take_profit_price, 8) if take_profit_price is not None else None,
        "stop_distance_pct": stop_distance_pct,
        "take_profit_distance_pct": take_profit_distance_pct,
        "risk_reward_ratio": rr_ratio,
        "estimated_notional": round(notional, 4),
        "estimated_quantity": estimated_quantity,
        "estimated_risk_usdt": estimated_risk_usdt,
        "account_equity": round(account_equity, 4),
        "liquidity_guard": {
            "ok": liquidity_ok,
            "volume_ok": volume_ok,
            "spread_ok": spread_ok,
            "quote_volume": round(quote_volume, 4),
            "required_min_volume": round(min_volume, 4),
            "spread_bps": round(spread_bps, 4),
            "max_spread_bps": round(max_spread, 4),
        },
        "validation_status": validation.get("validation_status"),
    }
