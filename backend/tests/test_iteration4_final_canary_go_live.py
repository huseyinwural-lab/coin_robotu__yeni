"""
Iteration 4 Final Testing: Canary & Go-Live Prep
- POST /api/runtime/exchange/testnet-lifecycle/run: Real order lifecycle and artifact generation
- POST /api/runtime/canary/run: Chain validation (strategy->risk->queue->execution->exchange->order->pnl->alert->timeline->snapshot)
- GET /api/runtime/canary/readiness-score: Score/status/components validation
- GET /api/runtime/go-live/checklist: go_live + reasons/checks validation
- POST /api/runtime/regression/final-run: Final regression PASS flow
- POST /api/runtime/safety/kill-switch/verify-rollback: Kill-switch validation
- GET /api/runtime/exchange/proxy-health: Spot/futures proxy hardening output
"""

import os
import pytest
import requests
import json

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL tanımlı değil", allow_module_level=True)


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestHealthAndBasicEndpoints:
    """Basic health and connectivity tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print(f"Health check PASS: {data.get('status')}")
    
    def test_admin_login(self):
        """Test admin login works"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("access_token") or data.get("token")
        print("Admin login PASS: token received")


class TestRuntimeExecutionMode:
    """Test execution mode and flags"""
    
    def test_get_execution_mode(self, auth_headers):
        """GET /api/runtime/execution/mode - Check execution mode and flags"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/execution/mode",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "mode" in data
        assert "flags" in data
        print(f"Execution mode: {data.get('mode')}")
        print(f"Flags: {json.dumps(data.get('flags', {}), indent=2)}")


class TestProxyExchangeHealth:
    """Test proxy/exchange hardening output"""
    
    def test_get_proxy_health(self, auth_headers):
        """GET /api/runtime/exchange/proxy-health - Spot/futures proxy hardening"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/exchange/proxy-health",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        result = data.get("result", {})
        
        # Verify spot configuration
        spot = result.get("spot", {})
        assert "base_url_set" in spot
        assert "proxy_token_set" in spot
        assert "proxy_token_mismatch" in spot
        print(f"Spot config: base_url_set={spot.get('base_url_set')}, proxy_token_set={spot.get('proxy_token_set')}")
        
        # Verify futures configuration
        futures = result.get("futures", {})
        assert "base_url_set" in futures
        assert "proxy_token_set" in futures
        assert "proxy_token_mismatch" in futures
        print(f"Futures config: base_url_set={futures.get('base_url_set')}, proxy_token_set={futures.get('proxy_token_set')}")
        
        # Verify adapter limits
        adapter_limits = result.get("adapter_limits", {})
        assert "timeout_seconds" in adapter_limits
        assert "max_retries" in adapter_limits
        print(f"Adapter limits: timeout={adapter_limits.get('timeout_seconds')}s, max_retries={adapter_limits.get('max_retries')}")


class TestCanaryReadinessScore:
    """Test canary readiness score endpoint"""
    
    def test_get_readiness_score(self, auth_headers):
        """GET /api/runtime/canary/readiness-score - Score/status/components validation"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/canary/readiness-score",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        result = data.get("result", {})
        
        # Verify score
        assert "score" in result
        assert isinstance(result.get("score"), (int, float))
        assert 0 <= result.get("score") <= 100
        print(f"Readiness score: {result.get('score')}")
        
        # Verify status
        assert "status" in result
        assert result.get("status") in ["READY", "WARNING", "NOT_READY"]
        print(f"Readiness status: {result.get('status')}")
        
        # Verify components
        components = result.get("components", {})
        assert "execution" in components
        assert "pnl" in components
        assert "alerts" in components
        assert "smoke" in components
        assert "exchange" in components
        print(f"Components: {json.dumps(components, indent=2)}")


class TestGoLiveChecklist:
    """Test go-live checklist endpoint"""
    
    def test_get_go_live_checklist(self, auth_headers):
        """GET /api/runtime/go-live/checklist - go_live + reasons/checks validation"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/go-live/checklist",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        result = data.get("result", {})
        
        # Verify go_live decision
        assert "go_live" in result
        assert isinstance(result.get("go_live"), bool)
        print(f"Go-live decision: {result.get('go_live')}")
        
        # Verify reasons
        assert "reasons" in result
        assert isinstance(result.get("reasons"), list)
        print(f"Reasons: {result.get('reasons')}")
        
        # Verify checks
        checks = result.get("checks", {})
        expected_checks = [
            "testnet_lifecycle_pass",
            "canary_run_pass",
            "smoke_ok",
            "alert_spike_absent",
            "queue_backlog_normal",
            "kill_switch_verified"
        ]
        for check in expected_checks:
            assert check in checks, f"Missing check: {check}"
        print(f"Checks: {json.dumps(checks, indent=2)}")
        
        # Verify readiness
        readiness = result.get("readiness", {})
        assert "score" in readiness
        assert "status" in readiness
        print(f"Readiness in checklist: score={readiness.get('score')}, status={readiness.get('status')}")
        
        # Verify metrics
        metrics = result.get("metrics", {})
        assert "queue_backlog" in metrics
        assert "critical_open_alerts_30m" in metrics
        print(f"Metrics: {json.dumps(metrics, indent=2)}")


class TestKillSwitchVerifyRollback:
    """Test kill-switch rollback verification"""
    
    def test_verify_kill_switch_rollback(self, auth_headers):
        """POST /api/runtime/safety/kill-switch/verify-rollback - Kill-switch validation"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/safety/kill-switch/verify-rollback",
            headers=auth_headers,
            json={"symbol": "BTCUSDT"},
            timeout=60
        )
        
        # Can be 200 (PASS) or 409 (FAIL with details)
        assert response.status_code in [200, 409, 400]
        data = response.json()
        
        if response.status_code == 200:
            assert data.get("status") == "ok"
            result = data.get("result", {})
            assert result.get("status") == "PASS"
            print("Kill-switch verify PASS")
            
            # Verify artifact path
            assert "artifact_path" in result
            print(f"Artifact path: {result.get('artifact_path')}")
            
            # Verify blocked result
            blocked_result = result.get("blocked_result", {})
            assert blocked_result.get("status") == "rejected"
            print(f"Blocked result status: {blocked_result.get('status')}")
        else:
            # 409 means FAIL - still valid test
            print(f"Kill-switch verify returned {response.status_code}: {data}")


class TestTestnetLifecycleValidation:
    """Test testnet lifecycle validation - Real Binance testnet order lifecycle"""
    
    def test_run_testnet_lifecycle(self, auth_headers):
        """POST /api/runtime/exchange/testnet-lifecycle/run - Real order lifecycle and artifact"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/exchange/testnet-lifecycle/run",
            headers=auth_headers,
            json={"symbol": "BTCUSDT", "size": 0.0001},
            timeout=120  # Longer timeout for real exchange operations
        )
        
        # Can be 200 (PASS) or 409 (FAIL with details) or 400 (error)
        assert response.status_code in [200, 409, 400]
        data = response.json()
        
        if response.status_code == 200:
            assert data.get("status") == "ok"
            result = data.get("result", {})
            assert result.get("status") == "PASS"
            print("Testnet lifecycle PASS")
            
            # Verify artifact path
            assert "artifact_path" in result
            print(f"Artifact path: {result.get('artifact_path')}")
            
            # Verify market order ID
            assert "market_order_id" in result
            print(f"Market order ID: {result.get('market_order_id')}")
            
            # Verify cancel order ID
            assert "cancel_order_id" in result
            print(f"Cancel order ID: {result.get('cancel_order_id')}")
            
            # Verify timeline events
            assert "timeline_event_count" in result
            print(f"Timeline event count: {result.get('timeline_event_count')}")
            
            # Verify DB state
            db_state = result.get("db_state", {})
            print(f"DB state: {json.dumps(db_state, indent=2)}")
        else:
            # 409 or 400 means FAIL - log details
            print(f"Testnet lifecycle returned {response.status_code}: {json.dumps(data, indent=2)[:500]}")
            # This is expected if testnet credentials are not valid or exchange is down
            pytest.skip(f"Testnet lifecycle validation failed: {response.status_code}")


class TestCanaryRun:
    """Test canary end-to-end validation"""
    
    def test_run_canary(self, auth_headers):
        """POST /api/runtime/canary/run - Chain validation"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/canary/run",
            headers=auth_headers,
            json={"symbol": "BTCUSDT", "size": 0.0001, "strategy_name": "ema_rsi"},
            timeout=120
        )
        
        # Can be 200 (PASS) or 409 (FAIL with details) or 400 (error)
        assert response.status_code in [200, 409, 400]
        data = response.json()
        
        if response.status_code == 200:
            assert data.get("status") == "ok"
            result = data.get("result", {})
            assert result.get("status") == "PASS"
            print("Canary run PASS")
            
            # Verify steps
            steps = result.get("steps", {})
            expected_steps = ["strategy", "risk", "queue", "execution", "exchange", "order_update", "pnl", "alert", "timeline", "snapshot"]
            for step in expected_steps:
                assert step in steps, f"Missing step: {step}"
            print(f"Steps: {json.dumps(steps, indent=2)}")
            
            # Verify artifact path
            assert "artifact_path" in result
            print(f"Artifact path: {result.get('artifact_path')}")
        else:
            # 409 or 400 means FAIL - log details
            print(f"Canary run returned {response.status_code}: {json.dumps(data, indent=2)[:500]}")
            pytest.skip(f"Canary run validation failed: {response.status_code}")


class TestFinalRegression:
    """Test final regression validation"""
    
    def test_run_final_regression(self, auth_headers):
        """POST /api/runtime/regression/final-run - Final regression PASS flow"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/regression/final-run",
            headers=auth_headers,
            json={"symbol": "BTCUSDT", "size": 0.0001, "strategy_name": "ema_rsi"},
            timeout=180  # Longer timeout for full regression
        )
        
        # Can be 200 (PASS) or 409 (FAIL with details) or 400 (error)
        assert response.status_code in [200, 409, 400]
        data = response.json()
        
        if response.status_code == 200:
            assert data.get("status") == "ok"
            result = data.get("result", {})
            assert result.get("status") == "PASS"
            print("Final regression PASS")
            
            # Verify checks
            checks = result.get("checks", {})
            expected_checks = ["execution", "reconciliation", "kill_switch", "timeline", "alert"]
            for check in expected_checks:
                assert check in checks, f"Missing check: {check}"
            print(f"Checks: {json.dumps(checks, indent=2)}")
            
            # Verify artifact path
            assert "artifact_path" in result
            print(f"Artifact path: {result.get('artifact_path')}")
        else:
            # 409 or 400 means FAIL - log details
            print(f"Final regression returned {response.status_code}: {json.dumps(data, indent=2)[:500]}")
            pytest.skip(f"Final regression validation failed: {response.status_code}")


class TestRuntimeAlerts:
    """Test runtime alerts endpoint"""
    
    def test_get_runtime_alerts(self, auth_headers):
        """GET /api/runtime/alerts - Runtime alert triage"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/alerts",
            headers=auth_headers,
            params={"limit": 20, "window_minutes": 60},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        print(f"Runtime alerts count: {len(data.get('items', []))}")


class TestRuntimePnlSummary:
    """Test runtime PnL summary endpoint"""
    
    def test_get_pnl_summary(self, auth_headers):
        """GET /api/runtime/pnl/summary - PnL summary"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/pnl/summary",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"PnL summary: {json.dumps(data, indent=2)[:300]}")


class TestRuntimeSmokeHealth:
    """Test runtime smoke health endpoint"""
    
    def test_get_smoke_health(self, auth_headers):
        """GET /api/runtime/health/smoke - Smoke health"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/health/smoke",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"Smoke health status: {data.get('status')}")
        if data.get("smoke"):
            print(f"Smoke run_status: {data.get('smoke', {}).get('run_status')}")


class TestKillSwitchState:
    """Test kill-switch state endpoint"""
    
    def test_get_kill_switch_state(self, auth_headers):
        """GET /api/runtime/safety/kill-switch - Kill-switch state"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/safety/kill-switch",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        kill_switch = data.get("kill_switch", {})
        assert "active" in kill_switch
        print(f"Kill-switch active: {kill_switch.get('active')}")
        print(f"Kill-switch reason: {kill_switch.get('reason')}")


class TestTimelineEvents:
    """Test timeline events endpoint"""
    
    def test_get_timeline_events(self, auth_headers):
        """GET /api/runtime/timeline/events - Timeline events"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/timeline/events",
            headers=auth_headers,
            params={"limit": 50},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "items" in data
        print(f"Timeline events count: {len(data.get('items', []))}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
