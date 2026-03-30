import json

from sqlalchemy.orm import Session

from core.policy.quote_policy import InvalidSymbol, extract_quote, normalize_symbol
from db import redis_client
from models import AdminControl, Position
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
    try:
        symbol = normalize_symbol(
            payload.get("symbol"),
            missing_error_code="symbol_required_for_execution_intent",
            invalid_error_code="invalid_quote_asset",
        )
    except InvalidSymbol as exc:
        raise ValueError(str(exc)) from exc
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
    applied_leverage = int(validation.get("applied_leverage") or payload.get("leverage") or 1)
    required_margin = round(notional / max(applied_leverage, 1), 4)
    estimated_fee = round(notional * 0.001, 4)

    spread_payload = _cached_json(f"market:spread:{symbol}")
    ticker_payload = _cached_json(f"market:ticker:{symbol}")
    spread_bps = _safe_float(spread_payload.get("spread_bps"), 0.0)
    quote_volume = _safe_float(ticker_payload.get("quote_volume"), 0.0)
    slippage_estimate_bps = round(spread_bps + max((notional / max(quote_volume, 1.0)) * 10000, 0.0), 6)
    expected_fill_price = round(entry_price * (1 + slippage_estimate_bps / 10000), 8) if direction == "long" else round(entry_price * (1 - slippage_estimate_bps / 10000), 8)
    liquidation_buffer_pct = max(4.0, 100.0 / max(applied_leverage, 1))
    liquidation_price = round(entry_price * (1 - liquidation_buffer_pct / 100), 8) if direction == "long" else round(entry_price * (1 + liquidation_buffer_pct / 100), 8)
    open_exposure = (
        db.query(Position)
        .filter(Position.user_id == user_id, Position.status == "open")
        .all()
    )
    current_exposure = sum(abs(_safe_float(row.size) * _safe_float(row.current_price or row.entry_price)) for row in open_exposure)
    exposure_after = round(current_exposure + notional, 4)
    projected_pnl_upside = round((take_profit_price - expected_fill_price) * estimated_quantity, 4) if direction == "long" and take_profit_price else None
    projected_pnl_downside = round((expected_fill_price - stop_price) * estimated_quantity, 4) if direction == "long" and stop_price else None
    if direction == "short":
        projected_pnl_upside = round((expected_fill_price - take_profit_price) * estimated_quantity, 4) if take_profit_price else None
        projected_pnl_downside = round((stop_price - expected_fill_price) * estimated_quantity, 4) if stop_price else None

    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    min_volume = _safe_float(control.minimum_volume_usd if control else 1_000_000, 1_000_000)
    max_spread = _safe_float(control.max_spread_bps if control else 40, 40)

    volume_ok = quote_volume >= min_volume
    spread_ok = spread_bps <= max_spread
    liquidity_ok = volume_ok and spread_ok

    return {
        "symbol": symbol,
        "quote_asset": extract_quote(symbol),
        "entry_price": round(entry_price, 8),
        "stop_price": round(stop_price, 8) if stop_price is not None else None,
        "take_profit_price": round(take_profit_price, 8) if take_profit_price is not None else None,
        "stop_distance_pct": stop_distance_pct,
        "take_profit_distance_pct": take_profit_distance_pct,
        "risk_reward_ratio": rr_ratio,
        "estimated_notional": round(notional, 4),
        "estimated_quantity": estimated_quantity,
        "estimated_risk_usdt": estimated_risk_usdt,
        "estimated_fee": estimated_fee,
        "slippage_estimate_bps": slippage_estimate_bps,
        "expected_fill_price": expected_fill_price,
        "account_equity": round(account_equity, 4),
        "required_margin": required_margin,
        "liquidation_price": liquidation_price,
        "leverage_impact": {
            "requested_leverage": int(payload.get("leverage") or 1),
            "applied_leverage": applied_leverage,
            "margin_mode": payload.get("margin_mode") or "isolated",
        },
        "post_trade_exposure": {
            "current_exposure": round(current_exposure, 4),
            "projected_exposure": exposure_after,
            "delta": round(notional, 4),
        },
        "projected_pnl_impact": {
            "upside": projected_pnl_upside,
            "downside": projected_pnl_downside,
        },
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
