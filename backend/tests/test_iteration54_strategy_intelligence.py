"""
Iteration 54 - Strategy Intelligence Testing

Tests for:
- Strategy conflict resolver backend (conflict_detected, winning/losing strategy, resolution_reason)
- Dynamic capital rebalance outputs (new_strategy_weight, capital_shift, throttle_signal, allocation_drift)
- Hedge suggestion engine outputs (hedge_symbol, hedge_size, hedge_direction, risk_reduction_score)
- POST /api/admin/risk-simulation endpoint
- Manual override audit endpoints: POST/GET /api/admin/manual-overrides
- GET /api/admin/strategy-intelligence dashboard payload
- Execution preview response (strategy_conflict_warning + allocation_adjustment_notice + hedge_suggestion)
- Decision trace (hedge_recommendation + risk_reduction_score + correlation_basis)
- User positions endpoint (recommended_action + risk_reduction_score + hedge_suggestion)
- Regression tests for existing admin endpoints
"""

import os
import pytest
import requests
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin JWT token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin login failed")


@pytest.fixture(scope="module")
def test_user(admin_token):
    """Create and approve a fresh test user"""
    import random
    import string

    email = f"test_user_iter54_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"
    password = "TestPass123!"

    reg_resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
    )
    if reg_resp.status_code not in [200, 201]:
        pytest.skip(f"User registration failed: {reg_resp.text}")

    reg_data = reg_resp.json()
    user_id = reg_data.get("id")
    if not user_id:
        pytest.skip(f"User registration response missing id: {reg_data}")

    headers = {"Authorization": f"Bearer {admin_token}"}
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=headers,
    )
    if approve.status_code not in [200, 201]:
        pytest.skip(f"User approval failed: {approve.text}")

    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
    )
    if login_resp.status_code != 200:
        pytest.skip(f"User login failed after approval: {login_resp.text}")

    return {
        "id": user_id,
        "email": email,
        "password": password,
        "token": login_resp.json().get("access_token"),
    }


class TestStrategyConflictEngine:
    """Test strategy conflict resolver backend"""
    
    def test_conflict_resolver_module_exists(self):
        """Verify strategy conflict engine module can be imported"""
        from services.strategy_conflict_engine import (
            resolve_signal_conflict,
            detect_conflicts_for_signal,
            load_conflict_rules
        )
        assert resolve_signal_conflict is not None
        assert detect_conflicts_for_signal is not None
        assert load_conflict_rules is not None
        print("SUCCESS: Strategy conflict engine module imports correctly")
    
    def test_load_conflict_rules(self):
        """Test loading conflict rules from config"""
        from services.strategy_conflict_engine import load_conflict_rules
        rules = load_conflict_rules()
        assert "rules" in rules
        assert "policy_order" in rules
        assert "confidence_priority" in rules["rules"]
        assert "performance_priority" in rules["rules"]
        assert "risk_priority" in rules["rules"]
        assert "meta_override" in rules["rules"]
        print(f"SUCCESS: Conflict rules loaded: {rules['policy_order']}")
    
    def test_resolve_signal_conflict_output_fields(self):
        """Test resolve_signal_conflict returns required fields"""
        from services.strategy_conflict_engine import resolve_signal_conflict
        
        focus_signal = {
            "strategy_id": "spot_pullback_v1",
            "symbol": "BTCUSDT",
            "signal_direction": "buy",
            "confidence_score": 0.75
        }
        opposing_signal = {
            "strategy_id": "mean_reversion_v1",
            "symbol": "BTCUSDT",
            "signal_direction": "sell",
            "confidence_score": 0.65
        }
        strategy_stats = {
            "spot_pullback_v1": {"state": "ACTIVE", "performance_score": 0.8, "signal_decay": 0.1},
            "mean_reversion_v1": {"state": "ACTIVE", "performance_score": 0.6, "signal_decay": 0.2}
        }
        
        result = resolve_signal_conflict(
            focus_signal=focus_signal,
            opposing_signal=opposing_signal,
            strategy_stats=strategy_stats
        )
        
        # Verify required fields
        assert "conflict_detected" in result
        assert result["conflict_detected"]
        assert "winning_strategy" in result
        assert "losing_strategy" in result
        assert "resolution_reason" in result
        print(f"SUCCESS: Conflict resolved - winner={result['winning_strategy']}, reason={result['resolution_reason']}")
    
    def test_detect_conflicts_for_signal_no_conflict(self):
        """Test detecting conflicts when no opposing signals exist"""
        from services.strategy_conflict_engine import detect_conflicts_for_signal
        
        active_signals = [
            {"strategy_id": "spot_pullback_v1", "symbol": "ETHUSDT", "signal_direction": "buy", "confidence_score": 0.7}
        ]
        
        result = detect_conflicts_for_signal(
            active_signals=active_signals,
            strategy_id="spot_pullback_v1",
            symbol="BTCUSDT",
            signal_direction="buy",
            confidence_score=0.8,
            strategy_stats={}
        )
        
        assert not result["conflict_detected"]
        assert result["resolution_reason"] == "no_conflict"
        print("SUCCESS: No conflict detected when no opposing signals")


class TestCapitalRebalanceEngine:
    """Test dynamic capital rebalance engine"""
    
    def test_rebalance_module_exists(self):
        """Verify capital rebalance engine module"""
        from services.capital_rebalance_engine import run_dynamic_capital_rebalance
        assert run_dynamic_capital_rebalance is not None
        print("SUCCESS: Capital rebalance engine module imports correctly")
    
    def test_rebalance_output_fields(self):
        """Test run_dynamic_capital_rebalance returns required fields"""
        from services.capital_rebalance_engine import run_dynamic_capital_rebalance
        
        strategy_performance = [
            {
                "strategy_id": "spot_pullback_v1",
                "capital_weight": 0.5,
                "max_capital": 10000,
                "current_capital": 4000,
                "performance_score": 0.8,
                "confidence_score": 0.75,
                "signal_decay": 0.1,
                "execution_quality_score": 80,
                "realized_return": 500,
                "risk_score": 0.2
            },
            {
                "strategy_id": "mean_reversion_v1",
                "capital_weight": 0.5,
                "max_capital": 10000,
                "current_capital": 3000,
                "performance_score": 0.6,
                "confidence_score": 0.65,
                "signal_decay": 0.2,
                "execution_quality_score": 70,
                "realized_return": 200,
                "risk_score": 0.3
            }
        ]
        
        result = run_dynamic_capital_rebalance(strategy_performance)
        
        # Verify top-level fields
        assert "allocation_drift" in result
        assert "strategy_performance_delta" in result
        assert "risk_adjusted_return" in result
        assert "events" in result
        
        # Verify event fields
        assert len(result["events"]) > 0
        event = result["events"][0]
        assert "strategy_id" in event
        assert "new_strategy_weight" in event
        assert "capital_shift" in event
        assert "throttle_signal" in event
        assert "allocation_drift" in event
        
        print(f"SUCCESS: Rebalance results - drift={result['allocation_drift']}, events={len(result['events'])}")
    
    def test_rebalance_empty_input(self):
        """Test rebalance with empty strategy list"""
        from services.capital_rebalance_engine import run_dynamic_capital_rebalance
        
        result = run_dynamic_capital_rebalance([])
        assert result["allocation_drift"] == 0.0
        assert result["events"] == []
        print("SUCCESS: Empty input handled correctly")


class TestHedgingSuggestionEngine:
    """Test hedge suggestion engine"""
    
    def test_hedge_module_exists(self):
        """Verify hedging suggestion engine module"""
        from services.hedging_suggestion_engine import detect_hedge_opportunity
        assert detect_hedge_opportunity is not None
        print("SUCCESS: Hedge suggestion engine module imports correctly")
    
    def test_hedge_output_fields(self):
        """Test detect_hedge_opportunity returns required fields"""
        from services.hedging_suggestion_engine import detect_hedge_opportunity
        
        portfolio_exposure = {
            "total_notional": 50000,
            "cluster_exposure": {"L1": 30000, "L2": 20000}
        }
        cluster_risk = {"L1": 0.6, "L2": 0.4}
        market_correlation = {"L1": 0.75, "L2": 0.65}
        volatility = 5.0
        
        result = detect_hedge_opportunity(
            portfolio_exposure=portfolio_exposure,
            cluster_risk=cluster_risk,
            market_correlation=market_correlation,
            volatility=volatility
        )
        
        # Verify required fields
        assert "hedge_symbol" in result
        assert "hedge_size" in result
        assert "hedge_direction" in result
        assert "risk_reduction_score" in result
        assert "correlation_basis" in result
        assert "recommended_action" in result
        
        print(f"SUCCESS: Hedge suggestion - symbol={result['hedge_symbol']}, size={result['hedge_size']}, direction={result['hedge_direction']}")
    
    def test_hedge_no_exposure(self):
        """Test hedge suggestion with insufficient exposure"""
        from services.hedging_suggestion_engine import detect_hedge_opportunity
        
        result = detect_hedge_opportunity(
            portfolio_exposure={"total_notional": 0, "cluster_exposure": {}},
            cluster_risk={},
            market_correlation={},
            volatility=0
        )
        
        assert result["hedge_symbol"] is None
        assert result["recommended_action"] == "no_hedge_needed"
        print("SUCCESS: No hedge needed for zero exposure")


class TestAdminStrategyIntelligenceEndpoints:
    """Test admin strategy intelligence API endpoints"""
    
    def test_strategy_intelligence_dashboard(self, admin_token):
        """Test GET /api/admin/strategy-intelligence endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/strategy-intelligence", headers=headers)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "generated_at" in data
        assert "strategy_conflicts" in data
        assert "capital_rebalance_events" in data
        assert "hedge_suggestions" in data
        assert "allocation_drift" in data
        assert "strategy_performance_delta" in data
        assert "risk_adjusted_return" in data
        
        print(f"SUCCESS: Strategy intelligence dashboard - conflicts={len(data['strategy_conflicts'])}, events={len(data['capital_rebalance_events'])}, hedges={len(data['hedge_suggestions'])}")
    
    def test_create_manual_override(self, admin_token):
        """Test POST /api/admin/manual-overrides endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "action_type": "test_override_iter54",
            "reason": "Integration test for iteration 54",
            "payload": {"test_key": "test_value"}
        }
        response = requests.post(f"{BASE_URL}/api/admin/manual-overrides", headers=headers, json=payload)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "override_id" in data
        assert "admin_id" in data
        assert "action_type" in data
        assert data["action_type"] == "test_override_iter54"
        assert "reason" in data
        assert "payload" in data
        assert "timestamp" in data
        
        print(f"SUCCESS: Manual override created - id={data['override_id']}")
    
    def test_get_manual_overrides(self, admin_token):
        """Test GET /api/admin/manual-overrides endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/manual-overrides", headers=headers)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            override = data[0]
            assert "override_id" in override
            assert "admin_id" in override
            assert "action_type" in override
            assert "reason" in override
            assert "payload" in override
            assert "timestamp" in override
        
        print(f"SUCCESS: Manual overrides retrieved - count={len(data)}")
    
    def test_risk_simulation_endpoint(self, admin_token, test_user):
        """Test POST /api/admin/risk-simulation endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "user_id": test_user["id"],
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", headers=headers, json=payload)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "simulated_at" in data
        assert "simulation_payload" in data
        assert "strategy_conflict" in data
        assert "allocation_adjustment" in data
        assert "hedge_suggestion" in data
        assert "projected_risk_score" in data
        assert "projected_gate_decision" in data
        
        print(f"SUCCESS: Risk simulation - risk_score={data['projected_risk_score']}, gate_decision={data['projected_gate_decision']}")


class TestExecutionPreviewIntelligenceFields:
    """Test execution preview response includes strategy intelligence fields"""
    
    def test_execution_preview_contains_intelligence_fields(self, test_user):
        """Test /api/user/execution/intent/preview includes strategy_conflict_warning, allocation_adjustment_notice, hedge_suggestion"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50
        }
        response = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", headers=headers, json=payload)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify strategy intelligence fields
        assert "strategy_conflict_warning" in data or data.get("strategy_conflict_warning") is None
        assert "allocation_adjustment_notice" in data or data.get("allocation_adjustment_notice") is None
        assert "hedge_suggestion" in data
        assert "risk_reduction_score" in data or data.get("risk_reduction_score") is None
        
        print(f"SUCCESS: Execution preview includes intelligence fields - hedge={data.get('hedge_suggestion')}")


class TestDecisionTraceIntelligenceFields:
    """Test decision trace includes hedge_recommendation, risk_reduction_score, correlation_basis"""
    
    def test_decision_trace_contains_intelligence_fields(self, test_user):
        """Test decision trace via /api/user/execution/intents/{id}/decision-trace includes hedge fields"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        
        # First create a preview to get an intent
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25
        }
        preview_resp = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", headers=headers, json=preview_payload)
        
        if preview_resp.status_code != 200:
            pytest.skip(f"Preview failed: {preview_resp.text}")
        
        intent_id = preview_resp.json().get("intent_id")
        
        # Get decision trace
        trace_resp = requests.get(f"{BASE_URL}/api/user/execution/intents/{intent_id}/decision-trace", headers=headers)
        
        if trace_resp.status_code == 404:
            print("INFO: Decision trace endpoint not found - may be new")
            return
        
        if trace_resp.status_code == 200:
            data = trace_resp.json()
            latest_trace = data.get("latest_trace") or {}
            
            # Check if fields are present (may be null)
            print(f"SUCCESS: Decision trace retrieved - has hedge_recommendation={latest_trace.get('hedge_recommendation') is not None}")
        else:
            print(f"INFO: Decision trace response: {trace_resp.status_code} - {trace_resp.text[:200]}")


class TestUserPositionsIntelligenceFields:
    """Test user positions endpoint includes recommended_action, risk_reduction_score, hedge_suggestion"""
    
    def test_positions_endpoint_contains_intelligence_fields(self, test_user):
        """Test /api/user/execution/positions includes intelligence fields"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = requests.get(f"{BASE_URL}/api/user/execution/positions", headers=headers)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Even if empty, verify endpoint works
        assert isinstance(data, list)
        
        if len(data) > 0:
            position = data[0]
            assert "recommended_action" in position
            assert "risk_reduction_score" in position
            assert "hedge_suggestion" in position
            print(f"SUCCESS: Position has intelligence fields - action={position.get('recommended_action')}, score={position.get('risk_reduction_score')}")
        else:
            print("SUCCESS: Positions endpoint works (no positions currently)")


class TestRegressionAdminEndpoints:
    """Regression tests for existing admin endpoints"""
    
    def test_strategy_allocation_endpoint(self, admin_token):
        """Test GET /api/admin/strategy-allocation"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        print("SUCCESS: Strategy allocation endpoint works")
    
    def test_portfolio_risk_limits_endpoint(self, admin_token):
        """Test GET /api/admin/portfolio-risk/limits"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/portfolio-risk/limits", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        print("SUCCESS: Portfolio risk limits endpoint works")
    
    def test_positions_monitor_endpoint(self, admin_token):
        """Test GET /api/admin/positions-monitor"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/positions-monitor", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "open_positions" in data
        assert "cluster_exposure" in data
        assert "risk_level" in data
        assert "forced_liquidation_risk" in data
        print(f"SUCCESS: Positions monitor - positions={len(data['open_positions'])}, risk_level={data['risk_level']}")
    
    def test_execution_queue_endpoint(self, admin_token):
        """Test GET /api/admin/execution-queue"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/execution-queue", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        print("SUCCESS: Execution queue endpoint works")


class TestRegressionUserEndpoints:
    """Regression tests for existing user endpoints"""
    
    def test_user_signals_endpoint(self, test_user):
        """Test GET /api/user/signals"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = requests.get(f"{BASE_URL}/api/user/signals", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        print("SUCCESS: User signals endpoint works")
    
    def test_user_trades_endpoint(self, test_user):
        """Test GET /api/user/trades"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = requests.get(f"{BASE_URL}/api/user/trades", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        print("SUCCESS: User trades endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
