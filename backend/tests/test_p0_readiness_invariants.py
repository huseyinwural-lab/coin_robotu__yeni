# P0 Readiness Invariant Tests - Verifies deterministic go_live_validator behavior
# Tests: strategy_engine UNKNOWN blocks, data missing blocks, blocking fail = execution_allowed=false
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.readiness.go_live_validator import run_go_live_validator


class DummyConfig:
    live_mode_enabled = True
    safe_mode_enabled = False
    kill_switch_enabled = False


def _base_context():
    """Base context with all data present and valid"""
    return {
        "generated_at": "2026-03-28T00:00:00+00:00",
        "execution_mode": "LIVE",
        "env_mode": "LIVE",
        "config": DummyConfig(),
        "kill_switch_active": False,
        "release_gate": {"status": "PASS", "reason_codes": []},
        "connection": {
            "exists": True,
            "connection_health": "online",
            "can_trade": True,
            "validation_success": True,
            "environment": "live",
            "source": "exchange_connection_snapshot",
        },
        "data_sources": {
            "balances": {
                "available": True,
                "fallback_used": False,
                "data_source": "cache",
                "payload": {
                    "available_balance": 10000,
                    "wallet_balance": 12000,
                    "timestamp": "2099-01-01T00:00:00+00:00",
                },
            },
            "positions": {"available": True, "fallback_used": False, "data_source": "cache", "payload": []},
            "open_orders": {"available": True, "fallback_used": False, "data_source": "cache", "payload": []},
            "market_data": {
                "available": True,
                "fallback_used": False,
                "data_source": "cache",
                "payload": {"bid": 50000, "ask": 50010},
            },
        },
        "risk_config": {
            "config_version": "p1",
            "max_leverage": 5,
            "max_total_exposure_pct": 300,
            "max_margin_usage_pct": 75,
            "max_drawdown_pct": 20,
            "stale_data_threshold_ms": 120000,
        },
        "risk_orchestrator_enabled": True,
        "trading_state": {
            "engine_positions": [],
            "engine_orders": [],
            "position_count": 0,
            "order_count": 0,
            "total_exposure": 0,
            "partial_fill_count": 1,
            "funding_available": True,
            "funding_count": 2,
            "funding_error": None,
        },
        "execution_tests": {
            "precision": {"status": "PASS"},
            "submit": {"status": "SUBMITTED", "mocked": False},
            "cancel": {"status": "CANCELLED", "mocked": False},
        },
        "exchange_account": {"payload": {"positions": []}, "status_code": 200},
        "position_risk": {"payload": [], "status_code": 200},
        "reduce_only_test": {"payload": {"status": "REJECTED"}, "status_code": 400},
        "exchange_metrics": {"websocket": {"age_sec": 5}, "rate_limit_status": "ok"},
        "latency_metrics": {"round_trip_ms": 120, "order_execution_ms": 180, "tick_to_trade_ms": 90},
        "pnl_snapshot": {"net_total_usd": -100, "as_of": "2099-01-01T00:00:00+00:00"},
        "dry_run_count": 2,
        "strategy_ids": ["alpha"],
        "symbols": ["BTCUSDT"],
        "infra": {
            "db_ok": True,
            "redis_ok": True,
            "queue_sizes": {"runtime:execution:queue": 0},
            "worker_events": 2,
            "worker_lag_sec": 5,
            "strategy_engine_status": "unknown",  # No canonical heartbeat
        },
    }


def test_p0_invariant_strategy_engine_unknown_blocks_ready():
    """P0: Strategy Engine heartbeat gelene kadar status UNKNOWN/BLOCKED kalsın"""
    context = _base_context()
    # strategy_engine_status is "unknown" - no canonical heartbeat
    result = run_go_live_validator(context)
    
    assert result["readiness_state"] in {"UNKNOWN", "BLOCKED"}, \
        f"Expected UNKNOWN/BLOCKED but got {result['readiness_state']}"
    assert result["go_live_allowed"] is False, \
        "go_live_allowed must be False when strategy_engine is UNKNOWN"
    assert result["execution_allowed"] is False, \
        "execution_allowed must be False when strategy_engine is UNKNOWN"
    assert "STRATEGY_ENGINE_UNKNOWN" in result["reason_codes"], \
        "STRATEGY_ENGINE_UNKNOWN must be in reason_codes"
    
    # Verify strategy_engine step exists and is UNKNOWN
    strategy_step = next((s for s in result["steps"] if s.get("step_key") == "strategy_engine"), None)
    assert strategy_step is not None, "strategy_engine step must exist"
    assert strategy_step["status"] == "UNKNOWN", \
        f"strategy_engine status must be UNKNOWN, got {strategy_step['status']}"
    
    print("PASS: P0 invariant - strategy_engine UNKNOWN blocks READY")


def test_p0_invariant_data_missing_blocks_ready():
    """P0: Veri eksikse READY yok"""
    context = _base_context()
    context["data_sources"]["balances"] = {"available": False, "fallback_used": False, "data_source": "cache"}
    
    result = run_go_live_validator(context)
    
    assert result["readiness_state"] != "READY", \
        f"Expected non-READY state but got {result['readiness_state']}"
    assert result["go_live_allowed"] is False, \
        "go_live_allowed must be False when data is missing"
    assert "BALANCE_DATA_MISSING" in result["reason_codes"], \
        "BALANCE_DATA_MISSING must be in reason_codes"
    
    print("PASS: P0 invariant - data missing blocks READY")


def test_p0_invariant_blocking_fail_disables_execution():
    """P0: Blocking fail varsa execution_allowed=false"""
    context = _base_context()
    context["kill_switch_active"] = True  # This is a blocking check
    
    result = run_go_live_validator(context)
    
    assert result["execution_allowed"] is False, \
        "execution_allowed must be False when blocking check fails"
    assert len(result["blocking_failures"]) > 0, \
        "blocking_failures must not be empty when blocking check fails"
    assert "KILL_SWITCH_ACTIVE" in result["reason_codes"], \
        "KILL_SWITCH_ACTIVE must be in reason_codes"
    
    print("PASS: P0 invariant - blocking fail disables execution")


def test_p0_invariant_unknown_does_not_fail_open():
    """P0: UNKNOWN fail-open üretmez"""
    context = _base_context()
    # Make multiple data sources unavailable to create UNKNOWN states
    context["data_sources"]["positions"] = {"available": False, "fallback_used": False, "data_source": "cache"}
    context["data_sources"]["open_orders"] = {"available": False, "fallback_used": False, "data_source": "cache"}
    
    result = run_go_live_validator(context)
    
    # UNKNOWN should not produce READY
    assert result["readiness_state"] != "READY", \
        f"UNKNOWN states should not produce READY, got {result['readiness_state']}"
    assert result["go_live_allowed"] is False, \
        "go_live_allowed must be False when UNKNOWN states exist"
    assert result["execution_allowed"] is False, \
        "execution_allowed must be False when UNKNOWN states exist"
    
    # Verify unknowns list is populated
    assert len(result["unknowns"]) > 0, \
        "unknowns list must not be empty when UNKNOWN states exist"
    
    print("PASS: P0 invariant - UNKNOWN does not fail-open")


def test_p0_invariant_validator_contract_structure():
    """P0: go_live_validator kontratı (scores/by_layer/blocking_failures/warnings/unknowns + reason_codes)"""
    context = _base_context()
    result = run_go_live_validator(context)
    
    # Required top-level fields
    required_fields = [
        "readiness_state",
        "go_live_allowed",
        "execution_allowed",
        "score",
        "scores",
        "summary",
        "steps",
        "by_layer",
        "blocking_failures",
        "warnings",
        "unknowns",
        "reason_codes",
        "degraded",
        "data_freshness",
        "generated_at",
    ]
    
    for field in required_fields:
        assert field in result, f"Missing required field: {field}"
    
    # Verify scores has all layer keys
    expected_layers = ["core", "trading_state", "exchange", "execution", "risk", "infra", "latency", "safety"]
    for layer in expected_layers:
        assert layer in result["scores"], f"scores missing layer: {layer}"
        assert layer in result["by_layer"], f"by_layer missing layer: {layer}"
    
    # Verify types
    assert isinstance(result["scores"], dict), "scores must be dict"
    assert isinstance(result["by_layer"], dict), "by_layer must be dict"
    assert isinstance(result["blocking_failures"], list), "blocking_failures must be list"
    assert isinstance(result["warnings"], list), "warnings must be list"
    assert isinstance(result["unknowns"], list), "unknowns must be list"
    assert isinstance(result["reason_codes"], list), "reason_codes must be list"
    
    print("PASS: P0 invariant - validator contract structure verified")


def test_p0_invariant_execution_readiness_block_behavior():
    """P0: execution_readiness_service kontratı ve block davranışı"""
    # This test verifies the execution_readiness_service contract
    from db import SessionLocal
    from services.execution_readiness_service import evaluate_execution_readiness
    
    db = SessionLocal()
    try:
        # Without a valid connection, should be BLOCKED
        result = evaluate_execution_readiness(db, user_id="nonexistent-user-id")
        
        assert result["final_status"] == "BLOCKED", \
            f"Expected BLOCKED but got {result['final_status']}"
        assert result["execution_allowed"] is False, \
            "execution_allowed must be False when BLOCKED"
        assert "reason_codes" in result, \
            "reason_codes must be present"
        
        print("PASS: P0 invariant - execution_readiness_service block behavior verified")
    finally:
        db.close()


def test_p0_invariant_build_state_path_alignment():
    """P0: _build_state_path çıktısı ile validator execution path uyumu"""
    from services.pipeline.execution_engine import _build_state_path
    
    # Test partial fill path
    partial_path = _build_state_path({}, {"forced_outcome": "partial"})
    partial_states = [s.upper() if isinstance(s, str) else str(s.get("state", s.get("to_state", ""))).upper() 
                      for s in partial_path.get("path", [])]
    
    assert "PARTIALLY_FILLED" in partial_states, \
        f"partial path must contain PARTIALLY_FILLED, got {partial_states}"
    assert "FILLED" in partial_states, \
        f"partial path must contain FILLED, got {partial_states}"
    
    # Test fill path
    fill_path = _build_state_path({})
    fill_states = [s.upper() if isinstance(s, str) else str(s.get("state", s.get("to_state", ""))).upper() 
                   for s in fill_path.get("path", [])]
    
    assert "FILLED" in fill_states, \
        f"fill path must contain FILLED, got {fill_states}"
    
    # Test reject path
    reject_path = _build_state_path({}, {"forced_outcome": "rejected"})
    reject_states = [s.upper() if isinstance(s, str) else str(s.get("state", s.get("to_state", ""))).upper() 
                     for s in reject_path.get("path", [])]
    
    assert "REJECTED" in reject_states, \
        f"reject path must contain REJECTED, got {reject_states}"
    
    print("PASS: P0 invariant - _build_state_path alignment verified")


if __name__ == "__main__":
    print("=" * 60)
    print("P0 Readiness Invariant Tests")
    print("=" * 60)
    
    tests = [
        ("strategy_engine_unknown_blocks_ready", test_p0_invariant_strategy_engine_unknown_blocks_ready),
        ("data_missing_blocks_ready", test_p0_invariant_data_missing_blocks_ready),
        ("blocking_fail_disables_execution", test_p0_invariant_blocking_fail_disables_execution),
        ("unknown_does_not_fail_open", test_p0_invariant_unknown_does_not_fail_open),
        ("validator_contract_structure", test_p0_invariant_validator_contract_structure),
        ("execution_readiness_block_behavior", test_p0_invariant_execution_readiness_block_behavior),
        ("build_state_path_alignment", test_p0_invariant_build_state_path_alignment),
    ]
    
    results = []
    for name, test_fn in tests:
        print(f"\nRunning: {name}")
        try:
            test_fn()
            results.append((name, True, None))
        except AssertionError as e:
            print(f"FAIL: {e}")
            results.append((name, False, str(e)))
        except Exception as e:
            print(f"ERROR: {e}")
            results.append((name, False, str(e)))
    
    print("\n" + "=" * 60)
    print("Summary:")
    passed = sum(1 for _, p, _ in results if p)
    failed = len(results) - passed
    
    for name, passed_flag, error in results:
        status = "PASS" if passed_flag else "FAIL"
        print(f"  {name}: {status}")
        if error:
            print(f"    Error: {error}")
    
    print(f"\nTotal: {passed}/{len(results)} passed")
    
    if failed > 0:
        exit(1)
