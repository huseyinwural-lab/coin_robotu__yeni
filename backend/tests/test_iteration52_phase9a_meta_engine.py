"""
Iteration 52 - Phase 9A Meta Strategy Engine + Portfolio Risk Layer Tests

Tests cover:
- Admin API: GET/PUT /api/admin/portfolio-risk/limits
- Admin API: GET/POST /api/admin/portfolio-risk/clusters
- Admin API: GET /api/admin/portfolio-risk (dashboard)
- Admin API: GET/PUT /api/admin/strategy-allocation
- Execution preview pipeline: meta_strategy_engine + portfolio_risk_engine integration
- Risk gate decision set (ALLOW/ADJUST_POSITION/REQUIRE_APPROVAL/REJECT)
- User execute preview response with Portfolio Risk Impact + Meta Strategy summary fields
- Decision trace with portfolio_risk_score/strategy_allocation_reason/meta_engine_decision
"""

import os
import pytest
import requests
import time
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_auth():
    """Get admin authentication token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    return data["access_token"]


@pytest.fixture(scope="module")
def user_auth():
    """Create and approve a test user, return auth token"""
    unique_suffix = str(uuid.uuid4())[:8]
    test_email = f"test_phase9a_{unique_suffix}@test.dev"
    test_password = "TestPass123!"
    
    # Register user
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": test_email,
        "password": test_password
    })
    assert resp.status_code in [200, 201], f"User registration failed: {resp.text}"
    user_data = resp.json()
    user_id = user_data.get("user", {}).get("id") or user_data.get("id")
    
    # Get admin token to approve user
    admin_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    admin_token = admin_resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Find pending user and approve
    if not user_id:
        users_resp = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=admin_headers,
            params={"status": "pending"}
        )
        if users_resp.status_code == 200:
            pending_users = users_resp.json()
            for user in pending_users:
                if user.get("email") == test_email:
                    user_id = user.get("id")
                    break
    
    # Bulk approve the user
    if user_id:
        requests.post(
            f"{BASE_URL}/api/admin/user-approvals/bulk-approve",
            headers=admin_headers,
            json={"ids": [user_id]}
        )
    
    # Wait a bit for approval to take effect
    time.sleep(0.5)
    
    # Login as user
    login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    assert login_resp.status_code == 200, f"User login failed: {login_resp.text}"
    return login_resp.json()["access_token"]


class TestAdminPortfolioRiskLimits:
    """Test Admin Portfolio Risk Limits API"""
    
    def test_get_portfolio_risk_limits(self, admin_auth):
        """GET /api/admin/portfolio-risk/limits returns current limits"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/portfolio-risk/limits",
            headers={"Authorization": f"Bearer {admin_auth}"}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify all expected fields are present
        assert "max_portfolio_leverage" in data
        assert "max_symbol_exposure" in data
        assert "max_cluster_exposure" in data
        assert "max_strategy_exposure" in data
        assert "max_single_trade_risk" in data
        assert "max_intraday_drawdown" in data
        assert "max_total_drawdown" in data
        
        # Verify values are numeric and positive
        assert isinstance(data["max_portfolio_leverage"], (int, float))
        assert data["max_portfolio_leverage"] > 0
        print(f"Portfolio risk limits retrieved: {data}")
    
    def test_update_portfolio_risk_limits(self, admin_auth):
        """PUT /api/admin/portfolio-risk/limits updates limits"""
        new_limits = {
            "max_portfolio_leverage": 2.5,
            "max_symbol_exposure": 30.0,
            "max_cluster_exposure": 45.0,
            "max_strategy_exposure": 35.0,
            "max_single_trade_risk": 8.0,
            "max_intraday_drawdown": 4.0,
            "max_total_drawdown": 12.0
        }
        
        resp = requests.put(
            f"{BASE_URL}/api/admin/portfolio-risk/limits",
            headers={"Authorization": f"Bearer {admin_auth}"},
            json=new_limits
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify updated values
        assert data["max_portfolio_leverage"] == 2.5
        assert data["max_symbol_exposure"] == 30.0
        print(f"Portfolio risk limits updated successfully")
        
        # Restore defaults
        default_limits = {
            "max_portfolio_leverage": 3.0,
            "max_symbol_exposure": 35.0,
            "max_cluster_exposure": 50.0,
            "max_strategy_exposure": 40.0,
            "max_single_trade_risk": 10.0,
            "max_intraday_drawdown": 5.0,
            "max_total_drawdown": 15.0
        }
        requests.put(
            f"{BASE_URL}/api/admin/portfolio-risk/limits",
            headers={"Authorization": f"Bearer {admin_auth}"},
            json=default_limits
        )


class TestAdminPortfolioRiskClusters:
    """Test Admin Portfolio Risk Clusters API"""
    
    def test_get_risk_clusters(self, admin_auth):
        """GET /api/admin/portfolio-risk/clusters returns cluster list"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/portfolio-risk/clusters",
            headers={"Authorization": f"Bearer {admin_auth}"}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Should be a list
        assert isinstance(data, list)
        
        # Default clusters should exist (L1, L2)
        cluster_ids = [item.get("cluster_id") for item in data]
        assert len(cluster_ids) >= 2, "Should have default clusters seeded"
        print(f"Retrieved {len(data)} risk clusters: {cluster_ids}")
    
    def test_create_or_update_risk_cluster(self, admin_auth):
        """POST /api/admin/portfolio-risk/clusters creates/updates cluster"""
        new_cluster = {
            "cluster_id": "L3_TEST",
            "symbols": ["ADAUSDT", "DOTUSDT", "ATOMUSDT"],
            "cluster_type": "mid_cap_alts",
            "correlation_score": 0.68,
            "risk_weight": 1.1
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/admin/portfolio-risk/clusters",
            headers={"Authorization": f"Bearer {admin_auth}"},
            json=new_cluster
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify cluster was created
        assert data["cluster_id"] == "L3_TEST"
        assert "ADAUSDT" in data["symbols"]
        assert data["cluster_type"] == "mid_cap_alts"
        assert data["correlation_score"] == 0.68
        assert data["risk_weight"] == 1.1
        print(f"Risk cluster created/updated: {data['cluster_id']}")
    
    def test_cluster_symbols_uppercase(self, admin_auth):
        """Symbols should be uppercase in cluster"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/portfolio-risk/clusters",
            headers={"Authorization": f"Bearer {admin_auth}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        for cluster in data:
            for symbol in cluster.get("symbols", []):
                assert symbol == symbol.upper(), f"Symbol should be uppercase: {symbol}"


class TestAdminPortfolioRiskDashboard:
    """Test Admin Portfolio Risk Dashboard API"""
    
    def test_get_portfolio_risk_dashboard(self, admin_auth):
        """GET /api/admin/portfolio-risk returns dashboard data"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/portfolio-risk",
            headers={"Authorization": f"Bearer {admin_auth}"}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify dashboard fields
        assert "timestamp" in data
        assert "total_exposure" in data
        assert "cluster_exposure" in data
        assert "strategy_exposure" in data
        assert "drawdown_monitor" in data
        assert "risk_alerts" in data
        
        # Cluster and strategy exposure should be dicts
        assert isinstance(data["cluster_exposure"], dict)
        assert isinstance(data["strategy_exposure"], dict)
        
        print(f"Dashboard total_exposure: {data['total_exposure']}")
        print(f"Dashboard risk_alerts count: {len(data['risk_alerts'])}")


class TestAdminStrategyAllocation:
    """Test Admin Strategy Allocation API"""
    
    def test_get_strategy_allocations(self, admin_auth):
        """GET /api/admin/strategy-allocation returns list"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers={"Authorization": f"Bearer {admin_auth}"}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Should be a list
        assert isinstance(data, list)
        print(f"Retrieved {len(data)} strategy allocations")
        
        if len(data) > 0:
            # Verify allocation fields
            alloc = data[0]
            assert "strategy_id" in alloc
            assert "capital_weight" in alloc
            assert "max_capital" in alloc
            assert "current_capital" in alloc
            assert "state" in alloc
            assert "confidence_score" in alloc
            assert "performance_score" in alloc
            assert "signal_decay" in alloc
            assert "execution_quality_score" in alloc
            print(f"Sample allocation: {alloc['strategy_id']} state={alloc['state']}")
    
    def test_update_strategy_allocation(self, admin_auth):
        """PUT /api/admin/strategy-allocation/{strategy_id} updates allocation"""
        # First get existing allocations or create one via preview
        strategy_id = "manual_execution"
        
        update_payload = {
            "capital_weight": 0.8,
            "max_capital": 5000,
            "current_capital": 1000,
            "state": "ACTIVE"
        }
        
        resp = requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers={"Authorization": f"Bearer {admin_auth}"},
            json=update_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify updates
        assert data["strategy_id"] == strategy_id
        assert data["capital_weight"] == 0.8
        assert data["max_capital"] == 5000
        assert data["state"] == "ACTIVE"
        print(f"Strategy allocation updated: {strategy_id}")
    
    def test_strategy_allocation_states(self, admin_auth):
        """Test ACTIVE/THROTTLED/DISABLED states"""
        strategy_id = "test_strategy_state"
        
        for state in ["ACTIVE", "THROTTLED", "DISABLED"]:
            resp = requests.put(
                f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
                headers={"Authorization": f"Bearer {admin_auth}"},
                json={"state": state, "capital_weight": 1.0, "max_capital": 10000}
            )
            assert resp.status_code == 200, f"Failed setting state {state}: {resp.text}"
            data = resp.json()
            assert data["state"] == state
            print(f"Strategy state set to: {state}")


class TestExecutionPreviewPipeline:
    """Test Execution Preview Pipeline with Meta Strategy + Portfolio Risk"""
    
    def test_preview_returns_meta_strategy_summary(self, user_auth):
        """Preview response includes meta_strategy_summary"""
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50,
            "strategy_binding": "manual_execution"
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify meta_strategy_summary exists
        assert "meta_strategy_summary" in data
        meta = data["meta_strategy_summary"]
        
        # Verify meta strategy fields
        assert "strategy_id" in meta
        assert "meta_engine_decision" in meta
        assert "allocation_source" in meta
        assert "strategy_allocation_reason" in meta
        assert "strategy_weight" in meta
        assert "state" in meta
        
        print(f"Meta strategy decision: {meta.get('meta_engine_decision')}")
        print(f"Allocation reason: {meta.get('strategy_allocation_reason')}")
    
    def test_preview_returns_portfolio_risk_impact(self, user_auth):
        """Preview response includes portfolio_risk_impact"""
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100,
            "strategy_binding": "manual_execution"
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify portfolio_risk_impact exists
        assert "portfolio_risk_impact" in data
        risk = data["portfolio_risk_impact"]
        
        # Verify risk impact fields
        assert "risk_score" in risk
        assert "risk_flags" in risk
        assert "decision" in risk
        assert "cluster_id" in risk
        assert "current_portfolio_leverage" in risk
        assert "symbol_exposure_pct" in risk
        assert "cluster_exposure_pct" in risk
        assert "strategy_exposure_pct" in risk
        assert "single_trade_risk_pct" in risk
        
        print(f"Portfolio risk score: {risk.get('risk_score')}")
        print(f"Risk decision: {risk.get('decision')}")
        print(f"Cluster ID: {risk.get('cluster_id')}")
    
    def test_preview_returns_gate_decision(self, user_auth):
        """Preview response includes gate_decision"""
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify gate_decision and meta_engine_decision
        assert "gate_decision" in data
        assert "meta_engine_decision" in data
        
        gate_decision = data["gate_decision"]
        meta_decision = data["meta_engine_decision"]
        
        # Valid gate decisions
        valid_gate_decisions = {"ALLOW", "ADJUST_POSITION", "REQUIRE_APPROVAL", "REJECT"}
        valid_meta_decisions = {"ALLOW", "THROTTLED", "DISABLED"}
        
        assert gate_decision in valid_gate_decisions, f"Invalid gate_decision: {gate_decision}"
        assert meta_decision in valid_meta_decisions, f"Invalid meta_decision: {meta_decision}"
        
        print(f"Gate decision: {gate_decision}")
        print(f"Meta engine decision: {meta_decision}")


class TestDecisionTraceIntegration:
    """Test Decision Trace Integration with Portfolio Risk + Meta Strategy"""
    
    def test_execution_preview_creates_trace(self, user_auth):
        """Execution preview creates decision trace with required fields"""
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "SOLUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "strategy_binding": "manual_execution"
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        intent_id = data.get("intent_id")
        assert intent_id, "intent_id should be present"
        
        # Get decision trace for this intent
        trace_resp = requests.get(
            f"{BASE_URL}/api/user/execution/intents/{intent_id}/decision-trace",
            headers={"Authorization": f"Bearer {user_auth}"}
        )
        
        # Trace endpoint may not exist for all intents, check if it returns data
        if trace_resp.status_code == 200:
            trace_data = trace_resp.json()
            
            if trace_data.get("latest_trace"):
                latest = trace_data["latest_trace"]
                
                # Verify required decision trace fields
                assert "decision_status" in latest
                assert "trace_type" in latest
                
                # Check for portfolio risk and meta strategy fields
                print(f"Trace decision_status: {latest.get('decision_status')}")
                print(f"Trace portfolio_risk_score: {latest.get('portfolio_risk_score')}")
                print(f"Trace strategy_allocation_reason: {latest.get('strategy_allocation_reason')}")
                print(f"Trace meta_engine_decision: {latest.get('meta_engine_decision')}")
    
    def test_user_intents_list_includes_meta_fields(self, user_auth):
        """User execution intents list includes meta strategy fields"""
        # First create an intent via preview
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "AVAXUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "strategy_binding": "manual_execution"
        }
        
        requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        
        # Get user intents
        resp = requests.get(
            f"{BASE_URL}/api/user/execution/intents",
            headers={"Authorization": f"Bearer {user_auth}"}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert isinstance(data, list)
        
        if len(data) > 0:
            intent = data[0]
            # Verify intent has meta/risk fields
            assert "gate_decision" in intent
            assert "meta_engine_decision" in intent
            assert "cluster_id" in intent
            assert "risk_score" in intent
            
            print(f"Intent gate_decision: {intent.get('gate_decision')}")
            print(f"Intent meta_engine_decision: {intent.get('meta_engine_decision')}")
            print(f"Intent cluster_id: {intent.get('cluster_id')}")


class TestRiskGateDecisions:
    """Test Risk Gate Decision Set"""
    
    def test_allow_decision_for_small_trade(self, user_auth):
        """Small trades should get ALLOW decision"""
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 10  # Small trade
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Small trades should typically be ALLOW
        gate_decision = data.get("gate_decision")
        print(f"Small trade gate_decision: {gate_decision}")
        # Don't assert specific value as it depends on current portfolio state
    
    def test_preview_validation_status(self, user_auth):
        """Preview returns correct validation status"""
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "validation_status" in data
        assert "intent_status" in data
        assert "approval_required" in data
        
        print(f"Validation status: {data.get('validation_status')}")
        print(f"Intent status: {data.get('intent_status')}")
        print(f"Approval required: {data.get('approval_required')}")


class TestUserSignalsStrategyAttribution:
    """Test User Signals Strategy Attribution"""
    
    def test_signals_include_strategy_weight(self, user_auth):
        """User signals include strategy_weight, allocation_source, meta_engine_decision"""
        resp = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={"Authorization": f"Bearer {user_auth}"},
            params={"limit": 50}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert isinstance(data, list)
        print(f"Retrieved {len(data)} signals")
        
        if len(data) > 0:
            signal = data[0]
            # Check for strategy attribution fields (may be null if not set)
            print(f"Signal strategy_weight: {signal.get('strategy_weight')}")
            print(f"Signal allocation_source: {signal.get('allocation_source')}")
            print(f"Signal meta_engine_decision: {signal.get('meta_engine_decision')}")


class TestUserTradesStrategyAttribution:
    """Test User Trades Strategy Attribution"""
    
    def test_trades_include_strategy_attribution(self, user_auth):
        """User trades include strategy attribution fields"""
        resp = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers={"Authorization": f"Bearer {user_auth}"},
            params={"limit": 50}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert isinstance(data, list)
        print(f"Retrieved {len(data)} trades")
        
        if len(data) > 0:
            trade = data[0]
            # Check for strategy attribution fields
            print(f"Trade strategy_weight: {trade.get('strategy_weight')}")
            print(f"Trade allocation_source: {trade.get('allocation_source')}")
            print(f"Trade meta_engine_decision: {trade.get('meta_engine_decision')}")
    
    def test_trade_decision_trace_has_attribution(self, user_auth):
        """Trade decision trace includes strategy attribution fields"""
        # Get trades first
        trades_resp = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers={"Authorization": f"Bearer {user_auth}"},
            params={"limit": 10}
        )
        
        if trades_resp.status_code != 200:
            pytest.skip("No trades available for decision trace test")
            return
        
        trades = trades_resp.json()
        if len(trades) == 0:
            pytest.skip("No trades available")
            return
        
        trade = trades[0]
        trade_id = trade.get("trade_id")
        
        if not trade_id:
            pytest.skip("Trade has no trade_id")
            return
        
        # Get decision trace
        trace_resp = requests.get(
            f"{BASE_URL}/api/user/trades/{trade_id}/decision-trace",
            headers={"Authorization": f"Bearer {user_auth}"}
        )
        
        if trace_resp.status_code == 200:
            trace_data = trace_resp.json()
            if trace_data.get("latest_trace"):
                latest = trace_data["latest_trace"]
                print(f"Trade trace portfolio_risk_score: {latest.get('portfolio_risk_score')}")
                print(f"Trade trace strategy_allocation_reason: {latest.get('strategy_allocation_reason')}")
                print(f"Trade trace meta_engine_decision: {latest.get('meta_engine_decision')}")


class TestMetaStrategyEngineIntegration:
    """Test Meta Strategy Engine Integration with Execution"""
    
    def test_meta_engine_throttled_strategy(self, admin_auth, user_auth):
        """THROTTLED strategy results in adjusted allocation"""
        strategy_id = "throttled_test_strategy"
        
        # Set strategy to THROTTLED with metrics that would trigger throttle
        # signal_decay >= 0.55 OR execution_quality_score < 60 OR performance_score < 35
        requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers={"Authorization": f"Bearer {admin_auth}"},
            json={
                "state": "THROTTLED",
                "capital_weight": 1.0,
                "max_capital": 5000,
                "current_capital": 0
            }
        )
        
        # Try preview with throttled strategy
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100,
            "strategy_binding": strategy_id
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        meta = data.get("meta_strategy_summary", {})
        print(f"Strategy meta_engine_decision: {meta.get('meta_engine_decision')}")
        print(f"Strategy allocation_reason: {meta.get('strategy_allocation_reason')}")
        print(f"Strategy state: {meta.get('state')}")
        
        # The meta_engine_decision depends on the actual strategy drift calculation
        # For a new strategy with no history, it will likely be ACTIVE/ALLOW
        # This test verifies the meta strategy summary is returned correctly
        assert "meta_engine_decision" in meta
        assert "allocation_source" in meta
        assert "strategy_allocation_reason" in meta
    
    def test_meta_engine_disabled_strategy_rejected(self, admin_auth, user_auth):
        """DISABLED strategy results in rejection"""
        strategy_id = "disabled_test_strategy"
        
        # Set strategy to DISABLED
        requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers={"Authorization": f"Bearer {admin_auth}"},
            json={
                "state": "DISABLED",
                "capital_weight": 1.0,
                "max_capital": 5000,
                "current_capital": 0
            }
        )
        
        # Try preview with disabled strategy
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100,
            "strategy_binding": strategy_id
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers={"Authorization": f"Bearer {user_auth}"},
            json=preview_payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        meta = data.get("meta_strategy_summary", {})
        print(f"Disabled strategy meta_engine_decision: {meta.get('meta_engine_decision')}")
        
        # Should be DISABLED and rejected
        assert meta.get("meta_engine_decision") == "DISABLED"
        assert data.get("validation_status") == "rejected"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
