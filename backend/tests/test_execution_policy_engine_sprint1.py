# ruff: noqa: E402
import json
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import SessionLocal, redis_client
from core.security import hash_password
from models import BrandSetting, ExecutionPolicy, LiveActivationConfig, User, UserRole
from services.execution_intent_service import preview_execution_intent
from services.execution_pipeline_orchestrator import run_execution_pipeline
from services.execution_policy_service import ensure_dynamic_execution_policies


def _create_user(db) -> User:
    row = User(
        email=f"policy-sprint1-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("PolicySprint1Strong123!"),
        role=UserRole.USER,
        is_active=True,
        approval_status="approved",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _set_rollout_mode(db, mode: str) -> None:
    row = db.query(BrandSetting).filter(BrandSetting.id == "default").first()
    if row is None:
        row = BrandSetting(id="default", metadata_json={})
        db.add(row)
        db.flush()

    metadata = dict(row.metadata_json or {})
    metadata["execution_policy_engine"] = {
        "enabled": True,
        "rollout_mode": mode,
        "progression": ["shadow", "soft", "partial", "full"],
        "fail_safe_mode": "block",
        "partial_live_only": True,
    }
    row.metadata_json = metadata
    db.commit()


def _set_live_safety(db, *, trading_enabled: bool, kill_switch_enabled: bool) -> None:
    row = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
    if row is None:
        row = LiveActivationConfig(id="global")
        db.add(row)
        db.flush()
    row.trading_enabled = trading_enabled
    row.kill_switch_enabled = kill_switch_enabled
    db.commit()


def _upsert_strategy_policy(db, *, strategy_id: str, max_order_notional: float) -> None:
    policy_code = f"sprint1:test:{strategy_id}"
    row = db.query(ExecutionPolicy).filter(ExecutionPolicy.policy_code == policy_code).first()
    if row is None:
        row = ExecutionPolicy(
            strategy_type=strategy_id,
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

    row.policy_code = policy_code
    row.policy_scope = "strategy"
    row.scope_key = strategy_id
    row.priority = 40
    row.override_behavior = "merge"
    row.conditions_payload = {}
    row.rules_payload = {
        "runtime": {"require_market_data": True, "dependency_timeout_ms": 500},
        "risk": {
            "max_order_notional": max_order_notional,
            "max_symbol_exposure": 200000,
            "max_strategy_exposure": 200000,
            "max_user_exposure": 300000,
            "max_portfolio_exposure": 300000,
        },
        "safety": {
            "max_loss_usdt": 100000,
            "max_drawdown_pct": 99,
            "circuit_breaker_window_minutes": 15,
            "circuit_breaker_violation_threshold": 100,
            "strategy_kill_switches": [],
            "symbol_kill_switches": [],
            "environment_kill_switches": [],
        },
    }
    row.enforcement_action = "BLOCK"
    row.severity = "HIGH"
    row.is_active = True
    db.commit()


def _payload(*, strategy_binding: str, environment: str, position_size_value: float = 120.0) -> dict:
    return {
        "source_type": "manual",
        "source_ref_id": f"sprint1-{uuid.uuid4().hex[:8]}",
        "intent_type": "OPEN_POSITION",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": position_size_value,
        "execution_mode": "manual",
        "strategy_binding": strategy_binding,
        "environment": environment,
    }


def _seed_market_data() -> None:
    try:
        redis_client.set("market:ticker:BTCUSDT", json.dumps({"last_price": 44000.0}))
    except Exception:
        pass


def test_same_order_different_policy_produces_different_outcome():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="sprint1_allow_strategy", max_order_notional=100000)
        _upsert_strategy_policy(db, strategy_id="sprint1_block_strategy", max_order_notional=10)
        user = _create_user(db)

        allowed_intent, allowed_validation = preview_execution_intent(
            db,
            user.id,
            _payload(strategy_binding="sprint1_allow_strategy", environment="testnet", position_size_value=120.0),
        )
        blocked_intent, blocked_validation = preview_execution_intent(
            db,
            user.id,
            _payload(strategy_binding="sprint1_block_strategy", environment="testnet", position_size_value=120.0),
        )

        assert allowed_intent.status == "PREVIEWED"
        assert allowed_validation.get("validation_status") == "valid"
        assert blocked_intent.status == "REJECTED"
        assert blocked_validation.get("validation_status") == "rejected"
        assert any(code.startswith("RISK_ORDER_BREACH") for code in (blocked_validation.get("reject_reason_codes") or []))
    finally:
        db.close()


def test_strategy_policy_missing_is_soft_non_live_and_block_live():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        user = _create_user(db)

        non_live_intent, non_live_validation = preview_execution_intent(
            db,
            user.id,
            _payload(strategy_binding="sprint1_missing_strategy", environment="testnet"),
        )
        live_intent, live_validation = preview_execution_intent(
            db,
            user.id,
            _payload(strategy_binding="sprint1_missing_strategy", environment="live"),
        )

        assert non_live_intent.status == "PREVIEWED"
        assert non_live_validation.get("validation_status") == "valid"
        assert (non_live_validation.get("standardized_reject") or {}).get("reason_code") == "STRATEGY_POLICY_MISSING"

        assert live_intent.status == "REJECTED"
        assert live_validation.get("validation_status") == "rejected"
        assert "STRATEGY_POLICY_MISSING" in (live_validation.get("reject_reason_codes") or [])
    finally:
        db.close()


def test_risk_breach_rejected_in_pretrade():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="sprint1_risk_breach_strategy", max_order_notional=5)
        user = _create_user(db)

        intent, validation = preview_execution_intent(
            db,
            user.id,
            _payload(strategy_binding="sprint1_risk_breach_strategy", environment="live", position_size_value=120.0),
        )

        assert intent.status == "REJECTED"
        assert validation.get("validation_status") == "rejected"
        reject_codes = validation.get("reject_reason_codes") or []
        assert any(code.startswith("RISK_ORDER_BREACH") for code in reject_codes)
    finally:
        db.close()


def test_kill_switch_blocks_all_orders_in_live():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=True)
        _upsert_strategy_policy(db, strategy_id="sprint1_killswitch_strategy", max_order_notional=100000)
        user = _create_user(db)

        intent, validation = preview_execution_intent(
            db,
            user.id,
            _payload(strategy_binding="sprint1_killswitch_strategy", environment="live"),
        )

        assert intent.status == "REJECTED"
        assert validation.get("validation_status") == "rejected"
        assert "SAFETY_GLOBAL_KILL_SWITCH" in (validation.get("reject_reason_codes") or [])
    finally:
        db.close()


def test_shadow_mode_generates_decision_but_submit_continues():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "shadow")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        user = _create_user(db)

        intent, validation = preview_execution_intent(
            db,
            user.id,
            _payload(strategy_binding="sprint1_shadow_missing_strategy", environment="testnet"),
        )

        assert intent.status == "PREVIEWED"
        assert validation.get("validation_status") == "valid"
        assert (validation.get("standardized_reject") or {}).get("reason_code") == "STRATEGY_POLICY_MISSING"

        pipeline_result = run_execution_pipeline(
            db,
            lifecycle_action="submit",
            context={
                "intent_id": intent.id,
                "intent_token": intent.intent_token,
                "user_id": user.id,
                "portfolio_id": user.id,
                "strategy_binding": "sprint1_shadow_missing_strategy",
                "symbol": "BTCUSDT",
                "environment": "testnet",
                "market_type": "spot",
                "margin_mode": "",
                "volatility_pct": 0.0,
                "risk_score": 0.0,
                "proposed_notional": 120.0,
                "market_data_available": True,
                "portfolio_drawdown_pct": 0.0,
                "market_snapshot": {"last_price": 44000},
            },
        )
        assert str(pipeline_result.get("recommended_action") or "").upper() == "BLOCK"
        assert str(pipeline_result.get("enforced_action") or "").upper() == "ALLOW"
        stage_names = [str(item.get("stage") or "") for item in (pipeline_result.get("stages") or [])]
        assert "EXECUTION" in stage_names
        assert "POST_TRADE" in stage_names
    finally:
        db.close()
