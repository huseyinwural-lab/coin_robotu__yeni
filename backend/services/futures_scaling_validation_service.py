import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.config import settings
from core.simulation.capital_scaling_simulator import run_capital_scaling_simulation
from core.simulation.scaling_governance_adapter import build_scaling_governance_actions
from core.simulation.scaling_robustness_engine import compute_scaling_robustness_score
from core.simulation.stress_replay_engine import run_stress_replay


def _safe_json(raw, default):
    if not raw:
        return default
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        if isinstance(raw, str):
            return json.loads(raw)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list):
            return raw
    except Exception:
        return default
    return default


def _trades_from_status(cache, user_id: str) -> list[dict]:
    status = _safe_json(cache.get(f"futures:strategy:status:{user_id}"), {}) if cache else {}
    decision_trace = status.get("decision_trace") or []

    trades: list[dict] = []
    for row in decision_trace:
        if row.get("decision") != "ALLOW":
            continue
        leverage = float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0)
        size_ratio = float((row.get("leverage_decision") or {}).get("position_size_ratio") or 1.0)
        trades.append(
            {
                "strategy": row.get("strategy"),
                "symbol": row.get("symbol"),
                "order_size": 20_000 * leverage * max(0.1, min(size_ratio, 1.0)),
                "expected_pnl": float(next((item.get("paper_pnl") for item in (status.get("paper_trades") or []) if item.get("symbol") == row.get("symbol")), 0.0)),
                "volatility_regime": "HIGH" if row.get("strategy") == "breakout_v1" else "NORMAL",
            }
        )

    if not trades:
        trades = [
            {"strategy": "trend_follow_v1", "symbol": "BTCUSDT", "order_size": 10000, "expected_pnl": 120.0, "volatility_regime": "NORMAL"},
            {"strategy": "mean_reversion_v1", "symbol": "ETHUSDT", "order_size": 8000, "expected_pnl": 85.0, "volatility_regime": "NORMAL"},
            {"strategy": "breakout_v1", "symbol": "SOLUSDT", "order_size": 6000, "expected_pnl": 70.0, "volatility_regime": "HIGH"},
        ]
    return trades


def _scaling_components(report_rows: list[dict]) -> dict:
    if not report_rows:
        return {
            "pnl_stability": 50.0,
            "slippage_impact": 50.0,
            "execution_quality": 50.0,
            "liquidity_stress": 50.0,
        }

    pnls = [float(item.get("pnl") or 0.0) for item in report_rows]
    max_pnl = max(pnls)
    min_pnl = min(pnls)
    avg_pnl = sum(pnls) / len(pnls)
    pnl_stability = 100.0 if avg_pnl == 0 else max(0.0, 100.0 - abs((max_pnl - min_pnl) / max(abs(avg_pnl), 1.0)) * 20)

    avg_slippage = sum(float(item.get("slippage") or 0.0) for item in report_rows) / len(report_rows)
    avg_quality = sum(float(item.get("execution_quality") or 0.0) for item in report_rows) / len(report_rows)
    avg_liquidity_stress = sum(float(item.get("liquidity_stress") or 0.0) for item in report_rows) / len(report_rows)

    return {
        "pnl_stability": round(max(0.0, min(pnl_stability, 100.0)), 2),
        "slippage_impact": round(max(0.0, min(100.0 - avg_slippage * 1.6, 100.0)), 2),
        "execution_quality": round(max(0.0, min(avg_quality * 100, 100.0)), 2),
        "liquidity_stress": round(max(0.0, min(100.0 - avg_liquidity_stress * 100, 100.0)), 2),
    }


def get_futures_scaling_validation(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    _ = db
    cache_key = f"futures:scaling:validation:{user_id}"
    if cache and not refresh:
        cached = _safe_json(cache.get(cache_key), None)
        if isinstance(cached, dict):
            return cached

    trades = _trades_from_status(cache, user_id)
    scaling = run_capital_scaling_simulation(
        trades=trades,
        capital_levels=[1_000_000.0, 10_000_000.0, 100_000_000.0],
        market_depth=4_500_000.0,
        spread_bps=12.0,
        liquidity_tier="MEDIUM",
    )
    report_rows = scaling.get("scaling_performance_report") or []
    components = _scaling_components(report_rows)

    robustness = compute_scaling_robustness_score(
        pnl_stability=components["pnl_stability"],
        slippage_impact=components["slippage_impact"],
        execution_quality=components["execution_quality"],
        liquidity_stress=components["liquidity_stress"],
        weights={
            "pnl_stability": settings.scaling_weight_pnl_stability,
            "slippage_impact": settings.scaling_weight_slippage_impact,
            "execution_quality": settings.scaling_weight_execution_quality,
            "liquidity_stress": settings.scaling_weight_liquidity_stress,
        },
    )
    governance = build_scaling_governance_actions(robustness)

    stress_dashboard = [
        run_stress_replay({"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}, "high_volatility"),
        run_stress_replay({"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}, "low_liquidity"),
        run_stress_replay({"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}, "flash_crash"),
        run_stress_replay({"volatility": 1.0, "liquidity": 1.0, "spread_bps": 12.0}, "liquidation_cascade"),
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scaling_performance_report": report_rows,
        "scaling_robustness_score": robustness.get("scaling_robustness_score", 0.0),
        "robustness_state": robustness.get("robustness_state", "unstable"),
        "robustness_components": robustness.get("components") or {},
        "robustness_weights": robustness.get("weights") or {},
        "scaling_governance_actions": governance,
        "stress_replay_dashboard": stress_dashboard,
    }
    if cache:
        cache.set(cache_key, json.dumps(payload))
    return payload


def get_futures_scaling_report(db: Session, cache, user_id: str, refresh: bool = False) -> dict:
    payload = get_futures_scaling_validation(db, cache, user_id, refresh=refresh)
    return {
        "generated_at": payload.get("generated_at"),
        "scaling_performance_report": payload.get("scaling_performance_report") or [],
        "scaling_robustness_score": payload.get("scaling_robustness_score", 0.0),
        "robustness_state": payload.get("robustness_state", "unstable"),
        "stress_replay_dashboard": payload.get("stress_replay_dashboard") or [],
    }
