"""
Iteration 74 - Approval-Gated State Machine + Sprint2 Features Testing

Tests:
- POST /api/admin/manual-overrides: admin için pending_approval dönüyor
- POST /api/admin/override-approval-requests/{id}/approve: super_admin request'i approve+execute ediyor
- POST /api/admin/override-approval-requests/{id}/reject: super_admin reject ediyor
- GET /api/admin/override-approval-requests listesi çalışıyor
- GET /api/admin/risk-simulation/history kalıcı run kayıtlarını dönüyor
- POST /api/admin/risk-simulation/batch seçili symbol listesi ile çalışıyor
- Risk simulation response ve batch item içinde confidence_adjusted_risk_score dönüyor
"""

import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"


class TestApprovalGatedStateMachine:
    """Tests for approval-gated state machine (admin request-only / super_admin approve-execute)"""

    @pytest.fixture(scope="class")
    def super_admin_token(self):
        """Get super_admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Super admin login failed: {response.status_code}")
        data = response.json()
        return data.get("access_token")

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code} - admin account may not exist")
        data = response.json()
        return data.get("access_token")

    @pytest.fixture(scope="class")
    def super_admin_user_id(self, super_admin_token):
        """Get super_admin user ID"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        if response.status_code != 200:
            pytest.skip("Could not get super_admin user info")
        return response.json().get("id")

    @pytest.fixture(scope="class")
    def admin_user_id(self, admin_token):
        """Get admin user ID"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        if response.status_code != 200:
            pytest.skip("Could not get admin user info")
        return response.json().get("id")

    def test_super_admin_login_success(self, super_admin_token):
        """Test super_admin can login successfully"""
        assert super_admin_token is not None
        print(f"PASS: Super admin login successful, token obtained")

    def test_admin_login_or_skip(self, admin_token):
        """Test admin can login or skip if account doesn't exist"""
        if admin_token:
            print(f"PASS: Admin login successful, token obtained")
        else:
            pytest.skip("Admin account not available")

    def test_strategy_intelligence_dashboard_loads(self, super_admin_token):
        """Test strategy intelligence dashboard endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Dashboard failed: {response.status_code}"
        data = response.json()
        assert "generated_at" in data
        assert "strategy_conflicts" in data
        assert "hedge_suggestions" in data
        print(f"PASS: Strategy intelligence dashboard loaded successfully")

    def test_risk_simulation_returns_confidence_adjusted_risk_score(self, super_admin_token, super_admin_user_id):
        """Test single risk simulation returns confidence_adjusted_risk_score"""
        payload = {
            "user_id": super_admin_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100,
            },
            "apply_override": False,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            json=payload,
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Simulation failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify confidence_adjusted_risk_score is present
        assert "confidence_adjusted_risk_score" in data, "confidence_adjusted_risk_score missing from response"
        assert isinstance(data["confidence_adjusted_risk_score"], (int, float)), "confidence_adjusted_risk_score should be numeric"
        
        # Verify other expected fields
        assert "simulation_id" in data
        assert "projected_risk_score" in data
        assert "risk_delta" in data
        assert "decision_delta" in data
        assert "before_state" in data
        assert "after_state" in data
        
        print(f"PASS: Risk simulation returned confidence_adjusted_risk_score={data['confidence_adjusted_risk_score']}")
        return data["simulation_id"]

    def test_batch_simulation_returns_confidence_adjusted_risk_score(self, super_admin_token, super_admin_user_id):
        """Test batch simulation returns confidence_adjusted_risk_score for each item"""
        payload = {
            "user_id": super_admin_user_id,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "intent_payload": {
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/batch",
            json=payload,
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Batch simulation failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify batch response structure
        assert "batch_id" in data
        assert "total_symbols" in data
        assert "items" in data
        assert "summary" in data
        
        # Verify each item has confidence_adjusted_risk_score
        items = data.get("items", [])
        assert len(items) > 0, "Batch simulation returned no items"
        
        for item in items:
            assert "confidence_adjusted_risk_score" in item, f"confidence_adjusted_risk_score missing from item {item.get('symbol')}"
            assert isinstance(item["confidence_adjusted_risk_score"], (int, float))
            assert "simulation_id" in item
            assert "symbol" in item
            assert "projected_risk_score" in item
            assert "risk_delta" in item
            
        # Verify summary has avg_confidence_adjusted_risk_score
        summary = data.get("summary", {})
        assert "avg_confidence_adjusted_risk_score" in summary, "avg_confidence_adjusted_risk_score missing from summary"
        
        print(f"PASS: Batch simulation returned {len(items)} items with confidence_adjusted_risk_score")
        print(f"  Summary: {summary}")

    def test_simulation_history_returns_persisted_runs(self, super_admin_token):
        """Test simulation history endpoint returns persisted run records"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            params={"limit": 20},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"History failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert "items" in data
        items = data.get("items", [])
        
        # Verify history item structure
        if len(items) > 0:
            item = items[0]
            assert "run_id" in item
            assert "actor_id" in item
            assert "actor_role" in item
            assert "scope" in item
            assert "status" in item
            assert "request_mode" in item
            assert "symbols" in item
            assert "created_at" in item
            print(f"PASS: Simulation history returned {len(items)} records")
            print(f"  Latest: run_id={item['run_id']}, mode={item['request_mode']}, status={item['status']}")
        else:
            print(f"PASS: Simulation history endpoint working (no records yet)")

    def test_override_approval_requests_list(self, super_admin_token):
        """Test override approval requests list endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/override-approval-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Approval requests list failed: {response.status_code}"
        data = response.json()
        
        assert "items" in data
        items = data.get("items", [])
        
        if len(items) > 0:
            item = items[0]
            assert "request_id" in item
            assert "request_type" in item
            assert "status" in item
            assert "requested_by" in item
            assert "reason_note" in item
            print(f"PASS: Approval requests list returned {len(items)} items")
        else:
            print(f"PASS: Approval requests list endpoint working (no pending requests)")

    def test_super_admin_override_applies_directly(self, super_admin_token, super_admin_user_id):
        """Test super_admin can apply override directly (not pending_approval)"""
        # First run simulation to get simulation_id
        sim_payload = {
            "user_id": super_admin_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
            },
            "apply_override": False,
        }
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            json=sim_payload,
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert sim_response.status_code == 200
        simulation_id = sim_response.json().get("simulation_id")
        
        # Apply override as super_admin
        override_payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": super_admin_user_id,
            "action_type": "test_super_admin_direct_apply",
            "reason": "Testing super_admin direct apply capability",
            "simulation_id": simulation_id,
            "ttl_minutes": 60,
            "confirmation_id": f"confirm_test_{int(time.time())}",
            "previous_state": {},
            "next_state": {},
            "impact_preview": {},
            "payload": {"test": True},
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/manual-overrides",
            json=override_payload,
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Override apply failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Super admin should get "applied" status, not "pending_approval"
        assert data.get("status") == "applied", f"Expected 'applied' status for super_admin, got: {data.get('status')}"
        assert data.get("override") is not None, "Override object should be present"
        print(f"PASS: Super admin override applied directly with status='applied'")


class TestAdminApprovalGatedFlow:
    """Tests for admin role approval-gated flow (requires admin account)"""

    @pytest.fixture(scope="class")
    def super_admin_token(self):
        """Get super_admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Super admin login failed: {response.status_code}")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code} - admin account may not exist")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def admin_user_id(self, admin_token):
        """Get admin user ID"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        if response.status_code != 200:
            pytest.skip("Could not get admin user info")
        return response.json().get("id")

    def test_admin_override_returns_pending_approval(self, admin_token, admin_user_id):
        """Test admin role override returns pending_approval status"""
        # First run simulation to get simulation_id
        sim_payload = {
            "user_id": admin_user_id,
            "intent_payload": {
                "symbol": "ETHUSDT",
                "side": "buy",
                "notional": 50,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 2,
            },
            "apply_override": False,
        }
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            json=sim_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert sim_response.status_code == 200
        simulation_id = sim_response.json().get("simulation_id")
        
        # Apply override as admin - should return pending_approval
        override_payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": admin_user_id,
            "action_type": "test_admin_pending_approval",
            "reason": "Testing admin pending approval flow",
            "simulation_id": simulation_id,
            "ttl_minutes": 60,
            "confirmation_id": f"confirm_admin_{int(time.time())}",
            "previous_state": {},
            "next_state": {},
            "impact_preview": {},
            "payload": {"test": True},
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/manual-overrides",
            json=override_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Override request failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Admin should get "pending_approval" status
        assert data.get("status") == "pending_approval", f"Expected 'pending_approval' for admin, got: {data.get('status')}"
        assert data.get("request_id") is not None, "request_id should be present for pending_approval"
        assert "onaya gönderildi" in data.get("message", "").lower() or "pending" in data.get("message", "").lower()
        
        print(f"PASS: Admin override returned pending_approval with request_id={data.get('request_id')}")
        return data.get("request_id")

    def test_super_admin_can_approve_request(self, super_admin_token, admin_token, admin_user_id):
        """Test super_admin can approve a pending request"""
        # First create a pending request as admin
        sim_payload = {
            "user_id": admin_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "sell",
                "notional": 75,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 4,
            },
            "apply_override": False,
        }
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            json=sim_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert sim_response.status_code == 200
        simulation_id = sim_response.json().get("simulation_id")
        
        override_payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": admin_user_id,
            "action_type": "test_approve_flow",
            "reason": "Testing approve flow by super_admin",
            "simulation_id": simulation_id,
            "ttl_minutes": 60,
            "confirmation_id": f"confirm_approve_{int(time.time())}",
            "previous_state": {},
            "next_state": {},
            "impact_preview": {},
            "payload": {"test": True},
        }
        override_response = requests.post(
            f"{BASE_URL}/api/admin/manual-overrides",
            json=override_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert override_response.status_code == 200
        request_id = override_response.json().get("request_id")
        assert request_id is not None
        
        # Now approve as super_admin
        approve_response = requests.post(
            f"{BASE_URL}/api/admin/override-approval-requests/{request_id}/approve",
            json={"reason_note": "Approved for testing purposes"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert approve_response.status_code == 200, f"Approve failed: {approve_response.status_code} - {approve_response.text}"
        data = approve_response.json()
        
        assert data.get("status") == "approved_applied", f"Expected 'approved_applied', got: {data.get('status')}"
        assert data.get("override") is not None, "Override object should be present after approval"
        print(f"PASS: Super admin approved request {request_id}, status=approved_applied")

    def test_super_admin_can_reject_request(self, super_admin_token, admin_token, admin_user_id):
        """Test super_admin can reject a pending request"""
        # First create a pending request as admin
        sim_payload = {
            "user_id": admin_user_id,
            "intent_payload": {
                "symbol": "SOLUSDT",
                "side": "buy",
                "notional": 30,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 5,
            },
            "apply_override": False,
        }
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            json=sim_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert sim_response.status_code == 200
        simulation_id = sim_response.json().get("simulation_id")
        
        override_payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": admin_user_id,
            "action_type": "test_reject_flow",
            "reason": "Testing reject flow by super_admin",
            "simulation_id": simulation_id,
            "ttl_minutes": 60,
            "confirmation_id": f"confirm_reject_{int(time.time())}",
            "previous_state": {},
            "next_state": {},
            "impact_preview": {},
            "payload": {"test": True},
        }
        override_response = requests.post(
            f"{BASE_URL}/api/admin/manual-overrides",
            json=override_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert override_response.status_code == 200
        request_id = override_response.json().get("request_id")
        assert request_id is not None
        
        # Now reject as super_admin
        reject_response = requests.post(
            f"{BASE_URL}/api/admin/override-approval-requests/{request_id}/reject",
            json={"reason_note": "Rejected for testing purposes"},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert reject_response.status_code == 200, f"Reject failed: {reject_response.status_code} - {reject_response.text}"
        data = reject_response.json()
        
        assert data.get("status") == "rejected", f"Expected 'rejected', got: {data.get('status')}"
        assert data.get("override") is None, "Override object should be None after rejection"
        print(f"PASS: Super admin rejected request {request_id}, status=rejected")

    def test_non_super_admin_cannot_approve(self, admin_token):
        """Test that non-super_admin cannot approve requests"""
        # Try to approve a non-existent request as admin (should fail with 403)
        response = requests.post(
            f"{BASE_URL}/api/admin/override-approval-requests/fake_request_id/approve",
            json={"reason_note": "Should fail"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Should get 403 Forbidden, not 404 Not Found
        assert response.status_code == 403, f"Expected 403 for non-super_admin, got: {response.status_code}"
        print(f"PASS: Non-super_admin correctly blocked from approving (403)")

    def test_non_super_admin_cannot_reject(self, admin_token):
        """Test that non-super_admin cannot reject requests"""
        response = requests.post(
            f"{BASE_URL}/api/admin/override-approval-requests/fake_request_id/reject",
            json={"reason_note": "Should fail"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 403, f"Expected 403 for non-super_admin, got: {response.status_code}"
        print(f"PASS: Non-super_admin correctly blocked from rejecting (403)")


class TestBatchSimulationSelectedSymbols:
    """Tests for batch simulation with selected symbol list"""

    @pytest.fixture(scope="class")
    def super_admin_token(self):
        """Get super_admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Super admin login failed: {response.status_code}")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def super_admin_user_id(self, super_admin_token):
        """Get super_admin user ID"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        if response.status_code != 200:
            pytest.skip("Could not get super_admin user info")
        return response.json().get("id")

    def test_batch_simulation_with_multiple_symbols(self, super_admin_token, super_admin_user_id):
        """Test batch simulation processes multiple symbols correctly"""
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        payload = {
            "user_id": super_admin_user_id,
            "symbols": symbols,
            "intent_payload": {
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/batch",
            json=payload,
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Batch failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert data.get("total_symbols") >= 1, "Should have at least 1 symbol processed"
        items = data.get("items", [])
        
        # Verify symbols in response
        returned_symbols = [item.get("symbol") for item in items]
        for symbol in returned_symbols:
            assert symbol in symbols, f"Unexpected symbol in response: {symbol}"
        
        print(f"PASS: Batch simulation processed {len(items)} symbols: {returned_symbols}")

    def test_batch_simulation_empty_symbols_fails(self, super_admin_token, super_admin_user_id):
        """Test batch simulation with empty symbols list fails"""
        payload = {
            "user_id": super_admin_user_id,
            "symbols": [],
            "intent_payload": {
                "side": "buy",
                "notional": 100,
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/batch",
            json=payload,
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 400, f"Expected 400 for empty symbols, got: {response.status_code}"
        print(f"PASS: Empty symbols list correctly rejected with 400")

    def test_batch_simulation_persists_to_history(self, super_admin_token, super_admin_user_id):
        """Test batch simulation runs are persisted to history"""
        # Run batch simulation
        payload = {
            "user_id": super_admin_user_id,
            "symbols": ["BTCUSDT"],
            "intent_payload": {
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
            },
        }
        batch_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/batch",
            json=payload,
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert batch_response.status_code == 200
        
        # Check history
        history_response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            params={"limit": 10},
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert history_response.status_code == 200
        history_data = history_response.json()
        
        items = history_data.get("items", [])
        batch_items = [item for item in items if item.get("request_mode") == "batch"]
        
        assert len(batch_items) > 0, "Batch simulation should be persisted to history"
        print(f"PASS: Batch simulation persisted to history, found {len(batch_items)} batch records")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
