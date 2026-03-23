"""
Faz-2 Strategy Control + Governance System Tests
=================================================
Tests for:
- GET /api/admin/futures/strategy-control/overview (Faz-2 scope + rollout/bulk metadata)
- GET /api/admin/futures/strategy/{id}/rollout-precheck
- POST /api/admin/futures/strategy/{id}/promote-shadow (confirm required + precheck fail behavior)
- POST /api/admin/futures/strategy/{id}/rollout (10/25/50/100 constraint + auto rollback)
- POST /api/admin/futures/strategy/{id}/rollback (single-step last action rollback)
- POST /api/admin/futures/strategy/bulk-action (pause/resume/throttle only; disable/decommission rejected)
- Response contract: {status, trace_id, message, state_snapshot}
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://execution-safety-hub.preview.emergentagent.com"

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def ops_token():
    """Get ops user auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Ops login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def admin_headers(super_admin_token):
    """Headers with super admin auth"""
    return {
        "Authorization": f"Bearer {super_admin_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def ops_headers(ops_token):
    """Headers with ops user auth"""
    return {
        "Authorization": f"Bearer {ops_token}",
        "Content-Type": "application/json"
    }


class TestOverviewEndpointFaz2:
    """Test GET /api/admin/futures/strategy-control/overview for Faz-2 scope"""

    def test_overview_returns_phase_scope(self, admin_headers):
        """Overview should return phase_scope = phase_2_rollout_bulk_rollback"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("status") == "ok", "Expected status=ok"
        assert data.get("phase_scope") == "phase_2_rollout_bulk_rollback", f"Expected phase_2_rollout_bulk_rollback, got {data.get('phase_scope')}"
        print(f"PASS: phase_scope = {data.get('phase_scope')}")

    def test_overview_returns_bulk_capabilities(self, admin_headers):
        """Overview should return bulk_capabilities = [pause, resume, throttle]"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        bulk_caps = data.get("bulk_capabilities", [])
        assert "pause" in bulk_caps, "bulk_capabilities should include 'pause'"
        assert "resume" in bulk_caps, "bulk_capabilities should include 'resume'"
        assert "throttle" in bulk_caps, "bulk_capabilities should include 'throttle'"
        assert "disable" not in bulk_caps, "bulk_capabilities should NOT include 'disable'"
        assert "decommission" not in bulk_caps, "bulk_capabilities should NOT include 'decommission'"
        print(f"PASS: bulk_capabilities = {bulk_caps}")

    def test_overview_returns_rollout_policy(self, admin_headers):
        """Overview should return rollout_policy with canary_steps and auto_rollback_thresholds"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        rollout_policy = data.get("rollout_policy", {})
        assert "canary_steps" in rollout_policy, "rollout_policy should have canary_steps"
        assert rollout_policy["canary_steps"] == [10, 25, 50, 100], f"Expected [10,25,50,100], got {rollout_policy['canary_steps']}"
        
        thresholds = rollout_policy.get("auto_rollback_thresholds", {})
        assert thresholds.get("health_score_min") == 50.0, f"Expected health_score_min=50.0, got {thresholds.get('health_score_min')}"
        assert thresholds.get("error_rate_max_pct") == 3.0, f"Expected error_rate_max_pct=3.0, got {thresholds.get('error_rate_max_pct')}"
        print(f"PASS: rollout_policy = {rollout_policy}")

    def test_overview_strategies_have_rollout_fields(self, admin_headers):
        """Strategies should have rollout_mode, rollout_percentage, auto_rollback_enabled"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        strategies = data.get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available to test rollout fields")
        
        first_strategy = strategies[0]
        assert "rollout_mode" in first_strategy, "Strategy should have rollout_mode"
        assert "rollout_percentage" in first_strategy, "Strategy should have rollout_percentage"
        assert "auto_rollback_enabled" in first_strategy, "Strategy should have auto_rollback_enabled"
        assert "auto_rollback_thresholds" in first_strategy, "Strategy should have auto_rollback_thresholds"
        print(f"PASS: Strategy {first_strategy.get('strategy_id')} has rollout fields: mode={first_strategy.get('rollout_mode')}, pct={first_strategy.get('rollout_percentage')}")


class TestRolloutPrecheckEndpoint:
    """Test GET /api/admin/futures/strategy/{id}/rollout-precheck"""

    def test_rollout_precheck_returns_checks(self, admin_headers):
        """Rollout precheck should return health, recent_error, drift, checklist checks"""
        # First get a strategy ID
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        assert overview_resp.status_code == 200
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available for precheck test")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollout-precheck",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("status") == "ok", "Expected status=ok"
        assert data.get("strategy_id") == strategy_id, f"Expected strategy_id={strategy_id}"
        
        precheck = data.get("precheck", {})
        assert "status" in precheck, "precheck should have status (pass/fail)"
        assert "checks" in precheck, "precheck should have checks"
        
        checks = precheck.get("checks", {})
        assert "health" in checks, "checks should have health"
        assert "recent_error" in checks, "checks should have recent_error"
        assert "drift" in checks, "checks should have drift"
        assert "checklist" in checks, "checks should have checklist"
        
        # Verify health check structure
        health_check = checks.get("health", {})
        assert "ok" in health_check, "health check should have ok field"
        assert "current" in health_check, "health check should have current field"
        assert "required_min" in health_check, "health check should have required_min field"
        
        print(f"PASS: Precheck for {strategy_id}: status={precheck.get('status')}, checks={list(checks.keys())}")


class TestPromoteShadowEndpoint:
    """Test POST /api/admin/futures/strategy/{id}/promote-shadow"""

    def test_promote_shadow_requires_confirm_phrase(self, admin_headers):
        """Promote shadow should reject without correct confirm phrase"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # Try without confirm phrase
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/promote-shadow",
            headers=admin_headers,
            json={
                "reason": "Test promote shadow",
                "confirm_phrase": "WRONG PHRASE",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Should be rejected due to wrong confirm phrase
        assert data.get("status") == "rejected", f"Expected status=rejected, got {data.get('status')}"
        assert "PROMOTE SHADOW" in data.get("message", ""), f"Message should mention required phrase: {data.get('message')}"
        assert "trace_id" in data, "Response should have trace_id"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        print(f"PASS: Promote shadow rejected without correct confirm phrase: {data.get('message')}")

    def test_promote_shadow_with_correct_confirm(self, admin_headers):
        """Promote shadow with correct confirm phrase (may fail precheck - expected)"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        # Find a SHADOW strategy if available
        shadow_strategies = [s for s in strategies if s.get("shadow_live_state") == "SHADOW"]
        strategy_id = shadow_strategies[0]["strategy_id"] if shadow_strategies else strategies[0]["strategy_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/promote-shadow",
            headers=admin_headers,
            json={
                "reason": "Test promote shadow with correct confirm",
                "confirm_phrase": "PROMOTE SHADOW",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        # Response should have contract fields
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        # May be rejected due to precheck fail or non-SHADOW strategy - both are valid
        print(f"PASS: Promote shadow response: status={data.get('status')}, message={data.get('message')}")


class TestRolloutEndpoint:
    """Test POST /api/admin/futures/strategy/{id}/rollout"""

    def test_rollout_requires_confirm_phrase(self, admin_headers):
        """Rollout should reject without correct confirm phrase"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollout",
            headers=admin_headers,
            json={
                "reason": "Test rollout",
                "confirm_phrase": "WRONG",
                "rollout_percentage": 10,
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected, got {data.get('status')}"
        assert "APPLY ROLLOUT" in data.get("message", ""), f"Message should mention required phrase"
        print(f"PASS: Rollout rejected without correct confirm phrase")

    def test_rollout_rejects_invalid_percentage(self, admin_headers):
        """Rollout should reject percentages not in [10, 25, 50, 100]"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # Try with invalid percentage (15%)
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollout",
            headers=admin_headers,
            json={
                "reason": "Test invalid percentage",
                "confirm_phrase": "APPLY ROLLOUT",
                "rollout_percentage": 15,
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected for invalid percentage, got {data.get('status')}"
        assert "[10, 25, 50, 100]" in data.get("message", ""), f"Message should mention valid percentages"
        print(f"PASS: Rollout rejected invalid percentage 15%")

    def test_rollout_with_valid_percentage(self, admin_headers):
        """Rollout with valid percentage (may trigger auto-rollback if health<50 or error>3%)"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollout",
            headers=admin_headers,
            json={
                "reason": "Test valid rollout percentage",
                "confirm_phrase": "APPLY ROLLOUT",
                "rollout_percentage": 10,
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        # Response should have contract fields
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        # Check for auto_rollback info in response
        if "auto_rollback" in data:
            auto_rollback = data["auto_rollback"]
            assert "triggered" in auto_rollback, "auto_rollback should have triggered field"
            assert "reason" in auto_rollback, "auto_rollback should have reason field"
            assert "thresholds" in auto_rollback, "auto_rollback should have thresholds field"
            assert "previous_state" in auto_rollback, "auto_rollback should have previous_state field"
            print(f"PASS: Rollout response has auto_rollback info: triggered={auto_rollback.get('triggered')}, reason={auto_rollback.get('reason')}")
        else:
            print(f"PASS: Rollout response: status={data.get('status')}, message={data.get('message')}")


class TestRollbackEndpoint:
    """Test POST /api/admin/futures/strategy/{id}/rollback"""

    def test_rollback_requires_confirm_phrase(self, admin_headers):
        """Rollback should reject without correct confirm phrase"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback",
            headers=admin_headers,
            json={
                "reason": "Test rollback",
                "confirm_phrase": "WRONG",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected, got {data.get('status')}"
        assert "ROLLBACK LAST ACTION" in data.get("message", ""), f"Message should mention required phrase"
        print(f"PASS: Rollback rejected without correct confirm phrase")

    def test_rollback_with_correct_confirm(self, admin_headers):
        """Rollback with correct confirm phrase (may fail if no previous action)"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/rollback",
            headers=admin_headers,
            json={
                "reason": "Test rollback with correct confirm",
                "confirm_phrase": "ROLLBACK LAST ACTION",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        # Response should have contract fields
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        # May be rejected if no previous action exists
        print(f"PASS: Rollback response: status={data.get('status')}, message={data.get('message')}")


class TestBulkActionEndpoint:
    """Test POST /api/admin/futures/strategy/bulk-action"""

    def test_bulk_action_rejects_disable(self, admin_headers):
        """Bulk action should reject disable action"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_ids = [s["strategy_id"] for s in strategies[:2]]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=admin_headers,
            json={
                "reason": "Test bulk disable",
                "confirm_phrase": "BULK DISABLE",
                "strategy_ids": strategy_ids,
                "action": "disable",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected for bulk disable, got {data.get('status')}"
        assert "pause/resume/throttle" in data.get("message", "").lower(), f"Message should mention allowed actions"
        print(f"PASS: Bulk disable rejected: {data.get('message')}")

    def test_bulk_action_rejects_decommission(self, admin_headers):
        """Bulk action should reject decommission action"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_ids = [s["strategy_id"] for s in strategies[:2]]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=admin_headers,
            json={
                "reason": "Test bulk decommission",
                "confirm_phrase": "BULK DECOMMISSION",
                "strategy_ids": strategy_ids,
                "action": "decommission",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected for bulk decommission, got {data.get('status')}"
        print(f"PASS: Bulk decommission rejected: {data.get('message')}")

    def test_bulk_pause_requires_confirm(self, admin_headers):
        """Bulk pause should require correct confirm phrase"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_ids = [s["strategy_id"] for s in strategies[:2]]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=admin_headers,
            json={
                "reason": "Test bulk pause wrong confirm",
                "confirm_phrase": "WRONG",
                "strategy_ids": strategy_ids,
                "action": "pause",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected", f"Expected rejected for wrong confirm, got {data.get('status')}"
        assert "BULK PAUSE" in data.get("message", ""), f"Message should mention required phrase"
        print(f"PASS: Bulk pause rejected without correct confirm phrase")

    def test_bulk_pause_with_correct_confirm(self, admin_headers):
        """Bulk pause with correct confirm phrase should work"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_ids = [s["strategy_id"] for s in strategies[:1]]  # Just one to minimize impact
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=admin_headers,
            json={
                "reason": "Test bulk pause correct confirm",
                "confirm_phrase": "BULK PAUSE",
                "strategy_ids": strategy_ids,
                "action": "pause",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        # Response should have contract fields
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        assert "message" in data, "Response should have message"
        assert "state_snapshot" in data, "Response should have state_snapshot"
        
        # Should have results array
        if "results" in data:
            assert isinstance(data["results"], list), "results should be a list"
            print(f"PASS: Bulk pause response: status={data.get('status')}, results_count={len(data.get('results', []))}")
        else:
            print(f"PASS: Bulk pause response: status={data.get('status')}, message={data.get('message')}")

    def test_bulk_resume_with_correct_confirm(self, admin_headers):
        """Bulk resume with correct confirm phrase should work"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_ids = [s["strategy_id"] for s in strategies[:1]]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=admin_headers,
            json={
                "reason": "Test bulk resume",
                "confirm_phrase": "BULK RESUME",
                "strategy_ids": strategy_ids,
                "action": "resume",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        print(f"PASS: Bulk resume response: status={data.get('status')}")

    def test_bulk_throttle_with_correct_confirm(self, admin_headers):
        """Bulk throttle with correct confirm phrase should work"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_ids = [s["strategy_id"] for s in strategies[:1]]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=admin_headers,
            json={
                "reason": "Test bulk throttle",
                "confirm_phrase": "BULK THROTTLE",
                "strategy_ids": strategy_ids,
                "action": "throttle",
                "throttle_level": "L1",
                "dry_run": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data, "Response should have status"
        assert "trace_id" in data, "Response should have trace_id"
        print(f"PASS: Bulk throttle response: status={data.get('status')}")


class TestResponseContract:
    """Test that all control/rollout/bulk/rollback responses have {status, trace_id, message, state_snapshot}"""

    def test_all_endpoints_return_contract_fields(self, admin_headers):
        """All endpoints should return {status, trace_id, message, state_snapshot}"""
        overview_resp = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=admin_headers,
            timeout=30
        )
        strategies = overview_resp.json().get("strategies", [])
        if len(strategies) == 0:
            pytest.skip("No strategies available")
        
        strategy_id = strategies[0]["strategy_id"]
        
        # Test endpoints that should return contract
        endpoints = [
            ("POST", f"/api/admin/futures/strategy/{strategy_id}/promote-shadow", {"reason": "test", "confirm_phrase": "WRONG", "dry_run": True}),
            ("POST", f"/api/admin/futures/strategy/{strategy_id}/rollout", {"reason": "test", "confirm_phrase": "WRONG", "rollout_percentage": 10, "dry_run": True}),
            ("POST", f"/api/admin/futures/strategy/{strategy_id}/rollback", {"reason": "test", "confirm_phrase": "WRONG", "dry_run": True}),
            ("POST", f"/api/admin/futures/strategy/bulk-action", {"reason": "test", "confirm_phrase": "WRONG", "strategy_ids": [strategy_id], "action": "pause", "dry_run": True}),
        ]
        
        for method, endpoint, body in endpoints:
            if method == "POST":
                response = requests.post(f"{BASE_URL}{endpoint}", headers=admin_headers, json=body, timeout=30)
            else:
                response = requests.get(f"{BASE_URL}{endpoint}", headers=admin_headers, timeout=30)
            
            assert response.status_code == 200, f"{endpoint} returned {response.status_code}"
            data = response.json()
            
            assert "status" in data, f"{endpoint} missing 'status' field"
            assert "trace_id" in data, f"{endpoint} missing 'trace_id' field"
            assert "message" in data, f"{endpoint} missing 'message' field"
            assert "state_snapshot" in data, f"{endpoint} missing 'state_snapshot' field"
            
            print(f"PASS: {endpoint} has contract fields: status={data.get('status')}")


class TestOpsUserAuthorization:
    """Test that ops users cannot access super_admin-only endpoints"""

    def test_ops_cannot_access_rollout_precheck(self, ops_headers):
        """Ops user should get 403 on rollout-precheck"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/test_strategy/rollout-precheck",
            headers=ops_headers,
            timeout=30
        )
        assert response.status_code == 403, f"Expected 403 for ops user, got {response.status_code}"
        print("PASS: Ops user blocked from rollout-precheck")

    def test_ops_cannot_access_bulk_action(self, ops_headers):
        """Ops user should get 403 on bulk-action"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/bulk-action",
            headers=ops_headers,
            json={
                "reason": "test",
                "confirm_phrase": "BULK PAUSE",
                "strategy_ids": ["test"],
                "action": "pause"
            },
            timeout=30
        )
        assert response.status_code == 403, f"Expected 403 for ops user, got {response.status_code}"
        print("PASS: Ops user blocked from bulk-action")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
