"""
Phase 5.5 Testnet Control Comprehensive Test Suite
Tests: execution contract, testnet adapter, preflight, retry policy, 
       cancel/replace guard, reduce-only guard, slippage tracker, 
       reconciler, release gate, parity check, admin endpoints
"""
import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")

# ============================================================================
# Fixtures
# ============================================================================
@pytest.fixture(scope="module")
def admin_token():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=25,
        )
    except requests.RequestException as exc:
        pytest.skip(f"Auth endpoint erişilemedi: {exc}")
    if response.status_code != 200:
        pytest.skip(f"Admin login başarısız: {response.text}")
    return response.json()["access_token"]


# ============================================================================
# Core Execution Contract Tests
# ============================================================================
class TestFuturesExecutionContract:
    """FuturesExecutionRequest ve FuturesExecutionResponse contract testleri"""
    
    def test_execution_request_valid_payload(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            reduce_only=False,
            client_order_id="test-order-123456",
            decision_trace_id="trace-123456",
            strategy="futures_trend_follow_v1",
            reason_context={"test": True},
        )
        assert req.symbol == "BTCUSDT"
        assert req.side == "BUY"
        assert req.leverage == 3.0

    def test_execution_request_normalizes_symbol(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        req = FuturesExecutionRequest(
            symbol="  ethusdt  ",
            side="SELL",
            order_type="LIMIT",
            quantity=0.01,
            leverage=2.0,
            client_order_id="test-order-654321",
            decision_trace_id="trace-654321",
            strategy="test_strategy",
        )
        assert req.symbol == "ETHUSDT"

    def test_execution_request_rejects_non_usdt(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            FuturesExecutionRequest(
                symbol="BTCETH",
                side="BUY",
                order_type="MARKET",
                quantity=0.001,
                leverage=1.0,
                client_order_id="test-order-999999",
                decision_trace_id="trace-999999",
                strategy="test_strategy",
            )


# ============================================================================
# Testnet Adapter Tests
# ============================================================================
class TestFuturesTestnetAdapter:
    """Testnet adapter (BinanceFuturesTestnetAdapter wrapper) testleri"""
    
    def test_adapter_instantiation(self):
        from core.execution.futures_testnet_adapter import FuturesTestnetAdapter
        adapter = FuturesTestnetAdapter()
        assert adapter is not None
        assert adapter.adapter is not None


# ============================================================================
# Order Preflight Tests
# ============================================================================
class TestFuturesOrderPreflight:
    """Order preflight kontrol testleri"""
    
    def test_preflight_pass_all_checks(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_order_preflight import FuturesOrderPreflight
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            client_order_id="preflight-123456",
            decision_trace_id="trace-preflight-1",
            strategy="futures_trend_follow_v1",
        )
        context = {
            "active_symbols": ["BTCUSDT", "ETHUSDT"],
            "max_trade_leverage": 5.0,
            "testnet_mode_enabled": True,
            "release_gate_status": "PASS",
            "environment": "testnet",
            "margin_available": 1000.0,
            "margin_required": 100.0,
        }
        result = FuturesOrderPreflight().evaluate(req, context)
        assert result["preflight_pass"] is True
        assert result["reason_code"] == "PASS"

    def test_preflight_blocks_when_release_gate_blocked(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_order_preflight import FuturesOrderPreflight
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            client_order_id="preflight-blocked",
            decision_trace_id="trace-blocked-1",
            strategy="futures_trend_follow_v1",
        )
        context = {
            "testnet_mode_enabled": True,
            "release_gate_status": "BLOCKED",
            "environment": "testnet",
        }
        result = FuturesOrderPreflight().evaluate(req, context)
        assert result["preflight_pass"] is False
        release_gate_check = next((c for c in result["checks"] if c["key"] == "release_gate"), None)
        assert release_gate_check is not None
        assert release_gate_check["pass"] is False

    def test_preflight_blocks_when_testnet_disabled(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_order_preflight import FuturesOrderPreflight
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            client_order_id="preflight-disabled",
            decision_trace_id="trace-disabled-1",
            strategy="futures_trend_follow_v1",
        )
        context = {
            "testnet_mode_enabled": False,
            "release_gate_status": "PASS",
            "environment": "testnet",
        }
        result = FuturesOrderPreflight().evaluate(req, context)
        assert result["preflight_pass"] is False
        testnet_check = next((c for c in result["checks"] if c["key"] == "testnet_mode_enabled"), None)
        assert testnet_check is not None
        assert testnet_check["pass"] is False

    def test_preflight_blocks_live_environment(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_order_preflight import FuturesOrderPreflight
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            client_order_id="preflight-live",
            decision_trace_id="trace-live-1",
            strategy="futures_trend_follow_v1",
        )
        context = {
            "testnet_mode_enabled": True,
            "release_gate_status": "PASS",
            "environment": "live",  # should fail live_endpoint_block
        }
        result = FuturesOrderPreflight().evaluate(req, context)
        assert result["preflight_pass"] is False
        live_block = next((c for c in result["checks"] if c["key"] == "live_endpoint_block"), None)
        assert live_block is not None
        assert live_block["pass"] is False


# ============================================================================
# Retry Policy Tests
# ============================================================================
class TestFuturesRetryPolicy:
    """Retry policy (reason-aware) testleri"""
    
    def test_retry_timeout_is_retryable(self):
        from core.execution.futures_retry_policy import FuturesRetryPolicy
        policy = FuturesRetryPolicy()
        decision = policy.classify("TIMEOUT")
        assert decision["should_retry"] is True
        assert decision["action"] == "retry"

    def test_retry_rate_limit_is_retryable(self):
        from core.execution.futures_retry_policy import FuturesRetryPolicy
        policy = FuturesRetryPolicy()
        decision = policy.classify("RATE_LIMIT")
        assert decision["should_retry"] is True
        assert decision["action"] == "retry"

    def test_retry_invalid_order_is_fail_fast(self):
        from core.execution.futures_retry_policy import FuturesRetryPolicy
        policy = FuturesRetryPolicy()
        decision = policy.classify("INVALID_ORDER")
        assert decision["should_retry"] is False
        assert decision["action"] == "fail_fast"

    def test_retry_duplicate_order_is_reconcile(self):
        from core.execution.futures_retry_policy import FuturesRetryPolicy
        policy = FuturesRetryPolicy()
        decision = policy.classify("DUPLICATE_CLIENT_ORDER")
        assert decision["should_retry"] is False
        assert decision["action"] == "reconcile"

    def test_backoff_exponential_for_timeout(self):
        from core.execution.futures_retry_policy import FuturesRetryPolicy
        policy = FuturesRetryPolicy()
        backoff_1 = policy.next_backoff_seconds(1, "TIMEOUT")
        backoff_2 = policy.next_backoff_seconds(2, "TIMEOUT")
        assert backoff_1 > 0
        assert backoff_2 > backoff_1

    def test_backoff_zero_for_non_retryable(self):
        from core.execution.futures_retry_policy import FuturesRetryPolicy
        policy = FuturesRetryPolicy()
        backoff = policy.next_backoff_seconds(1, "INVALID_ORDER")
        assert backoff == 0.0


# ============================================================================
# Cancel/Replace Guard Tests
# ============================================================================
class TestFuturesCancelReplaceGuard:
    """Cancel/Replace guard testleri"""
    
    def test_blocks_duplicate_exposure(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_cancel_replace_guard import FuturesCancelReplaceGuard
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            client_order_id="guard-test-1",
            decision_trace_id="trace-duplicate-1",
            strategy="futures_trend_follow_v1",
        )
        open_orders = [
            {"decision_trace_id": "trace-duplicate-1", "symbol": "BTCUSDT", "side": "BUY", "status": "NEW", "order_id": 123}
        ]
        result = FuturesCancelReplaceGuard().block_duplicate_entry(req, open_orders)
        assert result["blocked"] is True
        assert result["reason_code"] == "DUPLICATE_EXPOSURE_BLOCKED"
        assert result["existing_order_id"] == 123

    def test_allows_different_trace_id(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_cancel_replace_guard import FuturesCancelReplaceGuard
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            client_order_id="guard-test-2",
            decision_trace_id="trace-unique-1",
            strategy="futures_trend_follow_v1",
        )
        open_orders = [
            {"decision_trace_id": "trace-different-1", "symbol": "BTCUSDT", "side": "BUY", "status": "NEW"}
        ]
        result = FuturesCancelReplaceGuard().block_duplicate_entry(req, open_orders)
        assert result["blocked"] is False
        assert result["reason_code"] == "PASS"

    def test_reconcile_after_cancel(self):
        from core.execution.futures_cancel_replace_guard import FuturesCancelReplaceGuard
        result = FuturesCancelReplaceGuard().reconcile_after_cancel({"status": "CANCELED"})
        assert result["can_replace"] is True

    def test_partial_fill_blocks_replace(self):
        from core.execution.futures_cancel_replace_guard import FuturesCancelReplaceGuard
        result = FuturesCancelReplaceGuard().reconcile_after_cancel({"status": "PARTIALLY_FILLED"})
        assert result["can_replace"] is False


# ============================================================================
# Reduce-Only Guard Tests
# ============================================================================
class TestFuturesReduceOnlyGuard:
    """Reduce-only guard testleri"""
    
    def test_allows_normal_order_path(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_reduce_only_guard import FuturesReduceOnlyGuard
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            reduce_only=False,
            client_order_id="reduce-test-1",
            decision_trace_id="trace-reduce-1",
            strategy="futures_trend_follow_v1",
        )
        result = FuturesReduceOnlyGuard().evaluate(req, {"quantity": 0.0, "side": "NONE"})
        assert result["pass"] is True
        assert result["audit_path"] == "normal_order_path"

    def test_blocks_reduce_only_no_position(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_reduce_only_guard import FuturesReduceOnlyGuard
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="SELL",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            reduce_only=True,
            client_order_id="reduce-test-2",
            decision_trace_id="trace-reduce-2",
            strategy="futures_trend_follow_v1",
        )
        result = FuturesReduceOnlyGuard().evaluate(req, {"quantity": 0.0, "side": "NONE"})
        assert result["pass"] is False
        assert result["reason_code"] == "REDUCE_ONLY_NO_OPEN_POSITION"

    def test_blocks_reduce_only_would_increase_long(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_reduce_only_guard import FuturesReduceOnlyGuard
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            reduce_only=True,
            client_order_id="reduce-test-3",
            decision_trace_id="trace-reduce-3",
            strategy="futures_trend_follow_v1",
        )
        result = FuturesReduceOnlyGuard().evaluate(req, {"quantity": 0.01, "side": "LONG"})
        assert result["pass"] is False
        assert result["reason_code"] == "REDUCE_ONLY_WOULD_INCREASE_LONG"

    def test_allows_reduce_only_sell_on_long(self):
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from core.execution.futures_reduce_only_guard import FuturesReduceOnlyGuard
        req = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="SELL",
            order_type="MARKET",
            quantity=0.001,
            leverage=3.0,
            reduce_only=True,
            client_order_id="reduce-test-4",
            decision_trace_id="trace-reduce-4",
            strategy="futures_trend_follow_v1",
        )
        result = FuturesReduceOnlyGuard().evaluate(req, {"quantity": 0.01, "side": "LONG"})
        assert result["pass"] is True
        assert result["audit_path"] == "reduce_only_liquidation_adl_policy_path"


# ============================================================================
# Slippage Tracker Tests
# ============================================================================
class TestFuturesSlippageTracker:
    """Slippage tracker testleri"""
    
    def test_slippage_calculation_positive(self):
        from core.execution.futures_slippage_tracker import FuturesSlippageTracker
        result = FuturesSlippageTracker().evaluate(
            symbol="BTCUSDT",
            order_type="MARKET",
            expected_price=50000.0,
            realized_price=50025.0,
        )
        assert result["symbol"] == "BTCUSDT"
        assert result["expected_slippage"] > 0
        assert result["realized_slippage"] > 0
        assert result["slippage_delta"] == 25.0

    def test_slippage_calculation_negative(self):
        from core.execution.futures_slippage_tracker import FuturesSlippageTracker
        result = FuturesSlippageTracker().evaluate(
            symbol="ETHUSDT",
            order_type="MARKET",
            expected_price=3000.0,
            realized_price=2995.0,
        )
        assert result["realized_slippage"] < 0
        assert result["slippage_delta"] == -5.0

    def test_slippage_zero_when_no_expected(self):
        from core.execution.futures_slippage_tracker import FuturesSlippageTracker
        result = FuturesSlippageTracker().evaluate(
            symbol="BTCUSDT",
            order_type="MARKET",
            expected_price=0.0,
            realized_price=50000.0,
        )
        assert result["expected_slippage"] == 0.0
        assert result["realized_slippage"] == 0.0


# ============================================================================
# Execution Reconciler Tests
# ============================================================================
class TestFuturesExecutionReconciler:
    """Execution reconciler testleri"""
    
    def test_reconciler_filled_state(self):
        from core.execution.futures_execution_reconciler import FuturesExecutionReconciler
        result = FuturesExecutionReconciler().reconcile(
            submitted=True, exchange_status="FILLED", executed_qty=0.001
        )
        assert result["state"] == "filled"
        assert result["submitted"] is True

    def test_reconciler_partially_filled_state(self):
        from core.execution.futures_execution_reconciler import FuturesExecutionReconciler
        result = FuturesExecutionReconciler().reconcile(
            submitted=True, exchange_status="PARTIALLY_FILLED", executed_qty=0.0005
        )
        assert result["state"] == "partially_filled"

    def test_reconciler_accepted_with_qty_becomes_partial(self):
        from core.execution.futures_execution_reconciler import FuturesExecutionReconciler
        result = FuturesExecutionReconciler().reconcile(
            submitted=True, exchange_status="ACCEPTED", executed_qty=0.0002
        )
        assert result["state"] == "partially_filled"

    def test_reconciler_unknown_when_not_submitted(self):
        from core.execution.futures_execution_reconciler import FuturesExecutionReconciler
        result = FuturesExecutionReconciler().reconcile(
            submitted=False, exchange_status="FILLED", executed_qty=0.0
        )
        assert result["state"] == "unknown_needs_reconcile"


# ============================================================================
# Release Gate Tests
# ============================================================================
class TestFuturesTestnetReleaseGate:
    """Testnet release gate testleri"""
    
    def test_release_gate_blocked_when_disabled(self):
        from core.execution.futures_testnet_release_gate import FuturesTestnetReleaseGate
        result = FuturesTestnetReleaseGate().evaluate(
            live_mode_enabled=False,
            release_gate_status="PASS",
            has_live_credentials=False,
        )
        assert result["status"] == "BLOCKED"
        assert result["order_path_open"] is False
        assert "TESTNET_MODE_DISABLED_BY_DEFAULT" in result["reasons"]

    def test_release_gate_blocked_with_live_credentials(self):
        from core.execution.futures_testnet_release_gate import FuturesTestnetReleaseGate
        result = FuturesTestnetReleaseGate().evaluate(
            live_mode_enabled=True,
            release_gate_status="PASS",
            has_live_credentials=True,
        )
        assert result["status"] == "BLOCKED"
        assert result["order_path_open"] is False
        assert "LIVE_CREDENTIALS_FORBIDDEN" in result["reasons"]

    def test_release_gate_pass_with_warnings(self):
        from core.execution.futures_testnet_release_gate import FuturesTestnetReleaseGate
        result = FuturesTestnetReleaseGate().evaluate(
            live_mode_enabled=True,
            release_gate_status="PASS_WITH_WARNINGS",
            has_live_credentials=False,
        )
        assert result["status"] == "PASS_WITH_WARNINGS"
        assert result["order_path_open"] is True

    def test_release_gate_full_pass(self):
        from core.execution.futures_testnet_release_gate import FuturesTestnetReleaseGate
        result = FuturesTestnetReleaseGate().evaluate(
            live_mode_enabled=True,
            release_gate_status="PASS",
            has_live_credentials=False,
        )
        assert result["status"] == "PASS"
        assert result["order_path_open"] is True
        assert result["reasons"] == ["PASS"]


# ============================================================================
# Parity Check Tests
# ============================================================================
class TestFuturesExecutionParityCheck:
    """Parity check (paper vs testnet) testleri"""
    
    def test_parity_check_pass_within_tolerance(self):
        from core.execution.futures_execution_parity_check import FuturesExecutionParityCheck
        result = FuturesExecutionParityCheck().evaluate(
            paper_fill_price=50000.0,
            testnet_fill_price=50005.0,
            tolerance_bps=20.0,
        )
        assert result["status"] == "PASS"
        assert result["drift_bps"] < 20.0

    def test_parity_check_warn_outside_tolerance(self):
        from core.execution.futures_execution_parity_check import FuturesExecutionParityCheck
        result = FuturesExecutionParityCheck().evaluate(
            paper_fill_price=50000.0,
            testnet_fill_price=50200.0,
            tolerance_bps=20.0,
        )
        assert result["status"] == "WARN"
        assert result["drift_bps"] > 20.0

    def test_parity_check_zero_paper_price(self):
        from core.execution.futures_execution_parity_check import FuturesExecutionParityCheck
        result = FuturesExecutionParityCheck().evaluate(
            paper_fill_price=0.0,
            testnet_fill_price=50000.0,
            tolerance_bps=20.0,
        )
        assert result["drift_bps"] == 0.0
        assert result["status"] == "PASS"


# ============================================================================
# Admin Endpoint Tests
# ============================================================================
class TestAdminTestnetEndpoints:
    """Admin testnet control endpoint testleri"""
    
    def test_testnet_status_endpoint_200(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/testnet/status", headers=headers, timeout=25)
        assert response.status_code == 200

    def test_testnet_status_contract_fields(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/testnet/status", headers=headers, timeout=25)
        payload = response.json()
        required_fields = [
            "default_mode", "testnet_enabled", "live_endpoint_access", 
            "release_gate", "preflight_template", "retry_policy", 
            "slippage", "parity_check"
        ]
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"

    def test_testnet_status_default_mode_paper(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/testnet/status", headers=headers, timeout=25)
        payload = response.json()
        assert payload["default_mode"] == "paper"

    def test_testnet_status_live_endpoint_access_false(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/testnet/status", headers=headers, timeout=25)
        payload = response.json()
        assert payload["live_endpoint_access"] is False

    def test_release_gate_endpoint_200(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/testnet/release-gate", headers=headers, timeout=25)
        assert response.status_code == 200

    def test_release_gate_contract_fields(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/testnet/release-gate", headers=headers, timeout=25)
        payload = response.json()
        required_fields = ["status", "order_path_open", "reasons", "secret_isolation", "testnet_enabled"]
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"

    def test_release_gate_order_path_blocked_by_default(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/testnet/release-gate", headers=headers, timeout=25)
        payload = response.json()
        # Gate should be blocked when testnet is disabled by default
        assert payload["order_path_open"] is False


# ============================================================================
# Regression Tests (existing endpoints)
# ============================================================================
class TestRegressionEndpoints:
    """Regression testleri - mevcut endpointlerin çalıştığını doğrulama"""
    
    def test_strategy_status_endpoint(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy/status", headers=headers, timeout=25)
        assert response.status_code == 200
        payload = response.json()
        assert "strategy" in payload

    def test_decision_diagnostics_endpoint(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/decision-diagnostics", headers=headers, timeout=25)
        assert response.status_code == 200
        payload = response.json()
        assert "gate_reason_distribution" in payload

    def test_leverage_status_endpoint(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/futures/leverage/status", headers=headers, timeout=25)
        assert response.status_code == 200
        payload = response.json()
        assert "final_leverage" in payload
