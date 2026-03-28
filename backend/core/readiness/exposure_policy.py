from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


EXPOSURE_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "exposure_policy.json"


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
    policy_overrides: dict | None = None,
) -> dict:
    policy = load_exposure_policy(risk_config=risk_config, overrides=policy_overrides)
    global_policy = policy.get("global") or {}
    symbol_policy = policy.get("symbol") or {}
    strategy_policy = policy.get("strategy") or {}

    max_total_pct = _safe_float(global_policy.get("max_total_exposure_pct"))
    max_symbol_pct = _safe_float(symbol_policy.get("max_symbol_exposure_pct"), max_total_pct)
    max_strategy_pct = _safe_float(strategy_policy.get("max_strategy_exposure_pct"), max_total_pct)

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
        "policy": policy,
    }


def load_exposure_policy(*, risk_config: dict | None = None, overrides: dict | None = None) -> dict:
    payload = {
        "global": {"max_total_exposure_pct": _safe_float((risk_config or {}).get("max_total_exposure_pct"), 300), "warn_ratio": 0.8},
        "symbol": {"max_symbol_exposure_pct": _safe_float((risk_config or {}).get("max_symbol_exposure_pct"), _safe_float((risk_config or {}).get("max_total_exposure_pct"), 300))},
        "strategy": {"max_strategy_exposure_pct": _safe_float((risk_config or {}).get("max_strategy_exposure_pct"), _safe_float((risk_config or {}).get("max_total_exposure_pct"), 300))},
        "capital_guard": {
            "max_drawdown_pct": _safe_float((risk_config or {}).get("max_drawdown_pct") or (risk_config or {}).get("max_daily_loss_pct"), 20),
            "grace_wallet_min_usd": 10,
            "unrealized_weight": 1.0,
            "realized_weight": 1.0,
        },
    }

    file_payload = {}
    try:
        if EXPOSURE_POLICY_PATH.exists():
            file_payload = json.loads(EXPOSURE_POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        file_payload = {}

    env_payload = {}
    raw_env = os.environ.get("READINESS_EXPOSURE_POLICY_JSON")
    if raw_env:
        try:
            env_payload = json.loads(raw_env)
        except Exception:
            env_payload = {}

    for candidate in [file_payload, env_payload, overrides or {}]:
        if not isinstance(candidate, dict):
            continue
        for section in ["global", "symbol", "strategy", "capital_guard"]:
            existing = payload.get(section) or {}
            incoming = candidate.get(section) or {}
            if isinstance(incoming, dict):
                payload[section] = {**existing, **incoming}

    risk_config = risk_config or {}
    if risk_config.get("max_total_exposure_pct") is not None:
        payload.setdefault("global", {})["max_total_exposure_pct"] = _safe_float(risk_config.get("max_total_exposure_pct"), payload.get("global", {}).get("max_total_exposure_pct"))
    if risk_config.get("max_symbol_exposure_pct") is not None:
        payload.setdefault("symbol", {})["max_symbol_exposure_pct"] = _safe_float(risk_config.get("max_symbol_exposure_pct"), payload.get("symbol", {}).get("max_symbol_exposure_pct"))
    if risk_config.get("max_strategy_exposure_pct") is not None:
        payload.setdefault("strategy", {})["max_strategy_exposure_pct"] = _safe_float(risk_config.get("max_strategy_exposure_pct"), payload.get("strategy", {}).get("max_strategy_exposure_pct"))
    if risk_config.get("max_drawdown_pct") is not None or risk_config.get("max_daily_loss_pct") is not None:
        payload.setdefault("capital_guard", {})["max_drawdown_pct"] = _safe_float(
            risk_config.get("max_drawdown_pct") or risk_config.get("max_daily_loss_pct"),
            payload.get("capital_guard", {}).get("max_drawdown_pct"),
        )
    return payload
