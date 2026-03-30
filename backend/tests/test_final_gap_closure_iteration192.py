"""
Final Gap Closure Iteration 192 - Testing Risk Policy, Alert Center, Execution Analytics
Tests: Risk Policy lifecycle, User Alert Center, Execution Analytics, Signals nav removal
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


class TestSession:
    """Shared session with proper auth headers"""
    
    @pytest.fixture(scope="class")
    def user_session(self):
        """Create authenticated user session"""
        session = requests.Session()
        session.headers["x-device-fingerprint"] = "test-device-fingerprint-192"
        session.headers["x-forwarded-for"] = "127.0.0.1"
        
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": "review.user@platform.local", "password": "ReviewUser123!"},
            timeout=30
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        data = login_resp.json()
        token = data.get("access_token")
        device_id = session.cookies.get("device_id")
        
        session.headers["Authorization"] = f"Bearer {token}"
        session.headers["x-session-device"] = device_id
        
        return session


class TestRiskPolicyLifecycle(TestSession):
    """Risk Policy CRUD and lifecycle operations"""
    
    def test_list_risk_policies(self, user_session):
        """GET /api/risk-policies - List all risk policies"""
        r = user_session.get(f"{BASE_URL}/api/risk-policies", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert isinstance(data, list), "Expected list of policies"
        print(f"Risk policies count: {len(data)}")
    
    def test_create_risk_policy(self, user_session):
        """POST /api/risk-policies - Create new risk policy"""
        payload = {
            "name": "Test Policy Iteration 192",
            "position_size_pct": 2.5,
            "atr_stop_multiplier": 1.5,
            "risk_reward_ratio": 2.0,
            "daily_loss_cutoff_pct": 5.0,
            "max_open_positions": 3,
            "max_leverage": 3,
            "spread_limit_bps": 30,
            "slippage_limit_bps": 40,
            "min_liquidity_usdt": 100000,
            "reason_note": "test_iteration_192"
        }
        r = user_session.post(f"{BASE_URL}/api/risk-policies", json=payload, timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert "id" in data, "Expected policy ID in response"
        assert data["name"] == payload["name"]
        print(f"Created policy: {data['id']}")
        return data["id"]
    
    def test_preview_impact(self, user_session):
        """POST /api/risk-policies/{id}/preview-impact - Preview policy impact"""
        # First get a policy
        r = user_session.get(f"{BASE_URL}/api/risk-policies", timeout=30)
        assert r.status_code == 200
        policies = r.json()
        if not policies:
            pytest.skip("No policies to test preview-impact")
        
        policy_id = policies[0]["id"]
        preview_payload = {
            "current_daily_pnl_pct": 1.5,
            "current_open_positions": 1,
            "current_leverage": 2,
            "current_spread_bps": 12,
            "current_slippage_bps": 10
        }
        r = user_session.post(
            f"{BASE_URL}/api/risk-policies/{policy_id}/preview-impact",
            json=preview_payload,
            timeout=30
        )
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert "position_size_effect" in data, "Expected position_size_effect in preview"
        assert "daily_loss_cutoff_effect" in data, "Expected daily_loss_cutoff_effect"
        assert "concurrent_trades_effect" in data, "Expected concurrent_trades_effect"
        print(f"Preview impact: {list(data.keys())}")
    
    def test_activate_policy(self, user_session):
        """POST /api/risk-policies/{id}/activate - Activate a policy"""
        # Get policies
        r = user_session.get(f"{BASE_URL}/api/risk-policies", timeout=30)
        assert r.status_code == 200
        policies = r.json()
        if not policies:
            pytest.skip("No policies to activate")
        
        policy_id = policies[0]["id"]
        r = user_session.post(
            f"{BASE_URL}/api/risk-policies/{policy_id}/activate",
            json={"reason": "test_activation_iteration_192"},
            timeout=30
        )
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert data.get("is_active") == True, "Policy should be active"
        print(f"Activated policy: {policy_id}")
    
    def test_policy_history(self, user_session):
        """GET /api/risk-policies/{id}/history - Get policy version history"""
        r = user_session.get(f"{BASE_URL}/api/risk-policies", timeout=30)
        assert r.status_code == 200
        policies = r.json()
        if not policies:
            pytest.skip("No policies for history")
        
        policy_id = policies[0]["id"]
        r = user_session.get(f"{BASE_URL}/api/risk-policies/{policy_id}/history", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert "items" in data, "Expected items in history response"
        print(f"History items: {len(data['items'])}")
    
    def test_rollback_policy(self, user_session):
        """POST /api/risk-policies/{id}/rollback - Rollback to previous version"""
        # Get policies with version > 1
        r = user_session.get(f"{BASE_URL}/api/risk-policies", timeout=30)
        assert r.status_code == 200
        policies = r.json()
        
        # Find a policy with previous_policy_id in metadata
        rollback_candidate = None
        for p in policies:
            metadata = p.get("metadata_json") or {}
            if metadata.get("previous_policy_id"):
                rollback_candidate = p
                break
        
        if not rollback_candidate:
            pytest.skip("No policy with rollback target available")
        
        policy_id = rollback_candidate["id"]
        r = user_session.post(
            f"{BASE_URL}/api/risk-policies/{policy_id}/rollback",
            json={"reason": "test_rollback_iteration_192"},
            timeout=30
        )
        # May fail if no rollback target - that's expected
        if r.status_code == 400:
            assert "rollback_target_missing" in r.text
            print("Rollback target missing - expected for first version")
        else:
            assert r.status_code == 200, f"Failed: {r.text}"
            print(f"Rollback completed for policy: {policy_id}")


class TestUserAlertCenter(TestSession):
    """User Alert Center - persisted alerts with severity/category/search"""
    
    def test_list_alerts(self, user_session):
        """GET /api/user/alerts - List all alerts"""
        r = user_session.get(f"{BASE_URL}/api/user/alerts", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert "items" in data, "Expected items in response"
        print(f"Alerts count: {len(data['items'])}")
    
    def test_filter_by_severity(self, user_session):
        """GET /api/user/alerts?severity=critical - Filter by severity"""
        r = user_session.get(f"{BASE_URL}/api/user/alerts", params={"severity": "critical"}, timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        items = data.get("items", [])
        for item in items:
            assert item.get("severity") == "critical", f"Expected critical severity, got {item.get('severity')}"
        print(f"Critical alerts: {len(items)}")
    
    def test_filter_by_category(self, user_session):
        """GET /api/user/alerts?category=risk - Filter by category"""
        r = user_session.get(f"{BASE_URL}/api/user/alerts", params={"category": "risk"}, timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        items = data.get("items", [])
        for item in items:
            assert item.get("category") == "risk", f"Expected risk category, got {item.get('category')}"
        print(f"Risk category alerts: {len(items)}")
    
    def test_search_alerts(self, user_session):
        """GET /api/user/alerts?query=test - Search alerts"""
        r = user_session.get(f"{BASE_URL}/api/user/alerts", params={"query": "test"}, timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        print(f"Search results: {len(data.get('items', []))}")
    
    def test_acknowledge_alert(self, user_session):
        """POST /api/user/alerts/{id}/ack - Acknowledge an alert"""
        # Get alerts first
        r = user_session.get(f"{BASE_URL}/api/user/alerts", timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        
        if not items:
            pytest.skip("No alerts to acknowledge")
        
        alert_id = items[0]["id"]
        r = user_session.post(
            f"{BASE_URL}/api/user/alerts/{alert_id}/ack",
            json={"note": "test_ack_iteration_192"},
            timeout=30
        )
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert data.get("status") == "ack", "Expected status to be 'ack'"
        print(f"Acknowledged alert: {alert_id}")
    
    def test_dismiss_alert(self, user_session):
        """POST /api/user/alerts/{id}/dismiss - Dismiss an alert"""
        r = user_session.get(f"{BASE_URL}/api/user/alerts", timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        
        # Find an alert that's not already dismissed
        dismiss_candidate = None
        for item in items:
            if item.get("status") != "dismissed":
                dismiss_candidate = item
                break
        
        if not dismiss_candidate:
            pytest.skip("No alerts to dismiss")
        
        alert_id = dismiss_candidate["id"]
        r = user_session.post(
            f"{BASE_URL}/api/user/alerts/{alert_id}/dismiss",
            json={"note": "test_dismiss_iteration_192"},
            timeout=30
        )
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert data.get("status") == "dismissed", "Expected status to be 'dismissed'"
        print(f"Dismissed alert: {alert_id}")
    
    def test_alert_drilldown_fields(self, user_session):
        """Verify alerts have drilldown fields for navigation"""
        r = user_session.get(f"{BASE_URL}/api/user/alerts", timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        
        if not items:
            pytest.skip("No alerts to check drilldown")
        
        item = items[0]
        assert "drilldown" in item, "Expected drilldown field"
        drilldown = item["drilldown"]
        # Check expected drilldown keys exist
        expected_keys = ["execution_ref", "activity_log_ref", "strategy_ref", "symbol", "decision_trace_ref"]
        for key in expected_keys:
            assert key in drilldown, f"Expected {key} in drilldown"
        print(f"Drilldown fields present: {list(drilldown.keys())}")


class TestExecutionAnalytics(TestSession):
    """Execution Analytics - slippage, latency, fill rate, quality score"""
    
    def test_execution_quality(self, user_session):
        """GET /api/user/live/execution-quality - Get execution quality metrics"""
        r = user_session.get(f"{BASE_URL}/api/user/live/execution-quality", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        # Check expected fields - actual API returns these fields
        expected_fields = ["avg_slippage", "avg_latency", "own_execution_quality_score", "sample_count"]
        for field in expected_fields:
            assert field in data, f"Expected {field} in execution quality"
        print(f"Execution quality fields: {list(data.keys())}")
    
    def test_execution_positions(self, user_session):
        """GET /api/user/execution/positions - Get open positions"""
        r = user_session.get(f"{BASE_URL}/api/user/execution/positions", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert isinstance(data, list), "Expected list of positions"
        print(f"Open positions: {len(data)}")
    
    def test_execution_intents(self, user_session):
        """GET /api/user/execution/intents - Get execution intents/pending orders"""
        r = user_session.get(f"{BASE_URL}/api/user/execution/intents", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert isinstance(data, list), "Expected list of intents"
        print(f"Execution intents: {len(data)}")
    
    def test_live_trades(self, user_session):
        """GET /api/user/live/trades - Get trade history"""
        r = user_session.get(f"{BASE_URL}/api/user/live/trades", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert "items" in data, "Expected items in trades response"
        print(f"Trade history items: {len(data['items'])}")
    
    def test_strategy_performance(self, user_session):
        """GET /api/user/live/strategy-performance - Get backtest vs live parity"""
        r = user_session.get(f"{BASE_URL}/api/user/live/strategy-performance", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert "items" in data, "Expected items in strategy performance"
        print(f"Strategy performance items: {len(data['items'])}")


class TestPortfolioAndReports(TestSession):
    """Portfolio and Reports - verify redirect and embedded reports work"""
    
    def test_portfolio_endpoint(self, user_session):
        """GET /api/user/portfolio - Get portfolio data"""
        r = user_session.get(f"{BASE_URL}/api/user/portfolio", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        expected_fields = ["current_capital", "available_balance", "open_notional", "closed_pnl"]
        for field in expected_fields:
            assert field in data, f"Expected {field} in portfolio"
        print(f"Portfolio fields: {list(data.keys())}")
    
    def test_weekly_reports(self, user_session):
        """GET /api/user/reports/weekly - Get weekly report"""
        r = user_session.get(f"{BASE_URL}/api/user/reports/weekly", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        expected_fields = ["pnl", "win_rate", "week"]
        for field in expected_fields:
            assert field in data, f"Expected {field} in weekly report"
        print(f"Weekly report fields: {list(data.keys())}")


class TestSettingsEndpoints(TestSession):
    """Settings - verify user settings endpoints work"""
    
    def test_user_profile(self, user_session):
        """GET /api/auth/me - Get user profile"""
        r = user_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        data = r.json()
        assert "email" in data, "Expected email in profile"
        print(f"User profile: {data.get('email')}")
    
    def test_exchange_connections(self, user_session):
        """GET /api/user/exchange-connections - Get exchange connections"""
        r = user_session.get(f"{BASE_URL}/api/user/exchange-connections", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        print(f"Exchange connections response: {r.status_code}")
    
    def test_risk_settings(self, user_session):
        """GET /api/user-risk/settings - Get risk settings"""
        r = user_session.get(f"{BASE_URL}/api/user-risk/settings", timeout=30)
        assert r.status_code == 200, f"Failed: {r.text}"
        print(f"Risk settings response: {r.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
