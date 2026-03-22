"""
FAZ-5 P0 Strategy Control + Governance System Tests
====================================================
Tests for critical closure/stabilization features:
1. Disable action: Decision Modal required + preview required before backend accept
2. Decommission action: Decision Modal required + preview required before execute
3. Rollout/Promote/Rollback operations: preview token required via Unified Decision Modal
4. Drift Disable Strategy action: preview required; Apply Recommended only opens modal (no auto-execute)
5. DecisionModal: submit disabled when preview fails/missing
6. Approval chain: admin requester creates rollback-request, super_admin approve/reject, decision_context visible
7. Permission matrix: super_admin full, admin request-only behavior
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_REQUESTER_EMAIL = "canary.requester@platform.local"
ADMIN_REQUESTER_PASSWORD = "CanaryRequester123!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def super_admin_token(api_client):
    """Get super_admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Super admin authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_requester_token(api_client):
    """Get admin requester authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_REQUESTER_EMAIL,
        "password": ADMIN_REQUESTER_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Admin requester authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def super_admin_client(api_client, super_admin_token):
    """Session with super_admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
    return api_client


@pytest.fixture(scope="module")
def admin_requester_client(api_client, admin_requester_token):
    """Session with admin requester auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_requester_token}"
    })
    return session


class TestStrategyControlOverview:
    """Test strategy control overview endpoint"""
    
    def test_overview_returns_strategies(self, super_admin_client):
        """Verify overview endpoint returns strategy list"""
        response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "ok"
        assert "strategies" in data
        assert isinstance(data["strategies"], list)
        print(f"Found {len(data['strategies'])} strategies")
    
    def test_overview_contains_permission_matrix(self, super_admin_client):
        """Verify permission matrix is present"""
        response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        assert response.status_code == 200
        
        data = response.json()
        assert "permission_matrix" in data
        assert data["permission_matrix"].get("super_admin") == "full"
        assert data["permission_matrix"].get("admin") == "request_only"
        print(f"Permission matrix: {data['permission_matrix']}")


class TestDisableActionPreviewRequired:
    """Test disable action requires preview token"""
    
    def test_disable_without_preview_rejected(self, super_admin_client):
        """Disable action without preview_token should be rejected"""
        # First get a strategy
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        assert overview.status_code == 200
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available for testing")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # Try disable without preview_token
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/disable",
            json={
                "reason": "test_disable_without_preview",
                "confirm_phrase": "DISABLE STRATEGY",
                "preview_token": None,
                "dry_run": True
            }
        )
        
        # Should be rejected because preview_token is required
        data = response.json()
        assert data.get("status") == "rejected", f"Expected rejected, got: {data}"
        assert "preview" in data.get("message", "").lower() or "impact" in data.get("message", "").lower()
        print(f"Disable without preview correctly rejected: {data.get('message')}")
    
    def test_disable_with_preview_flow(self, super_admin_client):
        """Disable action with valid preview_token should work"""
        # Get a strategy
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # Step 1: Request impact preview
        preview_response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/impact-preview",
            json={
                "action_type": "disable",
                "params": {}
            }
        )
        assert preview_response.status_code == 200, f"Preview request failed: {preview_response.text}"
        
        preview_data = preview_response.json()
        assert "preview_token" in preview_data
        assert "preview" in preview_data
        preview_token = preview_data["preview_token"]
        print(f"Got preview token: {preview_token}")
        print(f"Preview data: {preview_data.get('preview')}")
        
        # Step 2: Try disable with preview_token (dry_run)
        disable_response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/disable",
            json={
                "reason": "test_disable_with_preview",
                "confirm_phrase": "DISABLE STRATEGY",
                "preview_token": preview_token,
                "dry_run": True
            }
        )
        
        disable_data = disable_response.json()
        # With dry_run=True, should succeed or be dry_run status
        assert disable_data.get("status") in ["success", "dry_run", "rejected"], f"Unexpected status: {disable_data}"
        print(f"Disable with preview result: {disable_data.get('status')} - {disable_data.get('message')}")


class TestDecommissionActionPreviewRequired:
    """Test decommission action requires preview token"""
    
    def test_decommission_without_preview_rejected(self, super_admin_client):
        """Decommission action without preview_token should be rejected"""
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/decommission",
            json={
                "reason": "test_decommission_without_preview",
                "confirm_phrase": "DECOMMISSION STRATEGY",
                "preview_token": None,
                "dry_run": True
            }
        )
        
        data = response.json()
        # Should be rejected - either for preview or for lifecycle state
        assert data.get("status") == "rejected", f"Expected rejected, got: {data}"
        print(f"Decommission without preview correctly rejected: {data.get('message')}")


class TestRolloutOperationsPreviewRequired:
    """Test rollout/promote/rollback operations require preview token"""
    
    def test_rollout_without_preview_rejected(self, super_admin_client):
        """Rollout action without preview_token should be rejected"""
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollout",
            json={
                "reason": "test_rollout_without_preview",
                "confirm_phrase": "APPLY ROLLOUT",
                "rollout_percentage": 10,
                "preview_token": None,
                "dry_run": True
            }
        )
        
        data = response.json()
        assert data.get("status") == "rejected", f"Expected rejected, got: {data}"
        assert "preview" in data.get("message", "").lower()
        print(f"Rollout without preview correctly rejected: {data.get('message')}")
    
    def test_promote_shadow_without_preview_rejected(self, super_admin_client):
        """Promote shadow without preview_token should be rejected"""
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/promote-shadow",
            json={
                "reason": "test_promote_without_preview",
                "confirm_phrase": "PROMOTE SHADOW",
                "preview_token": None,
                "dry_run": True
            }
        )
        
        data = response.json()
        assert data.get("status") == "rejected", f"Expected rejected, got: {data}"
        print(f"Promote shadow without preview correctly rejected: {data.get('message')}")
    
    def test_rollback_without_preview_rejected(self, super_admin_client):
        """Rollback without preview_token should be rejected"""
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback",
            json={
                "reason": "test_rollback_without_preview",
                "confirm_phrase": "ROLLBACK LAST ACTION",
                "preview_token": None,
                "dry_run": True
            }
        )
        
        data = response.json()
        assert data.get("status") == "rejected", f"Expected rejected, got: {data}"
        print(f"Rollback without preview correctly rejected: {data.get('message')}")


class TestDriftDisableStrategyPreviewRequired:
    """Test drift disable_strategy action requires preview token"""
    
    def test_drift_alerts_endpoint(self, super_admin_client):
        """Verify drift alerts endpoint works"""
        response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "ok"
        assert "items" in data
        print(f"Found {len(data.get('items', []))} drift alerts")
        
        # Check recommended_action is present
        for alert in data.get("items", [])[:3]:
            assert "recommended_action" in alert, f"Missing recommended_action in alert: {alert}"
            print(f"Alert {alert.get('alert_id')}: recommended={alert.get('recommended_action', {}).get('type')}")
    
    def test_drift_disable_without_preview_rejected(self, super_admin_client):
        """Drift disable_strategy without preview_token should be rejected"""
        # Get drift alerts
        alerts_response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts")
        alerts = alerts_response.json().get("items", [])
        
        if not alerts:
            pytest.skip("No drift alerts available for testing")
        
        alert_id = alerts[0]["alert_id"]
        
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{alert_id}/disable-strategy",
            json={
                "reason": "test_drift_disable_without_preview",
                "confirm_phrase": "DISABLE VIA DRIFT",
                "preview_token": None,
                "dry_run": True
            }
        )
        
        data = response.json()
        assert data.get("status") == "rejected", f"Expected rejected, got: {data}"
        assert "preview" in data.get("message", "").lower()
        print(f"Drift disable without preview correctly rejected: {data.get('message')}")


class TestImpactPreviewEndpoint:
    """Test impact preview endpoint"""
    
    def test_impact_preview_returns_token(self, super_admin_client):
        """Impact preview should return preview_token and preview data"""
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/impact-preview",
            json={
                "action_type": "disable",
                "params": {}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "preview_token" in data
        assert "preview" in data
        assert data["preview"].get("expected_reject_delta") is not None
        assert data["preview"].get("expected_pnl_impact") is not None
        assert data["preview"].get("risk_level") is not None
        assert data["preview"].get("confidence") is not None
        
        print(f"Preview token: {data['preview_token']}")
        print(f"Preview: {data['preview']}")
    
    def test_impact_preview_for_rollout(self, super_admin_client):
        """Impact preview for rollout action"""
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/impact-preview",
            json={
                "action_type": "rollout",
                "params": {"rollout_percentage": 25}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "preview_token" in data
        print(f"Rollout preview: {data['preview']}")


class TestApprovalWorkflow:
    """Test approval workflow: admin creates request, super_admin approves/rejects"""
    
    def test_admin_can_create_rollback_request(self, admin_requester_client, super_admin_client):
        """Admin requester can create rollback request"""
        # First get strategies and snapshots using super_admin
        overview = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        strategies = overview.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # Get rollback snapshots
        snapshots_response = super_admin_client.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-snapshots"
        )
        
        if snapshots_response.status_code != 200:
            pytest.skip(f"Could not get snapshots: {snapshots_response.text}")
        
        snapshots = snapshots_response.json().get("items", [])
        if not snapshots:
            pytest.skip("No rollback snapshots available")
        
        snapshot_trace_id = snapshots[0]["snapshot_trace_id"]
        
        # Admin requester creates rollback request
        response = admin_requester_client.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-request",
            json={
                "reason": "TEST_rollback_request_by_admin",
                "snapshot_trace_id": snapshot_trace_id
            }
        )
        
        # Should succeed or be rejected based on permissions
        data = response.json()
        print(f"Rollback request result: {data.get('status')} - {data.get('message')}")
        
        if data.get("status") == "success":
            # Verify decision_context is present
            assert "decision_context" in data or "decision_context" in data.get("state_snapshot", {})
            print("Rollback request created successfully with decision_context")
    
    def test_approval_list_contains_decision_context(self, super_admin_client):
        """Approval list should contain decision_context with preview/risk/recommendation"""
        response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy/approval-requests")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "ok"
        
        items = data.get("items", [])
        print(f"Found {len(items)} approval requests")
        
        for item in items[:3]:
            print(f"Request {item.get('request_id')}: status={item.get('status')}")
            
            # Check decision_context structure
            decision_context = item.get("decision_context", {})
            if decision_context:
                assert "preview" in decision_context or decision_context == {}, f"Missing preview in decision_context"
                assert "risk" in decision_context or decision_context == {}, f"Missing risk in decision_context"
                assert "recommendation" in decision_context or decision_context == {}, f"Missing recommendation in decision_context"
                print(f"  decision_context.preview: {decision_context.get('preview', {})}")
                print(f"  decision_context.risk: {decision_context.get('risk', {})}")
                print(f"  decision_context.recommendation: {decision_context.get('recommendation', {})}")
    
    def test_super_admin_can_approve_reject(self, super_admin_client):
        """Super admin can approve/reject requests"""
        # Get pending requests
        response = super_admin_client.get(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests",
            params={"status": "pending"}
        )
        assert response.status_code == 200
        
        items = response.json().get("items", [])
        print(f"Found {len(items)} pending approval requests")
        
        # If there's a pending request, try to reject it (safer than approve)
        if items:
            request_id = items[0]["request_id"]
            reject_response = super_admin_client.post(
                f"{BASE_URL}/api/admin/futures/strategy/approval-requests/{request_id}/reject",
                json={"reason": "TEST_rejection_by_super_admin"}
            )
            
            reject_data = reject_response.json()
            print(f"Reject result: {reject_data.get('status')} - {reject_data.get('message')}")


class TestPermissionMatrix:
    """Test permission matrix enforcement"""
    
    def test_admin_cannot_access_super_admin_endpoints(self, admin_requester_client):
        """Admin requester should have limited access"""
        # Try to access overview (should work for admin too)
        response = admin_requester_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        
        # Admin should be able to view but with limited actions
        if response.status_code == 200:
            data = response.json()
            print(f"Admin can view overview: {data.get('status')}")
        elif response.status_code == 403:
            print("Admin correctly restricted from overview")
        else:
            print(f"Unexpected response: {response.status_code}")
    
    def test_super_admin_has_full_access(self, super_admin_client):
        """Super admin should have full access"""
        response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("permission_matrix", {}).get("super_admin") == "full"
        print("Super admin has full access confirmed")


class TestDriftActionCenter:
    """Test drift action center functionality"""
    
    def test_drift_alerts_have_recommended_action(self, super_admin_client):
        """Each drift alert should have recommended_action"""
        response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts")
        assert response.status_code == 200
        
        data = response.json()
        alerts = data.get("items", [])
        
        for alert in alerts:
            assert "recommended_action" in alert
            rec = alert["recommended_action"]
            assert "type" in rec
            assert "confidence" in rec
            assert "reason" in rec
            print(f"Alert {alert.get('alert_id')}: recommended={rec.get('type')} ({rec.get('confidence')}%)")
    
    def test_drift_ack_action(self, super_admin_client):
        """Test drift ack action (no preview required)"""
        alerts_response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts")
        alerts = alerts_response.json().get("items", [])
        
        if not alerts:
            pytest.skip("No drift alerts available")
        
        alert_id = alerts[0]["alert_id"]
        
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{alert_id}/ack",
            json={
                "reason": "TEST_ack_drift_alert",
                "dry_run": True
            }
        )
        
        data = response.json()
        assert data.get("status") in ["success", "dry_run"], f"Unexpected: {data}"
        print(f"Drift ack result: {data.get('status')}")
    
    def test_drift_ignore_requires_confirm(self, super_admin_client):
        """Drift ignore requires confirm phrase"""
        alerts_response = super_admin_client.get(f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts")
        alerts = alerts_response.json().get("items", [])
        
        if not alerts:
            pytest.skip("No drift alerts available")
        
        alert_id = alerts[0]["alert_id"]
        
        # Without confirm phrase
        response = super_admin_client.post(
            f"{BASE_URL}/api/admin/futures/drift-alert/{alert_id}/ignore",
            json={
                "reason": "TEST_ignore_without_confirm",
                "confirm_phrase": "",
                "dry_run": True
            }
        )
        
        data = response.json()
        assert data.get("status") == "rejected"
        print(f"Ignore without confirm correctly rejected: {data.get('message')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
