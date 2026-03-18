"""
Iteration 158: FAZ-A+B Final Lock Testing
Tests for execution guard, readiness endpoints, validate-order, and release-gate contracts.
"""

import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is required")


def _admin_headers():
    """Login as admin and return auth headers."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=30,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    assert token, "No access token returned"
    return {"Authorization": f"Bearer {token}"}


def _create_user_and_get_headers(admin_headers: dict) -> dict:
    """Create a new test user, approve, and return user headers."""
    email = f"test_iter158_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestIter158!"

    # Register
    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert register.status_code == 200, f"Register failed: {register.text}"
    user_id = register.json().get("id")

    # Approve
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=30,
    )
    assert approve.status_code == 200, f"Approve failed: {approve.text}"

    # Login
    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert login.status_code == 200, f"User login failed: {login.text}"
    token = login.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


class TestExecutionReadiness:
    """Tests for GET /api/admin/execution-readiness endpoint."""

    def test_execution_readiness_returns_200(self):
        """Endpoint returns 200 with deterministic fields."""
        headers = _admin_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()

        # Contract: deterministic fields must exist
        assert "final_status" in payload
        assert payload["final_status"] in {"READY", "BLOCKED"}
        assert "mode" in payload
        assert payload["mode"] in {"MOCKED", "LIVE"}
        assert "latency_ms" in payload
        assert isinstance(payload["latency_ms"], int)
        assert "exchange_connection" in payload
        assert "permissions" in payload
        assert "order_test" in payload
        assert "mocked_flag" in payload
        assert "override_active" in payload
        assert "reason_codes" in payload
        assert isinstance(payload["reason_codes"], list)


class TestValidateOrder:
    """Tests for POST /api/user/validate-order endpoint."""

    def test_validate_order_returns_contract_with_execution_mode_and_violations(self):
        """Endpoint returns contract with execution_mode and violations."""
        admin_headers = _admin_headers()
        user_headers = _create_user_and_get_headers(admin_headers)

        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 100,
                "size": 0.0001,
                "leverage": 100,
                "margin_mode": "isolated",
            },
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()

        # Contract: must have execution_mode and violations
        assert "execution_mode" in payload
        assert payload["execution_mode"] in {"mocked", "live"}
        assert "valid" in payload
        assert isinstance(payload["valid"], bool)
        assert "violations" in payload
        assert isinstance(payload["violations"], list)
        # With leverage=100 and small size, should have violations
        assert len(payload["violations"]) > 0


class TestExecutionGuard:
    """Tests for execution guard dependency on protected endpoints."""

    def test_guard_returns_423_on_open_position(self):
        """User without exchange connection gets 423 on open-position."""
        admin_headers = _admin_headers()
        user_headers = _create_user_and_get_headers(admin_headers)

        response = requests.post(
            f"{BASE_URL}/api/user/open-position",
            headers=user_headers,
            json={"intent_token": "test_token", "preview_hash": "test_hash"},
            timeout=30,
        )
        assert response.status_code == 423
        assert response.json().get("detail") == "EXECUTION_BLOCKED_BY_READINESS"

    def test_guard_returns_423_on_execute_order(self):
        """User without exchange connection gets 423 on execute-order."""
        admin_headers = _admin_headers()
        user_headers = _create_user_and_get_headers(admin_headers)

        response = requests.post(
            f"{BASE_URL}/api/user/execute-order",
            headers=user_headers,
            json={"intent_token": "test_token", "preview_hash": "test_hash"},
            timeout=30,
        )
        assert response.status_code == 423
        assert response.json().get("detail") == "EXECUTION_BLOCKED_BY_READINESS"

    def test_guard_returns_423_on_manual_trade(self):
        """User without exchange connection gets 423 on manual-trade."""
        admin_headers = _admin_headers()
        user_headers = _create_user_and_get_headers(admin_headers)

        response = requests.post(
            f"{BASE_URL}/api/user/manual-trade",
            headers=user_headers,
            json={"intent_token": "test_token", "preview_hash": "test_hash"},
            timeout=30,
        )
        assert response.status_code == 423
        assert response.json().get("detail") == "EXECUTION_BLOCKED_BY_READINESS"

    def test_admin_approve_trade_has_guard(self):
        """Admin approve-trade endpoint has guard dependency attached."""
        admin_headers = _admin_headers()
        
        # This should return 400 (intent_not_found) not 423, because guard passes for admin
        # but the intent lookup fails (which happens after guard check)
        response = requests.post(
            f"{BASE_URL}/api/admin/approve-trade",
            headers=admin_headers,
            json={"intent_id": "nonexistent_intent", "note": "test"},
            timeout=30,
        )
        # Guard passes (admin), then intent lookup fails -> 400
        assert response.status_code == 400
        assert response.json().get("detail") == "intent_not_found"


class TestReleaseGate:
    """Tests for GET /api/admin/release-gate endpoint."""

    def test_release_gate_returns_contract(self):
        """Endpoint returns proper contract with reason_codes when BLOCKED."""
        headers = _admin_headers()
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()

        # Contract fields
        assert "status" in payload
        assert payload["status"] in {"PASS", "BLOCKED"}
        assert "reason_codes" in payload
        assert isinstance(payload["reason_codes"], list)
        assert "blocking_metrics" in payload
        assert isinstance(payload["blocking_metrics"], dict)
        assert "deploy_enable_flag" in payload

        # If BLOCKED, reason_codes must be non-empty
        if payload["status"] == "BLOCKED":
            assert len(payload["reason_codes"]) > 0, "BLOCKED status must have reason_codes"

    def test_release_gate_via_phase4_router(self):
        """Phase4 release-gate alias returns same contract."""
        headers = _admin_headers()
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate",
            headers=headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()

        assert "status" in payload
        assert "reason_codes" in payload
        assert "blocking_metrics" in payload

        if payload["status"] == "BLOCKED":
            assert len(payload["reason_codes"]) > 0


class TestDoubleSafety:
    """Tests for double safety: guard + precheck at service layer."""

    def test_execution_intent_service_has_guard_and_precheck(self):
        """Verify submit_execution_intent has both enforce_execution_guard_or_raise and validate_order_precheck."""
        import sys
        from pathlib import Path

        backend_root = Path(__file__).resolve().parents[1]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))

        import inspect
        from services import execution_intent_service

        source = inspect.getsource(execution_intent_service.submit_execution_intent)
        assert "enforce_execution_guard_or_raise" in source, "Guard call missing in submit_execution_intent"
        assert "validate_order_precheck" in source, "Precheck call missing in submit_execution_intent"

    def test_user_trade_path_has_guard_and_precheck(self):
        """Verify _submit_trade_with_guard has both enforcement calls."""
        import sys
        from pathlib import Path

        backend_root = Path(__file__).resolve().parents[1]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))

        import inspect
        from routers import user_platform

        source = inspect.getsource(user_platform._submit_trade_with_guard)
        assert "enforce_execution_guard_or_raise" in source, "Guard call missing in _submit_trade_with_guard"
        assert "validate_order_precheck" in source, "Precheck call missing in _submit_trade_with_guard"


class TestGuardDependencyAttachment:
    """Tests to verify guard dependency is attached to all required endpoints."""

    def test_guard_attached_to_all_endpoints(self):
        """Verify execution_guard_dependency is attached to listed endpoints."""
        import sys
        from pathlib import Path

        backend_root = Path(__file__).resolve().parents[1]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))

        from server import fastapi_app

        target_paths = {
            "/api/user/open-position",
            "/api/user/execute-order",
            "/api/user/manual-trade",
            "/api/admin/approve-trade",
        }

        found = {}
        for route in fastapi_app.routes:
            path = getattr(route, "path", "")
            if path in target_paths and "POST" in getattr(route, "methods", set()):
                dep_names = {
                    getattr(getattr(dep, "call", None), "__name__", "")
                    for dep in getattr(route, "dependant", None).dependencies
                }
                found[path] = dep_names

        for path in target_paths:
            assert path in found, f"Route missing: {path}"
            assert any(
                "execution_guard" in name for name in found[path]
            ), f"Guard dependency missing on {path}"
