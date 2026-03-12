import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.futures.adl.adl_exposure_reducer import ADLExposureReducer
from core.futures.adl.adl_gate import ADLGate
from core.futures.adl.adl_pressure_aggregator import ADLPressureAggregator
from core.futures.adl.adl_protection_policy import ADLProtectionPolicy
from core.futures.adl.adl_risk_detector import ADLRiskDetector
from core.futures.capital_reporting import futures_capital_recommendation
from core.futures.funding_bias_engine import calculate_funding_bias
from core.futures.liquidation_engine import (
    calculate_distance_to_liquidation,
    calculate_liquidation_price,
    calculate_margin_ratio,
    liquidation_risk_level,
)
from core.futures.liquidation_protection.cascade_detector import CascadeDetector
from core.futures.liquidation_protection.emergency_deleverage_executor import EmergencyDeleverageExecutor, build_deleverage_plan
from core.futures.liquidation_protection.liquidation_gate import LiquidationGate
from core.futures.liquidation_protection.liquidation_risk_aggregator import LiquidationRiskAggregator
from core.futures.liquidation_protection.margin_utilization_guard import evaluate_margin_utilization
from core.futures.liquidation_protection.protection_policy_engine import ProtectionPolicyEngine
from core.futures.position_model import FuturesPosition
from core.observability.futures_liquidation_metrics import build_futures_liquidation_metrics_snapshot
from core.risk.futures_risk_engine import evaluate_futures_risk
from models import PaperPosition, PositionLedgerEvent
from services.pipeline.position_sizing_engine import compute_position_sizing


def _position_strategy_map(db: Session) -> dict[str, str]:
    rows = db.query(PositionLedgerEvent).filter(PositionLedgerEvent.event_type == "trade_open").all()
    mapping: dict[str, str] = {}
    for row in rows:
        strategy_id = str((row.payload or {}).get("strategy_id") or "unknown")
        mapping[row.position_id] = strategy_id
    return mapping


def _safe_json(raw):
    if not raw:
        return {}
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        if isinstance(raw, str):
            return json.loads(raw)
        if isinstance(raw, dict):
            return raw
    except Exception:
        return {}
    return {}


def _funding_payload(cache, symbol: str) -> dict:
    raw = cache.get(f"futures:funding:{symbol}") if cache else None
    payload = _safe_json(raw)
    rate = float(payload.get("funding_rate", 0.0))
    history = payload.get("history", [])
    if not history:
        history = [rate]
    calculated = calculate_funding_bias(rate, history)
    calculated["funding_skew"] = float(payload.get("funding_skew", calculated.get("funding_trend", 0.0)))
    return calculated


def _market_pressure_payload(cache, symbol: str) -> dict:
    if not cache:
        return {}
    payload = _safe_json(cache.get(f"futures:adl:{symbol}"))
    return payload if isinstance(payload, dict) else {}


def _build_futures_positions(db: Session, cache, user_id: str) -> list[dict]:
    strategy_map = _position_strategy_map(db)
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.market_type == "futures", PaperPosition.status == "open")
        .all()
    )
    positions: list[dict] = []
    for row in rows:
        ticker = _safe_json(cache.get(f"market:ticker:{row.symbol}")) if cache else {}
        mark = float(ticker.get("last_price", row.entry_price))
        notional = float(row.entry_price) * float(row.quantity)
        leverage = float(max(row.leverage, 1))
        initial_margin = notional / leverage
        maintenance_margin = notional * 0.005
        unrealized = (mark - float(row.entry_price)) * float(row.quantity) if row.side == "long" else (float(row.entry_price) - mark) * float(row.quantity)

        side = "LONG" if row.side == "long" else "SHORT"
        position = FuturesPosition(
            symbol=row.symbol,
            side=side,
            entry_price=float(row.entry_price),
            mark_price=mark,
            position_size=float(row.quantity),
            notional_value=notional,
            leverage=leverage,
            initial_margin=initial_margin,
            maintenance_margin=maintenance_margin,
            unrealized_pnl=unrealized,
            liquidation_price=0.0,
            margin_ratio=0.0,
            distance_to_liquidation=0.0,
        )
        liq_price = calculate_liquidation_price(position)
        margin_ratio = calculate_margin_ratio(position)
        distance = calculate_distance_to_liquidation(position)
        funding_bias = _funding_payload(cache, row.symbol)
        pressure_payload = _market_pressure_payload(cache, row.symbol)

        positions.append(
            {
                "position_id": row.id,
                "symbol": row.symbol,
                "side": side,
                "strategy_id": strategy_map.get(row.id, "unknown"),
                "entry_price": float(row.entry_price),
                "mark_price": mark,
                "position_size": float(row.quantity),
                "notional_value": notional,
                "leverage": leverage,
                "initial_margin": initial_margin,
                "maintenance_margin": maintenance_margin,
                "unrealized_pnl": unrealized,
                "liquidation_price": liq_price,
                "margin_ratio": margin_ratio,
                "distance_to_liquidation": distance,
                "risk_level": liquidation_risk_level(distance),
                "funding_bias_score": funding_bias["funding_bias_score"],
                "funding_bias": funding_bias,
                "funding_rate": funding_bias.get("funding_rate", 0.0),
                "funding_skew": float(pressure_payload.get("funding_skew", funding_bias.get("funding_skew", 0.0))),
                "exchange_adl_indicator": float(pressure_payload.get("exchange_adl_indicator", min(abs(funding_bias.get("funding_rate", 0.0)) * 400, 1.0))),
                "open_interest_change": float(pressure_payload.get("open_interest_change", 0.0)),
                "long_short_ratio": float(pressure_payload.get("long_short_ratio", 1.0)),
                "liquidation_volume": float(pressure_payload.get("liquidation_volume", 0.0)),
                "volatility_regime": str(pressure_payload.get("volatility_regime", "NORMAL")).upper(),
                "cluster_exposure": float(pressure_payload.get("cluster_exposure", 0.0)),
            }
        )
    return positions


def build_futures_risk_status(db: Session, cache, user_id: str) -> dict:
    liquidation_aggregator = LiquidationRiskAggregator()
    cascade_detector = CascadeDetector()
    policy_engine = ProtectionPolicyEngine()
    liquidation_gate = LiquidationGate()
    deleverage_executor = EmergencyDeleverageExecutor()
    adl_detector = ADLRiskDetector()
    adl_aggregator = ADLPressureAggregator()
    adl_policy_engine = ADLProtectionPolicy()
    adl_gate = ADLGate()
    adl_exposure_reducer = ADLExposureReducer()

    positions = _build_futures_positions(db, cache, user_id)
    ticker = _safe_json(cache.get("market:ticker:BTCUSDT")) if cache else {}
    mark = float(ticker.get("last_price", 100.0))
    sizing = compute_position_sizing(db, user_id, mark)
    equity = float(sizing["equity"])
    total_notional = sum(float(item["notional_value"]) for item in positions)
    total_initial_margin = sum(float(item["initial_margin"]) for item in positions)
    portfolio_leverage = (total_notional / equity) if equity > 0 else 0.0
    margin_usage = (total_initial_margin / equity) * 100 if equity > 0 else 0.0
    avg_distance = sum(item["distance_to_liquidation"] for item in positions) / len(positions) if positions else 100.0

    guard = evaluate_margin_utilization(margin_usage)
    spread_payload = _safe_json(cache.get("market:spread:BTCUSDT")) if cache else {}
    kill_switch_payload = _safe_json(cache.get("pipeline:kill_switch")) if cache else {}
    volatility_spike = bool(abs(float(spread_payload.get("spread_bps", 0) or 0)) > 30)
    reject_rate = float((kill_switch_payload.get("execution_health", {}) or {}).get("reject_rate", 0.0))
    aggregation = liquidation_aggregator.evaluate_portfolio(positions)
    cascade = cascade_detector.evaluate(
        {
            "positions": aggregation.positions,
            "positions_at_risk": sum(1 for item in positions if item["distance_to_liquidation"] < 15),
            "volatility_spike": volatility_spike,
            "spread_widening": volatility_spike,
            "reject_rate": reject_rate,
            "slippage_spike": False,
            "correlated_cluster_risk": False,
        }
    )

    adl_symbol_rows = []
    for item in aggregation.positions:
        adl_result = adl_detector.evaluate_symbol(
            {
                "exchange_adl_indicator": item.get("exchange_adl_indicator", 0.0),
                "funding_rate": item.get("funding_rate", 0.0),
                "funding_skew": item.get("funding_skew", 0.0),
                "open_interest_change": item.get("open_interest_change", 0.0),
                "long_short_ratio": item.get("long_short_ratio", 1.0),
                "liquidation_volume": item.get("liquidation_volume", 0.0),
                "volatility_regime": item.get("volatility_regime", "NORMAL"),
            }
        )
        row = {
            "symbol": item.get("symbol"),
            "adl_risk_score": adl_result.adl_risk_score,
            "adl_risk_level": adl_result.adl_risk_level,
            "adl_pressure_side": adl_result.adl_pressure_side,
        }
        adl_symbol_rows.append(row)
        item["adl_risk_score"] = adl_result.adl_risk_score
        item["adl_risk_level"] = adl_result.adl_risk_level
        item["adl_pressure_side"] = adl_result.adl_pressure_side

    adl_state = adl_aggregator.aggregate(adl_symbol_rows)
    adl_policy = adl_policy_engine.evaluate(adl_state)

    policy = policy_engine.evaluate(
        liquidation_state=aggregation.risk_level,
        cascade_state=cascade.cascade_state,
        margin_state=guard["margin_state"],
        adl_state=adl_state["risk_level"],
    )

    policy_payload = {
        "policy_state": policy.policy_state,
        "policy_action": policy.policy_action,
        "reduce_ratio": policy.reduce_ratio,
        "leverage_cap": policy.leverage_cap,
        "reason_code": policy.reason_code,
    }

    gate_rejections: list[dict] = []
    adl_gate_rejection_total = 0
    for item in positions:
        gate = liquidation_gate.evaluate(
            distance_to_liquidation=item["distance_to_liquidation"],
            margin_usage=margin_usage,
            cascade_confirmed=cascade.cascade_state == "CASCADE_CONFIRMED",
            emergency_policy_active=policy.policy_action == "FREEZE",
            leverage=item["leverage"],
            leverage_cap=policy.leverage_cap,
        )
        adl_gate_result = adl_gate.evaluate(
            adl_risk_level=adl_state["risk_level"],
            adl_pressure_side=adl_state["dominant_side"],
            portfolio_adl_risk=adl_state["portfolio_adl_risk"],
            trade_side=item["side"],
        )
        if not adl_gate_result["adl_gate_pass"]:
            adl_gate_rejection_total += 1
        if not gate["gate_pass"]:
            gate_rejections.append(
                {
                    "symbol": item["symbol"],
                    "reason": gate["gate_reason"],
                    "all_reasons": gate["all_reasons"],
                    "gate_type": "LIQUIDATION",
                }
            )
        if not adl_gate_result["adl_gate_pass"]:
            gate_rejections.append(
                {
                    "symbol": item["symbol"],
                    "reason": adl_gate_result["reason"],
                    "all_reasons": adl_gate_result["all_reasons"],
                    "gate_type": "ADL",
                }
            )

    execution_plan = deleverage_executor.execute(aggregation.positions, policy_payload)
    deleverage_plan = build_deleverage_plan(aggregation.positions, policy.policy_action, float(policy.reduce_ratio))
    adl_reduce_plan = adl_exposure_reducer.build_plan(aggregation.positions, adl_state, adl_policy)
    funding_summary = {
        "avg_funding_bias_score": round(
            sum(item["funding_bias_score"] for item in positions) / len(positions),
            4,
        )
        if positions
        else 0.0,
        "dominant_bias": (
            max(positions, key=lambda item: item["funding_bias_score"]).get("funding_bias", {}).get("bias_direction")
            if positions
            else "NEUTRAL"
        ),
    }

    capital_recommendation = futures_capital_recommendation(total_equity=equity, futures_notional=total_notional)

    risk_checks = []
    for item in positions:
        check = evaluate_futures_risk(
            FuturesPosition(
                symbol=item["symbol"],
                side=item["side"],
                entry_price=item["entry_price"],
                mark_price=item["mark_price"],
                position_size=item["position_size"],
                notional_value=item["notional_value"],
                leverage=item["leverage"],
                initial_margin=item["initial_margin"],
                maintenance_margin=item["maintenance_margin"],
                unrealized_pnl=item["unrealized_pnl"],
                liquidation_price=item["liquidation_price"],
                margin_ratio=item["margin_ratio"],
                distance_to_liquidation=item["distance_to_liquidation"],
            ),
            {
                "portfolio_leverage": portfolio_leverage,
                "margin_usage": margin_usage,
                "distance_to_liquidation": item["distance_to_liquidation"],
            },
        )
        risk_checks.append({"symbol": item["symbol"], **check})

    critical_positions = [
        {
            "symbol": item["symbol"],
            "side": item["side"],
            "distance_to_liquidation": item["distance_to_liquidation"],
            "leverage": item["leverage"],
            "action": policy.policy_action,
            "adl_risk_level": item.get("adl_risk_level", "LOW"),
        }
        for item in aggregation.positions
        if item.get("risk_level") in {"WARNING", "CRITICAL"} or item.get("distance_to_liquidation", 100) < 15
    ]

    status = {
        "portfolio_leverage": round(portfolio_leverage, 4),
        "margin_usage": round(margin_usage, 4),
        "policy_state": policy.policy_state,
        "policy_action": policy.policy_action,
        "liquidation_risk": aggregation.risk_level,
        "liquidation_risk_score": round(aggregation.portfolio_risk_score / 100, 4),
        "adl_risk_score": adl_state["portfolio_adl_risk"],
        "funding_bias": funding_summary,
        "active_positions": len(positions),
        "risk_check_result": "reject" if any(item["risk_check_result"] == "reject" for item in risk_checks) else "allow",
        "risk_reason": sorted({reason for item in risk_checks for reason in item.get("risk_reason", [])}),
        "risk_checks": risk_checks,
        "gate_state": {
            "policy_action": policy.policy_action,
            "gate_rejection_total": len(gate_rejections),
            "adl_gate_rejection_total": adl_gate_rejection_total,
            "gate_rejections": gate_rejections,
        },
        "critical_positions": critical_positions,
        "positions": aggregation.positions,
        "portfolio_risk_score": aggregation.portfolio_risk_score,
        "position_risk_score": aggregation.position_risk_score,
        "dominant_risk_factor": aggregation.dominant_risk_factor,
        "cascade_status": cascade.cascade_state,
        "cascade_score": cascade.cascade_score,
        "cascade_risk_symbols": cascade.risk_symbols,
        "margin_state": guard["margin_state"],
        "avg_distance_to_liquidation": round(avg_distance, 4),
        "deleverage_plan": deleverage_plan,
        "execution_plan": {
            "positions_to_reduce": execution_plan.positions_to_reduce,
            "reduce_ratio": execution_plan.reduce_ratio,
            "execution_priority": execution_plan.execution_priority,
        },
        "adl_state": adl_state,
        "adl_policy": adl_policy,
        "adl_reduce_plan": adl_reduce_plan,
        "adl_symbol_details": adl_state.get("symbol_details", []),
        "adl_gate_rejection_total": adl_gate_rejection_total,
        "capital_recommendation": capital_recommendation,
        "decision_trace": {
            "snapshot_positions": len(positions),
            "liquidation_risk": aggregation.risk_level,
            "cascade_state": cascade.cascade_state,
            "adl_risk_level": adl_state["risk_level"],
            "policy_action": policy.policy_action,
            "gate_rejections": len(gate_rejections),
            "execution_actions": len(execution_plan.positions_to_reduce) + len(adl_reduce_plan.get("actions", [])),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    metrics = build_futures_liquidation_metrics_snapshot({
        **status,
        "policy_action": policy.policy_action,
        "gate_rejection_total": len(gate_rejections),
    })
    if cache:
        cache.set("futures:risk:status", json.dumps(status))
        cache.set("futures:risk:metrics", json.dumps(metrics))
        timeline_raw = _safe_json(cache.get("futures:risk:policy_timeline")) or []
        timeline_raw = ([
            {
                "ts": status["updated_at"],
                "policy_action": policy.policy_action,
                "risk_level": aggregation.risk_level,
                "cascade": cascade.cascade_state,
                "margin_state": guard["margin_state"],
                "adl_risk_level": adl_state["risk_level"],
            }
        ] + timeline_raw)[:50]
        cache.set("futures:risk:policy_timeline", json.dumps(timeline_raw))
        status["policy_timeline"] = timeline_raw
    return status


def build_futures_liquidation_status(db: Session, cache, user_id: str) -> dict:
    status = build_futures_risk_status(db, cache, user_id)
    return {
        "policy_state": status["policy_action"],
        "portfolio_risk_score": status["portfolio_risk_score"],
        "cascade_status": status["cascade_status"],
        "margin_usage": status["margin_usage"],
        "positions_at_risk": len(status["critical_positions"]),
        "critical_positions": status["critical_positions"],
        "gate_rejections": status["gate_state"]["gate_rejections"],
        "adl_risk_score": status["adl_risk_score"],
        "adl_risk_level": (status.get("adl_state") or {}).get("risk_level", "LOW"),
        "adl_pressure_side": (status.get("adl_state") or {}).get("dominant_side", "NONE"),
        "adl_symbols_at_risk": (status.get("adl_state") or {}).get("risk_symbols", []),
        "adl_policy": status.get("adl_policy", {}),
        "policy_timeline": status.get("policy_timeline", []),
        "symbol_risk_heatmap": [
            {
                "symbol": item.get("symbol"),
                "risk_score": item.get("position_risk_score"),
                "risk_level": item.get("risk_level"),
                "distance_to_liquidation": item.get("distance_to_liquidation"),
                "adl_risk_score": item.get("adl_risk_score", 0.0),
                "adl_risk_level": item.get("adl_risk_level", "LOW"),
            }
            for item in status.get("positions", [])
        ],
        "decision_trace": status.get("decision_trace", {}),
        "updated_at": status["updated_at"],
    }


def build_futures_adl_status(db: Session, cache, user_id: str) -> dict:
    status = build_futures_risk_status(db, cache, user_id)
    adl_state = status.get("adl_state", {})
    adl_policy = status.get("adl_policy", {})
    return {
        "portfolio_adl_risk": adl_state.get("portfolio_adl_risk", 0.0),
        "risk_level": adl_state.get("risk_level", "LOW"),
        "dominant_side": adl_state.get("dominant_side", "NONE"),
        "symbols_at_risk": adl_state.get("risk_symbols", []),
        "adl_policy_state": adl_policy.get("adl_policy_action", "ALLOW"),
        "updated_at": status.get("updated_at"),
    }
