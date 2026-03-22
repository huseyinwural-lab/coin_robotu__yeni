"""
Faz-4+ Strategy Control Governance Tests - Rollback Snapshots & Approval Workflow
- GET /api/admin/futures/strategy/{id}/rollback-snapshots: timestamp/actor/action_type/diff preview, single-strategy scope
- POST /api/admin/futures/strategy/{id}/rollback-request: reason required, preview, expires_at (24h)
- GET /api/admin/futures/strategy/approval-requests: pending/expired/approved views
- POST /api/admin/futures/strategy/approval-requests/{id}/approve: super_admin only, before/after snapshot + rollback_reference/audit
- POST /api/admin/futures/strategy/approval-requests/{id}/reject: super_admin only
- Permission matrix: super_admin full, admin request-only, ops read-only
- GET /api/admin/futures/strategy-control/drift-alerts: recommended_action deterministic output (type/confidence/reason)
- GET /api/admin/futures/strategy-control/policy-suggestions: taxonomy 24h/7d aggregation + rule-based suggestion
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_REQUESTER_EMAIL = "canary.requester@platform.local"
ADMIN_REQUESTER_PASSWORD = "CanaryRequester123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_requester_token():
    """Get admin requester auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_REQUESTER_EMAIL, "password": ADMIN_REQUESTER_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin requester login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def ops_token():
    """Get ops user auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Ops login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def strategy_id(super_admin_token):
    """Get first available strategy ID"""
    headers = {"Authorization": f"Bearer {super_admin_token}"}
    response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview", headers=headers)
    if response.status_code != 200:
        pytest.skip("Cannot get strategy overview")
    strategies = response.json().get("strategies", [])
    if not strategies:
        pytest.skip("No strategies available")
    return strategies[0]["strategy_id"]


@pytest.fixture(scope="module")
def drift_alert_id(super_admin_token, strategy_id):
    """Get first drift alert ID for the strategy"""
    headers = {"Authorization": f"Bearer {super_admin_token}"}
    response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts", headers=headers)
    if response.status_code != 200:
        pytest.skip("Cannot get drift alerts")
    alerts = response.json().get("items", [])
    for alert in alerts:
        if alert.get("strategy_id") == strategy_id:
            return alert.get("alert_id")
    if alerts:
        return alerts[0].get("alert_id")
    pytest.skip("No drift alerts available")


class TestRollbackSnapshotsEndpoint:
    """GET /api/admin/futures/strategy/{id}/rollback-snapshots tests"""

    def test_rollback_snapshots_super_admin_success(self, super_admin_token, strategy_id):
        """Test super_admin can access rollback snapshots"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-snapshots",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("status") == "ok"
        assert data.get("strategy_id") == strategy_id
        assert "items" in data
        assert "permission_matrix" in data
        
        # Verify permission matrix
        perm = data.get("permission_matrix", {})
        assert perm.get("super_admin") == "full"
        assert perm.get("admin") == "request_only"
        assert perm.get("ops") == "read_only"
        
        print(f"PASS: Rollback snapshots returned {len(data.get('items', []))} items for strategy {strategy_id}")

    def test_rollback_snapshots_admin_requester_success(self, admin_requester_token, strategy_id):
        """Test admin requester can access rollback snapshots (request_only permission)"""
        headers = {"Authorization": f"Bearer {admin_requester_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-snapshots",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        print(f"PASS: Admin requester can access rollback snapshots")

    def test_rollback_snapshots_ops_read_only(self, ops_token, strategy_id):
        """Test ops user can read rollback snapshots (read_only permission)"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-snapshots",
            headers=headers
        )
        # Ops has read_only access - can read but not write
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        # Verify permission matrix shows ops as read_only
        perm = data.get("permission_matrix", {})
        assert perm.get("ops") == "read_only"
        print(f"PASS: Ops user can read rollback snapshots (read_only permission)")

    def test_rollback_snapshots_item_structure(self, super_admin_token, strategy_id):
        """Test rollback snapshot items have correct structure"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-snapshots",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        
        if items:
            item = items[0]
            # Verify required fields
            assert "snapshot_trace_id" in item, "Missing snapshot_trace_id"
            assert "timestamp" in item, "Missing timestamp"
            assert "actor" in item, "Missing actor"
            assert "action_type" in item, "Missing action_type"
            assert "diff_preview" in item, "Missing diff_preview"
            assert "rollback_scope" in item, "Missing rollback_scope"
            
            # Verify single-strategy scope
            assert item.get("rollback_scope") == "single_strategy"
            
            print(f"PASS: Rollback snapshot item has correct structure: {list(item.keys())}")
        else:
            print("INFO: No rollback snapshots available yet (empty history)")


class TestRollbackRequestEndpoint:
    """POST /api/admin/futures/strategy/{id}/rollback-request tests"""

    def test_rollback_request_requires_reason(self, super_admin_token, strategy_id):
        """Test rollback request requires reason field"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {
            "snapshot_trace_id": "nonexistent_trace_id"
            # Missing reason
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-request",
            headers=headers,
            json=payload
        )
        # Should fail validation
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        print("PASS: Rollback request correctly requires reason field")

    def test_rollback_request_invalid_snapshot(self, super_admin_token, strategy_id):
        """Test rollback request with invalid snapshot_trace_id"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {
            "reason": "TEST_FAZ4PLUS rollback request test",
            "snapshot_trace_id": "nonexistent_trace_id_12345"
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-request",
            headers=headers,
            json=payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "rejected"
        assert "bulunamadı" in data.get("message", "").lower() or "not found" in data.get("message", "").lower()
        print("PASS: Rollback request correctly rejects invalid snapshot_trace_id")

    def test_rollback_request_ops_can_create(self, ops_token, strategy_id):
        """Test ops user can create rollback request (read_only but request creation allowed via require_admin)"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        payload = {
            "reason": "TEST_FAZ4PLUS ops rollback attempt",
            "snapshot_trace_id": "any_trace_id"
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-request",
            headers=headers,
            json=payload
        )
        # Ops can create requests but they will be rejected if snapshot not found
        # The endpoint uses require_admin which includes ops
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Should be rejected because snapshot doesn't exist, not because of permission
        assert data.get("status") == "rejected"
        print("PASS: Ops user can access rollback request endpoint (rejected due to invalid snapshot)")


class TestApprovalRequestsEndpoint:
    """GET /api/admin/futures/strategy/approval-requests tests"""

    def test_approval_requests_super_admin_success(self, super_admin_token):
        """Test super_admin can access approval requests"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("status") == "ok"
        assert "items" in data
        assert "permission_matrix" in data
        
        # Verify permission matrix
        perm = data.get("permission_matrix", {})
        assert perm.get("super_admin") == "full"
        assert perm.get("admin") == "request_only"
        assert perm.get("ops") == "read_only"
        
        print(f"PASS: Approval requests returned {len(data.get('items', []))} items")

    def test_approval_requests_admin_requester_success(self, admin_requester_token):
        """Test admin requester can access approval requests (filtered to own requests)"""
        headers = {"Authorization": f"Bearer {admin_requester_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        print("PASS: Admin requester can access approval requests")

    def test_approval_requests_ops_read_only(self, ops_token):
        """Test ops user can read approval requests (read_only permission)"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests",
            headers=headers
        )
        # Ops has read_only access - can read approval requests
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        # Verify permission matrix shows ops as read_only
        perm = data.get("permission_matrix", {})
        assert perm.get("ops") == "read_only"
        print("PASS: Ops user can read approval requests (read_only permission)")

    def test_approval_requests_status_filter(self, super_admin_token):
        """Test approval requests can be filtered by status"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        for status_filter in ["pending", "approved", "rejected", "expired"]:
            response = requests.get(
                f"{BASE_URL}/api/admin/futures/strategy/approval-requests",
                headers=headers,
                params={"status": status_filter}
            )
            assert response.status_code == 200, f"Expected 200 for status={status_filter}, got {response.status_code}"
            data = response.json()
            items = data.get("items", [])
            # Verify all items match the filter
            for item in items:
                assert item.get("status") == status_filter, f"Item status {item.get('status')} doesn't match filter {status_filter}"
        
        print("PASS: Approval requests status filter works correctly")


class TestApprovalDecisionEndpoints:
    """POST /api/admin/futures/strategy/approval-requests/{id}/approve and /reject tests"""

    def test_approve_super_admin_only(self, admin_requester_token):
        """Test approve endpoint requires super_admin"""
        headers = {"Authorization": f"Bearer {admin_requester_token}"}
        payload = {"reason": "TEST_FAZ4PLUS approve attempt by admin"}
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests/fake_request_id/approve",
            headers=headers,
            json=payload
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: Approve endpoint correctly requires super_admin")

    def test_reject_super_admin_only(self, admin_requester_token):
        """Test reject endpoint requires super_admin"""
        headers = {"Authorization": f"Bearer {admin_requester_token}"}
        payload = {"reason": "TEST_FAZ4PLUS reject attempt by admin"}
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests/fake_request_id/reject",
            headers=headers,
            json=payload
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: Reject endpoint correctly requires super_admin")

    def test_approve_nonexistent_request(self, super_admin_token):
        """Test approve with nonexistent request_id returns 404"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {"reason": "TEST_FAZ4PLUS approve nonexistent"}
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests/nonexistent_request_id/approve",
            headers=headers,
            json=payload
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("PASS: Approve correctly returns 404 for nonexistent request")

    def test_reject_nonexistent_request(self, super_admin_token):
        """Test reject with nonexistent request_id returns 404"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {"reason": "TEST_FAZ4PLUS reject nonexistent"}
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests/nonexistent_request_id/reject",
            headers=headers,
            json=payload
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("PASS: Reject correctly returns 404 for nonexistent request")


class TestDriftAlertsRecommendedAction:
    """GET /api/admin/futures/strategy-control/drift-alerts recommended_action tests"""

    def test_drift_alerts_recommended_action_structure(self, super_admin_token):
        """Test drift alerts include recommended_action with deterministic output"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("status") == "ok"
        items = data.get("items", [])
        
        if items:
            for item in items:
                rec = item.get("recommended_action")
                assert rec is not None, "Missing recommended_action"
                
                # Verify recommended_action structure
                assert "type" in rec, "Missing recommended_action.type"
                assert "confidence" in rec, "Missing recommended_action.confidence"
                assert "reason" in rec, "Missing recommended_action.reason"
                
                # Verify type is one of expected values
                valid_types = ["ACK", "MUTE", "DISABLE", "RETRAIN"]
                assert rec.get("type") in valid_types, f"Invalid type: {rec.get('type')}"
                
                # Verify confidence is a number
                assert isinstance(rec.get("confidence"), (int, float)), "confidence should be numeric"
                
                # Verify inputs are present
                assert "inputs" in rec, "Missing recommended_action.inputs"
                
            print(f"PASS: All {len(items)} drift alerts have valid recommended_action structure")
        else:
            print("INFO: No drift alerts available to test recommended_action")

    def test_drift_alerts_summary(self, super_admin_token):
        """Test drift alerts include summary counts"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        summary = data.get("summary", {})
        assert "open" in summary, "Missing summary.open"
        assert "acked" in summary, "Missing summary.acked"
        assert "muted" in summary, "Missing summary.muted"
        assert "ignored" in summary, "Missing summary.ignored"
        
        print(f"PASS: Drift alerts summary: open={summary.get('open')}, acked={summary.get('acked')}, muted={summary.get('muted')}, ignored={summary.get('ignored')}")


class TestPolicySuggestionsEndpoint:
    """GET /api/admin/futures/strategy-control/policy-suggestions tests"""

    def test_policy_suggestions_super_admin_success(self, super_admin_token):
        """Test super_admin can access policy suggestions"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/policy-suggestions",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("status") == "ok"
        assert "summary" in data
        
        summary = data.get("summary", {})
        # Verify taxonomy aggregation fields
        assert "taxonomy_24h" in summary, "Missing taxonomy_24h"
        assert "taxonomy_7d" in summary, "Missing taxonomy_7d"
        assert "rules" in summary, "Missing rules"
        
        print(f"PASS: Policy suggestions returned with taxonomy_24h={summary.get('taxonomy_24h')}, taxonomy_7d={summary.get('taxonomy_7d')}, rules={summary.get('rules')}")

    def test_policy_suggestions_ops_forbidden(self, ops_token):
        """Test ops user gets 403 on policy suggestions"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/policy-suggestions",
            headers=headers
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: Ops user correctly gets 403 on policy suggestions")


class TestPermissionMatrixOverview:
    """Test permission matrix in overview endpoint"""

    def test_overview_permission_matrix(self, super_admin_token):
        """Test overview includes permission_matrix"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        perm = data.get("permission_matrix", {})
        assert perm.get("super_admin") == "full", "super_admin should have full access"
        assert perm.get("admin") == "request_only", "admin should have request_only access"
        assert perm.get("ops") == "read_only", "ops should have read_only access"
        
        print(f"PASS: Overview permission_matrix: {perm}")


class TestFullRollbackApprovalWorkflow:
    """End-to-end test of rollback request and approval workflow"""

    def test_create_action_then_rollback_request_then_approve(self, super_admin_token, strategy_id):
        """Test full workflow: create action -> get snapshot -> create rollback request -> approve"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # Step 1: Create an action to generate a snapshot
        action_payload = {
            "reason": "TEST_FAZ4PLUS workflow test action",
            "dry_run": False
        }
        action_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/throttle",
            headers=headers,
            json={**action_payload, "throttle_level": "L1"}
        )
        
        if action_response.status_code != 200:
            print(f"INFO: Could not create action for workflow test: {action_response.status_code}")
            pytest.skip("Cannot create action for workflow test")
        
        action_data = action_response.json()
        print(f"Step 1: Created action with trace_id={action_data.get('trace_id')}")
        
        # Step 2: Get rollback snapshots
        time.sleep(0.5)  # Allow cache to update
        snapshots_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-snapshots",
            headers=headers
        )
        assert snapshots_response.status_code == 200
        snapshots = snapshots_response.json().get("items", [])
        
        if not snapshots:
            print("INFO: No snapshots available after action")
            pytest.skip("No snapshots available for workflow test")
        
        snapshot_trace_id = snapshots[0].get("snapshot_trace_id")
        print(f"Step 2: Got snapshot with trace_id={snapshot_trace_id}")
        
        # Step 3: Create rollback request
        request_payload = {
            "reason": "TEST_FAZ4PLUS workflow rollback request",
            "snapshot_trace_id": snapshot_trace_id
        }
        request_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-request",
            headers=headers,
            json=request_payload
        )
        assert request_response.status_code == 200
        request_data = request_response.json()
        
        if request_data.get("status") == "rejected":
            print(f"INFO: Rollback request rejected: {request_data.get('message')}")
            pytest.skip("Rollback request rejected")
        
        request_item = request_data.get("state_snapshot", {})
        request_id = request_item.get("request_id")
        
        # Verify request has preview and expires_at
        assert "preview" in request_item, "Missing preview in rollback request"
        assert "expires_at" in request_item, "Missing expires_at in rollback request"
        
        print(f"Step 3: Created rollback request with id={request_id}, expires_at={request_item.get('expires_at')}")
        
        # Step 4: Verify request appears in approval list
        approval_list_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests",
            headers=headers,
            params={"status": "pending"}
        )
        assert approval_list_response.status_code == 200
        pending_items = approval_list_response.json().get("items", [])
        found = any(item.get("request_id") == request_id for item in pending_items)
        assert found, f"Request {request_id} not found in pending list"
        print(f"Step 4: Verified request appears in pending approval list")
        
        # Step 5: Approve the request
        approve_payload = {"reason": "TEST_FAZ4PLUS workflow approval"}
        approve_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests/{request_id}/approve",
            headers=headers,
            json=approve_payload
        )
        assert approve_response.status_code == 200
        approve_data = approve_response.json()
        
        assert approve_data.get("status") == "success", f"Approval failed: {approve_data.get('message')}"
        
        # Verify approval includes rollback_reference
        approval_request = approve_data.get("approval_request", {})
        assert approval_request.get("status") == "approved"
        assert "rollback_reference" in approval_request, "Missing rollback_reference in approved request"
        
        print(f"Step 5: Approved request, rollback_reference={approval_request.get('rollback_reference')}")
        print("PASS: Full rollback approval workflow completed successfully")


class TestRollbackRequestRejectWorkflow:
    """Test rollback request rejection workflow"""

    def test_create_and_reject_rollback_request(self, super_admin_token, strategy_id):
        """Test creating and rejecting a rollback request"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # Get snapshots
        snapshots_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-snapshots",
            headers=headers
        )
        assert snapshots_response.status_code == 200
        snapshots = snapshots_response.json().get("items", [])
        
        if not snapshots:
            pytest.skip("No snapshots available for reject workflow test")
        
        snapshot_trace_id = snapshots[0].get("snapshot_trace_id")
        
        # Create rollback request
        request_payload = {
            "reason": "TEST_FAZ4PLUS reject workflow test",
            "snapshot_trace_id": snapshot_trace_id
        }
        request_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback-request",
            headers=headers,
            json=request_payload
        )
        
        if request_response.status_code != 200 or request_response.json().get("status") == "rejected":
            pytest.skip("Cannot create rollback request for reject test")
        
        request_id = request_response.json().get("state_snapshot", {}).get("request_id")
        
        # Reject the request
        reject_payload = {"reason": "TEST_FAZ4PLUS rejection reason"}
        reject_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/approval-requests/{request_id}/reject",
            headers=headers,
            json=reject_payload
        )
        assert reject_response.status_code == 200
        reject_data = reject_response.json()
        
        assert reject_data.get("status") == "success"
        assert reject_data.get("state_snapshot", {}).get("status") == "rejected"
        
        print(f"PASS: Rollback request {request_id} rejected successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
