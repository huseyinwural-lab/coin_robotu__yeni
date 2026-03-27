# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

from db import SessionLocal

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from models import ExecutionPolicy, User, UserRole
from services.execution_environment_control_service import (
    list_safe_mode_states,
    normalize_environment,
    upsert_environment_override,
)
from services.execution_governance_service import seed_default_strategy_bindings
from services.execution_policy_service import (
    append_execution_policy_decision_log,
    ensure_dynamic_execution_policies,
    evaluate_execution_policy_engine,
)


def _create_user(db) -> User:
    row = User(
        email=f"env-phase1-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("EnvPhase1Strong123!"),
        role=UserRole.ADMIN,
        is_active=True,
        approval_status="approved",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_policy(db, strategy: str):
    row = db.query(ExecutionPolicy).filter(ExecutionPolicy.strategy_type == strategy).first()
    if row is None:
        row = ExecutionPolicy(
            strategy_type=strategy,
            execution_style="balanced",
            order_preference="limit_first",
            timeout_seconds=8,
            fallback_behavior="market_fallback",
            partial_fill_tolerance_pct=60,
            execution_urgency="medium",
            retry_limit=1,
            is_active=True,
        )
        db.add(row)
    row.policy_code = f"phase1:{strategy}"
    row.policy_scope = "strategy"
    row.scope_key = strategy
    row.rules_payload = {
        "runtime": {"require_market_data": True, "dependency_timeout_ms": 5000},
        "risk": {
            "max_order_notional": 100000,
            "max_symbol_exposure": 500000,
            "max_strategy_exposure": 500000,
            "max_user_exposure": 500000,
            "max_portfolio_exposure": 500000,
        },
        "execution": {"max_price_deviation_bps": 50, "min_fill_ratio": 0.7, "max_fill_latency_ms": 5000},
        "post_trade": {"max_slippage_bps": 100, "max_exposure_after_trade": 500000, "max_leverage_after_trade": 4, "min_liquidation_distance_pct": 3},
    }
    db.commit()


def test_environment_normalization_mapping():
    assert normalize_environment("testnet") == "DEV"
    assert normalize_environment("staging") == "STAGING"
    assert normalize_environment("prod") == "PROD"


def test_environment_override_is_deterministic_and_applied():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        user = _create_user(db)
        strategy = "phase1_env_override_strategy"
        _ensure_policy(db, strategy)
        seed_default_strategy_bindings(db, strategy_ids=[strategy])

        upsert_environment_override(
            db,
            environment="DEV",
            scope_type="STRATEGY",
            scope_value=strategy,
            priority=10,
            override_payload={
                "set_rules": {
                    "risk.max_order_notional": 50,
                }
            },
            actor_user_id=user.id,
            change_summary="DEV strict order cap",
        )
        db.commit()

        dev_result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": strategy,
                "symbol": "BTCUSDT",
                "environment": "testnet",
                "market_type": "spot",
                    "intent_type": "CLOSE_POSITION",
                    "reduce_only": True,
                "proposed_notional": 100.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )
        prod_result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": strategy,
                "symbol": "BTCUSDT",
                "environment": "live",
                "market_type": "spot",
                    "intent_type": "CLOSE_POSITION",
                    "reduce_only": True,
                "proposed_notional": 100.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )

        assert str(dev_result.get("enforced_action") or "").upper() == "BLOCK"
        assert (dev_result.get("trace") or {}).get("environment", {}).get("override_trace")
        assert str(prod_result.get("enforced_action") or "").upper() == "ALLOW"
    finally:
        db.close()


def test_safe_mode_auto_activation_and_enforcement():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        user = _create_user(db)
        strategy = "phase1_safe_mode_strategy"
        _ensure_policy(db, strategy)
        seed_default_strategy_bindings(db, strategy_ids=[strategy])

        for idx in range(6):
            append_execution_policy_decision_log(
                db,
                lifecycle_action="submit",
                stage="VIOLATION",
                context={
                    "trace_id": f"safe-mode-trace-{idx}",
                    "pipeline_id": f"safe-mode-pipe-{idx}",
                    "intent_token": str(uuid.uuid4()),
                    "user_id": user.id,
                    "portfolio_id": f"default:{user.id}",
                    "strategy_binding": strategy,
                    "environment": "DEV",
                    "symbol": "BTCUSDT",
                    "execution_mode": "SIMULATION",
                    "strategy_risk_class": "HIGH",
                },
                policy_result={
                    "recommended_action": "BLOCK",
                    "enforced_action": "BLOCK",
                    "rollout_mode": "full",
                    "standardized_reject": {
                        "reason_code": "RISK_ORDER_BREACH",
                        "reason_message": "risk breach",
                        "policy_id": "p",
                        "rule_id": "r",
                        "stage": "PRE_TRADE",
                        "severity": "CRITICAL",
                        "action_taken": "BLOCK",
                    },
                    "trace": {"action_taken": "BLOCK", "metrics_snapshot": {}},
                    "metrics_snapshot": {},
                },
                action_taken="BLOCK",
                is_violation=True,
            )
        db.commit()

        result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": strategy,
                "symbol": "BTCUSDT",
                "environment": "testnet",
                "market_type": "spot",
                "intent_type": "OPEN_POSITION",
                "reduce_only": False,
                "proposed_notional": 10.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )

        assert str(result.get("enforced_action") or "").upper() == "BLOCK"
        assert (result.get("trace") or {}).get("safe_mode", {}).get("active") is True
        reason_code = (result.get("standardized_reject") or {}).get("reason_code") or ""
        assert reason_code.startswith("SAFE_MODE_")

        safe_states = list_safe_mode_states(db, environment="DEV", active_only=True)
        assert safe_states
        assert safe_states[0]["trigger_reason"] in {
            "critical_violation_rate_high",
            "failsafe_spike_detected",
            "release_gate_fail",
        }
    finally:
        db.close()
