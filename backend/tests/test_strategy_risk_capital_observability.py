"""
Test suite for Strategy Risk Capital and Observability endpoints
Testing P1-1 + P1-2 + P1-3 features:
- Risk & Capital Control Layer: status, limits preview/apply, exposure preview/apply
- Role enforcement: admin vs super_admin permissions
- Report detail page endpoints
- Export controls: CSV/JSON
- Action Impact Timeline
- Risk breach ↔ alert detail link
"""
import os
import pytest
import requests
import json
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"

# Global token cache
_token_cache = {"token": None, "expires": 0}


def get_auth_token():
    """Get cached auth token or login"""
    global _token_cache
    current_time = time.time()
    
    if _token_cache["token"] and current_time < _token_cache["expires"]:
        return _token_cache["token"]
    
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.text}")
    
    data = response.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires"] = current_time + 600  # Cache for 10 minutes
    return _token_cache["token"]


def get_auth_headers():
    """Get auth headers"""
    return {"Authorization": f"Bearer {get_auth_token()}"}


class TestHealthAndAuth:
    """Health and authentication tests"""
    
    def test_health_check(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        print("✓ Health check passed")
    
    def test_login_super_admin(self):
        """Test super_admin login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "super_admin"
        print("✓ Super admin login passed")


class TestRiskCapitalStatus:
    """Test Risk & Capital Control Layer status endpoint"""
    
    def test_risk_capital_status(self):
        """Test GET /admin/strategy/risk-capital/status"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=get_auth_headers(),
            params={"include_alerts": True}
        )
        assert response.status_code == 200, f"Status failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "limits" in data, "Missing limits in response"
        assert "allocation" in data, "Missing allocation in response"
        assert "breaches" in data, "Missing breaches in response"
        assert "updated_at" in data, "Missing updated_at in response"
        print(f"✓ Risk capital status returned with {len(data.get('breaches', []))} breaches")
    
    def test_risk_capital_status_without_alerts(self):
        """Test GET /admin/strategy/risk-capital/status without alerts"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=get_auth_headers(),
            params={"include_alerts": False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("linked_alerts") == [], "Alerts should be empty when include_alerts=False"
        print("✓ Risk capital status without alerts passed")


class TestRiskLimitsPreviewApply:
    """Test Risk Limits Preview and Apply endpoints"""
    
    def test_risk_limits_preview(self):
        """Test POST /admin/strategy/risk-capital/limits/preview"""
        payload = {
            "max_open_risk_pct": 15.0,
            "max_daily_loss_pct": 5.0,
            "max_portfolio_drawdown_pct": 10.0
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/limits/preview",
            headers=get_auth_headers(),
            json=payload
        )
        assert response.status_code == 200, f"Preview failed: {response.text}"
        data = response.json()
        
        assert data["status"] == "success"
        assert "preview_token" in data, "Missing preview_token"
        assert "state_snapshot" in data, "Missing state_snapshot"
        assert "before_limits" in data["state_snapshot"]
        assert "after_limits" in data["state_snapshot"]
        print(f"✓ Risk limits preview generated token: {data['preview_token'][:20]}...")
    
    def test_risk_limits_apply_requires_preview(self):
        """Test that apply requires valid preview token"""
        payload = {
            "preview_token": "invalid-token-12345",
            "confirm": True,
            "reason": "Test apply without valid preview"
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/limits/apply",
            headers=get_auth_headers(),
            json=payload
        )
        assert response.status_code == 422, "Should reject invalid preview token"
        print("✓ Risk limits apply correctly rejects invalid preview token")
    
    def test_risk_limits_apply_requires_confirm(self):
        """Test that apply requires confirm=True"""
        # First get a valid preview token
        preview_response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/limits/preview",
            headers=get_auth_headers(),
            json={"max_open_risk_pct": 12.0}
        )
        preview_token = preview_response.json()["preview_token"]
        
        # Try to apply without confirm
        payload = {
            "preview_token": preview_token,
            "confirm": False,
            "reason": "Test without confirm"
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/limits/apply",
            headers=get_auth_headers(),
            json=payload
        )
        assert response.status_code == 422, "Should reject when confirm=False"
        print("✓ Risk limits apply correctly requires confirm=True")
    
    def test_risk_limits_apply_requires_reason(self):
        """Test that apply requires reason with min 3 chars"""
        preview_response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/limits/preview",
            headers=get_auth_headers(),
            json={"max_open_risk_pct": 12.0}
        )
        preview_token = preview_response.json()["preview_token"]
        
        payload = {
            "preview_token": preview_token,
            "confirm": True,
            "reason": "ab"  # Too short
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/limits/apply",
            headers=get_auth_headers(),
            json=payload
        )
        assert response.status_code == 422, "Should reject short reason"
        print("✓ Risk limits apply correctly requires reason >= 3 chars")
    
    def test_risk_limits_full_flow(self):
        """Test complete preview -> apply flow"""
        # Preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/limits/preview",
            headers=get_auth_headers(),
            json={"max_open_risk_pct": 18.0, "max_daily_loss_pct": 6.0}
        )
        assert preview_response.status_code == 200
        preview_token = preview_response.json()["preview_token"]
        
        # Apply
        apply_response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/limits/apply",
            headers=get_auth_headers(),
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "Testing full flow for risk limits"
            }
        )
        assert apply_response.status_code == 200, f"Apply failed: {apply_response.text}"
        data = apply_response.json()
        assert data["status"] == "success"
        assert data["message"] == "risk_limits_applied"
        print("✓ Risk limits full preview->apply flow passed")


class TestExposureOverridePreviewApply:
    """Test Exposure Override Preview and Apply endpoints"""
    
    def test_exposure_override_preview(self):
        """Test POST /admin/strategy/risk-capital/exposure-override/preview"""
        # First get available strategies from status
        status_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=get_auth_headers()
        )
        allocation = status_response.json().get("allocation", {})
        
        if not allocation:
            pytest.skip("No strategies available for exposure override test")
        
        strategy_id = list(allocation.keys())[0]
        
        payload = {
            "strategy_id": strategy_id,
            "override_cap_pct": 25.0
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/exposure-override/preview",
            headers=get_auth_headers(),
            json=payload
        )
        assert response.status_code == 200, f"Preview failed: {response.text}"
        data = response.json()
        
        assert data["status"] == "success"
        assert "preview_token" in data
        assert "state_snapshot" in data
        print(f"✓ Exposure override preview for {strategy_id} generated")
    
    def test_exposure_override_requires_reason(self):
        """Test that exposure override apply requires reason"""
        status_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/status",
            headers=get_auth_headers()
        )
        allocation = status_response.json().get("allocation", {})
        
        if not allocation:
            pytest.skip("No strategies available")
        
        strategy_id = list(allocation.keys())[0]
        
        # Get preview token
        preview_response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/exposure-override/preview",
            headers=get_auth_headers(),
            json={"strategy_id": strategy_id, "override_cap_pct": 20.0}
        )
        preview_token = preview_response.json()["preview_token"]
        
        # Try apply with short reason
        apply_response = requests.post(
            f"{BASE_URL}/api/admin/strategy/risk-capital/exposure-override/apply",
            headers=get_auth_headers(),
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "ab"
            }
        )
        assert apply_response.status_code == 422
        print("✓ Exposure override correctly requires reason >= 3 chars")


class TestRiskBreaches:
    """Test Risk Breaches endpoint"""
    
    def test_get_all_breaches(self):
        """Test GET /admin/strategy/risk-capital/breaches"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/breaches",
            headers=get_auth_headers()
        )
        assert response.status_code == 200, f"Breaches failed: {response.text}"
        data = response.json()
        
        assert "count" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        print(f"✓ Got {data['count']} breaches")
    
    def test_get_only_open_breaches(self):
        """Test GET /admin/strategy/risk-capital/breaches?only_open=true"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/breaches",
            headers=get_auth_headers(),
            params={"only_open": True}
        )
        assert response.status_code == 200
        data = response.json()
        
        # All returned items should be breached
        for item in data["items"]:
            assert item.get("is_breached") == True, "only_open should return only breached items"
        print(f"✓ Got {data['count']} open breaches")


class TestAlertBreachLink:
    """Test Alert-Breach Link endpoint"""
    
    def test_alert_breach_link_not_found(self):
        """Test GET /admin/strategy/risk-capital/alerts/{alert_id}/breach-link with invalid ID"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/alerts/invalid-alert-id/breach-link",
            headers=get_auth_headers()
        )
        assert response.status_code == 404
        print("✓ Alert breach link correctly returns 404 for invalid alert")


class TestStrategyObservabilityEndpoints:
    """Test Strategy Observability endpoints"""
    
    def test_get_strategies_list(self):
        """Test GET /admin/strategy/observability/strategies"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/strategies",
            headers=get_auth_headers(),
            params={"window": "24h"}
        )
        assert response.status_code == 200, f"Strategies list failed: {response.text}"
        data = response.json()
        
        assert "items" in data
        assert "count" in data
        assert "window" in data
        print(f"✓ Got {data['count']} strategies")
    
    def test_get_strategy_detail(self):
        """Test GET /admin/strategy/observability/{strategyId}/detail"""
        # First get available strategies
        strategies_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/strategies",
            headers=get_auth_headers(),
            params={"window": "24h"}
        )
        strategies = strategies_response.json().get("items", [])
        
        if not strategies:
            pytest.skip("No strategies available for detail test")
        
        strategy_id = strategies[0]
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/{strategy_id}/detail",
            headers=get_auth_headers(),
            params={"window": "24h"}
        )
        assert response.status_code == 200, f"Detail failed: {response.text}"
        data = response.json()
        
        assert data["status"] == "success"
        assert "summary" in data
        assert "trend_rows" in data
        assert "top_symbols" in data
        assert "rejection_reasons" in data
        assert "recent_rows" in data
        print(f"✓ Got strategy detail for {strategy_id}")
    
    def test_get_strategy_detail_with_time_filters(self):
        """Test strategy detail with time_from and time_to filters"""
        strategies_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/strategies",
            headers=get_auth_headers()
        )
        strategies = strategies_response.json().get("items", [])
        
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/{strategy_id}/detail",
            headers=get_auth_headers(),
            params={
                "window": "7d",
                "time_from": "2026-03-20T00:00:00Z",
                "time_to": "2026-03-23T23:59:59Z"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "filters" in data
        print("✓ Strategy detail with time filters passed")


class TestExportControls:
    """Test Export Controls (CSV/JSON)"""
    
    def test_export_json(self):
        """Test GET /admin/strategy/observability/export?export_format=json"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/export",
            headers=get_auth_headers(),
            params={
                "export_format": "json",
                "window": "24h",
                "top_n": 100
            }
        )
        assert response.status_code == 200, f"JSON export failed: {response.text}"
        data = response.json()
        
        assert data["status"] == "success"
        assert data["export_format"] == "json"
        assert "filters" in data
        assert "items" in data
        
        # Verify filters are reflected
        assert data["filters"]["window"] == "24h"
        print(f"✓ JSON export returned {data['count']} items")
    
    def test_export_csv(self):
        """Test GET /admin/strategy/observability/export?export_format=csv"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/export",
            headers=get_auth_headers(),
            params={
                "export_format": "csv",
                "window": "24h",
                "top_n": 50
            }
        )
        assert response.status_code == 200, f"CSV export failed: {response.text}"
        assert "text/csv" in response.headers.get("Content-Type", "")
        
        # Check content-disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disposition
        assert ".csv" in content_disposition
        
        # Verify CSV content has headers
        content = response.text
        assert "signal_id" in content
        assert "strategy_id" in content
        print("✓ CSV export passed with proper headers")
    
    def test_export_with_strategy_filter(self):
        """Test export with strategy_id filter"""
        strategies_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/strategies",
            headers=get_auth_headers()
        )
        strategies = strategies_response.json().get("items", [])
        
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/export",
            headers=get_auth_headers(),
            params={
                "export_format": "json",
                "window": "24h",
                "strategy_id": strategy_id
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify filter is reflected
        assert data["filters"]["strategy_id"] == strategy_id
        print(f"✓ Export with strategy filter {strategy_id} passed")


class TestActionImpactTimeline:
    """Test Action Impact Timeline endpoint"""
    
    def test_action_impact_timeline(self):
        """Test GET /admin/strategy/action-impact-timeline"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=get_auth_headers(),
            params={"window": "24h", "limit": 100}
        )
        assert response.status_code == 200, f"Timeline failed: {response.text}"
        data = response.json()
        
        assert data["status"] == "success"
        assert "summary" in data
        assert "items" in data
        assert "filters" in data
        
        # Verify summary structure
        summary = data["summary"]
        assert "total" in summary
        assert "manual_action_count" in summary
        assert "system_reaction_count" in summary
        print(f"✓ Timeline returned {summary['total']} items (manual: {summary['manual_action_count']}, system: {summary['system_reaction_count']})")
    
    def test_action_impact_timeline_with_strategy_filter(self):
        """Test timeline with strategy_id filter"""
        strategies_response = requests.get(
            f"{BASE_URL}/api/admin/strategy/observability/strategies",
            headers=get_auth_headers()
        )
        strategies = strategies_response.json().get("items", [])
        
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=get_auth_headers(),
            params={"window": "7d", "strategy_id": strategy_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filters"]["strategy_id"] == strategy_id
        print(f"✓ Timeline with strategy filter {strategy_id} passed")
    
    def test_timeline_item_structure(self):
        """Test timeline item structure has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/action-impact-timeline",
            headers=get_auth_headers(),
            params={"window": "7d", "limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["items"]:
            item = data["items"][0]
            # Check required fields
            assert "event_id" in item
            assert "event_type" in item  # manual_action or system_reaction
            assert "timestamp" in item
            assert "action" in item
            assert "actor_role" in item
            print(f"✓ Timeline item structure verified: event_type={item['event_type']}")
        else:
            print("✓ Timeline returned empty (no events in window)")


class TestTopSignalsAndSimulation:
    """Test Top Signals and Simulation endpoints"""
    
    def test_get_top_signals(self):
        """Test GET /admin/strategy/top-signals"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/top-signals",
            headers=get_auth_headers(),
            params={"window": "24h", "top_n": 10}
        )
        assert response.status_code == 200, f"Top signals failed: {response.text}"
        data = response.json()
        
        assert "items" in data
        print(f"✓ Got {len(data.get('items', []))} top signals")
    
    def test_score_config(self):
        """Test GET /admin/strategy/score-config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/score-config",
            headers=get_auth_headers()
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert "config" in data
        config = data["config"]
        assert "threshold" in config
        assert "factor_weights" in config
        print(f"✓ Score config: threshold={config['threshold']}")


class TestReportEndpoint:
    """Test Strategy Observability Report endpoint"""
    
    def test_strategy_report(self):
        """Test GET /admin/strategy/report"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/report",
            headers=get_auth_headers(),
            params={"window": "24h"}
        )
        assert response.status_code == 200, f"Report failed: {response.text}"
        data = response.json()
        
        # Verify report structure
        assert "active_spot_strategies" in data or "signals_total" in data
        print("✓ Strategy report endpoint working")


class TestAuditLog:
    """Test Audit Log endpoint"""
    
    def test_strategy_audit_log(self):
        """Test GET /admin/strategy/audit-log"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/audit-log",
            headers=get_auth_headers(),
            params={"limit": 50}
        )
        assert response.status_code == 200, f"Audit log failed: {response.text}"
        data = response.json()
        
        assert "count" in data
        assert "items" in data
        print(f"✓ Audit log returned {data['count']} entries")
    
    def test_risk_capital_action_log(self):
        """Test GET /admin/strategy/risk-capital/action-log"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/risk-capital/action-log",
            headers=get_auth_headers(),
            params={"limit": 50}
        )
        assert response.status_code == 200, f"Action log failed: {response.text}"
        data = response.json()
        
        assert "count" in data
        assert "items" in data
        print(f"✓ Risk capital action log returned {data['count']} entries")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
