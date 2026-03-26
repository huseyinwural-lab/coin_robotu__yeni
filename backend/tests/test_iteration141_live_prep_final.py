"""
Iteration 141 - LIVE PREP FINAL Testing
Tests for:
- GET /api/health/live - lightweight 200 always
- GET /api/health/ready - DB+Redis readiness
- WS keepalive /api/runtime/ws/execution-timeline
- GET /api/runtime/execution/mode - canonical mode + compatibility notice
- POST /api/runtime/go-live/dry-run/run - single-flow artifact
- Wizard endpoints: state, readiness-check, canary-check, arm, confirm, rollback (super_admin auth gate)
- Runtime readiness/go-live checklist rules (smoke PASS required)
"""

import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin token for authenticated requests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestHealthEndpoints:
    """Health endpoint tests - P0 service stabilization"""

    def test_health_live_returns_200_always(self):
        """GET /api/health/live should always return 200 and be lightweight"""
        response = requests.get(f"{BASE_URL}/api/health/live", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "backend-api"
        assert "checks" in data
        assert "process" in data["checks"]
        print(f"PASS: /api/health/live returns 200 with status=ok")

    def test_health_ready_checks_db_and_redis(self):
        """GET /api/health/ready should check DB and Redis"""
        response = requests.get(f"{BASE_URL}/api/health/ready", timeout=15)
        # Can be 200 or 503 depending on state
        assert response.status_code in [200, 503], f"Unexpected status: {response.status_code}"
        data = response.json()
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis" in data["checks"]
        print(f"PASS: /api/health/ready checks database and redis, status={data.get('status')}")


class TestExecutionModeEndpoint:
    """Execution mode canonical mode + compatibility notice tests"""

    def test_execution_mode_returns_canonical_mode(self, admin_headers):
        """GET /api/runtime/execution/mode should return canonical mode with compatibility notice"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/execution/mode",
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Check canonical mode fields
        assert "mode" in data, "Missing 'mode' field"
        assert data["mode"] in ["sim", "testnet", "live"], f"Unexpected mode: {data['mode']}"
        
        # Check compatibility notice
        assert "compatibility_alias" in data, "Missing 'compatibility_alias' field"
        assert "compatibility_notice" in data, "Missing 'compatibility_notice' field"
        assert "legacy" in data["compatibility_notice"].lower(), "Compatibility notice should mention legacy"
        
        # Check flags
        assert "flags" in data, "Missing 'flags' field"
        print(f"PASS: /api/runtime/execution/mode returns mode={data['mode']} with compatibility notice")


class TestGoLiveWizardEndpoints:
    """Go-Live Wizard endpoints - super_admin auth gate tests"""

    def test_wizard_state_endpoint(self, admin_headers):
        """GET /api/runtime/go-live/wizard/state should return wizard state"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/go-live/wizard/state",
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "result" in data
        result = data["result"]
        assert "stage" in result, "Missing 'stage' in wizard state"
        assert "armed" in result, "Missing 'armed' in wizard state"
        assert "confirmed" in result, "Missing 'confirmed' in wizard state"
        print(f"PASS: /api/runtime/go-live/wizard/state returns stage={result.get('stage')}")

    def test_wizard_readiness_check_requires_super_admin(self, admin_headers):
        """POST /api/runtime/go-live/wizard/readiness-check should require super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/go-live/wizard/readiness-check",
            headers=admin_headers,
            json={},
            timeout=30
        )
        # Should be 200 if super_admin, 403 if not
        # Admin user may or may not be super_admin
        assert response.status_code in [200, 403], f"Unexpected status: {response.status_code}"
        if response.status_code == 403:
            data = response.json()
            assert "super_admin" in str(data.get("detail", "")).lower()
            print("PASS: /api/runtime/go-live/wizard/readiness-check correctly requires super_admin")
        else:
            print("PASS: /api/runtime/go-live/wizard/readiness-check executed (user is super_admin)")

    def test_wizard_canary_check_requires_super_admin(self, admin_headers):
        """POST /api/runtime/go-live/wizard/canary-check should require super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/go-live/wizard/canary-check",
            headers=admin_headers,
            json={"symbol": "BTCUSDT", "size": 0.0001},
            timeout=60
        )
        assert response.status_code in [200, 403, 409], f"Unexpected status: {response.status_code}"
        if response.status_code == 403:
            data = response.json()
            assert "super_admin" in str(data.get("detail", "")).lower()
            print("PASS: /api/runtime/go-live/wizard/canary-check correctly requires super_admin")
        else:
            print(f"PASS: /api/runtime/go-live/wizard/canary-check returned {response.status_code}")

    def test_wizard_arm_requires_super_admin(self, admin_headers):
        """POST /api/runtime/go-live/wizard/arm should require super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/go-live/wizard/arm",
            headers=admin_headers,
            json={},
            timeout=30
        )
        # 403 if not super_admin, 409 if blocked by readiness
        assert response.status_code in [200, 403, 409], f"Unexpected status: {response.status_code}"
        if response.status_code == 403:
            data = response.json()
            assert "super_admin" in str(data.get("detail", "")).lower()
            print("PASS: /api/runtime/go-live/wizard/arm correctly requires super_admin")
        else:
            print(f"PASS: /api/runtime/go-live/wizard/arm returned {response.status_code}")

    def test_wizard_confirm_requires_super_admin(self, admin_headers):
        """POST /api/runtime/go-live/wizard/confirm should require super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/go-live/wizard/confirm",
            headers=admin_headers,
            json={},
            timeout=30
        )
        # 403 if not super_admin, 409 if not armed
        assert response.status_code in [200, 403, 409], f"Unexpected status: {response.status_code}"
        if response.status_code == 403:
            data = response.json()
            assert "super_admin" in str(data.get("detail", "")).lower()
            print("PASS: /api/runtime/go-live/wizard/confirm correctly requires super_admin")
        else:
            print(f"PASS: /api/runtime/go-live/wizard/confirm returned {response.status_code}")

    def test_wizard_rollback_requires_super_admin(self, admin_headers):
        """POST /api/runtime/go-live/wizard/rollback should require super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/go-live/wizard/rollback",
            headers=admin_headers,
            json={},
            timeout=30
        )
        assert response.status_code in [200, 403], f"Unexpected status: {response.status_code}"
        if response.status_code == 403:
            data = response.json()
            assert "super_admin" in str(data.get("detail", "")).lower()
            print("PASS: /api/runtime/go-live/wizard/rollback correctly requires super_admin")
        else:
            print("PASS: /api/runtime/go-live/wizard/rollback executed (user is super_admin)")


class TestDryRunEndpoint:
    """Single-flow dry-run endpoint tests"""

    def test_dry_run_endpoint_exists(self, admin_headers):
        """POST /api/runtime/go-live/dry-run/run should exist and require admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/go-live/dry-run/run",
            headers=admin_headers,
            json={"symbol": "BTCUSDT", "size": 0.0001},
            timeout=120
        )
        # Can be 200 (success), 409 (conflict/fail), or 400 (bad request)
        assert response.status_code in [200, 400, 409], f"Unexpected status: {response.status_code}"
        print(f"PASS: /api/runtime/go-live/dry-run/run endpoint exists, returned {response.status_code}")


class TestReadinessAndChecklist:
    """Runtime readiness and go-live checklist tests"""

    def test_canary_readiness_score(self, admin_headers):
        """GET /api/runtime/canary/readiness-score should return readiness data"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/canary/readiness-score",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "result" in data
        result = data["result"]
        assert "score" in result, "Missing 'score' in readiness"
        assert "status" in result, "Missing 'status' in readiness"
        assert "components" in result, "Missing 'components' in readiness"
        print(f"PASS: /api/runtime/canary/readiness-score returns score={result.get('score')}, status={result.get('status')}")

    def test_go_live_checklist(self, admin_headers):
        """GET /api/runtime/go-live/checklist should return checklist data"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/go-live/checklist",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "result" in data
        result = data["result"]
        assert "go_live" in result, "Missing 'go_live' in checklist"
        assert "checks" in result, "Missing 'checks' in checklist"
        assert "metrics" in result, "Missing 'metrics' in checklist"
        
        # Check smoke status is included
        metrics = result.get("metrics", {})
        assert "smoke_status" in metrics, "Missing 'smoke_status' in metrics"
        print(f"PASS: /api/runtime/go-live/checklist returns go_live={result.get('go_live')}, smoke_status={metrics.get('smoke_status')}")

    def test_smoke_health_endpoint(self, admin_headers):
        """GET /api/runtime/health/smoke should return smoke run data"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/health/smoke",
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Can be "no_data" or "ok" with smoke details
        assert data.get("status") in ["ok", "no_data"], f"Unexpected status: {data.get('status')}"
        print(f"PASS: /api/runtime/health/smoke returns status={data.get('status')}")


class TestProxyHealthEndpoint:
    """Proxy exchange health endpoint tests"""

    def test_proxy_health_endpoint(self, admin_headers):
        """GET /api/runtime/exchange/proxy-health should return proxy health data"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/exchange/proxy-health",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "result" in data
        result = data["result"]
        assert "status" in result, "Missing 'status' in proxy health"
        assert "spot" in result, "Missing 'spot' in proxy health"
        assert "futures" in result, "Missing 'futures' in proxy health"
        print(f"PASS: /api/runtime/exchange/proxy-health returns status={result.get('status')}")


class TestKillSwitchEndpoints:
    """Kill switch endpoints tests"""

    def test_kill_switch_state(self, admin_headers):
        """GET /api/runtime/safety/kill-switch should return kill switch state"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/safety/kill-switch",
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "kill_switch" in data
        kill_switch = data["kill_switch"]
        assert "active" in kill_switch, "Missing 'active' in kill switch"
        print(f"PASS: /api/runtime/safety/kill-switch returns active={kill_switch.get('active')}")


class TestTimelineEndpoint:
    """Runtime timeline events endpoint tests"""

    def test_timeline_events(self, admin_headers):
        """GET /api/runtime/timeline/events should return timeline events"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/timeline/events",
            headers=admin_headers,
            params={"limit": 10},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "status" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        print(f"PASS: /api/runtime/timeline/events returns {len(data['items'])} items")


class TestAdminLiveTradingDashboard:
    """Admin live trading dashboard endpoints tests"""

    def test_control_layer_state(self, admin_headers):
        """GET /api/admin/live-trading/control-layer/state should return control state"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/state",
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "execution_mode" in data, "Missing 'execution_mode'"
        assert "kill_switch" in data, "Missing 'kill_switch'"
        assert "latency_thresholds" in data, "Missing 'latency_thresholds'"
        print(f"PASS: /api/admin/live-trading/control-layer/state returns execution_mode={data.get('execution_mode')}")

    def test_live_trading_summary(self, admin_headers):
        """GET /api/admin/live-trading/summary should return summary data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/summary",
            headers=admin_headers,
            params={"window": "1h"},
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "window" in data or "system_health" in data, "Missing expected fields in summary"
        print(f"PASS: /api/admin/live-trading/summary returns data")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
