from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_exposure_policy(
    *,
    wallet_balance: float | None,
    total_exposure: float,
    portfolio_exposure: dict,
    risk_config: dict,
) -> dict:
    max_total_pct = _safe_float(risk_config.get("max_total_exposure_pct"))
    max_symbol_pct = _safe_float(risk_config.get("max_symbol_exposure_pct"), max_total_pct)
    max_strategy_pct = _safe_float(risk_config.get("max_strategy_exposure_pct"), max_total_pct)

    wallet = _safe_float(wallet_balance)
    by_symbol = dict((portfolio_exposure or {}).get("by_symbol") or {})
    by_strategy = dict((portfolio_exposure or {}).get("by_strategy") or {})
    global_notional = max(float(total_exposure or 0.0), float(_safe_float((portfolio_exposure or {}).get("global_notional"), 0.0) or 0.0))

    global_pct = None
    if wallet is not None and wallet > 0:
        global_pct = (global_notional / wallet) * 100

    symbol_breakers: list[dict] = []
    strategy_breakers: list[dict] = []

    if wallet is not None and wallet > 0 and max_symbol_pct is not None:
        for symbol, notional in by_symbol.items():
            pct = (float(notional or 0.0) / wallet) * 100
            if pct > max_symbol_pct:
                symbol_breakers.append({"symbol": str(symbol), "exposure_pct": round(pct, 6), "threshold_pct": max_symbol_pct})

    if wallet is not None and wallet > 0 and max_strategy_pct is not None:
        for strategy_id, notional in by_strategy.items():
            pct = (float(notional or 0.0) / wallet) * 100
            if pct > max_strategy_pct:
                strategy_breakers.append({"strategy_id": str(strategy_id), "exposure_pct": round(pct, 6), "threshold_pct": max_strategy_pct})

    if wallet is None or wallet <= 0:
        global_state = "FAIL"
        global_reason = "EXPOSURE_NO_EQUITY"
    elif max_total_pct is None or global_pct is None:
        global_state = "UNKNOWN"
        global_reason = "EXPOSURE_LIMIT_MISSING"
    elif global_pct > max_total_pct:
        global_state = "FAIL"
        global_reason = "EXPOSURE_LIMIT_BREACH"
    elif global_pct > max_total_pct * 0.8:
        global_state = "WARN"
        global_reason = "EXPOSURE_LIMIT_NEAR"
    else:
        global_state = "PASS"
        global_reason = "PASS"

    if symbol_breakers:
        if global_state == "PASS":
            global_state = "FAIL"
        if global_reason == "PASS":
            global_reason = "EXPOSURE_SYMBOL_BREACH"

    if strategy_breakers:
        if global_state == "PASS":
            global_state = "FAIL"
        if global_reason == "PASS":
            global_reason = "EXPOSURE_STRATEGY_BREACH"

    return {
        "state": global_state,
        "reason_code": global_reason,
        "global_exposure_pct": round(global_pct, 6) if global_pct is not None else None,
        "global_threshold_pct": max_total_pct,
        "symbol_threshold_pct": max_symbol_pct,
        "strategy_threshold_pct": max_strategy_pct,
        "symbol_breakers": symbol_breakers,
        "strategy_breakers": strategy_breakers,
        "global_notional": round(global_notional, 6),
    }
