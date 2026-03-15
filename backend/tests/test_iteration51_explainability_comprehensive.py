"""
Iteration 51 - Phase-8 Explainability Engine E2E Comprehensive Tests
=====================================================================
Tests:
- Signal decision trace endpoint (GET /api/user/signals/{signal_id}/decision-trace)
- Trade decision trace endpoint (GET /api/user/trades/{trade_id}/decision-trace)
- Execution intent decision trace endpoint (GET /api/user/execution/intents/{intent_id}/decision-trace)
- Strategy explain endpoint (GET /api/user/strategies/{strategy_code}/explain)
- Coverage endpoint (GET /api/user/explainability/coverage)
- Signal flow trace capture (scanner run -> signal list -> trace mevcut)
- Trade flow trace capture (pending signal approve -> trade trace oluşuyor)
- Execution flow trace capture (preview intent -> execution trace oluşuyor)
"""

import os
import random
import string
from pathlib import Path

import pytest
import requests

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct

    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.strip().startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()


def _random_email(prefix: str = "iter51exp") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}@example.com"


@pytest.fixture(scope="module")
def auth_context():
    """Register a new test user, get admin approval, then login"""
    email = _random_email()
    password = "Iter51Explain123!"

    # Register new user
    register = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200, f"Register failed: {register.text}"
    user_id = register.json()["id"]

    # Admin login
    admin_login = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200, f"Admin login failed: {admin_login.text}"
    admin_token = admin_login.json()["access_token"]

    # Admin approves user
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert approve.status_code == 200, f"Approve failed: {approve.text}"

    # User login
    user_login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert user_login.status_code == 200, f"User login failed: {user_login.text}"
    user_token = user_login.json()["access_token"]

    return {
        "user_headers": {"Authorization": f"Bearer {user_token}"},
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "user_id": user_id,
        "email": email,
    }


# --- SIGNAL TRACE TESTS ---

class TestSignalDecisionTrace:
    """Test signal decision trace endpoint and scanner flow"""

    def test_scanner_run_generates_signals(self, auth_context):
        """Run scanner and verify signals are generated"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=auth_context["user_headers"],
            json={"mode": "ASSISTED", "max_results": 20},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["result_count"] >= 0
        print(f"Scanner run complete: {data['result_count']} results, {data['queued_count']} queued")

    def test_signal_list_returns_signals(self, auth_context):
        """Verify signals list endpoint returns signals after scanner run"""
        # First run scanner to ensure we have signals
        requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=auth_context["user_headers"],
            json={"mode": "ASSISTED", "max_results": 20},
            timeout=30,
        )
        
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_context["user_headers"],
            params={"limit": 100},
            timeout=20,
        )
        assert response.status_code == 200
        signals = response.json()
        assert isinstance(signals, list)
        print(f"Signal list returned {len(signals)} signals")

    def test_signal_decision_trace_endpoint_returns_trace(self, auth_context):
        """Test GET /api/user/signals/{signal_id}/decision-trace"""
        # Run scanner to generate signals
        requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=auth_context["user_headers"],
            json={"mode": "ASSISTED", "max_results": 20},
            timeout=30,
        )
        
        # Get signals
        signals_response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_context["user_headers"],
            params={"limit": 100},
            timeout=20,
        )
        assert signals_response.status_code == 200
        signals = signals_response.json()
        
        if not signals:
            pytest.skip("No signals available for trace test")
        
        signal = signals[0]
        signal_id = signal["id"]
        
        # Get decision trace for signal
        trace_response = requests.get(
            f"{BASE_URL}/api/user/signals/{signal_id}/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert trace_response.status_code == 200
        trace_data = trace_response.json()
        
        # Validate response structure
        assert trace_data["entity_scope"] == "signal"
        assert trace_data["entity_id"] == signal_id
        assert "trace_count" in trace_data
        assert trace_data["trace_count"] >= 1
        assert trace_data["latest_trace"] is not None
        assert trace_data["latest_trace"]["trace_scope"] == "signal"
        assert isinstance(trace_data["latest_trace"]["reason_details"], list)
        
        print(f"Signal trace: {trace_data['trace_count']} traces, decision_status={trace_data['latest_trace']['decision_status']}")

    def test_signal_trace_contains_reason_details(self, auth_context):
        """Verify signal trace contains reason_details with title/description"""
        # Run scanner
        requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=auth_context["user_headers"],
            json={"mode": "ASSISTED", "max_results": 20},
            timeout=30,
        )
        
        signals = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_context["user_headers"],
            params={"limit": 100},
            timeout=20,
        ).json()
        
        if not signals:
            pytest.skip("No signals for reason details test")
        
        trace_response = requests.get(
            f"{BASE_URL}/api/user/signals/{signals[0]['id']}/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert trace_response.status_code == 200
        trace_data = trace_response.json()
        
        # Check reason_details structure
        reason_details = trace_data["latest_trace"]["reason_details"]
        if reason_details:
            first_reason = reason_details[0]
            assert "code" in first_reason
            assert "title" in first_reason
            assert "description" in first_reason
            print(f"Reason detail: code={first_reason['code']}, title={first_reason['title']}")


# --- TRADE TRACE TESTS ---

class TestTradeDecisionTrace:
    """Test trade decision trace endpoint and signal approve flow"""

    def test_trade_trace_after_signal_approval(self, auth_context):
        """Test signal approve creates trade with trace"""
        # Run scanner
        requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=auth_context["user_headers"],
            json={"mode": "ASSISTED", "max_results": 20},
            timeout=30,
        )
        
        # Get pending signals
        signals = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_context["user_headers"],
            params={"limit": 100},
            timeout=20,
        ).json()
        
        pending = [s for s in signals if s.get("status") == "pending"]
        if not pending:
            pytest.skip("No pending signals for approval test")
        
        # Approve signal
        signal_id = pending[0]["id"]
        approve_response = requests.post(
            f"{BASE_URL}/api/user/signal/{signal_id}/approve",
            headers=auth_context["user_headers"],
            json={"note": "iter51_test_approve"},
            timeout=20,
        )
        assert approve_response.status_code == 200
        approved_data = approve_response.json()
        
        trade_id = approved_data.get("order_position_id")
        assert trade_id, "Approved signal should have order_position_id"
        
        # Get trade decision trace
        trade_trace = requests.get(
            f"{BASE_URL}/api/user/trades/{trade_id}/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert trade_trace.status_code == 200
        trace_data = trade_trace.json()
        
        assert trace_data["entity_scope"] == "trade"
        assert trace_data["trace_count"] >= 1
        assert trace_data["latest_trace"]["trace_scope"] == "trade"
        
        print(f"Trade trace created: trade_id={trade_id}, decision_status={trace_data['latest_trace']['decision_status']}")

    def test_trade_trace_endpoint_returns_404_for_invalid_id(self, auth_context):
        """Test trade trace returns 404 for non-existent trade"""
        trace_response = requests.get(
            f"{BASE_URL}/api/user/trades/nonexistent-trade-id-123/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert trace_response.status_code == 404


# --- EXECUTION TRACE TESTS ---

class TestExecutionIntentDecisionTrace:
    """Test execution intent decision trace endpoint"""

    def test_execution_preview_creates_trace(self, auth_context):
        """Test execution preview generates trace"""
        preview_payload = {
            "source_type": "manual",
            "source_ref_id": "",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "manual",
            "strategy_binding": "spot_pullback_v1",
            "holding_profile": "intraday",
        }
        
        preview = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=preview_payload,
            timeout=20,
        )
        assert preview.status_code == 200
        preview_data = preview.json()
        
        intent_id = preview_data["intent_id"]
        assert intent_id
        
        # Get execution trace
        trace_response = requests.get(
            f"{BASE_URL}/api/user/execution/intents/{intent_id}/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert trace_response.status_code == 200
        trace_data = trace_response.json()
        
        assert trace_data["entity_scope"] == "execution"
        assert trace_data["trace_count"] >= 1
        assert trace_data["latest_trace"]["trace_scope"] == "execution"
        
        print(f"Execution trace: intent_id={intent_id}, status={trace_data['latest_trace']['decision_status']}")

    def test_execution_trace_contains_feature_snapshot(self, auth_context):
        """Test execution trace contains feature snapshot with order details"""
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "execution_mode": "manual",
        }
        
        preview = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=preview_payload,
            timeout=20,
        )
        assert preview.status_code == 200
        intent_id = preview.json()["intent_id"]
        
        trace_response = requests.get(
            f"{BASE_URL}/api/user/execution/intents/{intent_id}/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert trace_response.status_code == 200
        trace_data = trace_response.json()
        
        feature_snapshot = trace_data["latest_trace"]["feature_snapshot"]
        assert "symbol" in feature_snapshot
        assert feature_snapshot["symbol"] == "ETHUSDT"
        assert "market_type" in feature_snapshot
        
        print(f"Feature snapshot: {feature_snapshot}")

    def test_execution_intent_not_found_returns_404(self, auth_context):
        """Test execution trace returns 404 for non-existent intent"""
        trace_response = requests.get(
            f"{BASE_URL}/api/user/execution/intents/nonexistent-intent-id/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert trace_response.status_code == 404


# --- STRATEGY EXPLAIN TESTS ---

class TestStrategyExplain:
    """Test strategy explain endpoint"""

    def test_strategy_explain_endpoint_returns_data(self, auth_context):
        """Test GET /api/user/strategies/{strategy_code}/explain"""
        # First generate some trace data by running scanner
        requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=auth_context["user_headers"],
            json={"mode": "ASSISTED", "max_results": 20},
            timeout=30,
        )
        
        response = requests.get(
            f"{BASE_URL}/api/user/strategies/spot_pullback_v1/explain",
            headers=auth_context["user_headers"],
            params={"lookback_days": 30},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["strategy_code"] == "spot_pullback_v1"
        assert data["lookback_days"] == 30
        assert "trace_count" in data
        assert "decision_distribution" in data
        assert "top_reason_codes" in data
        assert "latest_examples" in data
        
        print(f"Strategy explain: trace_count={data['trace_count']}, distribution={data['decision_distribution']}")

    def test_strategy_explain_with_custom_lookback(self, auth_context):
        """Test strategy explain with different lookback_days"""
        response = requests.get(
            f"{BASE_URL}/api/user/strategies/spot_pullback_v1/explain",
            headers=auth_context["user_headers"],
            params={"lookback_days": 7},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["lookback_days"] == 7
        
    def test_strategy_explain_top_reason_codes_format(self, auth_context):
        """Test top_reason_codes has proper format"""
        # Generate data
        requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=auth_context["user_headers"],
            json={"mode": "ASSISTED", "max_results": 20},
            timeout=30,
        )
        
        response = requests.get(
            f"{BASE_URL}/api/user/strategies/spot_pullback_v1/explain",
            headers=auth_context["user_headers"],
            params={"lookback_days": 30},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        top_codes = data["top_reason_codes"]
        if top_codes:
            first = top_codes[0]
            assert "code" in first
            assert "title" in first
            assert "description" in first
            assert "count" in first
            print(f"Top reason: {first['code']} ({first['count']} occurrences)")


# --- COVERAGE TESTS ---

class TestTraceCoverage:
    """Test explainability coverage endpoint"""

    def test_coverage_endpoint_returns_data(self, auth_context):
        """Test GET /api/user/explainability/coverage"""
        response = requests.get(
            f"{BASE_URL}/api/user/explainability/coverage",
            headers=auth_context["user_headers"],
            params={"days": 7},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["window_days"] == 7
        assert "generated_at" in data
        assert "overall_total_events" in data
        assert "overall_traced_events" in data
        assert "overall_coverage_pct" in data
        assert "scopes" in data
        
        print(f"Coverage: total={data['overall_total_events']}, traced={data['overall_traced_events']}, pct={data['overall_coverage_pct']}%")

    def test_coverage_scopes_include_all_types(self, auth_context):
        """Test coverage includes signal, trade, execution scopes"""
        response = requests.get(
            f"{BASE_URL}/api/user/explainability/coverage",
            headers=auth_context["user_headers"],
            params={"days": 7},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        scopes = {item["scope"] for item in data["scopes"]}
        assert "signal" in scopes
        assert "trade" in scopes
        assert "execution" in scopes
        
        for scope_item in data["scopes"]:
            assert "total_events" in scope_item
            assert "traced_events" in scope_item
            assert "coverage_pct" in scope_item
            print(f"Scope {scope_item['scope']}: total={scope_item['total_events']}, traced={scope_item['traced_events']}, coverage={scope_item['coverage_pct']}%")

    def test_coverage_with_different_window(self, auth_context):
        """Test coverage with different window days"""
        response = requests.get(
            f"{BASE_URL}/api/user/explainability/coverage",
            headers=auth_context["user_headers"],
            params={"days": 14},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window_days"] == 14


# --- E2E FLOW TESTS ---

class TestE2EExplainabilityFlow:
    """Test end-to-end explainability flow"""

    def test_full_signal_to_trade_trace_flow(self, auth_context):
        """Test complete flow: scanner -> signal -> approve -> trade trace"""
        # 1. Run scanner
        scanner = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=auth_context["user_headers"],
            json={"mode": "ASSISTED", "max_results": 20},
            timeout=30,
        )
        assert scanner.status_code == 200
        
        # 2. Get signals and their traces
        signals = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_context["user_headers"],
            params={"limit": 50},
            timeout=20,
        ).json()
        
        if not signals:
            pytest.skip("No signals generated")
        
        # Check signal trace exists
        signal_id = signals[0]["id"]
        signal_trace = requests.get(
            f"{BASE_URL}/api/user/signals/{signal_id}/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert signal_trace.status_code == 200
        assert signal_trace.json()["trace_count"] >= 1
        
        # 3. Approve pending signal if available
        pending = [s for s in signals if s.get("status") == "pending"]
        if pending:
            approve = requests.post(
                f"{BASE_URL}/api/user/signal/{pending[0]['id']}/approve",
                headers=auth_context["user_headers"],
                json={"note": "e2e_flow_test"},
                timeout=20,
            )
            assert approve.status_code == 200
            
            trade_id = approve.json().get("order_position_id")
            if trade_id:
                # 4. Verify trade trace exists
                trade_trace = requests.get(
                    f"{BASE_URL}/api/user/trades/{trade_id}/decision-trace",
                    headers=auth_context["user_headers"],
                    timeout=20,
                )
                assert trade_trace.status_code == 200
                assert trade_trace.json()["trace_count"] >= 1
                print(f"E2E flow complete: signal={signal_id} -> trade={trade_id}")

    def test_full_execution_intent_trace_flow(self, auth_context):
        """Test execution intent trace capture flow"""
        # 1. Preview intent
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "execution_mode": "manual",
        }
        
        preview = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=auth_context["user_headers"],
            json=preview_payload,
            timeout=20,
        )
        assert preview.status_code == 200
        intent_id = preview.json()["intent_id"]
        
        # 2. Check trace exists
        trace = requests.get(
            f"{BASE_URL}/api/user/execution/intents/{intent_id}/decision-trace",
            headers=auth_context["user_headers"],
            timeout=20,
        )
        assert trace.status_code == 200
        trace_data = trace.json()
        
        assert trace_data["entity_scope"] == "execution"
        assert trace_data["trace_count"] >= 1
        assert trace_data["latest_trace"]["trace_type"] == "execution_preview"
        
        print(f"Execution flow complete: intent={intent_id}, trace_count={trace_data['trace_count']}")
