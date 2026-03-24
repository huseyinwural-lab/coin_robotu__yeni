"""
Iteration 78 - P0 Governance, Simulation Output, Override System, Approval Queue, Escalation Center Testing

Features to test:
1. Simulation output response fields (projected_pnl, projected_drawdown, exposure_change, var_change, liquidity_impact, decision_summary)
2. Before/after panel delta color indicators (risk_delta, exposure_change, var_change)
3. Override active table: revoke, expiry countdown, impact preview, linked approval visibility
4. Decision queue hardening: assigned_to, ack_by/ack_at, execute in approved, bulk approve/reject max25, SLA breach highlight
5. Escalation complete: assign-owner, ack ownership change, resolve close, reason required, linked request visibility
6. Unified Governance Board UI tabs queue/escalation and role rules
"""

import os
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://strategy-version-gov.preview.emergentagent.com").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


class TestAuthHelpers:
    """Helper methods for authentication"""
    
    @staticmethod
    def get_token(email: str, password: str) -> str:
        """Get auth token for a user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token", "")
        return ""
    
    @staticmethod
    def get_headers(token: str) -> dict:
        """Get headers with auth token"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin token"""
    token = TestAuthHelpers.get_token(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    if not token:
        pytest.skip("Could not authenticate as super_admin")
    return token


@pytest.fixture(scope="module")
def admin_token():
    """Get admin token"""
    token = TestAuthHelpers.get_token(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        pytest.skip("Could not authenticate as admin")
    return token


@pytest.fixture(scope="module")
def ops_token():
    """Get ops token"""
    token = TestAuthHelpers.get_token(OPS_EMAIL, OPS_PASSWORD)
    if not token:
        pytest.skip("Could not authenticate as ops")
    return token


@pytest.fixture(scope="module")
def test_user_id(super_admin_token):
    """Get a valid user_id for simulation tests"""
    headers = TestAuthHelpers.get_headers(super_admin_token)
    response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
    if response.status_code == 200:
        users = response.json()
        if users and len(users) > 0:
            return users[0].get("id", "")
    pytest.skip("Could not get test user_id")


# ============================================================================
# SECTION 1: Simulation Output Response Fields
# ============================================================================

class TestSimulationOutputFields:
    """Test simulation output response fields and visibility"""
    
    def test_simulation_returns_projected_pnl(self, super_admin_token, test_user_id):
        """Verify simulation returns projected_pnl field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "projected_pnl" in data, "projected_pnl field missing from simulation response"
        assert isinstance(data["projected_pnl"], (int, float)), "projected_pnl should be numeric"
    
    def test_simulation_returns_projected_drawdown(self, super_admin_token, test_user_id):
        """Verify simulation returns projected_drawdown field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "ETHUSDT",
                "side": "buy",
                "notional": 200,
                "strategy_binding": "trend_follow_v1",
                "volatility_pct": 5,
                "position_size_value": 200
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "projected_drawdown" in data, "projected_drawdown field missing"
        assert isinstance(data["projected_drawdown"], (int, float)), "projected_drawdown should be numeric"
    
    def test_simulation_returns_exposure_change(self, super_admin_token, test_user_id):
        """Verify simulation returns exposure_change field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "sell",
                "notional": 150,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 4,
                "position_size_value": 150
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "exposure_change" in data, "exposure_change field missing"
        assert isinstance(data["exposure_change"], (int, float)), "exposure_change should be numeric"
    
    def test_simulation_returns_var_change(self, super_admin_token, test_user_id):
        """Verify simulation returns var_change field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "var_change" in data, "var_change field missing"
        assert isinstance(data["var_change"], (int, float)), "var_change should be numeric"
    
    def test_simulation_returns_liquidity_impact(self, super_admin_token, test_user_id):
        """Verify simulation returns liquidity_impact field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "liquidity_impact" in data, "liquidity_impact field missing"
        assert isinstance(data["liquidity_impact"], (int, float)), "liquidity_impact should be numeric"
    
    def test_simulation_returns_decision_summary(self, super_admin_token, test_user_id):
        """Verify simulation returns decision_summary field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "decision_summary" in data, "decision_summary field missing"
        assert isinstance(data["decision_summary"], dict), "decision_summary should be a dict"


# ============================================================================
# SECTION 2: Before/After Panel Delta Fields
# ============================================================================

class TestBeforeAfterDeltaFields:
    """Test before/after state and delta fields for UI color indicators"""
    
    def test_simulation_returns_before_state(self, super_admin_token, test_user_id):
        """Verify simulation returns before_state object"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "before_state" in data, "before_state field missing"
        before = data["before_state"]
        assert "risk_score" in before, "before_state.risk_score missing"
        assert "gate_decision" in before, "before_state.gate_decision missing"
        assert "exposure" in before, "before_state.exposure missing"
    
    def test_simulation_returns_after_state(self, super_admin_token, test_user_id):
        """Verify simulation returns after_state object"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "after_state" in data, "after_state field missing"
        after = data["after_state"]
        assert "risk_score" in after, "after_state.risk_score missing"
        assert "gate_decision" in after, "after_state.gate_decision missing"
        assert "exposure" in after, "after_state.exposure missing"
    
    def test_simulation_returns_risk_delta(self, super_admin_token, test_user_id):
        """Verify simulation returns risk_delta for color indicator"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "risk_delta" in data, "risk_delta field missing"
        assert isinstance(data["risk_delta"], (int, float)), "risk_delta should be numeric"
    
    def test_simulation_returns_decision_delta(self, super_admin_token, test_user_id):
        """Verify simulation returns decision_delta for color indicator"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "decision_delta" in data, "decision_delta field missing"
        assert isinstance(data["decision_delta"], str), "decision_delta should be string"


# ============================================================================
# SECTION 3: Active Overrides Table Features
# ============================================================================

class TestActiveOverridesTable:
    """Test active overrides table: revoke, expiry countdown, impact preview, linked approval"""
    
    def test_active_overrides_endpoint_returns_list(self, super_admin_token):
        """Verify active overrides endpoint returns list"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/active-overrides", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "active-overrides should return a list"
    
    def test_active_override_has_expiry_countdown_seconds(self, super_admin_token):
        """Verify active override items have expiry_countdown_seconds field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/active-overrides", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # If there are active overrides, check the field
        if len(data) > 0:
            item = data[0]
            assert "expiry_countdown_seconds" in item, "expiry_countdown_seconds field missing"
    
    def test_active_override_has_impact_preview(self, super_admin_token):
        """Verify active override items have impact_preview field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/active-overrides", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            item = data[0]
            assert "impact_preview" in item, "impact_preview field missing"
            assert isinstance(item["impact_preview"], dict), "impact_preview should be dict"
    
    def test_active_override_has_linked_approval_request_id(self, super_admin_token):
        """Verify active override items have linked_approval_request_id field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/active-overrides", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            item = data[0]
            assert "linked_approval_request_id" in item, "linked_approval_request_id field missing"
    
    def test_revoke_override_requires_reason_min_12_chars(self, super_admin_token):
        """Verify revoke override requires reason with minimum 12 characters"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        # Try to revoke with short reason
        response = requests.post(
            f"{BASE_URL}/api/admin/manual-overrides/fake_override_id/revoke",
            json={"reason": "short"},
            headers=headers
        )
        # Should fail with 400 or 422 for short reason (validation error)
        assert response.status_code in [400, 422], f"Expected 400/422 for short reason, got {response.status_code}"
    
    def test_ops_cannot_revoke_override(self, ops_token):
        """Verify ops role cannot revoke overrides"""
        headers = TestAuthHelpers.get_headers(ops_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/manual-overrides/fake_override_id/revoke",
            json={"reason": "ops_trying_to_revoke_override"},
            headers=headers
        )
        assert response.status_code == 403, f"Expected 403 for ops role, got {response.status_code}"


# ============================================================================
# SECTION 4: Decision Queue Hardening
# ============================================================================

class TestDecisionQueueHardening:
    """Test decision queue: assigned_to, ack_by/ack_at, execute, bulk actions, SLA breach"""
    
    def test_decision_requests_returns_list(self, super_admin_token):
        """Verify decision requests endpoint returns list"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/decision-requests", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data, "decision-requests should return items array"
        assert isinstance(data["items"], list), "items should be a list"
    
    def test_decision_request_has_assigned_to_field(self, super_admin_token):
        """Verify decision request items have assigned_to field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/decision-requests", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if len(data.get("items", [])) > 0:
            item = data["items"][0]
            assert "assigned_to" in item, "assigned_to field missing"
    
    def test_decision_request_has_ack_by_field(self, super_admin_token):
        """Verify decision request items have ack_by field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/decision-requests", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if len(data.get("items", [])) > 0:
            item = data["items"][0]
            assert "ack_by" in item, "ack_by field missing"
    
    def test_decision_request_has_ack_at_field(self, super_admin_token):
        """Verify decision request items have ack_at field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/decision-requests", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if len(data.get("items", [])) > 0:
            item = data["items"][0]
            assert "ack_at" in item, "ack_at field missing"
    
    def test_decision_request_has_sla_countdown_seconds(self, super_admin_token):
        """Verify decision request items have sla_countdown_seconds field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/decision-requests", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if len(data.get("items", [])) > 0:
            item = data["items"][0]
            assert "sla_countdown_seconds" in item, "sla_countdown_seconds field missing"
    
    def test_decision_request_has_sla_state(self, super_admin_token):
        """Verify decision request items have sla_state field (breach/warning/healthy/n/a)"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/decision-requests", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if len(data.get("items", [])) > 0:
            item = data["items"][0]
            assert "sla_state" in item, "sla_state field missing"
            assert item["sla_state"] in ["breach", "warning", "healthy", "n/a"], f"Invalid sla_state: {item['sla_state']}"
    
    def test_bulk_action_max_25_limit(self, super_admin_token):
        """Verify bulk action enforces max 25 limit"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        # Create 26 fake request IDs
        fake_ids = [f"req_fake_{i}" for i in range(26)]
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/bulk-action",
            json={
                "action": "approve",
                "request_ids": fake_ids,
                "reason_note": "bulk_test_reason_note"
            },
            headers=headers
        )
        assert response.status_code == 400, f"Expected 400 for >25 items, got {response.status_code}"
    
    def test_bulk_action_requires_super_admin(self, admin_token):
        """Verify bulk action requires super_admin role"""
        headers = TestAuthHelpers.get_headers(admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/bulk-action",
            json={
                "action": "approve",
                "request_ids": ["req_fake_1"],
                "reason_note": "admin_trying_bulk_action"
            },
            headers=headers
        )
        assert response.status_code == 403, f"Expected 403 for admin role, got {response.status_code}"
    
    def test_execute_requires_approved_status(self, super_admin_token):
        """Verify execute requires request to be in approved status"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        # Try to execute a non-existent request
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/fake_request_id/execute",
            json={
                "reason_note": "execute_test_reason",
                "preview_token": "fake_preview_token"
            },
            headers=headers
        )
        # Should fail with 404 (not found) or 400 (not approved)
        assert response.status_code in [400, 404], f"Expected 400/404, got {response.status_code}"
    
    def test_assign_owner_endpoint_exists(self, super_admin_token):
        """Verify assign-owner endpoint exists"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/fake_request_id/assign-owner",
            json={"assigned_to": "ops"},
            headers=headers
        )
        # Should fail with 404 (not found) not 405 (method not allowed)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_ack_endpoint_exists(self, super_admin_token):
        """Verify ack endpoint exists"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/fake_request_id/ack",
            json={"reason_note": "ack_test_reason_note"},
            headers=headers
        )
        # Should fail with 404 (not found) not 405 (method not allowed)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


# ============================================================================
# SECTION 5: Escalation Center Complete
# ============================================================================

class TestEscalationCenterComplete:
    """Test escalation center: assign-owner, ack, resolve, reason required, linked request"""
    
    def test_escalation_center_returns_structure(self, super_admin_token):
        """Verify escalation center returns correct structure"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/escalation-center", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "active_breaches" in data, "active_breaches field missing"
        assert "acknowledged" in data, "acknowledged field missing"
        assert "resolved" in data, "resolved field missing"
        assert isinstance(data["active_breaches"], list), "active_breaches should be list"
        assert isinstance(data["acknowledged"], list), "acknowledged should be list"
        assert isinstance(data["resolved"], list), "resolved should be list"
    
    def test_escalation_item_has_linked_request_id(self, super_admin_token):
        """Verify escalation items have linked_request_id field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/escalation-center", headers=headers)
        assert response.status_code == 200
        data = response.json()
        all_items = data.get("active_breaches", []) + data.get("acknowledged", []) + data.get("resolved", [])
        if len(all_items) > 0:
            item = all_items[0]
            assert "linked_request_id" in item, "linked_request_id field missing"
    
    def test_escalation_item_has_current_owner(self, super_admin_token):
        """Verify escalation items have current_owner field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/escalation-center", headers=headers)
        assert response.status_code == 200
        data = response.json()
        all_items = data.get("active_breaches", []) + data.get("acknowledged", []) + data.get("resolved", [])
        if len(all_items) > 0:
            item = all_items[0]
            assert "current_owner" in item, "current_owner field missing"
    
    def test_escalation_item_has_breach_age_seconds(self, super_admin_token):
        """Verify escalation items have breach_age_seconds field"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.get(f"{BASE_URL}/api/admin/escalation-center", headers=headers)
        assert response.status_code == 200
        data = response.json()
        all_items = data.get("active_breaches", []) + data.get("acknowledged", []) + data.get("resolved", [])
        if len(all_items) > 0:
            item = all_items[0]
            assert "breach_age_seconds" in item, "breach_age_seconds field missing"
    
    def test_escalation_assign_owner_endpoint_exists(self, super_admin_token):
        """Verify escalation assign-owner endpoint exists"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/fake_escalation_id/assign-owner",
            json={"current_owner": "ops", "escalation_reason": "assign_owner_test_reason"},
            headers=headers
        )
        # Should fail with 404 (not found) not 405 (method not allowed)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_escalation_ack_endpoint_exists(self, super_admin_token):
        """Verify escalation ack endpoint exists"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/fake_escalation_id/ack",
            json={"current_owner": "ops", "escalation_reason": "ack_test_reason_note"},
            headers=headers
        )
        # Should fail with 404 (not found) not 405 (method not allowed)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_escalation_resolve_endpoint_exists(self, super_admin_token):
        """Verify escalation resolve endpoint exists"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/fake_escalation_id/resolve",
            json={"escalation_reason": "resolve_test_reason_note"},
            headers=headers
        )
        # Should fail with 404 (not found) not 405 (method not allowed)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_escalation_resolve_requires_super_admin(self, admin_token):
        """Verify escalation resolve requires super_admin role"""
        headers = TestAuthHelpers.get_headers(admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/fake_escalation_id/resolve",
            json={"escalation_reason": "admin_trying_resolve"},
            headers=headers
        )
        # Should fail with 403 (forbidden) for admin role
        assert response.status_code == 403, f"Expected 403 for admin role, got {response.status_code}"
    
    def test_escalation_ack_requires_admin_or_super_admin(self, ops_token):
        """Verify escalation ack requires admin or super_admin role"""
        headers = TestAuthHelpers.get_headers(ops_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/fake_escalation_id/ack",
            json={"current_owner": "ops", "escalation_reason": "ops_trying_ack"},
            headers=headers
        )
        # Should fail with 403 (forbidden) for ops role
        assert response.status_code == 403, f"Expected 403 for ops role, got {response.status_code}"


# ============================================================================
# SECTION 6: Role Rules Verification
# ============================================================================

class TestRoleRulesVerification:
    """Test role-based access control for governance features"""
    
    def test_super_admin_can_approve_decision_request(self, super_admin_token):
        """Verify super_admin can access approve endpoint"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/fake_request_id/approve",
            json={"reason_note": "super_admin_approve_test"},
            headers=headers
        )
        # Should fail with 404 (not found) not 403 (forbidden)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_admin_cannot_approve_decision_request(self, admin_token):
        """Verify admin cannot approve decision requests"""
        headers = TestAuthHelpers.get_headers(admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/fake_request_id/approve",
            json={"reason_note": "admin_trying_approve"},
            headers=headers
        )
        # Should fail with 403 (forbidden) for admin role
        assert response.status_code == 403, f"Expected 403 for admin role, got {response.status_code}"
    
    def test_super_admin_can_reject_decision_request(self, super_admin_token):
        """Verify super_admin can access reject endpoint"""
        headers = TestAuthHelpers.get_headers(super_admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/fake_request_id/reject",
            json={"reason_note": "super_admin_reject_test"},
            headers=headers
        )
        # Should fail with 404 (not found) not 403 (forbidden)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_admin_cannot_reject_decision_request(self, admin_token):
        """Verify admin cannot reject decision requests"""
        headers = TestAuthHelpers.get_headers(admin_token)
        response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/fake_request_id/reject",
            json={"reason_note": "admin_trying_reject"},
            headers=headers
        )
        # Should fail with 403 (forbidden) for admin role
        assert response.status_code == 403, f"Expected 403 for admin role, got {response.status_code}"
    
    def test_ops_cannot_apply_override(self, ops_token, test_user_id):
        """Verify ops role cannot apply overrides"""
        headers = TestAuthHelpers.get_headers(ops_token)
        payload = {
            "scope": "strategy_intelligence",
            "target_type": "user",
            "target_id": test_user_id,
            "action_type": "test_override",
            "reason": "ops_trying_to_apply_override",
            "simulation_id": "fake_simulation_id",
            "ttl_minutes": 60
        }
        response = requests.post(f"{BASE_URL}/api/admin/manual-overrides", json=payload, headers=headers)
        assert response.status_code == 403, f"Expected 403 for ops role, got {response.status_code}"


# ============================================================================
# SECTION 7: End-to-End Workflow Test
# ============================================================================

class TestEndToEndWorkflow:
    """Test complete workflow: simulation -> decision request -> approve -> execute"""
    
    def test_complete_simulation_workflow(self, super_admin_token, admin_token, test_user_id):
        """Test complete simulation workflow"""
        # Step 1: Run simulation as super_admin
        headers = TestAuthHelpers.get_headers(super_admin_token)
        sim_payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3,
                "position_size_value": 100
            },
            "apply_override": False
        }
        sim_response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=sim_payload, headers=headers)
        assert sim_response.status_code == 200, f"Simulation failed: {sim_response.text}"
        sim_data = sim_response.json()
        simulation_id = sim_data.get("simulation_id")
        assert simulation_id, "simulation_id missing from response"
        
        # Verify all required fields are present
        required_fields = [
            "projected_pnl", "projected_drawdown", "exposure_change", 
            "var_change", "liquidity_impact", "decision_summary",
            "before_state", "after_state", "risk_delta", "decision_delta"
        ]
        for field in required_fields:
            assert field in sim_data, f"Required field {field} missing from simulation response"
        
        print(f"✓ Simulation completed with ID: {simulation_id}")
        print(f"  - projected_pnl: {sim_data.get('projected_pnl')}")
        print(f"  - projected_drawdown: {sim_data.get('projected_drawdown')}")
        print(f"  - exposure_change: {sim_data.get('exposure_change')}")
        print(f"  - var_change: {sim_data.get('var_change')}")
        print(f"  - liquidity_impact: {sim_data.get('liquidity_impact')}")
        print(f"  - risk_delta: {sim_data.get('risk_delta')}")
        print(f"  - decision_delta: {sim_data.get('decision_delta')}")
    
    def test_decision_request_creation_by_admin(self, admin_token, super_admin_token, test_user_id):
        """Test decision request creation by admin role"""
        # First run simulation as super_admin to get simulation_id
        headers_super = TestAuthHelpers.get_headers(super_admin_token)
        sim_payload = {
            "user_id": test_user_id,
            "intent_payload": {
                "symbol": "ETHUSDT",
                "side": "buy",
                "notional": 200,
                "strategy_binding": "trend_follow_v1",
                "volatility_pct": 5,
                "position_size_value": 200
            },
            "apply_override": False
        }
        sim_response = requests.post(f"{BASE_URL}/api/admin/risk-simulation", json=sim_payload, headers=headers_super)
        assert sim_response.status_code == 200
        simulation_id = sim_response.json().get("simulation_id")
        
        # Now create decision request as admin
        headers_admin = TestAuthHelpers.get_headers(admin_token)
        decision_payload = {
            "target_type": "strategy",
            "target_id": "trend_follow_v1",
            "reason_note": "test_conflict_resolution_request",
            "simulation_run_id": simulation_id
        }
        decision_response = requests.post(
            f"{BASE_URL}/api/admin/decision-requests/conflict-resolve",
            json=decision_payload,
            headers=headers_admin
        )
        assert decision_response.status_code == 200, f"Decision request creation failed: {decision_response.text}"
        decision_data = decision_response.json()
        assert "request_id" in decision_data, "request_id missing from decision response"
        
        print(f"✓ Decision request created: {decision_data.get('request_id')}")
        print(f"  - status: {decision_data.get('status')}")
        print(f"  - assigned_to: {decision_data.get('assigned_to')}")
        print(f"  - sla_state: {decision_data.get('sla_state')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
