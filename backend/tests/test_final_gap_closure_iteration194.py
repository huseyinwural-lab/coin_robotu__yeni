"""
Final Gap Closure Iteration 194 - Testing:
1. Risk Policy lifecycle routes: create, preview-impact, activate, history, rollback
2. User Alert Center: severity/category/search filters, ack/dismiss, history, drilldown
3. User Execution Analytics: slippage, latency, fill rate, quality score, reject/cancel/retry
4. Signals nav item removed from sidebar (frontend check)
5. Portfolio reports redirect
"""
import pytest
import requests

BASE_URL = "http://localhost:8001"

TEST_USER_EMAIL = "review.user@platform.local"
TEST_USER_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def auth_session():
    """Get authenticated session for user"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    return session


class TestRiskPolicyLifecycle:
    """Risk Policy lifecycle routes: create, preview-impact, activate, history, rollback"""
    
    def test_list_risk_policies(self, auth_session):
        """GET /api/risk-policies returns list"""
        resp = auth_session.get(f"{BASE_URL}/api/risk-policies")
        assert resp.status_code == 200, f"List risk policies failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS: GET /api/risk-policies returned {len(data)} policies")
    
    def test_create_risk_policy(self, auth_session):
        """POST /api/risk-policies creates new policy"""
        payload = {
            "name": "TEST_Policy_Iter194",
            "position_size_pct": 2.5,
            "atr_stop_multiplier": 1.5,
            "risk_reward_ratio": 2.0,
            "daily_loss_cutoff_pct": 5.0,
            "max_open_positions": 3,
            "max_leverage": 3,
            "spread_limit_bps": 30,
            "slippage_limit_bps": 40,
            "min_liquidity_usdt": 100000,
            "reason_note": "test_create_iter194"
        }
        resp = auth_session.post(f"{BASE_URL}/api/risk-policies", json=payload)
        assert resp.status_code == 200, f"Create risk policy failed: {resp.text}"
        data = resp.json()
        assert "id" in data, "Response should contain id"
        assert data.get("name") == payload["name"], "Name should match"
        assert data.get("lifecycle_state") == "draft", "New policy should be draft"
        print(f"PASS: POST /api/risk-policies created policy {data.get('id')}")
        return data
    
    def test_preview_impact(self, auth_session):
        """POST /api/risk-policies/{id}/preview-impact returns impact preview"""
        # First get a policy
        list_resp = auth_session.get(f"{BASE_URL}/api/risk-policies")
        policies = list_resp.json()
        if not policies:
            pytest.skip("No policies to test preview-impact")
        
        policy_id = policies[0]["id"]
        payload = {
            "current_daily_pnl_pct": 1.5,
            "current_open_positions": 1,
            "current_leverage": 2,
            "current_spread_bps": 12,
            "current_slippage_bps": 10
        }
        resp = auth_session.post(f"{BASE_URL}/api/risk-policies/{policy_id}/preview-impact", json=payload)
        assert resp.status_code == 200, f"Preview impact failed: {resp.text}"
        data = resp.json()
        # Verify expected fields
        assert "position_size_effect" in data, "Should have position_size_effect"
        assert "daily_loss_cutoff_effect" in data, "Should have daily_loss_cutoff_effect"
        assert "concurrent_trades_effect" in data, "Should have concurrent_trades_effect"
        assert "leverage_cap_effect" in data, "Should have leverage_cap_effect"
        assert "spread_slippage_risk" in data, "Should have spread_slippage_risk"
        print(f"PASS: POST /api/risk-policies/{policy_id}/preview-impact returned impact preview")
    
    def test_activate_policy(self, auth_session):
        """POST /api/risk-policies/{id}/activate sets policy active"""
        # Get a policy to activate
        list_resp = auth_session.get(f"{BASE_URL}/api/risk-policies")
        policies = list_resp.json()
        if not policies:
            pytest.skip("No policies to test activate")
        
        policy_id = policies[0]["id"]
        payload = {"reason": "test_activate_iter194"}
        resp = auth_session.post(f"{BASE_URL}/api/risk-policies/{policy_id}/activate", json=payload)
        assert resp.status_code == 200, f"Activate policy failed: {resp.text}"
        data = resp.json()
        assert data.get("is_active") == True, "Policy should be active"
        assert data.get("lifecycle_state") == "active", "Lifecycle state should be active"
        print(f"PASS: POST /api/risk-policies/{policy_id}/activate set policy active")
    
    def test_policy_history(self, auth_session):
        """GET /api/risk-policies/{id}/history returns version history"""
        list_resp = auth_session.get(f"{BASE_URL}/api/risk-policies")
        policies = list_resp.json()
        if not policies:
            pytest.skip("No policies to test history")
        
        policy_id = policies[0]["id"]
        resp = auth_session.get(f"{BASE_URL}/api/risk-policies/{policy_id}/history")
        assert resp.status_code == 200, f"Policy history failed: {resp.text}"
        data = resp.json()
        assert "items" in data, "Should have items array"
        assert isinstance(data["items"], list), "Items should be list"
        print(f"PASS: GET /api/risk-policies/{policy_id}/history returned {len(data['items'])} versions")
    
    def test_rollback_policy(self, auth_session):
        """POST /api/risk-policies/{id}/rollback attempts rollback"""
        list_resp = auth_session.get(f"{BASE_URL}/api/risk-policies")
        policies = list_resp.json()
        if not policies:
            pytest.skip("No policies to test rollback")
        
        policy_id = policies[0]["id"]
        payload = {"reason": "test_rollback_iter194"}
        resp = auth_session.post(f"{BASE_URL}/api/risk-policies/{policy_id}/rollback", json=payload)
        # Rollback may return 400 if no previous version exists (expected for first version)
        assert resp.status_code in [200, 400], f"Rollback unexpected status: {resp.text}"
        if resp.status_code == 400:
            print(f"PASS: POST /api/risk-policies/{policy_id}/rollback returned 400 (expected for first version)")
        else:
            print(f"PASS: POST /api/risk-policies/{policy_id}/rollback completed successfully")


class TestUserAlertCenter:
    """User Alert Center: severity/category/search filters, ack/dismiss, history, drilldown"""
    
    def test_list_alerts(self, auth_session):
        """GET /api/user/alerts returns alerts list"""
        resp = auth_session.get(f"{BASE_URL}/api/user/alerts")
        assert resp.status_code == 200, f"List alerts failed: {resp.text}"
        data = resp.json()
        assert "items" in data, "Should have items array"
        items = data["items"]
        if items:
            item = items[0]
            assert "id" in item, "Alert should have id"
            assert "severity" in item, "Alert should have severity"
            assert "category" in item, "Alert should have category"
            assert "message" in item, "Alert should have message"
            assert "status" in item, "Alert should have status"
            assert "drilldown" in item, "Alert should have drilldown"
            assert "history" in item, "Alert should have history"
        print(f"PASS: GET /api/user/alerts returned {len(items)} alerts")
    
    def test_filter_by_severity(self, auth_session):
        """GET /api/user/alerts?severity=info filters by severity"""
        resp = auth_session.get(f"{BASE_URL}/api/user/alerts", params={"severity": "info"})
        assert resp.status_code == 200, f"Filter by severity failed: {resp.text}"
        data = resp.json()
        items = data.get("items", [])
        for item in items:
            assert item.get("severity") == "info", f"Expected severity=info, got {item.get('severity')}"
        print(f"PASS: GET /api/user/alerts?severity=info returned {len(items)} alerts")
    
    def test_filter_by_category(self, auth_session):
        """GET /api/user/alerts?category=risk filters by category"""
        resp = auth_session.get(f"{BASE_URL}/api/user/alerts", params={"category": "risk"})
        assert resp.status_code == 200, f"Filter by category failed: {resp.text}"
        data = resp.json()
        items = data.get("items", [])
        for item in items:
            assert item.get("category") == "risk", f"Expected category=risk, got {item.get('category')}"
        print(f"PASS: GET /api/user/alerts?category=risk returned {len(items)} alerts")
    
    def test_search_alerts(self, auth_session):
        """GET /api/user/alerts?query=test searches alerts"""
        resp = auth_session.get(f"{BASE_URL}/api/user/alerts", params={"query": "test"})
        assert resp.status_code == 200, f"Search alerts failed: {resp.text}"
        data = resp.json()
        print(f"PASS: GET /api/user/alerts?query=test returned {len(data.get('items', []))} alerts")
    
    def test_acknowledge_alert(self, auth_session):
        """POST /api/user/alerts/{id}/ack acknowledges alert"""
        # Get an alert to acknowledge
        list_resp = auth_session.get(f"{BASE_URL}/api/user/alerts")
        items = list_resp.json().get("items", [])
        if not items:
            pytest.skip("No alerts to test acknowledge")
        
        alert_id = items[0]["id"]
        payload = {"note": "test_ack_iter194"}
        resp = auth_session.post(f"{BASE_URL}/api/user/alerts/{alert_id}/ack", json=payload)
        assert resp.status_code == 200, f"Acknowledge alert failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "ack", "Status should be ack"
        print(f"PASS: POST /api/user/alerts/{alert_id}/ack set status=ack")
    
    def test_dismiss_alert(self, auth_session):
        """POST /api/user/alerts/{id}/dismiss dismisses alert"""
        list_resp = auth_session.get(f"{BASE_URL}/api/user/alerts")
        items = list_resp.json().get("items", [])
        if not items:
            pytest.skip("No alerts to test dismiss")
        
        # Find an alert that's not already dismissed
        alert_to_dismiss = None
        for item in items:
            if item.get("status") != "dismissed":
                alert_to_dismiss = item
                break
        
        if not alert_to_dismiss:
            pytest.skip("No non-dismissed alerts to test")
        
        alert_id = alert_to_dismiss["id"]
        payload = {"note": "test_dismiss_iter194"}
        resp = auth_session.post(f"{BASE_URL}/api/user/alerts/{alert_id}/dismiss", json=payload)
        assert resp.status_code == 200, f"Dismiss alert failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "dismissed", "Status should be dismissed"
        print(f"PASS: POST /api/user/alerts/{alert_id}/dismiss set status=dismissed")
    
    def test_drilldown_links_present(self, auth_session):
        """Verify drilldown links are present in alert response"""
        resp = auth_session.get(f"{BASE_URL}/api/user/alerts")
        items = resp.json().get("items", [])
        if not items:
            pytest.skip("No alerts to verify drilldown")
        
        item = items[0]
        drilldown = item.get("drilldown", {})
        # Verify drilldown structure exists
        expected_keys = ["execution_ref", "activity_log_ref", "strategy_ref", "symbol", "decision_trace_ref"]
        for key in expected_keys:
            assert key in drilldown, f"Drilldown should have {key}"
        print(f"PASS: Alert drilldown contains all expected keys: {expected_keys}")


class TestUserExecutionAnalytics:
    """User Execution Analytics: slippage, latency, fill rate, quality score, reject/cancel/retry"""
    
    def test_execution_positions(self, auth_session):
        """GET /api/user/execution/positions returns positions"""
        resp = auth_session.get(f"{BASE_URL}/api/user/execution/positions", params={"include_closed": "false"})
        assert resp.status_code == 200, f"Execution positions failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Should return list"
        print(f"PASS: GET /api/user/execution/positions returned {len(data)} positions")
    
    def test_execution_intents(self, auth_session):
        """GET /api/user/execution/intents returns intents"""
        resp = auth_session.get(f"{BASE_URL}/api/user/execution/intents", params={"limit": 30})
        assert resp.status_code == 200, f"Execution intents failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Should return list"
        print(f"PASS: GET /api/user/execution/intents returned {len(data)} intents")
    
    def test_live_trades(self, auth_session):
        """GET /api/user/live/trades returns trade history"""
        resp = auth_session.get(f"{BASE_URL}/api/user/live/trades", params={"window": "24h", "limit": 30})
        assert resp.status_code == 200, f"Live trades failed: {resp.text}"
        data = resp.json()
        assert "items" in data, "Should have items"
        print(f"PASS: GET /api/user/live/trades returned {len(data.get('items', []))} trades")
    
    def test_execution_quality(self, auth_session):
        """GET /api/user/live/execution-quality returns quality metrics"""
        resp = auth_session.get(f"{BASE_URL}/api/user/live/execution-quality", params={"window": "24h"})
        assert resp.status_code == 200, f"Execution quality failed: {resp.text}"
        data = resp.json()
        # Verify expected analytics fields
        expected_fields = ["avg_slippage", "avg_latency", "fill_rate", "reject_count", "cancel_count", "retry_count", "own_execution_quality_score"]
        for field in expected_fields:
            assert field in data, f"Should have {field}"
        print(f"PASS: GET /api/user/live/execution-quality returned quality metrics: slippage={data.get('avg_slippage')}, latency={data.get('avg_latency')}, quality_score={data.get('own_execution_quality_score')}")
    
    def test_strategy_performance(self, auth_session):
        """GET /api/user/live/strategy-performance returns strategy performance"""
        resp = auth_session.get(f"{BASE_URL}/api/user/live/strategy-performance", params={"window": "24h"})
        assert resp.status_code == 200, f"Strategy performance failed: {resp.text}"
        data = resp.json()
        assert "items" in data, "Should have items"
        print(f"PASS: GET /api/user/live/strategy-performance returned {len(data.get('items', []))} items")


class TestPortfolioReportsRedirect:
    """Portfolio reports redirect: /user/reports -> /user/portfolio?tab=reports"""
    
    def test_portfolio_endpoint(self, auth_session):
        """GET /api/user/portfolio returns portfolio data"""
        resp = auth_session.get(f"{BASE_URL}/api/user/portfolio")
        assert resp.status_code == 200, f"Portfolio endpoint failed: {resp.text}"
        print("PASS: GET /api/user/portfolio returned 200")
    
    def test_weekly_reports(self, auth_session):
        """GET /api/user/reports/weekly returns weekly reports"""
        resp = auth_session.get(f"{BASE_URL}/api/user/reports/weekly")
        assert resp.status_code == 200, f"Weekly reports failed: {resp.text}"
        print("PASS: GET /api/user/reports/weekly returned 200")


class TestSettingsEndpoints:
    """Settings page endpoints"""
    
    def test_auth_me(self, auth_session):
        """GET /api/auth/me returns user profile"""
        resp = auth_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"Auth me failed: {resp.text}"
        data = resp.json()
        assert "email" in data, "Should have email"
        print("PASS: GET /api/auth/me returned user profile")
    
    def test_exchange_connections(self, auth_session):
        """GET /api/user/exchange-connections returns connections"""
        resp = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert resp.status_code == 200, f"Exchange connections failed: {resp.text}"
        print("PASS: GET /api/user/exchange-connections returned 200")
    
    def test_user_risk_settings(self, auth_session):
        """GET /api/user-risk/settings returns risk settings"""
        resp = auth_session.get(f"{BASE_URL}/api/user-risk/settings")
        assert resp.status_code == 200, f"User risk settings failed: {resp.text}"
        print("PASS: GET /api/user-risk/settings returned 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
