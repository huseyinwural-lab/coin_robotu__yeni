import json
from datetime import datetime, timezone
from pathlib import Path

from models import PaperPosition, RiskOrchestratorPolicy, UserExecutionIntent, UserRiskSetting
from services.cooldown_service import activate_cooldown, cooldown_state
from services.correlation_cluster_service import cluster_symbol_map, resolve_symbol_cluster
from services.execution_quality_service import evaluate_execution_quality
from services.pipeline.cache_store import get_counter, get_json, incr_counter, set_json
from services.pipeline.kill_switch_service import kill_switch_state


RISK_CONFIG_CACHE_KEY = "risk:config:active"
RISK_CONFIG_RELOAD_KEY = "risk:config:last_reload"
RISK_RUNTIME_STATE_KEY = "risk:runtime:latest:global"
RISK_CONFIG_BACKUP_KEY = "risk:config:last_known_good"
RISK_EXEC_QUALITY_TREND_KEY = "risk:metrics:execution_quality_trend"

SAFE_BOUNDS_MAX = {
    "max_risk_per_trade_pct": 5.0,
    "max_total_exposure_pct": 50.0,
    "max_leverage": 10,
}

DEFAULT_RISK_CONFIG = {
    "max_risk_per_trade_pct": 2.0,
    "max_total_exposure_pct": 50.0,
    "max_symbol_exposure_pct": 25.0,
    "max_cluster_exposure_pct": 35.0,
    "max_leverage": 5,
    "min_liquidation_distance_pct": 6.0,
    "max_margin_usage_pct": 70.0,
    "stale_data_threshold_ms": 120000,
    "spread_threshold_bps": 30.0,
    "max_slippage_pct": 0.8,
    "execution_quality_threshold": 65.0,
    "max_daily_loss_pct": 4.0,
    "max_consecutive_losses": 4,
    "symbol_cooldown_minutes": 30,
    "strategy_cooldown_minutes": 30,
    "global_cooldown_minutes": 60,
    "kill_switch_enabled": False,
    "config_version": 1,
    "changed_by": "system",
    "changed_at": datetime.now(timezone.utc).isoformat(),
}

RISK_POLICY_PROFILES = {
    "conservative": {
        "max_risk_per_trade_pct": 1.0,
        "max_total_exposure_pct": 35.0,
        "max_symbol_exposure_pct": 15.0,
        "max_cluster_exposure_pct": 20.0,
        "max_leverage": 3,
        "execution_quality_threshold": 72.0,
        "spread_threshold_bps": 20.0,
        "stale_data_threshold_ms": 90_000,
    },
    "balanced": {
        "max_risk_per_trade_pct": 2.0,
        "max_total_exposure_pct": 50.0,
        "max_symbol_exposure_pct": 25.0,
        "max_cluster_exposure_pct": 35.0,
        "max_leverage": 5,
        "execution_quality_threshold": 65.0,
        "spread_threshold_bps": 30.0,
        "stale_data_threshold_ms": 120_000,
    },
    "aggressive": {
        "max_risk_per_trade_pct": 3.5,
        "max_total_exposure_pct": 50.0,
        "max_symbol_exposure_pct": 35.0,
        "max_cluster_exposure_pct": 45.0,
        "max_leverage": 8,
        "execution_quality_threshold": 58.0,
        "spread_threshold_bps": 40.0,
        "stale_data_threshold_ms": 150_000,
    },
}


def _config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "risk_engine_config.json"


def _config_backup_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "risk_engine_config_backup.json"


def _policy_overrides_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "risk_policy_overrides.json"


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalized_config(raw: dict | None) -> dict:
    payload = {**DEFAULT_RISK_CONFIG, **(raw or {})}
    payload["max_risk_per_trade_pct"] = max(0.1, _to_float(payload.get("max_risk_per_trade_pct"), 2.0))
    payload["max_total_exposure_pct"] = max(1.0, _to_float(payload.get("max_total_exposure_pct"), 50.0))
    payload["max_symbol_exposure_pct"] = max(1.0, _to_float(payload.get("max_symbol_exposure_pct"), 25.0))
    payload["max_cluster_exposure_pct"] = max(1.0, _to_float(payload.get("max_cluster_exposure_pct"), 35.0))
    payload["max_leverage"] = max(1, _to_int(payload.get("max_leverage"), 5))
    payload["min_liquidation_distance_pct"] = max(0.1, _to_float(payload.get("min_liquidation_distance_pct"), 6.0))
    payload["max_margin_usage_pct"] = max(1.0, _to_float(payload.get("max_margin_usage_pct"), 70.0))
    payload["stale_data_threshold_ms"] = max(1000, _to_int(payload.get("stale_data_threshold_ms"), 120000))
    payload["spread_threshold_bps"] = max(0.1, _to_float(payload.get("spread_threshold_bps"), 30.0))
    payload["max_slippage_pct"] = max(0.01, _to_float(payload.get("max_slippage_pct"), 0.8))
    payload["execution_quality_threshold"] = max(1.0, _to_float(payload.get("execution_quality_threshold"), 65.0))
    payload["max_daily_loss_pct"] = max(0.1, _to_float(payload.get("max_daily_loss_pct"), 4.0))
    payload["max_consecutive_losses"] = max(1, _to_int(payload.get("max_consecutive_losses"), 4))
    payload["symbol_cooldown_minutes"] = max(0, _to_int(payload.get("symbol_cooldown_minutes"), 30))
    payload["strategy_cooldown_minutes"] = max(0, _to_int(payload.get("strategy_cooldown_minutes"), 30))
    payload["global_cooldown_minutes"] = max(0, _to_int(payload.get("global_cooldown_minutes"), 60))
    payload["kill_switch_enabled"] = bool(payload.get("kill_switch_enabled", False))
    payload["config_version"] = max(1, _to_int(payload.get("config_version"), 1))
    payload["changed_by"] = str(payload.get("changed_by") or "system")
    payload["changed_at"] = str(payload.get("changed_at") or datetime.now(timezone.utc).isoformat())
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def _validate_safe_bounds(patch: dict) -> list[str]:
    violations: list[str] = []
    if "max_risk_per_trade_pct" in patch and _to_float(patch.get("max_risk_per_trade_pct"), 0) > SAFE_BOUNDS_MAX["max_risk_per_trade_pct"]:
        violations.append("max_risk_per_trade_pct_exceeds_safe_bound")
    if "max_total_exposure_pct" in patch and _to_float(patch.get("max_total_exposure_pct"), 0) > SAFE_BOUNDS_MAX["max_total_exposure_pct"]:
        violations.append("max_total_exposure_pct_exceeds_safe_bound")
    if "max_leverage" in patch and _to_int(patch.get("max_leverage"), 0) > SAFE_BOUNDS_MAX["max_leverage"]:
        violations.append("max_leverage_exceeds_safe_bound")
    return violations


def _read_file_config() -> dict:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        normalized = _normalized_config(DEFAULT_RISK_CONFIG)
        path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
        _config_backup_path().write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
        return normalized
    try:
        raw = json.loads(path.read_text())
        normalized = _normalized_config(raw)
        path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
        if not _config_backup_path().exists():
            _config_backup_path().write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
        return normalized
    except Exception:
        normalized = _normalized_config(DEFAULT_RISK_CONFIG)
        path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
        _config_backup_path().write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
        return normalized


def load_risk_config(cache) -> dict:
    cached = get_json(cache, RISK_CONFIG_CACHE_KEY)
    if cached:
        return _normalized_config(cached)
    payload = _read_file_config()
    set_json(cache, RISK_CONFIG_CACHE_KEY, payload)
    return payload


def patch_risk_config(cache, patch: dict, *, changed_by: str = "admin") -> dict:
    violations = _validate_safe_bounds(patch or {})
    if violations:
        raise ValueError(
            "safe_bounds_violation: " + ",".join(violations)
        )

    current = load_risk_config(cache)
    backup_payload = _normalized_config(current)
    backup_payload["backup_at"] = datetime.now(timezone.utc).isoformat()
    _config_backup_path().write_text(json.dumps(backup_payload, indent=2, ensure_ascii=False))
    set_json(cache, RISK_CONFIG_BACKUP_KEY, backup_payload)

    merged = _normalized_config({**current, **(patch or {})})
    merged["config_version"] = int(current.get("config_version") or 1) + 1
    merged["changed_by"] = str(changed_by or "admin")
    merged["changed_at"] = datetime.now(timezone.utc).isoformat()
    _config_path().write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    set_json(cache, RISK_CONFIG_CACHE_KEY, merged)
    set_json(cache, RISK_CONFIG_RELOAD_KEY, {"reloaded_at": datetime.now(timezone.utc).isoformat()})
    return merged


def reload_risk_config(cache) -> dict:
    payload = _read_file_config()
    set_json(cache, RISK_CONFIG_CACHE_KEY, payload)
    set_json(cache, RISK_CONFIG_RELOAD_KEY, {"reloaded_at": datetime.now(timezone.utc).isoformat()})
    return payload


def rollback_risk_config(cache, *, changed_by: str = "admin") -> dict:
    backup_path = _config_backup_path()
    if not backup_path.exists():
        raise ValueError("backup_config_missing")
    raw = json.loads(backup_path.read_text())
    restored = _normalized_config(raw)
    restored["config_version"] = int(load_risk_config(cache).get("config_version") or 1) + 1
    restored["changed_by"] = str(changed_by or "admin")
    restored["changed_at"] = datetime.now(timezone.utc).isoformat()
    _config_path().write_text(json.dumps(restored, indent=2, ensure_ascii=False))
    set_json(cache, RISK_CONFIG_CACHE_KEY, restored)
    set_json(cache, RISK_CONFIG_RELOAD_KEY, {"reloaded_at": datetime.now(timezone.utc).isoformat(), "rollback": True})
    return restored


def get_policy_profiles() -> dict:
    return {
        "profiles": RISK_POLICY_PROFILES,
        "default_profile": "balanced",
    }


def apply_policy_profile(cache, *, profile: str, changed_by: str = "admin") -> dict:
    profile_key = str(profile or "").lower().strip()
    if profile_key not in RISK_POLICY_PROFILES:
        raise ValueError("unknown_policy_profile")
    patch_payload = {**RISK_POLICY_PROFILES[profile_key], "active_profile": profile_key}
    return patch_risk_config(cache, patch_payload, changed_by=changed_by)


def get_policy_overrides() -> dict:
    path = _policy_overrides_path()
    if not path.exists():
        payload = {"global": {}, "tenants": {}, "users": {}}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return payload
    try:
        parsed = json.loads(path.read_text())
        if isinstance(parsed, dict):
            return {
                "global": parsed.get("global") or {},
                "tenants": parsed.get("tenants") or {},
                "users": parsed.get("users") or {},
            }
    except Exception:
        pass
    payload = {"global": {}, "tenants": {}, "users": {}}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def upsert_policy_overrides(*, scope: str, key: str, values: dict) -> dict:
    payload = get_policy_overrides()
    scope_key = str(scope or "").lower().strip()
    if scope_key not in {"global", "tenants", "users"}:
        raise ValueError("invalid_scope")
    if scope_key == "global":
        payload["global"] = values or {}
    else:
        payload[scope_key][str(key or "default")] = values or {}
    _policy_overrides_path().write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def resolve_effective_config_for_user(cache, *, user_id: str, tenant_id: str | None = None) -> dict:
    base_config = load_risk_config(cache)
    overrides = get_policy_overrides()
    effective = {**base_config, **(overrides.get("global") or {})}
    if tenant_id:
        effective.update((overrides.get("tenants") or {}).get(str(tenant_id), {}) or {})
    effective.update((overrides.get("users") or {}).get(str(user_id), {}) or {})
    return _normalized_config(effective)


def _position_notional(row: PaperPosition) -> float:
    return max(float(row.entry_price or 0) * float(row.quantity or 0), 0.0)


def _pending_notional(row: UserExecutionIntent) -> float:
    return max(float(row.notional or 0), 0.0)


def build_exposure_snapshot(db, *, user_id: str, symbol: str, proposed_notional_usdt: float) -> dict:
    settings = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()
    policy = db.query(RiskOrchestratorPolicy).filter(RiskOrchestratorPolicy.id == "global").first()
    wallet = float((settings.base_capital if settings else None) or (policy.reference_equity_usd if policy else None) or 10000.0)

    open_positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .all()
    )
    pending_intents = (
        db.query(UserExecutionIntent)
        .filter(
            UserExecutionIntent.user_id == user_id,
            UserExecutionIntent.status.in_(["PREVIEWED", "SUBMITTED", "QUEUED", "APPROVED"]),
        )
        .all()
    )

    open_exposure = sum(_position_notional(row) for row in open_positions)
    pending_exposure = sum(_pending_notional(row) for row in pending_intents)

    symbol_upper = str(symbol or "").upper().strip()
    symbol_open_exposure = sum(_position_notional(row) for row in open_positions if str(row.symbol or "").upper() == symbol_upper)
    symbol_pending_exposure = sum(_pending_notional(row) for row in pending_intents if str(row.symbol or "").upper() == symbol_upper)

    symbol_map = cluster_symbol_map(db)
    cluster_id = resolve_symbol_cluster(db, symbol_upper)
    cluster_symbols = symbol_map.get(cluster_id, set())
    cluster_open = sum(_position_notional(row) for row in open_positions if str(row.symbol or "").upper() in cluster_symbols)
    cluster_pending = sum(_pending_notional(row) for row in pending_intents if str(row.symbol or "").upper() in cluster_symbols)

    return {
        "wallet_usdt_balance": round(wallet, 6),
        "open_exposure_usdt": round(open_exposure, 6),
        "pending_exposure_usdt": round(pending_exposure, 6),
        "symbol_exposure_usdt": round(symbol_open_exposure + symbol_pending_exposure, 6),
        "cluster_exposure_usdt": round(cluster_open + cluster_pending, 6),
        "cluster_id": cluster_id,
        "proposed_notional_usdt": round(max(float(proposed_notional_usdt or 0), 0), 6),
        "projected_total_exposure_usdt": round(open_exposure + pending_exposure + max(float(proposed_notional_usdt or 0), 0), 6),
        "projected_symbol_exposure_usdt": round(symbol_open_exposure + symbol_pending_exposure + max(float(proposed_notional_usdt or 0), 0), 6),
        "projected_cluster_exposure_usdt": round(cluster_open + cluster_pending + max(float(proposed_notional_usdt or 0), 0), 6),
    }


def _daily_loss_stats(db, *, user_id: str, wallet_usdt_balance: float) -> dict:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.closed_at.is_not(None), PaperPosition.closed_at >= start)
        .all()
    )
    daily_loss_usdt = abs(sum(float(item.realized_pnl or 0) for item in rows if float(item.realized_pnl or 0) < 0))
    daily_loss_pct = (daily_loss_usdt / max(wallet_usdt_balance, 1e-6)) * 100.0
    return {
        "daily_loss_usdt": round(daily_loss_usdt, 6),
        "daily_loss_pct": round(daily_loss_pct, 6),
    }


def _consecutive_losses(db, *, user_id: str) -> int:
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.closed_at.is_not(None))
        .order_by(PaperPosition.closed_at.desc())
        .limit(30)
        .all()
    )
    streak = 0
    for row in rows:
        pnl = float(row.realized_pnl or 0)
        if pnl < 0:
            streak += 1
            continue
        break
    return streak


def _merge_action(current: str, incoming: str) -> str:
    priority = {"ALLOW": 0, "REDUCE_SIZE": 1, "PASS": 2, "BLOCK": 3}
    return incoming if priority.get(incoming, 0) > priority.get(current, 0) else current


def is_risk_kill_switch_active(cache) -> bool:
    config = load_risk_config(cache)
    pipeline_state = kill_switch_state(cache)
    return bool(config.get("kill_switch_enabled", False) or pipeline_state.get("active", False))


def _execution_quality_trend(cache) -> dict:
    return get_json(cache, RISK_EXEC_QUALITY_TREND_KEY) or {
        "ema_score": 100.0,
        "sample_count": 0,
        "warning_count": 0,
        "partial_fill_count": 0,
        "reject_count": 0,
        "warning_rate": 0.0,
        "partial_fill_rate": 0.0,
        "reject_rate": 0.0,
    }


def _update_execution_quality_trend(cache, *, score: float, recommendation: str, status_hint: str = "") -> dict:
    trend = _execution_quality_trend(cache)
    alpha = 0.2
    previous_ema = float(trend.get("ema_score") or 100.0)
    sample_count = int(trend.get("sample_count") or 0) + 1
    warning_count = int(trend.get("warning_count") or 0)
    partial_fill_count = int(trend.get("partial_fill_count") or 0)
    reject_count = int(trend.get("reject_count") or 0)

    recommendation = str(recommendation or "ALLOW").upper()
    if recommendation in {"REDUCE_SIZE", "PASS", "BLOCK"}:
        warning_count += 1
    if recommendation == "REDUCE_SIZE" or "PARTIAL" in str(status_hint).upper():
        partial_fill_count += 1
    if recommendation in {"PASS", "BLOCK"} or "REJECT" in str(status_hint).upper() or "FAIL" in str(status_hint).upper():
        reject_count += 1

    ema_score = (score * alpha) + (previous_ema * (1 - alpha))
    trend_payload = {
        "ema_score": round(ema_score, 4),
        "sample_count": sample_count,
        "warning_count": warning_count,
        "partial_fill_count": partial_fill_count,
        "reject_count": reject_count,
        "warning_rate": round(warning_count / max(sample_count, 1), 6),
        "partial_fill_rate": round(partial_fill_count / max(sample_count, 1), 6),
        "reject_rate": round(reject_count / max(sample_count, 1), 6),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_json(cache, RISK_EXEC_QUALITY_TREND_KEY, trend_payload)
    return trend_payload


def evaluate_risk_decision(
    db,
    cache,
    *,
    user_id: str,
    symbol: str,
    strategy_decision: str,
    market_type: str,
    proposed_notional_usdt: float,
    strategy_code: str | None = None,
    requested_leverage: int = 1,
    snapshot_age_ms: float = 0.0,
    spread_bps: float = 0.0,
    execution_latency_ms: float = 0.0,
    slippage_pct: float = 0.0,
    orderbook_depth_score: float = 1.0,
    liquidation_distance_pct: float | None = None,
) -> dict:
    config = resolve_effective_config_for_user(cache, user_id=user_id)
    symbol_upper = str(symbol or "").upper().strip()
    strategy_decision_upper = str(strategy_decision or "PASS").upper().strip()
    action = "ALLOW"
    reason_codes: list[str] = []
    warnings: list[str] = []
    size_multiplier = 1.0
    adjusted_leverage = max(int(requested_leverage or 1), 1)

    exposure = build_exposure_snapshot(db, user_id=user_id, symbol=symbol_upper, proposed_notional_usdt=proposed_notional_usdt)
    wallet = max(float(exposure.get("wallet_usdt_balance") or 0), 1e-6)

    global_cd = cooldown_state(cache, scope="global", user_id=user_id)
    symbol_cd = cooldown_state(cache, scope="symbol", user_id=user_id, key=symbol_upper)
    strategy_cd = cooldown_state(cache, scope="strategy", user_id=user_id, key=str(strategy_code or "default"))
    if bool(global_cd.get("active")):
        action = _merge_action(action, "BLOCK")
        reason_codes.append("global_cooldown_active")
    if bool(symbol_cd.get("active")):
        action = _merge_action(action, "PASS")
        reason_codes.append("symbol_cooldown_active")
    if bool(strategy_cd.get("active")):
        action = _merge_action(action, "PASS")
        reason_codes.append("strategy_cooldown_active")

    pipeline_kill_switch = kill_switch_state(cache)
    if bool(config.get("kill_switch_enabled", False)):
        action = _merge_action(action, "BLOCK")
        reason_codes.append("risk_kill_switch_enabled")
    if bool(pipeline_kill_switch.get("active", False)):
        action = _merge_action(action, "BLOCK")
        reason_codes.append("pipeline_kill_switch_active")

    if strategy_decision_upper not in {"LONG", "SHORT"}:
        action = _merge_action(action, "PASS")
        reason_codes.append("strategy_pass")

    trade_risk_pct = (max(float(proposed_notional_usdt or 0), 0) / wallet) * 100.0
    projected_total_pct = (float(exposure.get("projected_total_exposure_usdt") or 0) / wallet) * 100.0
    projected_symbol_pct = (float(exposure.get("projected_symbol_exposure_usdt") or 0) / wallet) * 100.0
    projected_cluster_pct = (float(exposure.get("projected_cluster_exposure_usdt") or 0) / wallet) * 100.0

    if projected_total_pct > float(config.get("max_total_exposure_pct")):
        action = _merge_action(action, "BLOCK")
        reason_codes.append("max_total_exposure_pct_exceeded")
    if projected_symbol_pct > float(config.get("max_symbol_exposure_pct")):
        action = _merge_action(action, "PASS")
        reason_codes.append("max_symbol_exposure_pct_exceeded")
    if projected_cluster_pct > float(config.get("max_cluster_exposure_pct")):
        action = _merge_action(action, "PASS")
        reason_codes.append("max_cluster_exposure_pct_exceeded")

    max_trade_pct = float(config.get("max_risk_per_trade_pct"))
    if trade_risk_pct > max_trade_pct > 0:
        action = _merge_action(action, "REDUCE_SIZE")
        ratio = max_trade_pct / max(trade_risk_pct, 1e-6)
        size_multiplier = min(size_multiplier, max(0.05, min(1.0, ratio)))
        warnings.append("trade_size_reduced_by_max_risk_per_trade_pct")

    if str(market_type or "spot").lower() == "futures":
        max_leverage = int(config.get("max_leverage"))
        if adjusted_leverage > max_leverage:
            action = _merge_action(action, "REDUCE_SIZE")
            adjusted_leverage = max_leverage
            size_multiplier = min(size_multiplier, max_leverage / max(int(requested_leverage or 1), 1))
            warnings.append("leverage_capped")

        margin_usage_pct = projected_total_pct
        if margin_usage_pct > float(config.get("max_margin_usage_pct")):
            action = _merge_action(action, "PASS")
            reason_codes.append("max_margin_usage_pct_exceeded")

        if liquidation_distance_pct is not None and float(liquidation_distance_pct) < float(config.get("min_liquidation_distance_pct")):
            action = _merge_action(action, "BLOCK")
            reason_codes.append("liquidation_distance_too_low")

    quality_trend = _execution_quality_trend(cache)
    quality = evaluate_execution_quality(
        snapshot_age_ms=float(snapshot_age_ms or 0),
        spread_bps=float(spread_bps or 0),
        slippage_pct=float(slippage_pct or 0),
        execution_latency_ms=float(execution_latency_ms or 0),
        orderbook_depth_score=float(orderbook_depth_score or 0),
        partial_fill_rate=float(quality_trend.get("partial_fill_rate") or 0.0),
        reject_rate=float(quality_trend.get("reject_rate") or 0.0),
        stale_threshold_ms=float(config.get("stale_data_threshold_ms")),
        spread_threshold_bps=float(config.get("spread_threshold_bps")),
        max_slippage_pct=float(config.get("max_slippage_pct")),
        execution_quality_threshold=float(config.get("execution_quality_threshold")),
    )
    quality_action = str(quality.get("recommendation") or "ALLOW")
    action = _merge_action(action, quality_action)
    if quality_action == "REDUCE_SIZE":
        size_multiplier = min(size_multiplier, 0.75)
        warnings.append("execution_quality_mild_warning")
        incr_counter(cache, "risk:metrics:execution_quality_warning_count", 1)
    elif quality_action == "PASS":
        reason_codes.append("execution_quality_medium_veto")
        incr_counter(cache, "risk:metrics:execution_quality_warning_count", 1)
    elif quality_action == "BLOCK":
        reason_codes.append("execution_quality_severe_veto")
        incr_counter(cache, "risk:metrics:execution_quality_warning_count", 1)

    quality_trend = _update_execution_quality_trend(
        cache,
        score=float(quality.get("score") or 0.0),
        recommendation=quality_action,
        status_hint=quality_action,
    )

    stale_threshold = float(config.get("stale_data_threshold_ms"))
    spread_threshold = float(config.get("spread_threshold_bps"))
    if float(snapshot_age_ms or 0) > stale_threshold * 2:
        action = _merge_action(action, "BLOCK")
        reason_codes.append("stale_data_block")
        incr_counter(cache, "risk:metrics:stale_reject_count", 1)
    elif float(snapshot_age_ms or 0) > stale_threshold:
        action = _merge_action(action, "PASS")
        reason_codes.append("stale_data_pass")
        incr_counter(cache, "risk:metrics:stale_reject_count", 1)

    if float(spread_bps or 0) > spread_threshold * 2:
        action = _merge_action(action, "BLOCK")
        reason_codes.append("spread_block")
        incr_counter(cache, "risk:metrics:spread_reject_count", 1)
    elif float(spread_bps or 0) > spread_threshold:
        action = _merge_action(action, "PASS")
        reason_codes.append("spread_pass")
        incr_counter(cache, "risk:metrics:spread_reject_count", 1)

    daily = _daily_loss_stats(db, user_id=user_id, wallet_usdt_balance=wallet)
    if float(daily.get("daily_loss_pct") or 0) >= float(config.get("max_daily_loss_pct")):
        action = _merge_action(action, "BLOCK")
        reason_codes.append("max_daily_loss_pct_exceeded")
        activate_cooldown(
            cache,
            scope="global",
            user_id=user_id,
            minutes=int(config.get("global_cooldown_minutes")),
            reason="max_daily_loss_pct_exceeded",
        )

    loss_streak = _consecutive_losses(db, user_id=user_id)
    if loss_streak >= int(config.get("max_consecutive_losses")):
        action = _merge_action(action, "PASS")
        reason_codes.append("max_consecutive_losses_exceeded")
        activate_cooldown(
            cache,
            scope="strategy",
            user_id=user_id,
            key=str(strategy_code or "default"),
            minutes=int(config.get("strategy_cooldown_minutes")),
            reason="max_consecutive_losses_exceeded",
        )

    if action in {"PASS", "BLOCK"} and int(config.get("symbol_cooldown_minutes")) > 0:
        activate_cooldown(
            cache,
            scope="symbol",
            user_id=user_id,
            key=symbol_upper,
            minutes=int(config.get("symbol_cooldown_minutes")),
            reason="risk_veto",
        )

    final_multiplier = max(0.0, min(1.0, size_multiplier if action == "REDUCE_SIZE" else 1.0))
    adjusted_notional = max(float(proposed_notional_usdt or 0), 0.0)
    if action == "REDUCE_SIZE":
        adjusted_notional = round(adjusted_notional * final_multiplier, 6)
    if action in {"PASS", "BLOCK"}:
        adjusted_notional = 0.0

    cooldown_snapshot = {
        "global": cooldown_state(cache, scope="global", user_id=user_id),
        "symbol": cooldown_state(cache, scope="symbol", user_id=user_id, key=symbol_upper),
        "strategy": cooldown_state(cache, scope="strategy", user_id=user_id, key=str(strategy_code or "default")),
    }
    result = {
        "risk_decision": action,
        "size_multiplier": round(final_multiplier, 6),
        "adjusted_notional_usdt": round(adjusted_notional, 6),
        "adjusted_leverage": adjusted_leverage,
        "reason_codes": sorted(set(reason_codes)),
        "warnings": sorted(set(warnings)),
        "exposure_snapshot": exposure,
        "execution_quality": quality,
        "execution_quality_trend": quality_trend,
        "cooldown_state": cooldown_snapshot,
        "kill_switch_active": bool(config.get("kill_switch_enabled") or pipeline_kill_switch.get("active", False)),
        "daily_loss": daily,
        "consecutive_losses": int(loss_streak),
        "metrics": {
            "trade_risk_pct": round(trade_risk_pct, 6),
            "projected_total_exposure_pct": round(projected_total_pct, 6),
            "projected_symbol_exposure_pct": round(projected_symbol_pct, 6),
            "projected_cluster_exposure_pct": round(projected_cluster_pct, 6),
            "snapshot_age_ms": round(float(snapshot_age_ms or 0), 4),
            "spread_bps": round(float(spread_bps or 0), 4),
            "execution_latency_ms": round(float(execution_latency_ms or 0), 4),
        },
    }
    set_json(
        cache,
        RISK_RUNTIME_STATE_KEY,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "symbol": symbol_upper,
            "strategy_code": strategy_code,
            "risk_result": result,
            "stale_reject_count": get_counter(cache, "risk:metrics:stale_reject_count"),
            "spread_reject_count": get_counter(cache, "risk:metrics:spread_reject_count"),
            "execution_quality_warning_count": get_counter(cache, "risk:metrics:execution_quality_warning_count"),
        },
    )
    return result


def build_admin_risk_status(db, cache) -> dict:
    config = load_risk_config(cache)
    open_positions = db.query(PaperPosition).filter(PaperPosition.status == "open").all()
    closed_positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.closed_at.is_not(None))
        .order_by(PaperPosition.closed_at.desc())
        .limit(120)
        .all()
    )
    total_exposure = sum(_position_notional(row) for row in open_positions)

    symbol_exposure: dict[str, float] = {}
    for row in open_positions:
        symbol = str(row.symbol or "").upper().strip()
        symbol_exposure[symbol] = symbol_exposure.get(symbol, 0.0) + _position_notional(row)

    cluster_map = cluster_symbol_map(db)
    cluster_exposure: dict[str, float] = {cluster_id: 0.0 for cluster_id in cluster_map}
    for row in open_positions:
        symbol = str(row.symbol or "").upper().strip()
        matched_cluster = "unclustered"
        for cluster_id, symbols in cluster_map.items():
            if symbol in symbols:
                matched_cluster = cluster_id
                break
        cluster_exposure[matched_cluster] = cluster_exposure.get(matched_cluster, 0.0) + _position_notional(row)

    pnl_trend = [
        {
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "realized_pnl": round(float(row.realized_pnl or 0.0), 6),
            "symbol": str(row.symbol or "").upper().strip(),
        }
        for row in reversed(closed_positions)
    ]

    latest_runtime = get_json(cache, RISK_RUNTIME_STATE_KEY) or {}
    scanner_runtime = get_json(cache, "scanner:runtime:latest:global") or {}
    fallback_state = get_json(cache, "scanner:runtime:fallback_state") or {}
    risk_result = latest_runtime.get("risk_result") or {}
    quality_payload = risk_result.get("execution_quality") or {}
    quality_trend = get_json(cache, RISK_EXEC_QUALITY_TREND_KEY) or {}
    pipeline_switch = kill_switch_state(cache)
    return {
        "config": config,
        "portfolio_exposure": round(total_exposure, 6),
        "total_exposure": round(total_exposure, 6),
        "symbol_exposure": [
            {"symbol": key, "exposure_usdt": round(value, 6)}
            for key, value in sorted(symbol_exposure.items(), key=lambda item: item[1], reverse=True)[:20]
        ],
        "cluster_exposure": [
            {"cluster": key, "exposure_usdt": round(value, 6)}
            for key, value in sorted(cluster_exposure.items(), key=lambda item: item[1], reverse=True)
            if value > 0
        ],
        "daily_loss": (risk_result.get("daily_loss") or {}),
        "execution_quality_score": float(quality_payload.get("score") or quality_trend.get("ema_score") or 0.0),
        "execution_quality_trend": quality_trend,
        "fallback_state": fallback_state,
        "queue_depth": int((scanner_runtime.get("runtime_metrics") or {}).get("queue_depth") or 0),
        "stale_reject_count": int(get_counter(cache, "risk:metrics:stale_reject_count")),
        "spread_reject_count": int(get_counter(cache, "risk:metrics:spread_reject_count")),
        "execution_quality_warning": int(get_counter(cache, "risk:metrics:execution_quality_warning_count")),
        "cooldown_state": risk_result.get("cooldown_state") or {},
        "pnl_trend": pnl_trend,
        "kill_switch_state": {
            "risk_kill_switch_enabled": bool(config.get("kill_switch_enabled", False)),
            "pipeline_kill_switch_active": bool(pipeline_switch.get("active", False)),
            "reasons": pipeline_switch.get("reasons") or [],
        },
        "latest_risk_decision": risk_result.get("risk_decision"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
