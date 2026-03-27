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
from models import BrandSetting, ExecutionPolicy, LiveActivationConfig, Position, User, UserRole
from services.execution_pipeline_orchestrator import run_execution_pipeline
import services.execution_policy_service as execution_policy_service
from services.execution_governance_service import seed_default_strategy_bindings
from services.execution_policy_service import (
    ensure_dynamic_execution_policies,
    ensure_user_default_portfolio,
    evaluate_execution_policy_engine,
)


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


def _upsert_strategy_policy(
    db,
    *,
    strategy_id: str,
    max_order_notional: float,
    max_price_deviation_bps: float = 50.0,
    max_slippage_bps: float = 80.0,
    max_exposure_after_trade: float = 500000.0,
) -> None:
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
        "runtime": {"require_market_data": True, "dependency_timeout_ms": 5000},
        "execution": {
            "max_price_deviation_bps": max_price_deviation_bps,
            "min_fill_ratio": 0.7,
            "max_fill_latency_ms": 5000,
        },
        "post_trade": {
            "max_slippage_bps": max_slippage_bps,
            "max_exposure_after_trade": max_exposure_after_trade,
            "max_leverage_after_trade": 4.0,
            "min_liquidation_distance_pct": 3.0,
        },
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


def _submit_context(*, user_id: str, intent_token: str, strategy_binding: str, environment: str = "testnet") -> dict:
    return {
        "intent_token": intent_token,
        "user_id": user_id,
        "portfolio_id": f"default:{user_id}",
        "strategy_binding": strategy_binding,
        "symbol": "BTCUSDT",
        "side": "buy",
        "environment": environment,
        "market_type": "spot",
        "margin_mode": "",
        "volatility_pct": 0.0,
        "risk_score": 0.0,
        "proposed_notional": 120.0,
        "requested_price": 100.0,
        "requested_qty": 1.2,
        "execution_result": {
            "executed_price": 100.0,
            "executed_qty": 1.2,
            "status": "filled",
            "latency_ms": 120.0,
            "exposure_after_trade": 120.0,
            "leverage_after_trade": 1.0,
            "liquidation_distance_after_trade": 15.0,
        },
        "market_data_available": True,
        "portfolio_drawdown_pct": 0.0,
        "portfolio_equity": 10000.0,
        "market_snapshot": {"last_price": 100.0},
    }


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

        allowed = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "sprint1_allow_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "testnet",
                "market_type": "spot",
                "proposed_notional": 120.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )
        blocked = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "sprint1_block_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "testnet",
                "market_type": "spot",
                "proposed_notional": 120.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )

        assert str(allowed.get("enforced_action") or "").upper() == "ALLOW"
        assert str(blocked.get("enforced_action") or "").upper() == "BLOCK"
        assert (blocked.get("standardized_reject") or {}).get("reason_code") == "RISK_ORDER_BREACH"
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

        non_live = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "sprint1_missing_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "testnet",
                "market_type": "spot",
                "proposed_notional": 120.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )
        live = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "sprint1_missing_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "live",
                "market_type": "spot",
                "proposed_notional": 120.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )

        assert str(non_live.get("recommended_action") or "").upper() == "BLOCK"
        assert str(non_live.get("enforced_action") or "").upper() == "ALLOW"
        assert (non_live.get("standardized_reject") or {}).get("reason_code") == "STRATEGY_POLICY_MISSING"

        assert str(live.get("enforced_action") or "").upper() == "BLOCK"
        assert (live.get("standardized_reject") or {}).get("reason_code") == "STRATEGY_POLICY_MISSING"
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

        result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "sprint1_risk_breach_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "live",
                "market_type": "spot",
                "proposed_notional": 120.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )

        assert str(result.get("enforced_action") or "").upper() == "BLOCK"
        assert (result.get("standardized_reject") or {}).get("reason_code") == "RISK_ORDER_BREACH"
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

        result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "sprint1_killswitch_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "live",
                "market_type": "spot",
                "proposed_notional": 120.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )

        assert str(result.get("enforced_action") or "").upper() == "BLOCK"
        assert (result.get("standardized_reject") or {}).get("reason_code") == "SAFETY_GLOBAL_KILL_SWITCH"
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

        pipeline_result = run_execution_pipeline(
            db,
            lifecycle_action="submit",
            context={
                **_submit_context(
                    user_id=user.id,
                    intent_token=str(uuid.uuid4()),
                    strategy_binding="sprint1_shadow_missing_strategy",
                    environment="testnet",
                ),
                "intent_id": str(uuid.uuid4()),
            },
        )
        assert str(pipeline_result.get("recommended_action") or "").upper() == "BLOCK"
        assert str(pipeline_result.get("enforced_action") or "").upper() == "ALLOW"
        stage_names = [str(item.get("stage") or "") for item in (pipeline_result.get("stages") or [])]
        assert "EXECUTION" in stage_names
        assert "POST_TRADE" in stage_names
    finally:
        db.close()


def test_shadow_mode_failsafe_market_data_missing_hard_blocks():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _set_rollout_mode(db, "shadow")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="sprint1_failsafe_strategy", max_order_notional=100000)
        seed_default_strategy_bindings(db, strategy_ids=["sprint1_failsafe_strategy"])
        user = _create_user(db)

        result = run_execution_pipeline(
            db,
            lifecycle_action="preview",
            context={
                **_submit_context(
                    user_id=user.id,
                    intent_token=str(uuid.uuid4()),
                    strategy_binding="sprint1_failsafe_strategy",
                    environment="testnet",
                ),
                "market_data_available": False,
            },
        )

        reject = result.get("standardized_reject") or {}
        assert str(result.get("enforced_action") or "ALLOW").upper() == "BLOCK"
        assert reject.get("reason_code") == "FAILSAFE_MARKET_DATA_MISSING"
        assert reject.get("action_taken") == "HARD_BLOCK"
    finally:
        db.close()


def test_policy_load_error_always_hard_blocks(monkeypatch):
    db = SessionLocal()
    try:
        _set_rollout_mode(db, "shadow")
        user = _create_user(db)

        def _boom(*args, **kwargs):
            raise RuntimeError("policy_loader_down")

        monkeypatch.setattr(execution_policy_service, "_resolve_effective_rules", _boom)

        result = evaluate_execution_policy_engine(
            db,
            {
                    "user_id": user.id,
                    "portfolio_id": f"default:{user.id}",
                "strategy_binding": "trend_following",
                "symbol": "BTCUSDT",
                "environment": "testnet",
                "market_data_available": True,
                "proposed_notional": 10.0,
            },
            stage="PRE_TRADE",
        )

        reject = result.get("standardized_reject") or {}
        assert str(result.get("enforced_action") or "ALLOW").upper() == "BLOCK"
        assert reject.get("reason_code") == "FAILSAFE_POLICY_LOAD_ERROR"
        assert reject.get("action_taken") == "HARD_BLOCK"
    finally:
        db.close()


def test_risk_compute_error_always_hard_blocks(monkeypatch):
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _set_rollout_mode(db, "shadow")
        _upsert_strategy_policy(db, strategy_id="sprint1_risk_error_strategy", max_order_notional=100000)
        user = _create_user(db)

        def _boom(*args, **kwargs):
            raise RuntimeError("risk_engine_crash")

        monkeypatch.setattr(execution_policy_service, "_compute_multi_layer_risk", _boom)

        result = evaluate_execution_policy_engine(
            db,
            {
                    "user_id": user.id,
                    "portfolio_id": f"default:{user.id}",
                "strategy_binding": "sprint1_risk_error_strategy",
                "symbol": "BTCUSDT",
                "environment": "testnet",
                "market_data_available": True,
                "proposed_notional": 10.0,
            },
            stage="PRE_TRADE",
        )

        reject = result.get("standardized_reject") or {}
        assert str(result.get("enforced_action") or "ALLOW").upper() == "BLOCK"
        assert reject.get("reason_code") == "FAILSAFE_RISK_COMPUTE_ERROR"
        assert reject.get("action_taken") == "HARD_BLOCK"
    finally:
        db.close()


def test_execution_stage_missing_input_hard_blocks():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _set_rollout_mode(db, "shadow")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="sprint1_execution_input_strategy", max_order_notional=100000)
        user = _create_user(db)

        result = run_execution_pipeline(
            db,
            lifecycle_action="submit",
            context={
                **_submit_context(
                    user_id=user.id,
                    intent_token=str(uuid.uuid4()),
                    strategy_binding="sprint1_execution_input_strategy",
                    environment="testnet",
                ),
                "requested_price": 0,
                "execution_result": {},
            },
        )

        reject = result.get("standardized_reject") or {}
        assert str(result.get("enforced_action") or "ALLOW").upper() == "BLOCK"
        assert reject.get("reason_code") == "FAILSAFE_ENGINE_UNAVAILABLE"
        assert reject.get("action_taken") == "HARD_BLOCK"
    finally:
        db.close()


def test_execution_deviation_creates_execution_violation():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(
            db,
            strategy_id="sprint1_exec_deviation_strategy",
            max_order_notional=100000,
            max_price_deviation_bps=5,
            max_slippage_bps=5000,
            max_exposure_after_trade=500000,
        )
        user = _create_user(db)
        _seed_market_data()

        result = run_execution_pipeline(
            db,
            lifecycle_action="submit",
            context={
                **_submit_context(
                    user_id=user.id,
                    intent_token=str(uuid.uuid4()),
                    strategy_binding="sprint1_exec_deviation_strategy",
                    environment="testnet",
                ),
                "execution_result": {
                    "executed_price": 110.0,
                    "executed_qty": 1.2,
                    "status": "filled",
                    "latency_ms": 200.0,
                    "exposure_after_trade": 120.0,
                    "leverage_after_trade": 1.0,
                    "liquidation_distance_after_trade": 20.0,
                },
            },
        )

        execution_stage = next((item for item in (result.get("stages") or []) if item.get("stage") == "EXECUTION"), {})
        execution_reject = execution_stage.get("standardized_reject") or {}
        assert execution_reject.get("reason_code") == "EXECUTION_PRICE_DEVIATION"
        assert str(result.get("enforced_action") or "ALLOW").upper() == "ALLOW"
    finally:
        db.close()


def test_post_trade_exposure_breach_creates_violation():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(
            db,
            strategy_id="sprint1_post_breach_strategy",
            max_order_notional=100000,
            max_price_deviation_bps=1000,
            max_slippage_bps=1000,
            max_exposure_after_trade=50,
        )
        user = _create_user(db)
        _seed_market_data()

        result = run_execution_pipeline(
            db,
            lifecycle_action="submit",
            context={
                **_submit_context(
                    user_id=user.id,
                    intent_token=str(uuid.uuid4()),
                    strategy_binding="sprint1_post_breach_strategy",
                    environment="testnet",
                ),
                "execution_result": {
                    "executed_price": 100.0,
                    "executed_qty": 1.2,
                    "status": "filled",
                    "latency_ms": 100.0,
                    "exposure_after_trade": 250.0,
                    "leverage_after_trade": 3.0,
                    "liquidation_distance_after_trade": 20.0,
                },
            },
        )

        post_stage = next((item for item in (result.get("stages") or []) if item.get("stage") == "POST_TRADE"), {})
        post_reject = post_stage.get("standardized_reject") or {}
        assert post_reject.get("reason_code") == "POST_TRADE_EXPOSURE_BREACH"
        assert str(result.get("enforced_action") or "ALLOW").upper() == "ALLOW"
    finally:
        db.close()


def test_portfolio_domain_separated_from_user_and_limit_breach_blocks():
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="sprint1_portfolio_domain_strategy", max_order_notional=100000)
        seed_default_strategy_bindings(db, strategy_ids=["sprint1_portfolio_domain_strategy"])
        user = _create_user(db)
        _seed_market_data()

        portfolio = ensure_user_default_portfolio(db, user_id=user.id, portfolio_id=None)
        portfolio.exposure = 90.0
        portfolio.gross_exposure = 90.0
        portfolio.net_exposure = 90.0
        portfolio.limits = {"max_portfolio_exposure": 100.0, "max_drawdown_pct": 25.0, "max_leverage": 4.0}

        db.add(
            Position(
                position_id=str(uuid.uuid4()),
                user_id=user.id,
                symbol="BTCUSDT",
                size=2.0,
                entry_price=250.0,
                current_price=250.0,
                unrealized_pnl=0.0,
                leverage=1,
                strategy_id="sprint1_portfolio_domain_strategy",
                status="open",
            )
        )
        db.commit()

        result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": portfolio.portfolio_id,
                "strategy_binding": "sprint1_portfolio_domain_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "testnet",
                "market_type": "spot",
                "margin_mode": "",
                "proposed_notional": 20.0,
                "market_data_available": True,
                "portfolio_drawdown_pct": 0.0,
            },
            stage="PRE_TRADE",
        )

        risk_trace = ((result.get("trace") or {}).get("risk") or {})
        current = risk_trace.get("current") or {}
        assert float(current.get("user") or 0) > float(current.get("portfolio") or 0)
        assert str(result.get("enforced_action") or "ALLOW").upper() == "BLOCK"
        assert (result.get("standardized_reject") or {}).get("reason_code") == "RISK_PORTFOLIO_BREACH"
    finally:
        db.close()
