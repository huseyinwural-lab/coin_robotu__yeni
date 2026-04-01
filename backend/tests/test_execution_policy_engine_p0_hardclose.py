# ruff: noqa: E402
"""
P0 HARD CLOSE Tests - Fail-safe HARD_BLOCK, Execution/Post-trade enforcement, Portfolio domain
"""
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
from services.execution_policy_service import (
    FAILSAFE_REASON_CODES,
    ensure_dynamic_execution_policies,
    ensure_user_default_portfolio,
    evaluate_execution_policy_engine,
    evaluate_execution_stage_enforcement,
    evaluate_post_trade_enforcement,
    build_execution_policy_observability,
)


def _create_user(db) -> User:
    row = User(
        email=f"p0-hardclose-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("P0HardCloseStrong123!"),
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
    max_order_notional: float = 100000,
    max_price_deviation_bps: float = 50.0,
    max_slippage_bps: float = 80.0,
    max_exposure_after_trade: float = 500000.0,
    max_leverage_after_trade: float = 4.0,
    min_liquidation_distance_pct: float = 3.0,
) -> None:
    policy_code = f"p0:test:{strategy_id}"
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
            "max_leverage_after_trade": max_leverage_after_trade,
            "min_liquidation_distance_pct": min_liquidation_distance_pct,
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


# ============================================================================
# FAIL-SAFE HARD_BLOCK TESTS - All failsafe reasons must HARD_BLOCK regardless of rollout mode
# ============================================================================

def test_failsafe_dependency_timeout_hard_blocks_in_shadow_mode():
    """FAILSAFE_DEPENDENCY_TIMEOUT must HARD_BLOCK even in shadow mode"""
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "shadow")  # Shadow mode normally allows
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="p0_timeout_strategy", max_order_notional=100000)
        user = _create_user(db)

        result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "p0_timeout_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "testnet",
                "market_type": "spot",
                "proposed_notional": 120.0,
                "market_data_available": True,
                "dependency_timeout": True,  # Signal timeout
            },
            stage="PRE_TRADE",
        )

        reject = result.get("standardized_reject") or {}
        assert str(result.get("enforced_action") or "ALLOW").upper() == "BLOCK", "FAILSAFE_DEPENDENCY_TIMEOUT must BLOCK"
        assert reject.get("reason_code") == "FAILSAFE_DEPENDENCY_TIMEOUT"
        assert reject.get("action_taken") == "HARD_BLOCK"
    finally:
        db.close()


def test_all_failsafe_reason_codes_are_defined():
    """Verify all expected failsafe reason codes are in FAILSAFE_REASON_CODES"""
    expected_codes = {
        "FAILSAFE_POLICY_LOAD_ERROR",
        "FAILSAFE_RISK_COMPUTE_ERROR",
        "FAILSAFE_MARKET_DATA_MISSING",
        "FAILSAFE_DEPENDENCY_TIMEOUT",
        "FAILSAFE_ENGINE_UNAVAILABLE",
    }
    assert expected_codes == FAILSAFE_REASON_CODES, f"Missing failsafe codes: {expected_codes - FAILSAFE_REASON_CODES}"


def test_failsafe_market_data_missing_hard_blocks_in_full_mode():
    """FAILSAFE_MARKET_DATA_MISSING must HARD_BLOCK even in full mode"""
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="p0_market_data_strategy", max_order_notional=100000)
        user = _create_user(db)

        result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": f"default:{user.id}",
                "strategy_binding": "p0_market_data_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "testnet",
                "market_type": "spot",
                "proposed_notional": 120.0,
                "market_data_available": False,  # Missing market data
            },
            stage="PRE_TRADE",
        )

        reject = result.get("standardized_reject") or {}
        assert str(result.get("enforced_action") or "ALLOW").upper() == "BLOCK"
        assert reject.get("reason_code") == "FAILSAFE_MARKET_DATA_MISSING"
        assert reject.get("action_taken") in ("HARD_BLOCK", "FAILSAFE_BLOCK")
    finally:
        db.close()


# ============================================================================
# EXECUTION STAGE ENFORCEMENT TESTS
# ============================================================================

def test_execution_stage_partial_fill_low_ratio_creates_violation():
    """Execution stage: partial fill below min_fill_ratio creates violation"""
    effective_rules = {
        "execution": {
            "max_price_deviation_bps": 100.0,
            "min_fill_ratio": 0.7,
            "max_fill_latency_ms": 5000,
        }
    }
    
    result = evaluate_execution_stage_enforcement(
        context={
            "requested_price": 100.0,
            "requested_qty": 10.0,
            "execution_result": {
                "executed_price": 100.0,
                "executed_qty": 5.0,  # Only 50% filled, below 70% threshold
                "status": "partial_fill",
                "latency_ms": 200.0,
            },
        },
        effective_rules=effective_rules,
        rollout_mode="full",
    )

    reject = result.get("standardized_reject") or {}
    assert reject.get("reason_code") == "EXECUTION_PARTIAL_FILL_LOW_RATIO"
    assert result.get("stage_decision") == "FLAG"  # Not critical, so FLAG not VIOLATION


def test_execution_stage_timeout_creates_critical_violation():
    """Execution stage: latency exceeding max_fill_latency_ms creates CRITICAL violation"""
    effective_rules = {
        "execution": {
            "max_price_deviation_bps": 100.0,
            "min_fill_ratio": 0.5,
            "max_fill_latency_ms": 1000,  # 1 second max
        }
    }
    
    result = evaluate_execution_stage_enforcement(
        context={
            "requested_price": 100.0,
            "requested_qty": 10.0,
            "execution_result": {
                "executed_price": 100.0,
                "executed_qty": 10.0,
                "status": "filled",
                "latency_ms": 6000.0,  # 6 seconds, exceeds 1 second limit
            },
        },
        effective_rules=effective_rules,
        rollout_mode="full",
    )

    reject = result.get("standardized_reject") or {}
    assert reject.get("reason_code") == "EXECUTION_TIMEOUT"
    assert reject.get("severity") == "CRITICAL"


def test_execution_stage_invalid_status_creates_violation():
    """Execution stage: invalid status creates violation"""
    effective_rules = {
        "execution": {
            "max_price_deviation_bps": 100.0,
            "min_fill_ratio": 0.5,
            "max_fill_latency_ms": 5000,
        }
    }
    
    result = evaluate_execution_stage_enforcement(
        context={
            "requested_price": 100.0,
            "requested_qty": 10.0,
            "execution_result": {
                "executed_price": 100.0,
                "executed_qty": 10.0,
                "status": "rejected",  # Invalid status
                "latency_ms": 200.0,
            },
        },
        effective_rules=effective_rules,
        rollout_mode="full",
    )

    reject = result.get("standardized_reject") or {}
    assert reject.get("reason_code") == "EXECUTION_STATUS_INVALID"


# ============================================================================
# POST-TRADE STAGE ENFORCEMENT TESTS
# ============================================================================

def test_post_trade_slippage_breach_creates_violation():
    """Post-trade stage: slippage exceeding max_slippage_bps creates violation"""
    effective_rules = {
        "post_trade": {
            "max_slippage_bps": 50.0,  # 0.5% max slippage
            "max_exposure_after_trade": 500000.0,
            "max_leverage_after_trade": 4.0,
            "min_liquidation_distance_pct": 3.0,
        }
    }
    
    result = evaluate_post_trade_enforcement(
        context={
            "requested_price": 100.0,
            "execution_result": {
                "executed_price": 102.0,  # 2% slippage = 200 bps, exceeds 50 bps
                "executed_qty": 10.0,
            },
            "exposure_after_trade": 1000.0,
            "leverage_after_trade": 1.0,
            "liquidation_distance_after_trade": 20.0,
        },
        effective_rules=effective_rules,
        risk_reference={"projected": {"portfolio": 1000.0}},
        rollout_mode="full",
    )

    reject = result.get("standardized_reject") or {}
    assert reject.get("reason_code") == "POST_TRADE_SLIPPAGE_BREACH"
    assert result.get("stage_decision") == "VIOLATION"


def test_post_trade_leverage_breach_creates_critical_violation():
    """Post-trade stage: leverage exceeding max_leverage_after_trade creates CRITICAL violation"""
    effective_rules = {
        "post_trade": {
            "max_slippage_bps": 1000.0,
            "max_exposure_after_trade": 500000.0,
            "max_leverage_after_trade": 3.0,  # Max 3x leverage
            "min_liquidation_distance_pct": 3.0,
        }
    }
    
    result = evaluate_post_trade_enforcement(
        context={
            "requested_price": 100.0,
            "execution_result": {
                "executed_price": 100.0,
                "executed_qty": 10.0,
            },
            "exposure_after_trade": 1000.0,
            "leverage_after_trade": 5.0,  # 5x leverage, exceeds 3x limit
            "liquidation_distance_after_trade": 20.0,
            "portfolio_equity": 200.0,
        },
        effective_rules=effective_rules,
        risk_reference={"projected": {"portfolio": 1000.0}},
        rollout_mode="full",
    )

    reject = result.get("standardized_reject") or {}
    assert reject.get("reason_code") == "POST_TRADE_LEVERAGE_BREACH"
    assert reject.get("severity") == "CRITICAL"


def test_post_trade_liquidation_risk_breach_creates_critical_violation():
    """Post-trade stage: liquidation distance below min creates CRITICAL violation"""
    effective_rules = {
        "post_trade": {
            "max_slippage_bps": 1000.0,
            "max_exposure_after_trade": 500000.0,
            "max_leverage_after_trade": 10.0,
            "min_liquidation_distance_pct": 5.0,  # Min 5% distance
        }
    }
    
    result = evaluate_post_trade_enforcement(
        context={
            "requested_price": 100.0,
            "execution_result": {
                "executed_price": 100.0,
                "executed_qty": 10.0,
                "liquidation_distance_pct": 2.0,  # Only 2%, below 5% threshold
            },
            "exposure_after_trade": 1000.0,
            "leverage_after_trade": 2.0,
            "liquidation_distance_after_trade": 2.0,  # Only 2%, below 5% threshold
        },
        effective_rules=effective_rules,
        risk_reference={"projected": {"portfolio": 1000.0}},
        rollout_mode="full",
    )

    reject = result.get("standardized_reject") or {}
    assert reject.get("reason_code") == "POST_TRADE_LIQUIDATION_RISK_BREACH"
    assert reject.get("severity") == "CRITICAL"


# ============================================================================
# PORTFOLIO DOMAIN SEPARATION TESTS
# ============================================================================

def test_portfolio_auto_provision_via_ensure_function():
    """Default portfolio is auto-provisioned via ensure_user_default_portfolio"""
    db = SessionLocal()
    try:
        user = _create_user(db)

        # Call ensure_user_default_portfolio - should create portfolio
        portfolio = ensure_user_default_portfolio(db, user_id=user.id, portfolio_id=None)
        db.commit()
        
        # Verify portfolio was created with correct defaults
        assert portfolio is not None, "Portfolio should be auto-provisioned"
        assert portfolio.portfolio_id == f"default:{user.id}"
        assert portfolio.is_default is True
        assert portfolio.limits.get("max_portfolio_exposure") == 300000.0
        assert portfolio.limits.get("max_drawdown_pct") == 25.0
        assert portfolio.limits.get("max_leverage") == 4.0
        
        # Calling again should return same portfolio (idempotent)
        portfolio2 = ensure_user_default_portfolio(db, user_id=user.id, portfolio_id=None)
        assert portfolio2.portfolio_id == portfolio.portfolio_id
    finally:
        db.close()


def test_portfolio_exposure_separate_from_user_exposure():
    """Portfolio exposure is tracked separately from user exposure"""
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="p0_exposure_sep_strategy", max_order_notional=100000)
        user = _create_user(db)

        # Create portfolio with specific exposure
        portfolio = ensure_user_default_portfolio(db, user_id=user.id, portfolio_id=None)
        portfolio.exposure = 50.0
        portfolio.gross_exposure = 50.0
        portfolio.net_exposure = 50.0
        db.commit()

        # Add position that contributes to user exposure but not portfolio exposure
        db.add(
            Position(
                position_id=str(uuid.uuid4()),
                user_id=user.id,
                symbol="ETHUSDT",
                size=1.0,
                entry_price=200.0,
                current_price=200.0,
                unrealized_pnl=0.0,
                leverage=1,
                strategy_id="other_strategy",
                status="open",
            )
        )
        db.commit()

        result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": portfolio.portfolio_id,
                "strategy_binding": "p0_exposure_sep_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "testnet",
                "market_type": "spot",
                "proposed_notional": 100.0,
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )

        risk_trace = (result.get("trace") or {}).get("risk") or {}
        current = risk_trace.get("current") or {}
        
        # User exposure includes the ETHUSDT position (200), portfolio exposure is separate
        user_exposure = float(current.get("user") or 0)
        portfolio_exposure = float(current.get("portfolio") or 0)
        
        assert user_exposure >= 200.0, f"User exposure should include ETHUSDT position: {user_exposure}"
        assert portfolio_exposure == 50.0, f"Portfolio exposure should be 50: {portfolio_exposure}"
    finally:
        db.close()


def test_portfolio_limit_breach_blocks_even_when_user_limit_ok():
    """Portfolio limit breach blocks even when user-level limit is OK"""
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(db, strategy_id="p0_portfolio_limit_strategy", max_order_notional=100000)
        user = _create_user(db)

        # Create portfolio with low limit
        portfolio = ensure_user_default_portfolio(db, user_id=user.id, portfolio_id=None)
        portfolio.exposure = 90.0
        portfolio.gross_exposure = 90.0
        portfolio.limits = {
            "max_portfolio_exposure": 100.0,  # Very low portfolio limit
            "max_drawdown_pct": 25.0,
            "max_leverage": 4.0,
        }
        db.commit()

        result = evaluate_execution_policy_engine(
            db,
            {
                "user_id": user.id,
                "portfolio_id": portfolio.portfolio_id,
                "strategy_binding": "p0_portfolio_limit_strategy",
                "symbol": "BTCUSDT",
                "side": "buy",
                "environment": "testnet",
                "market_type": "spot",
                "proposed_notional": 20.0,  # Would push portfolio to 110, exceeding 100 limit
                "market_data_available": True,
            },
            stage="PRE_TRADE",
        )

        reject = result.get("standardized_reject") or {}
        assert str(result.get("enforced_action") or "ALLOW").upper() == "BLOCK"
        assert reject.get("reason_code") == "RISK_PORTFOLIO_BREACH"
    finally:
        db.close()


# ============================================================================
# ADMIN OBSERVABILITY METRICS TESTS
# ============================================================================

def test_observability_metrics_include_stage_violation_distribution():
    """Admin observability includes stage_violation_distribution"""
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        
        metrics = build_execution_policy_observability(db, hours=24)
        
        assert "stage_violation_distribution" in metrics
        assert "execution_stage_violation_count" in metrics
        assert "post_trade_violation_count" in metrics
        assert "failsafe_hard_block_count" in metrics
        assert "stage_decision_rates" in metrics
    finally:
        db.close()


def test_observability_metrics_include_risk_breach_metrics():
    """Admin observability includes risk_breach_metrics"""
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        
        metrics = build_execution_policy_observability(db, hours=24)
        
        assert "risk_breach_metrics" in metrics
        risk_metrics = metrics.get("risk_breach_metrics") or {}
        assert "breach_count" in risk_metrics
        assert "breach_rate" in risk_metrics
    finally:
        db.close()


def test_observability_metrics_include_recent_critical_violations():
    """Admin observability includes recent_critical_violations"""
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        
        metrics = build_execution_policy_observability(db, hours=24)
        
        assert "recent_critical_violations" in metrics
        assert isinstance(metrics.get("recent_critical_violations"), list)
    finally:
        db.close()


# ============================================================================
# PIPELINE INTEGRATION TESTS
# ============================================================================

def test_full_pipeline_with_execution_and_post_trade_violations():
    """Full pipeline captures both execution and post-trade violations"""
    db = SessionLocal()
    try:
        ensure_dynamic_execution_policies(db)
        _seed_market_data()
        _set_rollout_mode(db, "full")
        _set_live_safety(db, trading_enabled=True, kill_switch_enabled=False)
        _upsert_strategy_policy(
            db,
            strategy_id="p0_full_pipeline_strategy",
            max_order_notional=100000,
            max_price_deviation_bps=5,  # Very tight deviation limit
            max_slippage_bps=5,  # Very tight slippage limit
            max_exposure_after_trade=500000,
        )
        user = _create_user(db)

        result = run_execution_pipeline(
            db,
            lifecycle_action="submit",
            context={
                **_submit_context(
                    user_id=user.id,
                    intent_token=str(uuid.uuid4()),
                    strategy_binding="p0_full_pipeline_strategy",
                    environment="testnet",
                ),
                "execution_result": {
                    "executed_price": 110.0,  # 10% deviation = 1000 bps, exceeds 5 bps
                    "executed_qty": 1.2,
                    "status": "filled",
                    "latency_ms": 200.0,
                    "exposure_after_trade": 120.0,
                    "leverage_after_trade": 1.0,
                    "liquidation_distance_after_trade": 20.0,
                },
            },
        )

        stages = result.get("stages") or []
        stage_names = [s.get("stage") for s in stages]
        
        assert "PRE_TRADE" in stage_names
        assert "EXECUTION" in stage_names
        assert "POST_TRADE" in stage_names
        
        # Check execution stage has violation
        execution_stage = next((s for s in stages if s.get("stage") == "EXECUTION"), {})
        execution_reject = execution_stage.get("standardized_reject") or {}
        assert execution_reject.get("reason_code") == "EXECUTION_PRICE_DEVIATION"
        
        # Check post-trade stage has violation (slippage)
        post_stage = next((s for s in stages if s.get("stage") == "POST_TRADE"), {})
        post_reject = post_stage.get("standardized_reject") or {}
        assert post_reject.get("reason_code") == "POST_TRADE_SLIPPAGE_BREACH"
    finally:
        db.close()
