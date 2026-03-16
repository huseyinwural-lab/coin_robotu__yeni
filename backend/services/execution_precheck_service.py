import hashlib
import json
from pathlib import Path

from services.quote_asset_policy import extract_quote_asset, normalize_quote_symbol

POLICY_PATH = Path("/app/config/execution_policy_registry.json")
ALLOWED_EXECUTION_MODES = {"manual", "bot_assisted", "signal_follow"}


def load_execution_policy_registry() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def list_execution_presets() -> list[dict]:
    registry = load_execution_policy_registry()
    presets = registry.get("preset_definitions") or {}
    return [{"preset_code": preset_code, **preset} for preset_code, preset in presets.items()]


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _preview_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_symbol_numeric(config: dict, symbol: str, fallback: float) -> float:
    if not isinstance(config, dict):
        return fallback
    if symbol in config:
        return _safe_float(config.get(symbol), fallback)
    if "__default__" in config:
        return _safe_float(config.get("__default__"), fallback)
    return fallback


def validate_execution_payload(payload: dict) -> dict:
    registry = load_execution_policy_registry()
    market_policies = registry.get("market_type") or {}
    symbols_allowlist = set(registry.get("symbols_allowlist") or [])
    enforce_symbols_allowlist = bool(registry.get("enforce_symbols_allowlist", False))
    tp_sl_rules = registry.get("tp_sl_rules") or {}

    symbol = ""
    quote_asset = None
    symbol_error = None
    try:
        symbol = normalize_quote_symbol(
            payload.get("symbol"),
            field_name="symbol",
            missing_error_code="symbol_required_for_execution_intent",
            invalid_error_code="invalid_quote_asset",
        )
        quote_asset = extract_quote_asset(symbol)
    except ValueError as exc:
        symbol_error = str(exc)

    market_type = str(payload.get("market_type") or "spot").lower()
    side = str(payload.get("side") or "buy").lower()
    order_type = str(payload.get("order_type") or "market").lower()
    margin_mode = str(payload.get("margin_mode") or "").lower()
    execution_mode = str(payload.get("execution_mode") or "manual").lower()
    leverage = int(_safe_float(payload.get("leverage"), 1))
    position_size_mode = str(payload.get("position_size_mode") or "fixed_notional").lower()
    position_size_value = _safe_float(payload.get("position_size_value"), 0)

    take_profit_mode = str(payload.get("take_profit_mode") or "none").lower()
    stop_loss_mode = str(payload.get("stop_loss_mode") or "none").lower()
    take_profit_value = _safe_float(payload.get("take_profit_value"), 0)
    stop_loss_value = _safe_float(payload.get("stop_loss_value"), 0)

    reject_reason_codes: list[str] = []
    risk_flags: list[str] = []

    if symbol_error:
        reject_reason_codes.append(symbol_error)
    if quote_asset is None and not symbol_error:
        reject_reason_codes.append("invalid_quote_asset")

    requested_quote_asset = str(payload.get("quote_asset") or "").strip().upper()
    if requested_quote_asset and quote_asset and requested_quote_asset != quote_asset:
        reject_reason_codes.append("quote_asset_mismatch")

    market_policy = market_policies.get(market_type)
    if market_policy is None:
        reject_reason_codes.append("invalid_market_type")

    if enforce_symbols_allowlist and symbol not in symbols_allowlist:
        reject_reason_codes.append("symbol_not_allowed")

    if market_policy:
        allowed_order_types = set(market_policy.get("allowed_order_types") or [])
        if order_type not in allowed_order_types:
            reject_reason_codes.append("order_type_not_allowed")

        min_notional_map = market_policy.get("min_notional_by_symbol") or {}
        min_notional = _resolve_symbol_numeric(min_notional_map, symbol, 0.0)
        if position_size_mode == "risk_percent":
            notional = round(max(position_size_value, 0) * 100, 4)
        else:
            notional = round(max(position_size_value, 0), 4)
        if notional < min_notional:
            reject_reason_codes.append("min_notional_not_met")

        if market_type == "futures":
            allowed_margin_modes = set(market_policy.get("allowed_margin_modes") or [])
            if margin_mode not in allowed_margin_modes:
                reject_reason_codes.append("margin_mode_not_allowed")

            leverage_cap_map = market_policy.get("max_leverage_by_symbol") or {}
            leverage_cap = int(_resolve_symbol_numeric(leverage_cap_map, symbol, 1.0))
            if leverage > leverage_cap:
                reject_reason_codes.append("leverage_cap_exceeded")

            if stop_loss_mode == "none" and tp_sl_rules.get("futures_requires_sl_warning"):
                risk_flags.append("stop_loss_missing_warning")
        else:
            leverage = 1
            margin_mode = ""

    if execution_mode not in ALLOWED_EXECUTION_MODES:
        reject_reason_codes.append("execution_mode_not_allowed")

    max_tp_percent = _safe_float(tp_sl_rules.get("max_tp_percent"), 25)
    max_sl_percent = _safe_float(tp_sl_rules.get("max_sl_percent"), 10)
    min_rr_ratio = _safe_float(tp_sl_rules.get("min_rr_ratio"), 1)

    if take_profit_mode == "percent" and take_profit_value > max_tp_percent:
        reject_reason_codes.append("take_profit_percent_too_high")
    if stop_loss_mode == "percent" and stop_loss_value > max_sl_percent:
        reject_reason_codes.append("stop_loss_percent_too_high")
    if take_profit_mode == "percent" and stop_loss_mode == "percent" and stop_loss_value > 0:
        if (take_profit_value / stop_loss_value) < min_rr_ratio:
            reject_reason_codes.append("risk_reward_ratio_too_low")

    normalized_order_payload = {
        "symbol": symbol,
        "quote_asset": quote_asset,
        "market_type": market_type,
        "side": side,
        "order_type": order_type,
        "margin_mode": margin_mode,
        "leverage": leverage,
        "position_size_mode": position_size_mode,
        "position_size_value": position_size_value,
        "take_profit_mode": take_profit_mode,
        "take_profit_value": take_profit_value,
        "stop_loss_mode": stop_loss_mode,
        "stop_loss_value": stop_loss_value,
        "execution_mode": execution_mode,
        "strategy_binding": str(payload.get("strategy_binding") or ""),
        "holding_profile": str(payload.get("holding_profile") or "intraday"),
        "source_type": str(payload.get("source_type") or "manual"),
        "source_ref_id": str(payload.get("source_ref_id") or ""),
    }

    return {
        "validation_status": "valid" if not reject_reason_codes else "rejected",
        "reject_reason_codes": reject_reason_codes,
        "normalized_order_payload": normalized_order_payload,
        "risk_flags": risk_flags,
        "preview_hash": _preview_hash(normalized_order_payload),
        "queue_mode": registry.get("default_execution_mode", "ASSISTED"),
    }