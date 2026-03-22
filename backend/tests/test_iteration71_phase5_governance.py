"""
Phase 5 Governance Testing - Iteration 71
Tests for:
- Reason note zorunluluğu (required on all write actions)
- Role matrix: super_admin full, admin request-only (approval), ops read-only
- Approval flow: admin creates pending requests, super_admin approves/rejects
- State history / approval payload reason_code-reason_detail preservation
- Confidence band in rebalance preview (HIGH>=75, MED 50-74.99, LOW<50)
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_REQUESTER_EMAIL = "canary.requester@platform.local"
ADMIN_REQUESTER_PASSWORD = "CanaryRequester123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


import time

def get_auth_token(email: str, password: str, retries: int = 3) -> str | None:
    """Get authentication token for a user with retry on rate limit"""
    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": password},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("access_token")
            if resp.status_code == 429 or "rate_limit" in resp.text.lower():
                time.sleep(5 * (attempt + 1))  # Exponential backoff
                continue
            return None
        except Exception:
            time.sleep(2)
    return None


def get_headers(token: str) -> dict:
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


class TestReasonNoteRequired:
    """Test that reason_note is required on all write actions"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        if not self.token:
            pytest.skip("Super admin authentication failed")
        self.headers = get_headers(self.token)
    
    def test_normalize_without_reason_note_returns_400(self):
        """POST /admin/strategy-allocation/normalize without reason_note should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={"reason_note": ""},
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "reason_note" in resp.text.lower() or "zorunlu" in resp.text.lower()
    
    def test_normalize_with_reason_note_succeeds(self):
        """POST /admin/strategy-allocation/normalize with reason_note should succeed"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={"reason_note": "test_normalize_phase5"},
            headers=self.headers,
            timeout=15
        )
        # Should succeed or return pending_approval for admin role
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
    
    def test_create_without_reason_note_returns_400(self):
        """POST /admin/strategy-allocation without reason_note should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation",
            json={
                "strategy_id": "test_no_reason_strategy",
                "capital_weight": 0.1,
                "max_capital": 1000,
                "current_capital": 0,
                "state": "ACTIVE",
                "reason_note": ""
            },
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    
    def test_delete_without_reason_note_returns_400(self):
        """DELETE /admin/strategy-allocation/{id} without reason_note should return 400"""
        resp = requests.delete(
            f"{BASE_URL}/api/admin/strategy-allocation/nonexistent_strategy",
            params={"auto_normalize": True, "reason_note": ""},
            headers=self.headers,
            timeout=15
        )
        # Should return 400 for missing reason_note (before checking if strategy exists)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    
    def test_bulk_update_without_reason_note_returns_400(self):
        """POST /admin/strategy-allocation/bulk-update without reason_note should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/bulk-update",
            json={
                "updates": [],
                "auto_normalize": False,
                "reason_note": ""
            },
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    
    def test_throttle_toggle_without_reason_note_returns_400(self):
        """POST /admin/strategy-allocation/{id}/throttle-toggle without reason_note should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/nonexistent_strategy/throttle-toggle",
            json={
                "confirm_primary": "CONFIRM",
                "confirm_secondary": "STATE CHANGE",
                "reason_note": ""
            },
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


class TestRoleMatrixSuperAdmin:
    """Test super_admin has full write access (direct commit)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        if not self.token:
            pytest.skip("Super admin authentication failed")
        self.headers = get_headers(self.token)
    
    def test_super_admin_normalize_direct_commit(self):
        """super_admin normalize should commit directly (status=success)"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={"reason_note": "super_admin_direct_normalize"},
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "success", f"Expected status=success, got {data.get('status')}"
    
    def test_super_admin_can_read_allocation_dashboard(self):
        """super_admin can read strategy allocation dashboard"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert isinstance(resp.json(), list)
    
    def test_super_admin_can_read_approval_requests(self):
        """super_admin can read approval requests list"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "rows" in data


class TestRoleMatrixAdminRequestOnly:
    """Test admin role creates pending_approval requests instead of direct commit"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.admin_token = get_auth_token(ADMIN_REQUESTER_EMAIL, ADMIN_REQUESTER_PASSWORD)
        self.super_admin_token = get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        if not self.admin_token:
            pytest.skip("Admin requester authentication failed - account may not exist")
        self.admin_headers = get_headers(self.admin_token)
        if self.super_admin_token:
            self.super_admin_headers = get_headers(self.super_admin_token)
    
    def test_admin_normalize_returns_pending_approval(self):
        """admin normalize should return pending_approval status"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={"reason_note": "admin_request_normalize"},
            headers=self.admin_headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "pending_approval", f"Expected status=pending_approval, got {data.get('status')}"
        assert "request_id" in data.get("trace_id", "") or "alloc_req_" in data.get("trace_id", "")
    
    def test_admin_create_returns_pending_approval(self):
        """admin create should return pending_approval status"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation",
            json={
                "strategy_id": f"test_admin_create_{datetime.now().strftime('%H%M%S')}",
                "capital_weight": 0.05,
                "max_capital": 500,
                "current_capital": 0,
                "state": "ACTIVE",
                "reason_note": "admin_request_create"
            },
            headers=self.admin_headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "pending_approval", f"Expected status=pending_approval, got {data.get('status')}"
    
    def test_admin_bulk_update_returns_pending_approval(self):
        """admin bulk update should return pending_approval status"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/bulk-update",
            json={
                "updates": [],
                "auto_normalize": False,
                "reason_note": "admin_request_bulk"
            },
            headers=self.admin_headers,
            timeout=15
        )
        # Empty updates might fail validation, but if it passes, should be pending_approval
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("status") == "pending_approval"
        else:
            # Empty updates validation error is acceptable
            assert resp.status_code == 400


class TestRoleMatrixOpsReadOnly:
    """Test ops role is read-only (403 on write actions)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.ops_token = get_auth_token(OPS_EMAIL, OPS_PASSWORD)
        if not self.ops_token:
            pytest.skip("Ops user authentication failed - account may not exist")
        self.ops_headers = get_headers(self.ops_token)
    
    def test_ops_normalize_returns_403(self):
        """ops normalize should return 403 forbidden"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={"reason_note": "ops_attempt_normalize"},
            headers=self.ops_headers,
            timeout=15
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        assert "read-only" in resp.text.lower() or "ops" in resp.text.lower()
    
    def test_ops_create_returns_403(self):
        """ops create should return 403 forbidden"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation",
            json={
                "strategy_id": "test_ops_create",
                "capital_weight": 0.1,
                "max_capital": 1000,
                "current_capital": 0,
                "state": "ACTIVE",
                "reason_note": "ops_attempt_create"
            },
            headers=self.ops_headers,
            timeout=15
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    
    def test_ops_can_read_allocation_dashboard(self):
        """ops can read strategy allocation dashboard (read-only access)"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=self.ops_headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


class TestApprovalFlow:
    """Test approval flow: admin creates pending, super_admin approves/rejects"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.super_admin_token = get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        self.admin_token = get_auth_token(ADMIN_REQUESTER_EMAIL, ADMIN_REQUESTER_PASSWORD)
        if not self.super_admin_token:
            pytest.skip("Super admin authentication failed")
        self.super_admin_headers = get_headers(self.super_admin_token)
        if self.admin_token:
            self.admin_headers = get_headers(self.admin_token)
    
    def test_approval_requests_list_shows_pending(self):
        """GET approval-requests should show pending requests"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=self.super_admin_headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "rows" in data
        # Check structure of rows if any exist
        for row in data.get("rows", []):
            assert "request_id" in row
            assert "action_type" in row
            assert "status" in row
            assert "reason_note" in row
    
    def test_approval_requests_filter_by_status(self):
        """GET approval-requests with status_filter should filter correctly"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            params={"status_filter": "pending"},
            headers=self.super_admin_headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        for row in data.get("rows", []):
            assert row.get("status") == "pending"
    
    def test_approve_requires_super_admin(self):
        """Approve endpoint requires super_admin role"""
        if not self.admin_token:
            pytest.skip("Admin token not available")
        
        # Try to approve with admin role (should fail)
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/fake_request_id/approve",
            json={"reason_note": "admin_trying_to_approve"},
            headers=self.admin_headers,
            timeout=15
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        assert "super_admin" in resp.text.lower()
    
    def test_reject_requires_super_admin(self):
        """Reject endpoint requires super_admin role"""
        if not self.admin_token:
            pytest.skip("Admin token not available")
        
        # Try to reject with admin role (should fail)
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/fake_request_id/reject",
            json={"reason_note": "admin_trying_to_reject"},
            headers=self.admin_headers,
            timeout=15
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    
    def test_approve_nonexistent_request_returns_404(self):
        """Approve nonexistent request should return 404"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/nonexistent_request_id/approve",
            json={"reason_note": "approve_nonexistent"},
            headers=self.super_admin_headers,
            timeout=15
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    
    def test_reject_nonexistent_request_returns_404(self):
        """Reject nonexistent request should return 404"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/nonexistent_request_id/reject",
            json={"reason_note": "reject_nonexistent"},
            headers=self.super_admin_headers,
            timeout=15
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


class TestStateHistoryReasonPreservation:
    """Test that state history preserves reason_code and reason_detail"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        if not self.token:
            pytest.skip("Super admin authentication failed")
        self.headers = get_headers(self.token)
    
    def test_state_history_contains_reason_fields(self):
        """GET state-history should contain reason_code and reason_detail fields"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/state-history",
            params={"limit": 20},
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "rows" in data
        
        # Check structure of history entries
        for row in data.get("rows", []):
            assert "trace_id" in row
            assert "strategy_id" in row
            assert "action_type" in row
            # reason_code and reason_detail should be present (can be null)
            assert "reason_code" in row
            assert "reason_detail" in row
            assert "admin_id" in row
            assert "timestamp" in row


class TestConfidenceBandInRebalancePreview:
    """Test confidence band calculation in rebalance preview (HIGH>=75, MED 50-74.99, LOW<50)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        if not self.token:
            pytest.skip("Super admin authentication failed")
        self.headers = get_headers(self.token)
    
    def test_rebalance_suggestions_returns_confidence(self):
        """POST rebalance-suggestions should return confidence values"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions",
            json={"strategy_ids": []},
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "suggestions" in data
        assert "status" in data
        
        # Check each suggestion has confidence field
        for suggestion in data.get("suggestions", []):
            assert "strategy_id" in suggestion
            assert "confidence" in suggestion
            assert "suggested_weight" in suggestion
            assert "current_weight" in suggestion
    
    def test_confidence_band_calculation_logic(self):
        """Verify confidence band logic: HIGH>=75, MED 50-74.99, LOW<50"""
        # Test the band calculation logic
        def confidence_band(confidence_value):
            raw = float(confidence_value) if confidence_value is not None else 0
            pct = raw * 100 if raw <= 1 else raw
            if pct >= 75:
                return "HIGH"
            if pct >= 50:
                return "MED"
            return "LOW"
        
        # Test cases
        assert confidence_band(0.80) == "HIGH"  # 80% >= 75
        assert confidence_band(0.75) == "HIGH"  # 75% >= 75
        assert confidence_band(0.74) == "MED"   # 74% < 75, >= 50
        assert confidence_band(0.50) == "MED"   # 50% >= 50
        assert confidence_band(0.49) == "LOW"   # 49% < 50
        assert confidence_band(0.10) == "LOW"   # 10% < 50
        assert confidence_band(0) == "LOW"      # 0% < 50
    
    def test_allocation_dashboard_has_confidence_score(self):
        """GET strategy-allocation should return confidence_score for band calculation"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=self.headers,
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Check each row has confidence_score
        for row in data:
            assert "strategy_id" in row
            assert "confidence_score" in row


class TestApprovalApproveRejectFlow:
    """Test full approve/reject flow with super_admin"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.super_admin_token = get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        self.admin_token = get_auth_token(ADMIN_REQUESTER_EMAIL, ADMIN_REQUESTER_PASSWORD)
        if not self.super_admin_token:
            pytest.skip("Super admin authentication failed")
        self.super_admin_headers = get_headers(self.super_admin_token)
        if self.admin_token:
            self.admin_headers = get_headers(self.admin_token)
    
    def test_full_approval_flow(self):
        """Test: admin creates request -> super_admin approves -> request executed"""
        if not self.admin_token:
            pytest.skip("Admin token not available for full flow test")
        
        # Step 1: Admin creates a normalize request
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={"reason_note": "full_flow_test_normalize"},
            headers=self.admin_headers,
            timeout=15
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data.get("status") == "pending_approval"
        request_id = create_data.get("trace_id")
        
        # Step 2: Verify request appears in pending list
        list_resp = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            params={"status_filter": "pending"},
            headers=self.super_admin_headers,
            timeout=15
        )
        assert list_resp.status_code == 200
        pending_requests = list_resp.json().get("rows", [])
        request_ids = [r.get("request_id") for r in pending_requests]
        assert request_id in request_ids, f"Request {request_id} not found in pending list"
        
        # Step 3: Super admin approves
        approve_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/{request_id}/approve",
            json={"reason_note": "approved_by_super_admin"},
            headers=self.super_admin_headers,
            timeout=15
        )
        assert approve_resp.status_code == 200, f"Approve failed: {approve_resp.text}"
    
    def test_full_rejection_flow(self):
        """Test: admin creates request -> super_admin rejects -> status=rejected"""
        if not self.admin_token:
            pytest.skip("Admin token not available for rejection flow test")
        
        # Step 1: Admin creates a normalize request
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={"reason_note": "rejection_flow_test"},
            headers=self.admin_headers,
            timeout=15
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        request_id = create_data.get("trace_id")
        
        # Step 2: Super admin rejects
        reject_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/{request_id}/reject",
            json={"reason_note": "rejected_by_super_admin"},
            headers=self.super_admin_headers,
            timeout=15
        )
        assert reject_resp.status_code == 200, f"Reject failed: {reject_resp.text}"
        reject_data = reject_resp.json()
        assert reject_data.get("status") == "rejected"


class TestApprovalRequiresReasonNote:
    """Test that approve/reject also require reason_note"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = get_auth_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
        if not self.token:
            pytest.skip("Super admin authentication failed")
        self.headers = get_headers(self.token)
    
    def test_approve_without_reason_note_returns_400(self):
        """Approve without reason_note should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/any_request_id/approve",
            json={"reason_note": ""},
            headers=self.headers,
            timeout=15
        )
        # Should return 400 for missing reason_note (before checking if request exists)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    
    def test_reject_without_reason_note_returns_400(self):
        """Reject without reason_note should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/any_request_id/reject",
            json={"reason_note": ""},
            headers=self.headers,
            timeout=15
        )
        # Should return 400 for missing reason_note (before checking if request exists)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
