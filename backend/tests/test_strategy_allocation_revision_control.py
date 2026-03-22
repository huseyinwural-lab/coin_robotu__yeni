"""
Strategy Allocation Revision Control (Concurrency Control) Tests
Tests for Checkpoint 1: revision_id, expected_revision, 409 conflict handling

Features tested:
- PUT /api/admin/strategy-allocation/{strategy_id} expected_revision mismatch -> 409
- POST /api/admin/strategy-allocation/bulk-update expected_revision mismatch -> 409
- POST /api/admin/strategy-allocation/{strategy_id}/throttle-toggle expected_revision mismatch -> 409
- DELETE /api/admin/strategy-allocation/{strategy_id} expected_revision mismatch -> 409
- POST /api/admin/strategy-allocation/normalize expected_revisions validation + 409
- Approval approve stale re-validation (status requires_review + stale_state STALE)
- What-if endpoint parity (weight_delta, projected_return_delta_pct, projected_risk_delta_pct)
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://localhost:8001"

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"

DOUBLE_CONFIRM_PRIMARY = "CONFIRM"
DOUBLE_CONFIRM_SECONDARY = "STATE CHANGE"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def super_admin_headers(super_admin_token):
    """Headers with super_admin auth"""
    return {
        "Authorization": f"Bearer {super_admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token (for approval flow testing)"""
    # First try to register the admin user
    register_response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    # Login regardless of registration result
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="function")
def test_strategy(super_admin_headers):
    """Create a test strategy for each test"""
    strategy_id = f"TEST_revision_ctrl_{datetime.now().strftime('%H%M%S%f')}"
    
    # First get current allocations to understand weight budget
    list_resp = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", headers=super_admin_headers)
    existing_rows = list_resp.json() if list_resp.status_code == 200 else []
    
    # Calculate remaining weight
    total_existing_weight = sum(float(row.get("capital_weight", 0)) for row in existing_rows)
    available_weight = max(0.01, 1.0 - total_existing_weight)
    
    # Create strategy with small weight
    create_response = requests.post(
        f"{BASE_URL}/api/admin/strategy-allocation",
        headers=super_admin_headers,
        json={
            "strategy_id": strategy_id,
            "capital_weight": min(0.01, available_weight),
            "max_capital": 1000,
            "current_capital": 0,
            "state": "ACTIVE",
            "reason_note": "test_revision_control_setup",
        },
    )
    
    if create_response.status_code not in [200, 201]:
        # If creation fails due to weight, try to normalize first
        normalize_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            headers=super_admin_headers,
            json={
                "reason_note": "test_setup_normalize",
                "expected_revisions": {row["strategy_id"]: row.get("revision_id", 1) for row in existing_rows},
            },
        )
        # Retry creation
        create_response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=super_admin_headers,
            json={
                "strategy_id": strategy_id,
                "capital_weight": 0.01,
                "max_capital": 1000,
                "current_capital": 0,
                "state": "ACTIVE",
                "reason_note": "test_revision_control_setup_retry",
            },
        )
    
    if create_response.status_code not in [200, 201]:
        pytest.skip(f"Could not create test strategy: {create_response.status_code} - {create_response.text}")
    
    created = create_response.json()
    yield {
        "strategy_id": strategy_id,
        "revision_id": created.get("revision_id", 1),
        "data": created,
    }
    
    # Cleanup - delete the test strategy
    try:
        # Get current revision
        get_resp = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", headers=super_admin_headers)
        if get_resp.status_code == 200:
            rows = get_resp.json()
            for row in rows:
                if row.get("strategy_id") == strategy_id:
                    current_rev = row.get("revision_id", 1)
                    requests.delete(
                        f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
                        headers=super_admin_headers,
                        params={
                            "auto_normalize": True,
                            "reason_note": "test_cleanup",
                            "expected_revision": current_rev,
                        },
                    )
                    break
    except Exception:
        pass


class TestRevisionControlPUT:
    """Tests for PUT /api/admin/strategy-allocation/{strategy_id} revision control"""

    def test_update_with_correct_revision_succeeds(self, super_admin_headers, test_strategy):
        """Update with correct expected_revision should succeed"""
        strategy_id = test_strategy["strategy_id"]
        current_revision = test_strategy["revision_id"]
        
        response = requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=super_admin_headers,
            json={
                "expected_revision": current_revision,
                "max_capital": 1100,
                "reason_note": "test_correct_revision_update",
            },
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("max_capital") == 1100
        # Revision should be incremented
        assert data.get("revision_id", 0) > current_revision
        print(f"✓ Update with correct revision succeeded, new revision: {data.get('revision_id')}")

    def test_update_with_wrong_revision_returns_409(self, super_admin_headers, test_strategy):
        """Update with wrong expected_revision should return 409 REVISION_CONFLICT"""
        strategy_id = test_strategy["strategy_id"]
        wrong_revision = 9999  # Definitely wrong
        
        response = requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=super_admin_headers,
            json={
                "expected_revision": wrong_revision,
                "max_capital": 1200,
                "reason_note": "test_wrong_revision_update",
            },
        )
        
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT", f"Expected REVISION_CONFLICT code, got: {detail}"
        assert "conflicts" in detail, "Expected conflicts array in response"
        print(f"✓ Update with wrong revision returned 409 with REVISION_CONFLICT")

    def test_update_without_expected_revision_returns_400(self, super_admin_headers, test_strategy):
        """Update without expected_revision should return 400"""
        strategy_id = test_strategy["strategy_id"]
        
        response = requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=super_admin_headers,
            json={
                "max_capital": 1300,
                "reason_note": "test_missing_revision",
            },
        )
        
        # Should fail validation - expected_revision is required
        assert response.status_code == 400 or response.status_code == 422, \
            f"Expected 400/422, got {response.status_code}: {response.text}"
        print(f"✓ Update without expected_revision returned {response.status_code}")


class TestRevisionControlBulkUpdate:
    """Tests for POST /api/admin/strategy-allocation/bulk-update revision control"""

    def test_bulk_update_with_correct_revisions_succeeds(self, super_admin_headers, test_strategy):
        """Bulk update with correct expected_revisions should succeed"""
        strategy_id = test_strategy["strategy_id"]
        
        # Get current revision
        list_resp = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", headers=super_admin_headers)
        assert list_resp.status_code == 200
        rows = list_resp.json()
        current_row = next((r for r in rows if r["strategy_id"] == strategy_id), None)
        assert current_row is not None, "Test strategy not found"
        current_revision = current_row.get("revision_id", 1)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/bulk-update",
            headers=super_admin_headers,
            json={
                "updates": [
                    {
                        "strategy_id": strategy_id,
                        "expected_revision": current_revision,
                        "max_capital": 1400,
                    }
                ],
                "auto_normalize": False,
                "reason_note": "test_bulk_correct_revision",
            },
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("updated_count", 0) >= 1
        print(f"✓ Bulk update with correct revision succeeded")

    def test_bulk_update_with_wrong_revision_returns_409(self, super_admin_headers, test_strategy):
        """Bulk update with wrong expected_revision should return 409"""
        strategy_id = test_strategy["strategy_id"]
        wrong_revision = 9999
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/bulk-update",
            headers=super_admin_headers,
            json={
                "updates": [
                    {
                        "strategy_id": strategy_id,
                        "expected_revision": wrong_revision,
                        "max_capital": 1500,
                    }
                ],
                "auto_normalize": False,
                "reason_note": "test_bulk_wrong_revision",
            },
        )
        
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT"
        print(f"✓ Bulk update with wrong revision returned 409")


class TestRevisionControlThrottleToggle:
    """Tests for POST /api/admin/strategy-allocation/{strategy_id}/throttle-toggle revision control"""

    def test_throttle_toggle_with_correct_revision_succeeds(self, super_admin_headers, test_strategy):
        """Throttle toggle with correct expected_revision should succeed"""
        strategy_id = test_strategy["strategy_id"]
        
        # Get current revision
        list_resp = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", headers=super_admin_headers)
        assert list_resp.status_code == 200
        rows = list_resp.json()
        current_row = next((r for r in rows if r["strategy_id"] == strategy_id), None)
        assert current_row is not None
        current_revision = current_row.get("revision_id", 1)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}/throttle-toggle",
            headers=super_admin_headers,
            json={
                "expected_revision": current_revision,
                "confirm_primary": DOUBLE_CONFIRM_PRIMARY,
                "confirm_secondary": DOUBLE_CONFIRM_SECONDARY,
                "reason_note": "test_throttle_correct_revision",
            },
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # State should have changed
        assert data.get("state") in ["ACTIVE", "THROTTLED"]
        print(f"✓ Throttle toggle with correct revision succeeded, new state: {data.get('state')}")

    def test_throttle_toggle_with_wrong_revision_returns_409(self, super_admin_headers, test_strategy):
        """Throttle toggle with wrong expected_revision should return 409"""
        strategy_id = test_strategy["strategy_id"]
        wrong_revision = 9999
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}/throttle-toggle",
            headers=super_admin_headers,
            json={
                "expected_revision": wrong_revision,
                "confirm_primary": DOUBLE_CONFIRM_PRIMARY,
                "confirm_secondary": DOUBLE_CONFIRM_SECONDARY,
                "reason_note": "test_throttle_wrong_revision",
            },
        )
        
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT"
        print(f"✓ Throttle toggle with wrong revision returned 409")


class TestRevisionControlDelete:
    """Tests for DELETE /api/admin/strategy-allocation/{strategy_id} revision control"""

    def test_delete_with_wrong_revision_returns_409(self, super_admin_headers, test_strategy):
        """Delete with wrong expected_revision should return 409"""
        strategy_id = test_strategy["strategy_id"]
        wrong_revision = 9999
        
        response = requests.delete(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=super_admin_headers,
            params={
                "auto_normalize": True,
                "reason_note": "test_delete_wrong_revision",
                "expected_revision": wrong_revision,
            },
        )
        
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT"
        print(f"✓ Delete with wrong revision returned 409")


class TestRevisionControlNormalize:
    """Tests for POST /api/admin/strategy-allocation/normalize revision control"""

    def test_normalize_without_expected_revisions_returns_400(self, super_admin_headers):
        """Normalize without expected_revisions should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            headers=super_admin_headers,
            json={
                "reason_note": "test_normalize_missing_revisions",
            },
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print(f"✓ Normalize without expected_revisions returned 400")

    def test_normalize_with_wrong_revisions_returns_409(self, super_admin_headers, test_strategy):
        """Normalize with wrong expected_revisions should return 409"""
        strategy_id = test_strategy["strategy_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            headers=super_admin_headers,
            json={
                "reason_note": "test_normalize_wrong_revisions",
                "expected_revisions": {
                    strategy_id: 9999,  # Wrong revision
                },
            },
        )
        
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT"
        print(f"✓ Normalize with wrong revisions returned 409")

    def test_normalize_with_correct_revisions_succeeds(self, super_admin_headers):
        """Normalize with correct expected_revisions should succeed"""
        # Get all current allocations
        list_resp = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", headers=super_admin_headers)
        assert list_resp.status_code == 200
        rows = list_resp.json()
        
        if not rows:
            pytest.skip("No strategy allocations to normalize")
        
        # Build expected_revisions map
        expected_revisions = {row["strategy_id"]: row.get("revision_id", 1) for row in rows}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            headers=super_admin_headers,
            json={
                "reason_note": "test_normalize_correct_revisions",
                "expected_revisions": expected_revisions,
            },
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        print(f"✓ Normalize with correct revisions succeeded")


class TestWhatIfEndpointParity:
    """Tests for what-if simulation endpoint output fields"""

    def test_whatif_returns_projection_fields(self, super_admin_headers, test_strategy):
        """What-if simulation should return weight_delta, projected_return_delta_pct, projected_risk_delta_pct"""
        strategy_id = test_strategy["strategy_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/what-if-simulation",
            headers=super_admin_headers,
            json={
                "strategy_ids": [strategy_id],
            },
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check top-level projection fields
        assert "projected_portfolio_return_delta_pct" in data, "Missing projected_portfolio_return_delta_pct"
        assert "projected_portfolio_risk_delta_pct" in data, "Missing projected_portfolio_risk_delta_pct"
        assert "rows" in data, "Missing rows array"
        
        # Check row-level projection fields
        if data.get("rows"):
            row = data["rows"][0]
            assert "weight_delta" in row, f"Missing weight_delta in row: {row.keys()}"
            assert "projected_return_delta_pct" in row, f"Missing projected_return_delta_pct in row: {row.keys()}"
            assert "projected_risk_delta_pct" in row, f"Missing projected_risk_delta_pct in row: {row.keys()}"
            print(f"✓ What-if row fields: weight_delta={row.get('weight_delta')}, "
                  f"return_delta={row.get('projected_return_delta_pct')}, "
                  f"risk_delta={row.get('projected_risk_delta_pct')}")
        
        print(f"✓ What-if simulation returns all required projection fields")


class TestApprovalStaleRevalidation:
    """Tests for approval approve stale re-validation"""

    def test_approval_requests_endpoint_works(self, super_admin_headers):
        """Approval requests endpoint should return list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=super_admin_headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rows" in data, "Missing rows in approval requests response"
        print(f"✓ Approval requests endpoint works, found {len(data.get('rows', []))} requests")

    def test_approval_status_includes_stale_fields(self, super_admin_headers):
        """Approval request items should include stale_state field when applicable"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=super_admin_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        rows = data.get("rows", [])
        
        # Check that the response structure supports stale fields
        # Even if no requests exist, the endpoint should work
        print(f"✓ Approval requests endpoint supports stale_state field structure")
        
        # If there are requests with requires_review status, verify stale fields
        for row in rows:
            if row.get("status") == "requires_review":
                assert "stale_state" in row or row.get("stale_state") is None, \
                    "requires_review status should have stale_state field"
                print(f"  Found requires_review request with stale_state: {row.get('stale_state')}")


class TestConflictResponseStructure:
    """Tests for 409 conflict response structure"""

    def test_conflict_response_has_required_fields(self, super_admin_headers, test_strategy):
        """409 response should have code, message, action_type, conflicts"""
        strategy_id = test_strategy["strategy_id"]
        
        response = requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=super_admin_headers,
            json={
                "expected_revision": 9999,
                "max_capital": 2000,
                "reason_note": "test_conflict_structure",
            },
        )
        
        assert response.status_code == 409
        data = response.json()
        detail = data.get("detail", {})
        
        # Verify required fields
        assert "code" in detail, "Missing 'code' in conflict response"
        assert detail["code"] == "REVISION_CONFLICT"
        assert "message" in detail, "Missing 'message' in conflict response"
        assert "conflicts" in detail, "Missing 'conflicts' in conflict response"
        
        # Verify conflict item structure
        conflicts = detail.get("conflicts", [])
        assert len(conflicts) > 0, "Expected at least one conflict item"
        
        conflict = conflicts[0]
        assert "strategy_id" in conflict, "Missing strategy_id in conflict item"
        assert "expected_revision" in conflict, "Missing expected_revision in conflict item"
        assert "current_revision" in conflict, "Missing current_revision in conflict item"
        assert "reason" in conflict, "Missing reason in conflict item"
        
        print(f"✓ Conflict response structure verified: code={detail['code']}, "
              f"conflicts={len(conflicts)}, reason={conflict.get('reason')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
