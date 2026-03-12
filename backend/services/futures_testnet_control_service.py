from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.execution.futures_execution_contract import FuturesExecutionRequest
from core.execution.futures_execution_parity_check import FuturesExecutionParityCheck
from core.execution.futures_order_preflight import FuturesOrderPreflight
from core.execution.futures_retry_policy import FuturesRetryPolicy
from core.execution.futures_slippage_tracker import FuturesSlippageTracker
from core.execution.futures_testnet_release_gate import FuturesTestnetReleaseGate
from core.observability.futures_execution_audit import build_futures_execution_audit_event
from models import TestnetExecutionLog, UserExchangeSetting
from services.futures_execution_quality_service import (
    build_execution_quality_rolling_7d,
    build_execution_quality_snapshot,
    enrich_with_architecture_checklist,
)
from services.futures_strategy_service import get_futures_decision_diagnostics
from services.live_mode_service import adapter, get_or_create_live_config, release_gate_view


def _latest_execution_row(db: Session):
    return db.query(TestnetExecutionLog).order_by(TestnetExecutionLog.created_at.desc()).first()


def _has_live_mode_credentials(db: Session) -> bool:
    return (
        db.query(UserExchangeSetting)
        .filter(UserExchangeSetting.mode == "live")
        .count()
        > 0
    )


def _secret_isolation_status(db: Session) -> dict:
    has_live_credentials = _has_live_mode_credentials(db)
    return {
        "testnet_live_secret_isolation_pass": not has_live_credentials,
        "has_live_credentials": has_live_credentials,
        "reason_code": "LIVE_CREDENTIALS_FORBIDDEN" if has_live_credentials else "PASS",
    }


def build_testnet_release_gate_status(db: Session) -> dict:
    config = get_or_create_live_config(db)
    base_gate = release_gate_view(db, environment="stage")
    isolation = _secret_isolation_status(db)

    gate = FuturesTestnetReleaseGate().evaluate(
        live_mode_enabled=bool(config.live_mode_enabled),
        release_gate_status=str(base_gate.get("status") or "BLOCKED"),
        has_live_credentials=bool(isolation.get("has_live_credentials")),
    )
    return {
        "status": gate["status"],
        "order_path_open": gate["order_path_open"],
        "reasons": gate["reasons"],
        "base_release_gate": base_gate,
        "secret_isolation": isolation,
        "testnet_enabled": bool(config.live_mode_enabled),
        "safe_mode_enabled": bool(config.safe_mode_enabled),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_testnet_status(db: Session, cache, user_id: str) -> dict:
    connectivity = adapter.ping()
    gate = build_testnet_release_gate_status(db)
    config = get_or_create_live_config(db)
    latest = _latest_execution_row(db)
    decision_diagnostics = get_futures_decision_diagnostics(db, cache, user_id, refresh=False)

    expected_price = float(getattr(latest, "expected_price", 0.0) or 0.0) if latest else 0.0
    fill_price = float(getattr(latest, "fill_price", 0.0) or 0.0) if latest else 0.0
    slippage = FuturesSlippageTracker().evaluate(
        symbol=getattr(latest, "symbol", "BTCUSDT") if latest else "BTCUSDT",
        order_type="MARKET",
        expected_price=expected_price,
        realized_price=fill_price,
    )
    parity = FuturesExecutionParityCheck().evaluate(
        paper_fill_price=expected_price,
        testnet_fill_price=fill_price,
        tolerance_bps=20.0,
    )

    preflight_template = FuturesOrderPreflight().evaluate(
        request=(
            FuturesExecutionRequest(
                symbol="BTCUSDT",
                side="BUY",
                order_type="MARKET",
                quantity=0.001,
                leverage=min(float(config.leverage_cap or 1), 5.0),
                reduce_only=False,
                client_order_id="phase55-template-order",
                decision_trace_id="phase55-template-trace",
                strategy="futures_trend_follow_v1",
                reason_context={"template": True},
            )
        ),
        context={
            "active_symbols": list(config.symbol_whitelist or []),
            "max_trade_leverage": min(float(config.leverage_cap or 5), 5.0),
            "current_position_qty": 0.0,
            "current_position_side": "NONE",
            "margin_available": float(config.max_notional_exposure or 0.0),
            "margin_required": 0.0,
            "testnet_mode_enabled": bool(config.live_mode_enabled),
            "release_gate_status": gate["status"],
            "environment": "testnet",
        },
    )
    retry_policy = FuturesRetryPolicy()
    retry_matrix = [
        {
            "error_code": code,
            "decision": retry_policy.classify(code),
            "backoff_attempt_1": retry_policy.next_backoff_seconds(1, code),
            "backoff_attempt_2": retry_policy.next_backoff_seconds(2, code),
        }
        for code in ["TIMEOUT", "RATE_LIMIT", "INVALID_ORDER", "INSUFFICIENT_MARGIN", "DUPLICATE_CLIENT_ORDER"]
    ]

    audit_sample = build_futures_execution_audit_event(
        action="testnet_status_snapshot",
        symbol=getattr(latest, "symbol", "BTCUSDT") if latest else "BTCUSDT",
        status=str(getattr(latest, "status", "NO_EXECUTION") if latest else "NO_EXECUTION"),
        details={
            "gate_status": gate["status"],
            "order_path_open": gate["order_path_open"],
        },
    )

    execution_quality = build_execution_quality_snapshot(
        db,
        user_id,
        days=7,
        false_allow_count=int(decision_diagnostics.get("false_allow_count", 0)),
        false_reject_count=int(decision_diagnostics.get("false_reject_count", 0)),
    )

    layer_map = decision_diagnostics.get("decision_layer_distribution") or {}
    false_allow_reject_comparison_by_layer = [
        {
            "layer": layer,
            "false_allow": int(layer_map.get(layer, 0)) if layer == "GATE" else 0,
            "false_reject": int(layer_map.get(layer, 0)) if layer != "GATE" else 0,
        }
        for layer in sorted(layer_map.keys())
    ]
    execution_quality["false_allow_reject_comparison_by_layer"] = false_allow_reject_comparison_by_layer

    snapshot = {
        "default_mode": "paper",
        "testnet_enabled": bool(config.live_mode_enabled),
        "safe_mode_enabled": bool(config.safe_mode_enabled),
        "live_endpoint_access": False,
        "connectivity": connectivity,
        "release_gate": gate,
        "preflight_template": preflight_template,
        "retry_policy": retry_matrix,
        "slippage": {
            "expected_slippage": slippage["expected_slippage"],
            "realized_slippage": slippage["realized_slippage"],
            "delta": slippage["slippage_delta"],
            "latest_symbol": slippage["symbol"],
        },
        "reconciler_state": str(getattr(latest, "status", "unknown_needs_reconcile") if latest else "unknown_needs_reconcile").lower(),
        "parity_check": parity,
        "secret_isolation": gate["secret_isolation"],
        "execution_quality": execution_quality,
        "audit_sample": audit_sample,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return enrich_with_architecture_checklist(snapshot)


def build_testnet_execution_quality(db: Session, cache, user_id: str) -> dict:
    decision_diagnostics = get_futures_decision_diagnostics(db, cache, user_id, refresh=False)
    snapshot = build_execution_quality_snapshot(
        db,
        user_id,
        days=7,
        false_allow_count=int(decision_diagnostics.get("false_allow_count", 0)),
        false_reject_count=int(decision_diagnostics.get("false_reject_count", 0)),
    )
    snapshot["false_allow_reject_comparison_by_layer"] = [
        {
            "layer": layer,
            "count": int(count),
        }
        for layer, count in (decision_diagnostics.get("decision_layer_distribution") or {}).items()
    ]
    snapshot["architecture_checklist_15"] = []
    return snapshot


def build_testnet_execution_quality_rolling_7d(db: Session, cache, user_id: str) -> dict:
    decision_diagnostics = get_futures_decision_diagnostics(db, cache, user_id, refresh=False)
    return build_execution_quality_rolling_7d(
        db,
        user_id,
        false_allow_count=int(decision_diagnostics.get("false_allow_count", 0)),
        false_reject_count=int(decision_diagnostics.get("false_reject_count", 0)),
    )
