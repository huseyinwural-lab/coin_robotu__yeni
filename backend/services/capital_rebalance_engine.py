import json
from datetime import datetime, timezone
from pathlib import Path


GOVERNANCE_PATH = Path("/app/config/rebalance_governance_rules.json")

DEFAULT_GOVERNANCE = {
    "version": "rebalance_governance_v1",
    "cadence_window_minutes": 30,
    "max_weight_shift_per_cycle": 0.12,
    "max_capital_shift_pct": 0.2,
    "drift_threshold": 0.08,
}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_rebalance_governance() -> dict:
    if not GOVERNANCE_PATH.exists():
        return {**DEFAULT_GOVERNANCE}
    try:
        payload = json.loads(GOVERNANCE_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {**DEFAULT_GOVERNANCE}
        return {**DEFAULT_GOVERNANCE, **payload}
    except Exception:
        return {**DEFAULT_GOVERNANCE}


def _calculate_score(item: dict) -> float:
    performance_score = _safe_float(item.get("performance_score"), 0)
    sharpe_like = _safe_float(item.get("execution_quality_score"), 0) / 100
    drawdown_penalty = _safe_float(item.get("signal_decay"), 0)
    risk_score = _safe_float(item.get("risk_score"), 0)
    return (performance_score * 0.45) + (sharpe_like * 35) + ((1 - drawdown_penalty) * 15) + ((1 - risk_score) * 5)


def run_dynamic_capital_rebalance(
    strategy_performance: list[dict],
    drift_threshold: float = 0.08,
    governance: dict | None = None,
    now_ts: datetime | None = None,
) -> dict:
    governance_cfg = {**DEFAULT_GOVERNANCE, **(governance or load_rebalance_governance())}
    cadence_window_minutes = max(_safe_int(governance_cfg.get("cadence_window_minutes"), 30), 1)
    max_weight_shift_per_cycle = max(0.0, min(_safe_float(governance_cfg.get("max_weight_shift_per_cycle"), 0.12), 1.0))
    max_capital_shift_pct = max(0.0, min(_safe_float(governance_cfg.get("max_capital_shift_pct"), 0.2), 1.0))
    effective_drift_threshold = max(_safe_float(governance_cfg.get("drift_threshold"), drift_threshold), 0.0)
    current_ts = now_ts or _utc_now()

    if not strategy_performance:
        return {
            "allocation_drift": 0.0,
            "strategy_performance_delta": 0.0,
            "risk_adjusted_return": 0.0,
            "events": [],
            "governance_summary": {
                "cadence_window_minutes": cadence_window_minutes,
                "max_weight_shift_per_cycle": max_weight_shift_per_cycle,
                "max_capital_shift_pct": max_capital_shift_pct,
                "drift_threshold": effective_drift_threshold,
                "cadence_blocked_strategies": 0,
                "weight_shift_capped_strategies": 0,
                "capital_shift_capped_strategies": 0,
            },
        }

    scored = []
    total_score = 0.0
    for item in strategy_performance:
        score = max(_calculate_score(item), 0.0001)
        total_score += score
        scored.append({**item, "_score": score})

    events: list[dict] = []
    aggregate_drift = 0.0
    performance_deltas: list[float] = []
    risk_adjusted_returns: list[float] = []
    cadence_blocked_count = 0
    weight_shift_capped_count = 0
    capital_shift_capped_count = 0

    for item in scored:
        strategy_id = str(item.get("strategy_id") or "unknown_strategy")
        current_weight = _safe_float(item.get("capital_weight"), 1)
        raw_target_weight = round(item["_score"] / total_score, 6)
        capital_usage = _safe_float(item.get("current_capital"), 0)
        max_capital = max(_safe_float(item.get("max_capital"), 1), 1)
        usage_ratio = capital_usage / max_capital
        last_rebalanced_at = _safe_datetime(item.get("last_rebalanced_at"))
        minutes_since_last_rebalance = None
        cadence_window_blocked = False
        if last_rebalanced_at is not None:
            minutes_since_last_rebalance = max((current_ts - last_rebalanced_at).total_seconds() / 60, 0.0)
            cadence_window_blocked = minutes_since_last_rebalance < cadence_window_minutes

        target_weight = raw_target_weight
        raw_weight_shift = target_weight - current_weight
        max_weight_shift_applied = False
        if cadence_window_blocked:
            target_weight = round(current_weight, 6)
            raw_weight_shift = 0.0
            cadence_blocked_count += 1
        elif abs(raw_weight_shift) > max_weight_shift_per_cycle:
            target_weight = round(
                current_weight + (max_weight_shift_per_cycle if raw_weight_shift > 0 else -max_weight_shift_per_cycle),
                6,
            )
            raw_weight_shift = target_weight - current_weight
            max_weight_shift_applied = True
            weight_shift_capped_count += 1

        allocation_drift = round(abs(target_weight - current_weight), 6)
        aggregate_drift += allocation_drift

        raw_capital_shift = (target_weight - current_weight) * max_capital
        max_capital_shift_abs = max_capital * max_capital_shift_pct
        max_capital_shift_applied = False
        capital_shift = raw_capital_shift

        if not cadence_window_blocked and max_capital_shift_abs > 0 and abs(raw_capital_shift) > max_capital_shift_abs:
            capital_shift = max_capital_shift_abs if raw_capital_shift > 0 else -max_capital_shift_abs
            target_weight = round(current_weight + (capital_shift / max_capital), 6)
            allocation_drift = round(abs(target_weight - current_weight), 6)
            max_capital_shift_applied = True
            capital_shift_capped_count += 1

        capital_shift = round(capital_shift, 4)
        throttle_signal = allocation_drift > effective_drift_threshold or usage_ratio > 0.95

        performance_delta = round(_safe_float(item.get("performance_score"), 0) - _safe_float(item.get("confidence_score"), 0), 6)
        risk_adjusted_return = round(
            _safe_float(item.get("realized_return"), 0) - _safe_float(item.get("signal_decay"), 0) * 2,
            6,
        )

        performance_deltas.append(performance_delta)
        risk_adjusted_returns.append(risk_adjusted_return)

        events.append(
            {
                "strategy_id": strategy_id,
                "old_strategy_weight": round(current_weight, 6),
                "new_strategy_weight": target_weight,
                "target_strategy_weight": raw_target_weight,
                "capital_shift": capital_shift,
                "throttle_signal": bool(throttle_signal),
                "allocation_drift": allocation_drift,
                "strategy_performance_delta": performance_delta,
                "risk_adjusted_return": risk_adjusted_return,
                "cadence_window_blocked": cadence_window_blocked,
                "minutes_since_last_rebalance": round(minutes_since_last_rebalance, 3)
                if minutes_since_last_rebalance is not None
                else None,
                "max_weight_shift_applied": max_weight_shift_applied,
                "max_capital_shift_applied": max_capital_shift_applied,
            }
        )

    strategy_performance_delta = round(sum(performance_deltas) / max(len(performance_deltas), 1), 6)
    risk_adjusted_return = round(sum(risk_adjusted_returns) / max(len(risk_adjusted_returns), 1), 6)
    return {
        "allocation_drift": round(aggregate_drift / max(len(events), 1), 6),
        "strategy_performance_delta": strategy_performance_delta,
        "risk_adjusted_return": risk_adjusted_return,
        "events": events,
        "governance_summary": {
            "cadence_window_minutes": cadence_window_minutes,
            "max_weight_shift_per_cycle": max_weight_shift_per_cycle,
            "max_capital_shift_pct": max_capital_shift_pct,
            "drift_threshold": effective_drift_threshold,
            "cadence_blocked_strategies": cadence_blocked_count,
            "weight_shift_capped_strategies": weight_shift_capped_count,
            "capital_shift_capped_strategies": capital_shift_capped_count,
        },
    }
