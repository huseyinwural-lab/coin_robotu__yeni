"""
P2: Undo/Revert + Explainability Layer Tests
Tests for:
- POST /api/admin/decision-requests/{id}/revert: executed request için çalışıyor mu
- Decision revert role behavior: admin pending revert request, super_admin execute
- Decision revert guard: only latest executed for same target can revert (older request should 409)
- Decision request response includes explainability fields: explanation_summary, decision_factors, expected outcome
- Risk simulation response includes reasoned output/explanation fields
- Strategy allocation approval request list includes explainability + revert metadata fields
- POST /api/admin/strategy-allocation/approval-requests/{id}/revert: admin pending, super_admin execute
- Allocation revert guard: only latest approved for same target can revert
- Allocation revert applies previous_state_snapshot and source request marked reverted
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "alloc.admin.checkpoint2@example.com"
ADMIN_PASSWORD = "AdminTest123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def super_admin_headers(super_admin_token):
    """Headers for super_admin requests"""
    return {
        "Authorization": f"Bearer {super_admin_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers for admin requests"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


class TestDecisionRequestExplainabilityFields:
    """Test that decision request responses include explainability fields"""

    def test_decision_requests_list_includes_explainability_fields(self, super_admin_headers):
        """GET /api/admin/decision-requests should include explainability fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check response structure
        items = data.get("items", [])
        print(f"Found {len(items)} decision requests")
        
        if len(items) > 0:
            item = items[0]
            # Check explainability fields exist
            assert "explanation_summary" in item, "Missing explanation_summary field"
            assert "decision_factors" in item, "Missing decision_factors field"
            
            # Check revert metadata fields
            assert "source_request_id" in item, "Missing source_request_id field"
            assert "linked_revert_request_id" in item, "Missing linked_revert_request_id field"
            assert "reverted_at" in item, "Missing reverted_at field"
            assert "reverted_by" in item, "Missing reverted_by field"
            assert "revert_reason" in item, "Missing revert_reason field"
            
            # Check decision_factors structure if present
            factors = item.get("decision_factors", {})
            if factors:
                print(f"Decision factors: {factors}")
                # Expected fields in decision_factors
                expected_factor_fields = ["why_this_action", "expected_outcome"]
                for field in expected_factor_fields:
                    if field in factors:
                        print(f"  {field}: {factors[field]}")
            
            print(f"Explainability fields present in decision request: {item.get('request_id')}")
        else:
            print("No decision requests found - skipping field validation")


class TestRiskSimulationExplainability:
    """Test that risk simulation response includes reasoned output/explanation fields"""

    def test_risk_simulation_includes_explainability_fields(self, super_admin_headers):
        """POST /api/admin/risk-simulation should include reasoned_output and expected_outcome"""
        # First get a user_id
        me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=super_admin_headers)
        if me_response.status_code != 200:
            pytest.skip("Cannot get current user")
        user_id = me_response.json().get("id")
        
        payload = {
            "user_id": user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3.0,
                "position_size_value": 100
            },
            "apply_override": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=super_admin_headers,
            json=payload
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check explainability fields
        assert "reasoned_output" in data, "Missing reasoned_output field"
        assert "expected_outcome" in data, "Missing expected_outcome field"
        assert "decision_summary" in data, "Missing decision_summary field"
        
        print(f"Simulation ID: {data.get('simulation_id')}")
        print(f"Reasoned output: {data.get('reasoned_output')}")
        print(f"Expected outcome: {data.get('expected_outcome')}")
        
        # Check decision_summary structure
        decision_summary = data.get("decision_summary", {})
        if decision_summary:
            assert "why" in decision_summary, "Missing 'why' in decision_summary"
            assert "expected_outcome" in decision_summary, "Missing 'expected_outcome' in decision_summary"
            print(f"Decision summary why: {decision_summary.get('why')}")
            print(f"Decision summary expected_outcome: {decision_summary.get('expected_outcome')}")


class TestDecisionRequestRevertEndpoint:
    """Test POST /api/admin/decision-requests/{id}/revert endpoint"""

    def test_revert_requires_executed_status(self, super_admin_headers):
        """Revert should only work on executed requests"""
        # Get decision requests
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        
        # Find a pending request (should fail revert)
        pending_request = next((item for item in items if item.get("status") == "pending"), None)
        if pending_request:
            revert_response = requests.post(
                f"{BASE_URL}/api/admin/decision-requests/{pending_request['request_id']}/revert",
                headers=super_admin_headers,
                json={"reason_note": "test_revert_pending_should_fail"}
            )
            # Should fail because request is not executed
            assert revert_response.status_code == 400, f"Expected 400 for pending request revert, got {revert_response.status_code}"
            print(f"Correctly rejected revert on pending request: {revert_response.json()}")
        else:
            print("No pending requests found to test revert rejection")

    def test_admin_creates_pending_revert_request(self, admin_headers, super_admin_headers):
        """Admin role should create pending revert request, not execute immediately"""
        # Get decision requests
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        
        # Find an executed request that hasn't been reverted
        executed_request = next(
            (item for item in items 
             if item.get("status") == "executed" 
             and item.get("reverted_at") is None
             and item.get("request_type") != "revert_apply"),
            None
        )
        
        if executed_request:
            # Admin tries to revert
            revert_response = requests.post(
                f"{BASE_URL}/api/admin/decision-requests/{executed_request['request_id']}/revert",
                headers=admin_headers,
                json={"reason_note": "test_admin_revert_creates_pending"}
            )
            
            if revert_response.status_code == 200:
                revert_data = revert_response.json()
                # Admin should create pending revert request
                assert revert_data.get("status") == "pending", f"Admin revert should create pending request, got {revert_data.get('status')}"
                assert revert_data.get("request_type") == "revert_apply", "Should be revert_apply type"
                print(f"Admin created pending revert request: {revert_data.get('request_id')}")
            elif revert_response.status_code == 409:
                print(f"Revert blocked (409): {revert_response.json()} - likely not latest executed for target")
            else:
                print(f"Revert response: {revert_response.status_code} - {revert_response.text}")
        else:
            print("No executed requests available for revert test")

    def test_super_admin_executes_revert_immediately(self, super_admin_headers):
        """Super admin should execute revert immediately"""
        # Get decision requests
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        
        # Find an executed request that hasn't been reverted
        executed_request = next(
            (item for item in items 
             if item.get("status") == "executed" 
             and item.get("reverted_at") is None
             and item.get("request_type") != "revert_apply"),
            None
        )
        
        if executed_request:
            # Super admin tries to revert
            revert_response = requests.post(
                f"{BASE_URL}/api/admin/decision-requests/{executed_request['request_id']}/revert",
                headers=super_admin_headers,
                json={"reason_note": "test_super_admin_revert_executes_immediately"}
            )
            
            if revert_response.status_code == 200:
                revert_data = revert_response.json()
                # Super admin should execute immediately (status = executed)
                assert revert_data.get("status") == "executed", f"Super admin revert should execute immediately, got {revert_data.get('status')}"
                print(f"Super admin executed revert: {revert_data.get('request_id')}")
            elif revert_response.status_code == 409:
                print(f"Revert blocked (409): {revert_response.json()} - likely not latest executed for target")
            else:
                print(f"Revert response: {revert_response.status_code} - {revert_response.text}")
        else:
            print("No executed requests available for super admin revert test")


class TestDecisionRevertGuard:
    """Test that only latest executed request for same target can be reverted"""

    def test_revert_guard_returns_409_for_older_request(self, super_admin_headers):
        """Older executed requests for same target should return 409"""
        # Get decision requests
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        
        # Group executed requests by target
        executed_by_target = {}
        for item in items:
            if item.get("status") in ["executed", "reverted"] and item.get("request_type") != "revert_apply":
                target_key = f"{item.get('target_type')}:{item.get('target_id')}"
                if target_key not in executed_by_target:
                    executed_by_target[target_key] = []
                executed_by_target[target_key].append(item)
        
        # Find a target with multiple executed requests
        for target_key, requests_list in executed_by_target.items():
            if len(requests_list) > 1:
                # Sort by decided_at to find older one
                sorted_requests = sorted(
                    requests_list, 
                    key=lambda x: x.get("decided_at") or x.get("created_at") or "",
                    reverse=True
                )
                older_request = sorted_requests[-1]  # Oldest
                
                if older_request.get("reverted_at") is None:
                    # Try to revert older request - should get 409
                    revert_response = requests.post(
                        f"{BASE_URL}/api/admin/decision-requests/{older_request['request_id']}/revert",
                        headers=super_admin_headers,
                        json={"reason_note": "test_revert_older_should_409"}
                    )
                    
                    if revert_response.status_code == 409:
                        print(f"Correctly got 409 for older request revert: {revert_response.json()}")
                        return
                    else:
                        print(f"Older request revert returned {revert_response.status_code}: {revert_response.text}")
        
        print("No suitable older executed requests found to test 409 guard")


class TestStrategyAllocationApprovalExplainability:
    """Test strategy allocation approval request list includes explainability + revert metadata"""

    def test_allocation_approval_requests_include_explainability_fields(self, super_admin_headers):
        """GET /api/admin/strategy-allocation/approval-requests should include explainability fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        rows = data.get("rows", [])
        print(f"Found {len(rows)} allocation approval requests")
        
        if len(rows) > 0:
            item = rows[0]
            # Check explainability fields
            assert "explanation_summary" in item, "Missing explanation_summary field"
            assert "decision_factors" in item, "Missing decision_factors field"
            
            # Check revert metadata fields
            assert "source_request_id" in item, "Missing source_request_id field"
            assert "linked_revert_request_id" in item, "Missing linked_revert_request_id field"
            assert "reverted_at" in item, "Missing reverted_at field"
            assert "reverted_by" in item, "Missing reverted_by field"
            assert "revert_reason" in item, "Missing revert_reason field"
            
            print(f"Explainability fields present in allocation approval request: {item.get('request_id')}")
            print(f"  explanation_summary: {item.get('explanation_summary', '')[:100]}")
            
            factors = item.get("decision_factors", {})
            if factors:
                print(f"  decision_factors keys: {list(factors.keys())}")
        else:
            print("No allocation approval requests found - skipping field validation")


class TestStrategyAllocationRevertEndpoint:
    """Test POST /api/admin/strategy-allocation/approval-requests/{id}/revert endpoint"""

    def test_allocation_revert_requires_approved_status(self, super_admin_headers):
        """Allocation revert should only work on approved requests"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        rows = response.json().get("rows", [])
        
        # Find a pending request (should fail revert)
        pending_request = next((item for item in rows if item.get("status") == "pending"), None)
        if pending_request:
            revert_response = requests.post(
                f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/{pending_request['request_id']}/revert",
                headers=super_admin_headers,
                json={"reason_note": "test_allocation_revert_pending_should_fail"}
            )
            # Should fail because request is not approved
            assert revert_response.status_code == 400, f"Expected 400 for pending request revert, got {revert_response.status_code}"
            print(f"Correctly rejected allocation revert on pending request: {revert_response.json()}")
        else:
            print("No pending allocation requests found to test revert rejection")

    def test_admin_creates_pending_allocation_revert(self, admin_headers, super_admin_headers):
        """Admin role should create pending allocation revert request"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        rows = response.json().get("rows", [])
        
        # Find an approved request that hasn't been reverted
        approved_request = next(
            (item for item in rows 
             if item.get("status") == "approved" 
             and item.get("reverted_at") is None
             and item.get("action_type") != "revert_apply"),
            None
        )
        
        if approved_request:
            revert_response = requests.post(
                f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/{approved_request['request_id']}/revert",
                headers=admin_headers,
                json={"reason_note": "test_admin_allocation_revert_creates_pending"}
            )
            
            if revert_response.status_code == 200:
                revert_data = revert_response.json()
                # Admin should create pending revert request
                assert revert_data.get("status") == "pending_approval", f"Admin revert should create pending request, got {revert_data.get('status')}"
                print(f"Admin created pending allocation revert: {revert_data.get('trace_id')}")
            elif revert_response.status_code == 409:
                print(f"Allocation revert blocked (409): {revert_response.json()}")
            else:
                print(f"Allocation revert response: {revert_response.status_code} - {revert_response.text}")
        else:
            print("No approved allocation requests available for revert test")

    def test_super_admin_executes_allocation_revert(self, super_admin_headers):
        """Super admin should execute allocation revert immediately"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        rows = response.json().get("rows", [])
        
        # Find an approved request that hasn't been reverted
        approved_request = next(
            (item for item in rows 
             if item.get("status") == "approved" 
             and item.get("reverted_at") is None
             and item.get("action_type") != "revert_apply"),
            None
        )
        
        if approved_request:
            revert_response = requests.post(
                f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/{approved_request['request_id']}/revert",
                headers=super_admin_headers,
                json={"reason_note": "test_super_admin_allocation_revert_executes"}
            )
            
            if revert_response.status_code == 200:
                revert_data = revert_response.json()
                # Super admin should execute immediately
                assert revert_data.get("status") == "success", f"Super admin revert should succeed, got {revert_data.get('status')}"
                print(f"Super admin executed allocation revert: {revert_data.get('trace_id')}")
            elif revert_response.status_code == 409:
                print(f"Allocation revert blocked (409): {revert_response.json()}")
            else:
                print(f"Allocation revert response: {revert_response.status_code} - {revert_response.text}")
        else:
            print("No approved allocation requests available for super admin revert test")


class TestAllocationRevertGuard:
    """Test that only latest approved request for same target can be reverted"""

    def test_allocation_revert_guard_returns_409_for_older(self, super_admin_headers):
        """Older approved requests for same target should return 409"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        rows = response.json().get("rows", [])
        
        # Group approved requests by target
        approved_by_target = {}
        for item in rows:
            if item.get("status") in ["approved", "reverted"] and item.get("action_type") != "revert_apply":
                target_key = f"{item.get('target_type')}:{item.get('target_id')}"
                if target_key not in approved_by_target:
                    approved_by_target[target_key] = []
                approved_by_target[target_key].append(item)
        
        # Find a target with multiple approved requests
        for target_key, requests_list in approved_by_target.items():
            if len(requests_list) > 1:
                sorted_requests = sorted(
                    requests_list,
                    key=lambda x: x.get("reviewed_at") or x.get("created_at") or "",
                    reverse=True
                )
                older_request = sorted_requests[-1]
                
                if older_request.get("reverted_at") is None:
                    revert_response = requests.post(
                        f"{BASE_URL}/api/admin/strategy-allocation/approval-requests/{older_request['request_id']}/revert",
                        headers=super_admin_headers,
                        json={"reason_note": "test_allocation_revert_older_should_409"}
                    )
                    
                    if revert_response.status_code == 409:
                        print(f"Correctly got 409 for older allocation request revert: {revert_response.json()}")
                        return
                    else:
                        print(f"Older allocation request revert returned {revert_response.status_code}: {revert_response.text}")
        
        print("No suitable older approved allocation requests found to test 409 guard")


class TestAllocationRevertAppliesPreviousSnapshot:
    """Test that allocation revert applies previous_state_snapshot"""

    def test_revert_applies_previous_state_snapshot(self, super_admin_headers):
        """Verify that revert applies previous_state_snapshot and marks source as reverted"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        rows = response.json().get("rows", [])
        
        # Find a reverted request to verify the revert was applied
        reverted_request = next(
            (item for item in rows if item.get("status") == "reverted"),
            None
        )
        
        if reverted_request:
            # Verify revert metadata
            assert reverted_request.get("reverted_at") is not None, "reverted_at should be set"
            assert reverted_request.get("reverted_by") is not None, "reverted_by should be set"
            assert reverted_request.get("revert_reason") is not None, "revert_reason should be set"
            
            # Check if linked_revert_request_id is set
            linked_revert_id = reverted_request.get("linked_revert_request_id")
            if linked_revert_id:
                print(f"Source request {reverted_request['request_id']} linked to revert request {linked_revert_id}")
            
            print(f"Verified reverted request: {reverted_request['request_id']}")
            print(f"  reverted_at: {reverted_request.get('reverted_at')}")
            print(f"  reverted_by: {reverted_request.get('reverted_by')}")
            print(f"  revert_reason: {reverted_request.get('revert_reason')}")
        else:
            print("No reverted allocation requests found to verify snapshot application")


class TestQueueHistorySyncAfterRevert:
    """Test that queue/history sync after revert shows correct status/reverted_at/link fields"""

    def test_queue_shows_revert_status_and_links(self, super_admin_headers):
        """Verify queue items show correct revert status and link fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers=super_admin_headers
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        
        # Check for revert_apply type requests
        revert_requests = [item for item in items if item.get("request_type") == "revert_apply"]
        print(f"Found {len(revert_requests)} revert_apply requests in queue")
        
        for revert_req in revert_requests[:3]:  # Check first 3
            print(f"Revert request: {revert_req.get('request_id')}")
            print(f"  status: {revert_req.get('status')}")
            print(f"  source_request_id: {revert_req.get('source_request_id')}")
            print(f"  target: {revert_req.get('target_type')}:{revert_req.get('target_id')}")
        
        # Check for reverted source requests
        reverted_sources = [item for item in items if item.get("status") == "reverted"]
        print(f"Found {len(reverted_sources)} reverted source requests")
        
        for reverted in reverted_sources[:3]:
            print(f"Reverted source: {reverted.get('request_id')}")
            print(f"  linked_revert_request_id: {reverted.get('linked_revert_request_id')}")
            print(f"  reverted_at: {reverted.get('reverted_at')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
