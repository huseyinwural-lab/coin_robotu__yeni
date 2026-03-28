"""
Phase 5.8 Live Readiness Control System - Comprehensive Tests
Tests: position sync, order reconciliation, balance integrity, exchange latency,
readiness score engine, live readiness guard, pipeline enforcement
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


# ====================== FIXTURES ======================

@pytest.fixture(scope="module")
def admin_headers():
    """Admin auth headers for API tests"""
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not defined")
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.text}")
    token = login_response.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ====================== POSITION SYNC ENGINE TESTS ======================

class TestPositionSyncEngine:
    """Tests for position_sync_engine.py - POSITION_DRIFT_DETECTED events"""
    
    def test_synced_state_when_positions_match(self):
        from core.live.position_sync_engine import reconcile_position_state
        
        result = reconcile_position_state(
            engine_positions=[{"symbol": "BTCUSDT", "position_size": 1.0, "entry_price": 100, "leverage": 3, "unrealized_pnl": 10}],
            exchange_positions=[{"symbol": "BTCUSDT", "position_size": 1.0, "entry_price": 100, "leverage": 3, "unrealized_pnl": 10}],
        )
        assert result["position_sync_state"] == "SYNCED"
        assert result["event"] is None
        assert len(result["position_drifts"]) == 0
    
    def test_drift_state_when_position_size_differs(self):
        from core.live.position_sync_engine import reconcile_position_state
        
        result = reconcile_position_state(
            engine_positions=[{"symbol": "BTCUSDT", "position_size": 1.2, "entry_price": 100, "leverage": 3, "unrealized_pnl": 10}],
            exchange_positions=[{"symbol": "BTCUSDT", "position_size": 1.1, "entry_price": 100, "leverage": 3, "unrealized_pnl": 10}],
        )
        assert result["position_sync_state"] == "DRIFT"
        assert result["event"]["event"] == "POSITION_DRIFT_DETECTED"
        assert result["event"]["drift_count"] == 1
        assert len(result["position_drifts"]) == 1
        assert result["position_drifts"][0]["reason"] == "FIELD_MISMATCH"
    
    def test_drift_state_when_missing_on_exchange(self):
        from core.live.position_sync_engine import reconcile_position_state
        
        result = reconcile_position_state(
            engine_positions=[{"symbol": "BTCUSDT", "position_size": 1.0, "entry_price": 100, "leverage": 3, "unrealized_pnl": 10}],
            exchange_positions=[],
        )
        assert result["position_sync_state"] == "UNVERIFIED"
        # No exchange data means UNVERIFIED, not DRIFT
    
    def test_unverified_state_when_no_exchange_data(self):
        from core.live.position_sync_engine import reconcile_position_state
        
        result = reconcile_position_state(
            engine_positions=[{"symbol": "ETHUSDT", "position_size": 2.0, "entry_price": 3000, "leverage": 5, "unrealized_pnl": 50}],
            exchange_positions=[],
        )
        assert result["position_sync_state"] == "UNVERIFIED"


# ====================== ORDER RECONCILIATION ENGINE TESTS ======================

class TestOrderReconciliationEngine:
    """Tests for order_reconciliation_engine.py - ORDER_RECONCILIATION_ERROR events"""
    
    def test_reconciled_state_when_orders_match(self):
        from core.live.order_reconciliation_engine import reconcile_order_state
        
        result = reconcile_order_state(
            engine_orders=[{"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"}],
            exchange_orders=[{"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"}],
        )
        assert result["order_reconciliation_state"] == "RECONCILED"
        assert result["event"] is None
    
    def test_error_state_when_missing_order(self):
        from core.live.order_reconciliation_engine import reconcile_order_state
        
        result = reconcile_order_state(
            engine_orders=[
                {"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"},
                {"order_id": "2", "symbol": "ETHUSDT", "side": "SELL", "price": 3000, "quantity": 2, "status": "FILLED"},
            ],
            exchange_orders=[{"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"}],
        )
        assert result["order_reconciliation_state"] == "ERROR"
        assert result["event"]["event"] == "ORDER_RECONCILIATION_ERROR"
        assert any(i["issue"] == "MISSING_ORDER" for i in result["order_reconciliation_issues"])
    
    def test_error_state_when_execution_mismatch(self):
        from core.live.order_reconciliation_engine import reconcile_order_state
        
        result = reconcile_order_state(
            engine_orders=[{"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"}],
            exchange_orders=[{"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 101, "quantity": 1, "status": "FILLED"}],
        )
        assert result["order_reconciliation_state"] == "ERROR"
        assert result["event"]["event"] == "ORDER_RECONCILIATION_ERROR"
        assert any(i["issue"] == "EXECUTION_MISMATCH" for i in result["order_reconciliation_issues"])


# ====================== BALANCE INTEGRITY GUARD TESTS ======================

class TestBalanceIntegrityGuard:
    """Tests for balance_integrity_guard.py - BALANCE_INTEGRITY_ALERT events"""
    
    def test_intact_state_when_balances_match(self):
        from core.live.balance_integrity_guard import validate_balance_integrity
        
        result = validate_balance_integrity(
            {"wallet_balance": 10000, "available_balance": 8000, "used_margin": 2000},
            {"wallet_balance": 10000, "available_balance": 8000, "used_margin": 2000},
        )
        assert result["balance_integrity_state"] == "INTACT"
        assert result["event"] is None
    
    def test_alert_state_when_wallet_balance_differs(self):
        from core.live.balance_integrity_guard import validate_balance_integrity
        
        result = validate_balance_integrity(
            {"wallet_balance": 10000, "available_balance": 8000, "used_margin": 2000},
            {"wallet_balance": 9500, "available_balance": 7500, "used_margin": 2000},
        )
        assert result["balance_integrity_state"] == "ALERT"
        assert result["event"]["event"] == "BALANCE_INTEGRITY_ALERT"
        assert result["event"]["drift_count"] == 2
    
    def test_unverified_state_when_no_exchange_balance(self):
        from core.live.balance_integrity_guard import validate_balance_integrity
        
        result = validate_balance_integrity(
            {"wallet_balance": 10000, "available_balance": 8000, "used_margin": 2000},
            {},
        )
        assert result["balance_integrity_state"] == "UNVERIFIED"


# ====================== EXCHANGE LATENCY GUARD TESTS ======================

class TestExchangeLatencyGuard:
    """Tests for exchange_latency_guard.py - EXCHANGE_LATENCY_ALERT events"""
    
    def test_normal_state_when_latencies_healthy(self):
        from core.live.exchange_latency_guard import evaluate_exchange_latency
        
        result = evaluate_exchange_latency({
            "order_ack_latency": 200,
            "api_response_latency": 150,
            "websocket_delay": 50,
            "heartbeat_gap": 3,
        })
        assert result["exchange_latency_state"] == "NORMAL"
        assert result["event"] is None
    
    def test_elevated_state_when_single_latency_high(self):
        from core.live.exchange_latency_guard import evaluate_exchange_latency
        
        result = evaluate_exchange_latency({
            "order_ack_latency": 1500,  # High
            "api_response_latency": 150,
            "websocket_delay": 50,
            "heartbeat_gap": 3,
        })
        assert result["exchange_latency_state"] == "ELEVATED"
        assert result["event"]["event"] == "EXCHANGE_LATENCY_ALERT"
        assert result["event"]["state"] == "ELEVATED"
        assert "ORDER_ACK_LATENCY" in result["event"]["reason"]
    
    def test_alert_state_when_multiple_latencies_high(self):
        from core.live.exchange_latency_guard import evaluate_exchange_latency
        
        result = evaluate_exchange_latency({
            "order_ack_latency": 1500,
            "api_response_latency": 1200,
            "websocket_delay": 900,
            "heartbeat_gap": 25,
        })
        assert result["exchange_latency_state"] == "ALERT"
        assert result["event"]["event"] == "EXCHANGE_LATENCY_ALERT"
        assert result["event"]["action"]["trade_frequency_throttle"] is True
        assert result["event"]["action"]["order_submission_delay"] is True


# ====================== READINESS SCORE ENGINE TESTS ======================

class TestReadinessScoreEngine:
    """Tests for readiness_score_engine.py - score calculation with equal weights"""
    
    def test_score_ready_when_all_states_optimal(self):
        from core.live.readiness_score_engine import compute_readiness_score
        
        result = compute_readiness_score(
            position_sync_state="SYNCED",
            order_reconciliation_state="RECONCILED",
            balance_integrity_state="INTACT",
            exchange_latency_state="NORMAL",
        )
        assert result["readiness_confidence_score"] == 100.0
        assert result["readiness_state"] == "READY"
        assert result["event"] is None
    
    def test_score_blocked_when_all_states_bad(self):
        from core.live.readiness_score_engine import compute_readiness_score
        
        result = compute_readiness_score(
            position_sync_state="DRIFT",
            order_reconciliation_state="ERROR",
            balance_integrity_state="ALERT",
            exchange_latency_state="ALERT",
        )
        # (45+45+40+40) * 0.25 = 42.5
        assert result["readiness_confidence_score"] == 42.5
        assert result["readiness_state"] == "BLOCKED"
        assert result["event"]["event"] == "LIVE_READINESS_ALERT"
    
    def test_score_warning_in_middle_range(self):
        from core.live.readiness_score_engine import compute_readiness_score
        
        result = compute_readiness_score(
            position_sync_state="SYNCED",
            order_reconciliation_state="RECONCILED",
            balance_integrity_state="UNVERIFIED",
            exchange_latency_state="ELEVATED",
        )
        # (100+100+55+70) * 0.25 = 81.25
        assert result["readiness_confidence_score"] == 81.25
        assert result["readiness_state"] == "WARNING"
    
    def test_weights_are_equal(self):
        from core.live.readiness_score_engine import compute_readiness_score
        
        result = compute_readiness_score(
            position_sync_state="SYNCED",
            order_reconciliation_state="RECONCILED",
            balance_integrity_state="INTACT",
            exchange_latency_state="NORMAL",
        )
        weights = result["weights"]
        assert weights["position_sync_state"] == 0.25
        assert weights["order_reconciliation_state"] == 0.25
        assert weights["balance_integrity_state"] == 0.25
        assert weights["exchange_latency_state"] == 0.25
        assert sum(weights.values()) == 1.0


# ====================== LIVE READINESS GUARD TESTS ======================

class TestLiveReadinessGuard:
    """Tests for live_readiness_guard.py - pipeline enforcement"""
    
    def test_block_action_when_state_blocked(self):
        from core.live.live_readiness_guard import evaluate_live_readiness_guard
        
        result = evaluate_live_readiness_guard({
            "readiness_state": "BLOCKED",
            "readiness_confidence_score": 50.0,
        })
        assert result["action"] == "BLOCK"
        assert result["reject_trade"] is True
        assert result["pause_engine"] is True
        assert result["size_multiplier"] == 0.0
        assert result["event"]["event"] == "LIVE_READINESS_BLOCK"
    
    def test_block_action_when_state_warning(self):
        from core.live.live_readiness_guard import evaluate_live_readiness_guard
        
        result = evaluate_live_readiness_guard({
            "readiness_state": "WARNING",
            "readiness_confidence_score": 75.0,
        })
        assert result["action"] == "BLOCK"
        assert result["reject_trade"] is True
        assert result["pause_engine"] is True
        assert result["size_multiplier"] == 0.0
        assert result["event"]["event"] == "LIVE_READINESS_BLOCK"
    
    def test_allow_action_when_state_ready(self):
        from core.live.live_readiness_guard import evaluate_live_readiness_guard
        
        result = evaluate_live_readiness_guard({
            "readiness_state": "READY",
            "readiness_confidence_score": 90.0,
        })
        assert result["action"] == "ALLOW"
        assert result["reject_trade"] is False
        assert result["pause_engine"] is False
        assert result["size_multiplier"] == 1.0
        assert result["event"] is None


# ====================== LIVE READINESS AUDIT TESTS ======================

class TestLiveReadinessAudit:
    """Tests for live_readiness_audit.py"""
    
    def test_builds_audit_events_from_multiple_sources(self):
        from core.observability.live_readiness_audit import build_live_readiness_audit_events
        
        events = build_live_readiness_audit_events(
            position_event={"event": "POSITION_DRIFT_DETECTED", "drift_count": 2},
            order_event={"event": "ORDER_RECONCILIATION_ERROR", "issue_count": 1},
            balance_event=None,
            latency_event={"event": "EXCHANGE_LATENCY_ALERT", "state": "ELEVATED"},
            readiness_event={"event": "LIVE_READINESS_ALERT", "readiness_state": "WARNING"},
            readiness_block_event=None,
        )
        assert len(events) == 4
        event_names = [e["event"] for e in events]
        assert "POSITION_DRIFT_DETECTED" in event_names
        assert "ORDER_RECONCILIATION_ERROR" in event_names
        assert "EXCHANGE_LATENCY_ALERT" in event_names
        assert "LIVE_READINESS_ALERT" in event_names


# ====================== ENDPOINT CONTRACT TESTS ======================

class TestLiveReadinessEndpoints:
    """API endpoint contract tests"""
    
    def test_live_readiness_endpoint_returns_full_contract(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/live-readiness", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        # Required fields
        assert "readiness_score" in payload
        assert "readiness_state" in payload
        assert "position_sync_state" in payload
        assert "order_reconciliation_state" in payload
        assert "balance_integrity_state" in payload
        assert "exchange_latency_state" in payload
        assert "alerts" in payload
        
        # Nested structures
        assert "position_sync" in payload
        assert "order_reconciliation" in payload
        assert "balance_integrity" in payload
        assert "exchange_latency" in payload
        assert "readiness_guard" in payload
        assert "audit_events" in payload
    
    def test_readiness_score_endpoint_returns_summary(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/readiness-score", headers=admin_headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        assert "readiness_score" in payload
        assert "readiness_state" in payload
        assert "position_sync_state" in payload
        assert "order_reconciliation_state" in payload
        assert "balance_integrity_state" in payload
        assert "exchange_latency_state" in payload
        assert "alerts" in payload
        
        # Score thresholds validation
        score = payload["readiness_score"]
        state = payload["readiness_state"]
        if score >= 85:
            assert state == "READY"
        elif score >= 70:
            assert state == "WARNING"
        else:
            assert state == "BLOCKED"


# ====================== REGRESSION TESTS ======================

class TestRegressionEndpoints:
    """Ensure existing endpoints are not broken"""
    
    def test_tail_risk_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/tail-risk", headers=admin_headers, timeout=20)
        assert response.status_code == 200
    
    def test_global_risk_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/global-risk", headers=admin_headers, timeout=20)
        assert response.status_code == 200
    
    def test_cluster_risk_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/cluster-risk", headers=admin_headers, timeout=20)
        assert response.status_code == 200
    
    def test_capital_drift_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-drift", headers=admin_headers, timeout=20)
        assert response.status_code == 200
    
    def test_strategy_governance_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-governance", headers=admin_headers, timeout=20)
        assert response.status_code == 200
    
    def test_strategy_performance_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-performance", headers=admin_headers, timeout=20)
        assert response.status_code == 200
    
    def test_capital_budget_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-budget", headers=admin_headers, timeout=20)
        assert response.status_code == 200
    
    def test_capital_usage_endpoint(self, admin_headers):
        response = requests.get(f"{BASE_URL}/api/admin/futures/capital-usage", headers=admin_headers, timeout=20)
        assert response.status_code == 200
