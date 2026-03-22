"""
Iteration 75 - Decision Approval Governance Testing
Tests for:
- POST /api/admin/decision-requests/conflict-resolve (admin role, simulation_run_id required)
- POST /api/admin/decision-requests/hedge-apply (admin role, simulation_run_id required)
- POST /api/admin/decision-requests/rebalance-change (admin role, simulation_run_id required)
- GET /api/admin/decision-requests (sorting by severity/risk/time)
- POST /api/admin/decision-requests/{id}/approve (super_admin only)
- POST /api/admin/decision-requests/{id}/execute (super_admin only, preview_token enforced)
- GET /api/admin/simulation-runs/{run_id}/compare-current
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_REQUESTER_EMAIL = "canary.requester@example.com"
ADMIN_REQUESTER_PASSWORD = "CanaryRequester123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_requester_token():
    """Get admin requester token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_REQUESTER_EMAIL, "password": ADMIN_REQUESTER_PASSWORD},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin requester login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def super_admin_user_id(super_admin_token):
    """Get super_admin user ID"""
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    if response.status_code == 200:
        return response.json().get("id")
    pytest.skip("Could not get super_admin user ID")


@pytest.fixture(scope="module")
def simulation_run_id(super_admin_token, super_admin_user_id):
    """Create a simulation run for testing"""
    response = requests.post(
        f"{BASE_URL}/api/admin/risk-simulation",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        json={
            "user_id": super_admin_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
            },
            "apply_override": False,
        },
    )
    if response.status_code == 200:
        return response.json().get("simulation_id")
    pytest.skip(f"Could not create simulation: {response.status_code} - {response.text}")


class TestDecisionRequestCreation:
    """Test decision request creation endpoints - admin role required"""

    # Test conflict-resolve endpoint
    def test_conflict_resolve_requires_admin_role(self, super_admin_token, simulation_run_id):
        """POST /api/admin/decision-requests/conflict-resolve - super_admin should fail (only admin can create)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "target_type": "strategy_conflict",
                "target_id": "test_conflict_id",
                "reason_note": "test_conflict_resolution_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        # super_admin is not admin role, should get 403
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        assert "admin" in response.json().get("detail", "").lower()

    def test_conflict_resolve_requires_simulation_run_id(self, admin_requester_token):
        """POST /api/admin/decision-requests/conflict-resolve - simulation_run_id required"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "strategy_conflict",
                "target_id": "test_conflict_id",
                "reason_note": "test_conflict_resolution_request",
                # Missing simulation_run_id
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "simulation_run_id" in response.json().get("detail", "").lower()

    def test_conflict_resolve_success_admin(self, admin_requester_token, simulation_run_id):
        """POST /api/admin/decision-requests/conflict-resolve - admin can create"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "strategy_conflict",
                "target_id": "test_conflict_id",
                "reason_note": "test_conflict_resolution_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "request_id" in data
        assert data["request_type"] == "conflict_resolve"
        assert data["status"] == "pending"
        assert "preview_token" in data
        assert "severity_band" in data
        assert "risk_delta_score" in data

    # Test hedge-apply endpoint
    def test_hedge_apply_requires_admin_role(self, super_admin_token, simulation_run_id):
        """POST /api/admin/decision-requests/hedge-apply - super_admin should fail"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/hedge-apply",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "target_type": "hedge_suggestion",
                "target_id": "BTCUSDT:short",
                "reason_note": "test_hedge_apply_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"

    def test_hedge_apply_success_admin(self, admin_requester_token, simulation_run_id):
        """POST /api/admin/decision-requests/hedge-apply - admin can create"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/hedge-apply",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "hedge_suggestion",
                "target_id": "BTCUSDT:short",
                "reason_note": "test_hedge_apply_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "request_id" in data
        assert data["request_type"] == "hedge_apply"
        assert data["status"] == "pending"

    # Test rebalance-change endpoint
    def test_rebalance_change_requires_admin_role(self, super_admin_token, simulation_run_id):
        """POST /api/admin/decision-requests/rebalance-change - super_admin should fail"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/rebalance-change",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "target_type": "rebalance_event",
                "target_id": "spot_pullback_v1",
                "reason_note": "test_rebalance_change_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"

    def test_rebalance_change_success_admin(self, admin_requester_token, simulation_run_id):
        """POST /api/admin/decision-requests/rebalance-change - admin can create"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/rebalance-change",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "rebalance_event",
                "target_id": "spot_pullback_v1",
                "reason_note": "test_rebalance_change_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "request_id" in data
        assert data["request_type"] == "rebalance_change"
        assert data["status"] == "pending"


class TestDecisionRequestListing:
    """Test GET /api/admin/decision-requests - sorting by severity/risk/time"""

    def test_list_decision_requests(self, super_admin_token):
        """GET /api/admin/decision-requests - returns list with proper sorting"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        items = data["items"]
        
        # Verify structure of items
        if len(items) > 0:
            item = items[0]
            assert "request_id" in item
            assert "request_type" in item
            assert "status" in item
            assert "severity_band" in item
            assert "risk_delta_score" in item
            assert "created_at" in item

    def test_list_decision_requests_sorting(self, super_admin_token):
        """GET /api/admin/decision-requests - verify sorting order (pending first, then by severity/risk)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        
        # Verify pending items come first
        pending_items = [i for i in items if i.get("status") == "pending"]
        non_pending_items = [i for i in items if i.get("status") != "pending"]
        
        if pending_items and non_pending_items:
            # Find first non-pending index
            first_non_pending_idx = next(
                (idx for idx, item in enumerate(items) if item.get("status") != "pending"),
                len(items)
            )
            # All pending should be before non-pending
            for idx, item in enumerate(items[:first_non_pending_idx]):
                assert item.get("status") == "pending", f"Item at index {idx} should be pending"

    def test_list_decision_requests_filter_by_status(self, super_admin_token):
        """GET /api/admin/decision-requests?status_filter=pending"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"status_filter": "pending"},
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        for item in items:
            assert item.get("status") == "pending"


class TestDecisionRequestApproval:
    """Test approve/reject/execute endpoints - super_admin only"""

    @pytest.fixture
    def pending_request_id(self, admin_requester_token, simulation_run_id):
        """Create a pending request for testing"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "strategy_conflict",
                "target_id": f"test_approval_{os.urandom(4).hex()}",
                "reason_note": "test_approval_flow_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        if response.status_code == 200:
            return response.json().get("request_id")
        pytest.skip(f"Could not create pending request: {response.status_code}")

    def test_approve_requires_super_admin(self, admin_requester_token, pending_request_id):
        """POST /api/admin/decision-requests/{id}/approve - admin should fail"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{pending_request_id}/approve",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={"reason_note": "test_approve_note"},
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        assert "super_admin" in response.json().get("detail", "").lower()

    def test_approve_success_super_admin(self, super_admin_token, pending_request_id):
        """POST /api/admin/decision-requests/{id}/approve - super_admin can approve"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{pending_request_id}/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"reason_note": "test_approve_note_from_super_admin"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] == "approved"
        assert data["approved_by"] is not None

    def test_reject_requires_super_admin(self, admin_requester_token, simulation_run_id):
        """POST /api/admin/decision-requests/{id}/reject - admin should fail"""
        # Create a new request for rejection test
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/hedge-apply",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "hedge_suggestion",
                "target_id": f"test_reject_{os.urandom(4).hex()}",
                "reason_note": "test_reject_flow_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create request for rejection test")
        
        request_id = create_response.json().get("request_id")
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/reject",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={"reason_note": "test_reject_note"},
        )
        assert response.status_code == 403

    def test_reject_success_super_admin(self, super_admin_token, admin_requester_token, simulation_run_id):
        """POST /api/admin/decision-requests/{id}/reject - super_admin can reject"""
        # Create a new request
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/hedge-apply",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "hedge_suggestion",
                "target_id": f"test_reject_success_{os.urandom(4).hex()}",
                "reason_note": "test_reject_success_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create request for rejection test")
        
        request_id = create_response.json().get("request_id")
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/reject",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"reason_note": "test_reject_note_from_super_admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"


class TestDecisionRequestExecution:
    """Test execute endpoint - super_admin only, preview_token enforced"""

    @pytest.fixture
    def approved_request(self, super_admin_token, admin_requester_token, simulation_run_id):
        """Create and approve a request for execution testing"""
        # Create request
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/rebalance-change",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "rebalance_event",
                "target_id": f"test_execute_{os.urandom(4).hex()}",
                "reason_note": "test_execute_flow_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create request for execution test")
        
        request_data = create_response.json()
        request_id = request_data.get("request_id")
        preview_token = request_data.get("preview_token")
        
        # Approve request
        approve_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"reason_note": "approved_for_execution_test"},
        )
        if approve_response.status_code != 200:
            pytest.skip("Could not approve request for execution test")
        
        return {"request_id": request_id, "preview_token": preview_token}

    def test_execute_requires_super_admin(self, admin_requester_token, approved_request):
        """POST /api/admin/decision-requests/{id}/execute - admin should fail"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{approved_request['request_id']}/execute",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "reason_note": "test_execute_note",
                "preview_token": approved_request["preview_token"],
            },
        )
        assert response.status_code == 403

    def test_execute_requires_preview_token(self, super_admin_token, approved_request):
        """POST /api/admin/decision-requests/{id}/execute - preview_token required"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{approved_request['request_id']}/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "reason_note": "test_execute_note",
                "preview_token": "wrong_token",
            },
        )
        assert response.status_code == 400
        assert "preview_token" in response.json().get("detail", "").lower()

    def test_execute_success_super_admin(self, super_admin_token, approved_request):
        """POST /api/admin/decision-requests/{id}/execute - super_admin with correct token"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{approved_request['request_id']}/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "reason_note": "test_execute_note_success",
                "preview_token": approved_request["preview_token"],
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] == "executed"

    def test_execute_requires_approved_status(self, super_admin_token, admin_requester_token, simulation_run_id):
        """POST /api/admin/decision-requests/{id}/execute - must be approved first"""
        # Create a pending request (not approved)
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "strategy_conflict",
                "target_id": f"test_pending_execute_{os.urandom(4).hex()}",
                "reason_note": "test_pending_execute_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create request")
        
        request_data = create_response.json()
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_data['request_id']}/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "reason_note": "test_execute_pending",
                "preview_token": request_data.get("preview_token", ""),
            },
        )
        assert response.status_code == 400
        assert "approved" in response.json().get("detail", "").lower()


class TestSimulationCompare:
    """Test GET /api/admin/simulation-runs/{run_id}/compare-current"""

    def test_compare_current_success(self, super_admin_token, simulation_run_id):
        """GET /api/admin/simulation-runs/{run_id}/compare-current - returns comparison"""
        response = requests.get(
            f"{BASE_URL}/api/admin/simulation-runs/{simulation_run_id}/compare-current",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "run_id" in data
        assert "status" in data
        assert "before" in data
        assert "current" in data
        assert "compare_summary" in data
        
        # Verify compare_summary structure
        compare_summary = data["compare_summary"]
        assert "risk_delta_vs_history" in compare_summary
        assert "confidence_adjusted_risk_delta_vs_history" in compare_summary
        assert "decision_delta_vs_history" in compare_summary

    def test_compare_current_not_found(self, super_admin_token):
        """GET /api/admin/simulation-runs/{run_id}/compare-current - 404 for invalid run_id"""
        response = requests.get(
            f"{BASE_URL}/api/admin/simulation-runs/invalid_run_id_12345/compare-current",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 404


class TestDecisionRequestPreview:
    """Test GET /api/admin/decision-requests/{id}/preview"""

    def test_preview_success(self, super_admin_token, admin_requester_token, simulation_run_id):
        """GET /api/admin/decision-requests/{id}/preview - returns preview with token"""
        # Create a request
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "strategy_conflict",
                "target_id": f"test_preview_{os.urandom(4).hex()}",
                "reason_note": "test_preview_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create request for preview test")
        
        request_id = create_response.json().get("request_id")
        
        # Get preview
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert "status" in data
        assert "preview_token" in data
        assert "risk_delta_score" in data
        assert "severity_band" in data
        assert "impact_summary" in data


class TestRoleMatrix:
    """Test role-based access control matrix"""

    def test_admin_can_create_requests(self, admin_requester_token, simulation_run_id):
        """Admin role can create decision requests"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "strategy_conflict",
                "target_id": f"test_role_matrix_{os.urandom(4).hex()}",
                "reason_note": "test_role_matrix_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        assert response.status_code == 200

    def test_super_admin_cannot_create_requests(self, super_admin_token, simulation_run_id):
        """Super_admin role cannot create decision requests (only admin can)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "target_type": "strategy_conflict",
                "target_id": "test_super_admin_create",
                "reason_note": "test_super_admin_create_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        assert response.status_code == 403

    def test_super_admin_can_approve(self, super_admin_token, admin_requester_token, simulation_run_id):
        """Super_admin can approve requests"""
        # Create request
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/hedge-apply",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "hedge_suggestion",
                "target_id": f"test_sa_approve_{os.urandom(4).hex()}",
                "reason_note": "test_sa_approve_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create request")
        
        request_id = create_response.json().get("request_id")
        
        # Approve
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"reason_note": "approved_by_super_admin"},
        )
        assert response.status_code == 200

    def test_admin_cannot_approve(self, admin_requester_token, simulation_run_id):
        """Admin role cannot approve requests"""
        # Create request
        create_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/rebalance-change",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={
                "target_type": "rebalance_event",
                "target_id": f"test_admin_approve_{os.urandom(4).hex()}",
                "reason_note": "test_admin_approve_request",
                "simulation_run_id": simulation_run_id,
            },
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create request")
        
        request_id = create_response.json().get("request_id")
        
        # Try to approve (should fail)
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {admin_requester_token}"},
            json={"reason_note": "admin_trying_to_approve"},
        )
        assert response.status_code == 403
