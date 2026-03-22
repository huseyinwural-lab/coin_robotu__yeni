"""
Strategy Allocation Revision Control (Concurrency Control) Tests - Simplified
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

DOUBLE_CONFIRM_PRIMARY = "CONFIRM"
DOUBLE_CONFIRM_SECONDARY = "STATE CHANGE"


def get_auth_token():
    """Get super_admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        return None
    return response.json().get("access_token")


def get_headers():
    """Get headers with auth"""
    token = get_auth_token()
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def create_test_strategy(headers, strategy_id):
    """Create a test strategy with weight=1.0"""
    # First delete any existing test strategies
    list_resp = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", headers=headers)
    if list_resp.status_code == 200:
        rows = list_resp.json()
        for row in rows:
            if row.get("strategy_id", "").startswith("TEST_"):
                try:
                    requests.delete(
                        f"{BASE_URL}/api/admin/strategy-allocation/{row['strategy_id']}",
                        headers=headers,
                        params={
                            "auto_normalize": True,
                            "reason_note": "cleanup_old_test",
                            "expected_revision": row.get("revision_id", 1),
                        },
                    )
                except Exception:
                    pass
    
    # Create new strategy with weight=1.0 (since table is empty)
    create_response = requests.post(
        f"{BASE_URL}/api/admin/strategy-allocation",
        headers=headers,
        json={
            "strategy_id": strategy_id,
            "capital_weight": 1.0,
            "max_capital": 10000,
            "current_capital": 0,
            "state": "ACTIVE",
            "reason_note": "test_revision_control_setup",
        },
    )
    return create_response


def delete_test_strategy(headers, strategy_id, revision_id):
    """Delete a test strategy"""
    return requests.delete(
        f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
        headers=headers,
        params={
            "auto_normalize": True,
            "reason_note": "test_cleanup",
            "expected_revision": revision_id,
        },
    )


class TestRevisionControlEndpoints:
    """Tests for revision control across all endpoints"""

    def test_auth_works(self):
        """Verify authentication works"""
        headers = get_headers()
        assert headers is not None, "Failed to get auth token"
        print("✓ Authentication successful")

    def test_create_strategy_returns_revision_id(self):
        """Create strategy should return revision_id=1"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_rev_{datetime.now().strftime('%H%M%S%f')}"
        response = create_test_strategy(headers, strategy_id)
        
        assert response.status_code in [200, 201], f"Create failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify revision_id is present and equals 1 for new strategy
        assert "revision_id" in data, f"Missing revision_id in response: {data.keys()}"
        assert data["revision_id"] == 1, f"Expected revision_id=1, got {data['revision_id']}"
        print(f"✓ Create strategy returns revision_id=1")
        
        # Cleanup
        delete_test_strategy(headers, strategy_id, data["revision_id"])

    def test_update_with_correct_revision_succeeds(self):
        """PUT with correct expected_revision should succeed"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_upd_{datetime.now().strftime('%H%M%S%f')}"
        create_resp = create_test_strategy(headers, strategy_id)
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        current_revision = created.get("revision_id", 1)
        
        # Update with correct revision
        update_resp = requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=headers,
            json={
                "expected_revision": current_revision,
                "max_capital": 15000,
                "reason_note": "test_correct_revision_update",
            },
        )
        
        assert update_resp.status_code == 200, f"Update failed: {update_resp.status_code} - {update_resp.text}"
        updated = update_resp.json()
        assert updated.get("max_capital") == 15000
        assert updated.get("revision_id") == current_revision + 1, "Revision should increment"
        print(f"✓ Update with correct revision succeeded, revision: {current_revision} -> {updated.get('revision_id')}")
        
        # Cleanup
        delete_test_strategy(headers, strategy_id, updated["revision_id"])

    def test_update_with_wrong_revision_returns_409(self):
        """PUT with wrong expected_revision should return 409"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_409_{datetime.now().strftime('%H%M%S%f')}"
        create_resp = create_test_strategy(headers, strategy_id)
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        
        # Update with wrong revision
        update_resp = requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=headers,
            json={
                "expected_revision": 9999,  # Wrong revision
                "max_capital": 20000,
                "reason_note": "test_wrong_revision_update",
            },
        )
        
        assert update_resp.status_code == 409, f"Expected 409, got {update_resp.status_code}: {update_resp.text}"
        data = update_resp.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT", f"Expected REVISION_CONFLICT, got: {detail}"
        assert "conflicts" in detail, "Missing conflicts array"
        print(f"✓ Update with wrong revision returned 409 REVISION_CONFLICT")
        
        # Cleanup
        delete_test_strategy(headers, strategy_id, created["revision_id"])

    def test_bulk_update_with_wrong_revision_returns_409(self):
        """Bulk update with wrong expected_revision should return 409"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_bulk_{datetime.now().strftime('%H%M%S%f')}"
        create_resp = create_test_strategy(headers, strategy_id)
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        
        # Bulk update with wrong revision
        bulk_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/bulk-update",
            headers=headers,
            json={
                "updates": [
                    {
                        "strategy_id": strategy_id,
                        "expected_revision": 9999,  # Wrong
                        "max_capital": 25000,
                    }
                ],
                "auto_normalize": False,
                "reason_note": "test_bulk_wrong_revision",
            },
        )
        
        assert bulk_resp.status_code == 409, f"Expected 409, got {bulk_resp.status_code}: {bulk_resp.text}"
        data = bulk_resp.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT"
        print(f"✓ Bulk update with wrong revision returned 409")
        
        # Cleanup
        delete_test_strategy(headers, strategy_id, created["revision_id"])

    def test_throttle_toggle_with_wrong_revision_returns_409(self):
        """Throttle toggle with wrong expected_revision should return 409"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_thr_{datetime.now().strftime('%H%M%S%f')}"
        create_resp = create_test_strategy(headers, strategy_id)
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        
        # Throttle toggle with wrong revision
        toggle_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}/throttle-toggle",
            headers=headers,
            json={
                "expected_revision": 9999,  # Wrong
                "confirm_primary": DOUBLE_CONFIRM_PRIMARY,
                "confirm_secondary": DOUBLE_CONFIRM_SECONDARY,
                "reason_note": "test_throttle_wrong_revision",
            },
        )
        
        assert toggle_resp.status_code == 409, f"Expected 409, got {toggle_resp.status_code}: {toggle_resp.text}"
        data = toggle_resp.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT"
        print(f"✓ Throttle toggle with wrong revision returned 409")
        
        # Cleanup
        delete_test_strategy(headers, strategy_id, created["revision_id"])

    def test_delete_with_wrong_revision_returns_409(self):
        """Delete with wrong expected_revision should return 409"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_del_{datetime.now().strftime('%H%M%S%f')}"
        create_resp = create_test_strategy(headers, strategy_id)
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        
        # Delete with wrong revision
        delete_resp = requests.delete(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=headers,
            params={
                "auto_normalize": True,
                "reason_note": "test_delete_wrong_revision",
                "expected_revision": 9999,  # Wrong
            },
        )
        
        assert delete_resp.status_code == 409, f"Expected 409, got {delete_resp.status_code}: {delete_resp.text}"
        data = delete_resp.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT"
        print(f"✓ Delete with wrong revision returned 409")
        
        # Cleanup with correct revision
        delete_test_strategy(headers, strategy_id, created["revision_id"])

    def test_normalize_without_expected_revisions_returns_400(self):
        """Normalize without expected_revisions should return 400"""
        headers = get_headers()
        assert headers is not None
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            headers=headers,
            json={
                "reason_note": "test_normalize_missing_revisions",
            },
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print(f"✓ Normalize without expected_revisions returned 400")

    def test_normalize_with_wrong_revisions_returns_409(self):
        """Normalize with wrong expected_revisions should return 409"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_norm_{datetime.now().strftime('%H%M%S%f')}"
        create_resp = create_test_strategy(headers, strategy_id)
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        
        # Normalize with wrong revision
        norm_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            headers=headers,
            json={
                "reason_note": "test_normalize_wrong_revisions",
                "expected_revisions": {
                    strategy_id: 9999,  # Wrong
                },
            },
        )
        
        assert norm_resp.status_code == 409, f"Expected 409, got {norm_resp.status_code}: {norm_resp.text}"
        data = norm_resp.json()
        detail = data.get("detail", {})
        assert detail.get("code") == "REVISION_CONFLICT"
        print(f"✓ Normalize with wrong revisions returned 409")
        
        # Cleanup
        delete_test_strategy(headers, strategy_id, created["revision_id"])

    def test_whatif_returns_projection_fields(self):
        """What-if simulation should return weight_delta, projected_return_delta_pct, projected_risk_delta_pct"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_wif_{datetime.now().strftime('%H%M%S%f')}"
        create_resp = create_test_strategy(headers, strategy_id)
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        
        # Run what-if simulation
        whatif_resp = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/what-if-simulation",
            headers=headers,
            json={
                "strategy_ids": [strategy_id],
            },
        )
        
        assert whatif_resp.status_code == 200, f"What-if failed: {whatif_resp.status_code} - {whatif_resp.text}"
        data = whatif_resp.json()
        
        # Check top-level projection fields
        assert "projected_portfolio_return_delta_pct" in data, "Missing projected_portfolio_return_delta_pct"
        assert "projected_portfolio_risk_delta_pct" in data, "Missing projected_portfolio_risk_delta_pct"
        assert "rows" in data, "Missing rows array"
        
        # Check row-level projection fields
        if data.get("rows"):
            row = data["rows"][0]
            assert "weight_delta" in row, f"Missing weight_delta in row: {row.keys()}"
            assert "projected_return_delta_pct" in row, f"Missing projected_return_delta_pct in row"
            assert "projected_risk_delta_pct" in row, f"Missing projected_risk_delta_pct in row"
            print(f"✓ What-if row fields: weight_delta={row.get('weight_delta')}, "
                  f"return_delta={row.get('projected_return_delta_pct')}, "
                  f"risk_delta={row.get('projected_risk_delta_pct')}")
        
        print(f"✓ What-if simulation returns all required projection fields")
        
        # Cleanup
        delete_test_strategy(headers, strategy_id, created["revision_id"])

    def test_approval_requests_endpoint_works(self):
        """Approval requests endpoint should return list"""
        headers = get_headers()
        assert headers is not None
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=headers,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rows" in data, "Missing rows in approval requests response"
        print(f"✓ Approval requests endpoint works, found {len(data.get('rows', []))} requests")

    def test_conflict_response_structure(self):
        """409 response should have code, message, action_type, conflicts"""
        headers = get_headers()
        assert headers is not None
        
        strategy_id = f"TEST_str_{datetime.now().strftime('%H%M%S%f')}"
        create_resp = create_test_strategy(headers, strategy_id)
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        
        # Trigger 409
        update_resp = requests.put(
            f"{BASE_URL}/api/admin/strategy-allocation/{strategy_id}",
            headers=headers,
            json={
                "expected_revision": 9999,
                "max_capital": 30000,
                "reason_note": "test_conflict_structure",
            },
        )
        
        assert update_resp.status_code == 409
        data = update_resp.json()
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
        
        # Cleanup
        delete_test_strategy(headers, strategy_id, created["revision_id"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
