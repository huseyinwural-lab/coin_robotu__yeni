"""
FAZ-8 Canary Release Verification Tests
Tests for:
- Live config canary fields runtime reading (canary_enabled/symbols/capital/positions)
- Execution enforce rejects (CANARY_SYMBOL_BLOCKED, CANARY_CAPITAL_LIMIT_EXCEEDED, CANARY_MAX_POSITIONS_EXCEEDED)
- GET /api/admin/canary-status endpoint
- Kill-switch integration test
- Artifact files verification
"""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from the review request
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
CANARY_USER_EMAIL = "canary_1774010877@example.com"
CANARY_USER_PASSWORD = "CanaryPass123!"


class TestArtifactFilesExist:
    """Verify FAZ-8 artifact files exist and have correct content"""

    def test_faz8_canary_run_log_exists(self):
        """Check faz8_canary_run.log exists and has content"""
        log_path = "/app/artifacts/faz8_canary_run.log"
        assert os.path.exists(log_path), f"Artifact file {log_path} does not exist"
        
        with open(log_path, "r") as f:
            content = f.read()
        
        # Verify log has expected markers
        assert "FAZ-8 canary verify başladı" in content, "Log missing start marker"
        assert "SUMMARY: PASS" in content, "Log missing PASS summary"
        assert "T-8.1 canary config runtime" in content, "Log missing T-8.1 section"
        assert "T-8.2 execution enforce" in content, "Log missing T-8.2 section"
        assert "T-8.5 canary run" in content, "Log missing T-8.5 section"
        assert "T-8.7 kill switch" in content, "Log missing T-8.7 section"
        
        # Verify 60 min run evidence (check for multiple RUN_LOOP entries)
        loop_count = content.count("RUN_LOOP_")
        assert loop_count >= 12, f"Expected at least 12 run loops for 60 min run, got {loop_count}"

    def test_faz8_canary_summary_json_exists(self):
        """Check faz8_canary_summary.json exists and has required fields"""
        summary_path = "/app/artifacts/faz8_canary_summary.json"
        assert os.path.exists(summary_path), f"Artifact file {summary_path} does not exist"
        
        with open(summary_path, "r") as f:
            summary = json.load(f)
        
        # Required fields per FAZ-8 specification
        assert summary.get("phase") == "FAZ-8", f"phase should be FAZ-8, got {summary.get('phase')}"
        assert summary.get("canary_test") == "PASS", f"canary_test should be PASS, got {summary.get('canary_test')}"
        assert summary.get("duration_minutes") >= 60, f"duration_minutes should be >= 60, got {summary.get('duration_minutes')}"
        assert "symbols_tested" in summary, "Missing symbols_tested field"
        assert "error_rate" in summary, "Missing error_rate field"
        assert "reject_anomaly" in summary, "Missing reject_anomaly field"
        assert summary.get("kill_switch_test") == "PASS", f"kill_switch_test should be PASS, got {summary.get('kill_switch_test')}"
        assert "timestamp" in summary, "Missing timestamp field"

    def test_faz8_metrics_snapshot_json_exists(self):
        """Check faz8_metrics_snapshot.json exists and has required fields"""
        metrics_path = "/app/artifacts/faz8_metrics_snapshot.json"
        assert os.path.exists(metrics_path), f"Artifact file {metrics_path} does not exist"
        
        with open(metrics_path, "r") as f:
            metrics = json.load(f)
        
        # Required fields
        assert metrics.get("phase") == "FAZ-8", f"phase should be FAZ-8, got {metrics.get('phase')}"
        assert metrics.get("health_http") == 200, f"health_http should be 200, got {metrics.get('health_http')}"
        assert metrics.get("ready_http") == 200, f"ready_http should be 200, got {metrics.get('ready_http')}"
        assert metrics.get("crash_count") == 0, f"crash_count should be 0, got {metrics.get('crash_count')}"
        assert metrics.get("error_5xx_count") == 0, f"error_5xx_count should be 0, got {metrics.get('error_5xx_count')}"
        assert metrics.get("loop_count") >= 12, f"loop_count should be >= 12, got {metrics.get('loop_count')}"
        assert "canary_status" in metrics, "Missing canary_status field"
        assert "timestamp" in metrics, "Missing timestamp field"


class TestCanaryLogTimeline:
    """Verify 60 minute canary run timeline"""

    def test_timeline_spans_60_minutes(self):
        """Verify log timeline shows 60+ minute duration"""
        log_path = "/app/artifacts/faz8_canary_run.log"
        
        with open(log_path, "r") as f:
            lines = f.readlines()
        
        # Parse timestamps from first and last entries
        # Format: 2026-03-20T12:51:36Z
        first_ts = None
        last_ts = None
        
        for line in lines:
            if line.strip():
                parts = line.split(" ", 1)
                if parts[0].endswith("Z"):
                    if first_ts is None:
                        first_ts = parts[0]
                    last_ts = parts[0]
        
        assert first_ts is not None, "Could not parse first timestamp"
        assert last_ts is not None, "Could not parse last timestamp"
        
        # Parse ISO timestamps
        from datetime import datetime
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        start = datetime.strptime(first_ts, fmt)
        end = datetime.strptime(last_ts, fmt)
        
        duration_minutes = (end - start).total_seconds() / 60
        assert duration_minutes >= 60, f"Run duration should be >= 60 min, got {duration_minutes:.2f} min"


class TestExecutionEnforceRejects:
    """Verify execution enforce reject reasons are logged"""

    def test_canary_symbol_blocked_logged(self):
        """Check CANARY_SYMBOL_BLOCKED reject is logged"""
        log_path = "/app/artifacts/faz8_canary_run.log"
        
        with open(log_path, "r") as f:
            content = f.read()
        
        assert "CANARY_SYMBOL_BLOCKED" in content, "CANARY_SYMBOL_BLOCKED not found in log"
        assert "PASS: test-order reject (CANARY_SYMBOL_BLOCKED)" in content, "CANARY_SYMBOL_BLOCKED test did not pass"

    def test_canary_capital_limit_exceeded_logged(self):
        """Check CANARY_CAPITAL_LIMIT_EXCEEDED reject is logged"""
        log_path = "/app/artifacts/faz8_canary_run.log"
        
        with open(log_path, "r") as f:
            content = f.read()
        
        assert "CANARY_CAPITAL_LIMIT_EXCEEDED" in content, "CANARY_CAPITAL_LIMIT_EXCEEDED not found in log"
        assert "PASS: test-order reject (CANARY_CAPITAL_LIMIT_EXCEEDED)" in content, "CANARY_CAPITAL_LIMIT_EXCEEDED test did not pass"

    def test_canary_max_positions_exceeded_logged(self):
        """Check CANARY_MAX_POSITIONS_EXCEEDED reject is logged"""
        log_path = "/app/artifacts/faz8_canary_run.log"
        
        with open(log_path, "r") as f:
            content = f.read()
        
        assert "CANARY_MAX_POSITIONS_EXCEEDED" in content, "CANARY_MAX_POSITIONS_EXCEEDED not found in log"
        assert "PASS: test-order reject (CANARY_MAX_POSITIONS_EXCEEDED)" in content, "CANARY_MAX_POSITIONS_EXCEEDED test did not pass"


class TestKillSwitchIntegration:
    """Verify kill-switch integration during canary run"""

    def test_kill_switch_test_passed(self):
        """Check kill-switch integration test passed in log"""
        log_path = "/app/artifacts/faz8_canary_run.log"
        
        with open(log_path, "r") as f:
            content = f.read()
        
        assert "T-8.7 kill switch" in content, "Kill switch section not found in log"
        assert "TRADING_DISABLED" in content, "TRADING_DISABLED reject not found in log"

    def test_kill_switch_pass_in_summary(self):
        """Check kill_switch_test is PASS in summary"""
        summary_path = "/app/artifacts/faz8_canary_summary.json"
        
        with open(summary_path, "r") as f:
            summary = json.load(f)
        
        assert summary.get("kill_switch_test") == "PASS", f"kill_switch_test should be PASS, got {summary.get('kill_switch_test')}"


class TestCanaryStatusEndpoint:
    """Test GET /api/admin/canary-status endpoint"""

    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        if not BASE_URL:
            pytest.skip("BASE_URL not set")
        
        # Try login with the provided admin credentials
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        if response.status_code != 200:
            # Fall back to standard admin credentials
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": "admin@platform.local", "password": "Admin12345!"},
                timeout=10
            )
        
        if response.status_code != 200:
            pytest.skip(f"Admin login failed with status {response.status_code}")
        
        data = response.json()
        token = data.get("access_token")
        if not token:
            pytest.skip("No access_token in response")
        
        return token

    def test_canary_status_endpoint_returns_200(self, admin_token):
        """Verify canary-status endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/canary-status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_canary_status_response_structure(self, admin_token):
        """Verify canary-status response has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/canary-status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Check required fields per AdminCanaryStatusResponse schema
        required_fields = [
            "enabled",
            "active_symbols",
            "capital_used",
            "position_count",
            "violations",
            "error_rate",
            "latency_ms_p95",
            "order_fail_rate",
            "reject_rate",
            "pnl_drift",
            "alert_ids"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_canary_status_matches_metrics_snapshot(self, admin_token):
        """Verify canary-status returns consistent data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/canary-status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify data types
        assert isinstance(data["enabled"], bool), "enabled should be boolean"
        assert isinstance(data["active_symbols"], list), "active_symbols should be list"
        assert isinstance(data["capital_used"], (int, float)), "capital_used should be numeric"
        assert isinstance(data["position_count"], int), "position_count should be integer"
        assert isinstance(data["violations"], int), "violations should be integer"
        assert isinstance(data["error_rate"], (int, float)), "error_rate should be numeric"
        assert isinstance(data["latency_ms_p95"], (int, float)), "latency_ms_p95 should be numeric"
        assert isinstance(data["alert_ids"], list), "alert_ids should be list"


class TestKillSwitchEndpoint:
    """Test /api/admin/kill-switch endpoint"""

    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        if not BASE_URL:
            pytest.skip("BASE_URL not set")
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        if response.status_code != 200:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": "admin@platform.local", "password": "Admin12345!"},
                timeout=10
            )
        
        if response.status_code != 200:
            pytest.skip(f"Admin login failed with status {response.status_code}")
        
        return response.json().get("access_token")

    def test_kill_switch_get_returns_200(self, admin_token):
        """Verify GET /api/admin/kill-switch returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/kill-switch",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_kill_switch_response_structure(self, admin_token):
        """Verify kill-switch response has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/kill-switch",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields per AdminKillSwitchResponse schema
        required_fields = [
            "trading_enabled",
            "max_total_exposure",
            "max_active_positions",
            "current_total_exposure",
            "current_active_positions",
            "open_positions_count",
            "pending_user_intents_count",
            "pending_runtime_intents_count",
            "reason_code",
            "idempotent",
            "updated_at"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


class TestLiveConfigCanaryFields:
    """Verify live config contains canary fields"""

    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        if not BASE_URL:
            pytest.skip("BASE_URL not set")
        
        import time
        time.sleep(2)  # Rate limit buffer
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": "admin@platform.local", "password": "Admin12345!"},
            timeout=10
        )
        
        if response.status_code != 200:
            time.sleep(5)
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=10
            )
        
        if response.status_code != 200:
            pytest.skip(f"Admin login failed with status {response.status_code}")
        
        token = response.json().get("access_token")
        if not token:
            pytest.skip("No access_token in response")
        return token

    def test_live_config_get_returns_200(self, admin_token):
        """Verify GET /api/phase4/live-config returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/live-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_live_config_has_canary_fields(self, admin_token):
        """Verify live-config has canary fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/live-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Canary fields per FAZ-8 specification
        canary_fields = [
            "canary_enabled",
            "canary_symbols",
            "canary_max_capital_usdt",
            "canary_max_positions"
        ]
        
        for field in canary_fields:
            assert field in data, f"Missing canary field: {field}"


class TestSummaryJSONCriteria:
    """Verify summary JSON passes all criteria"""

    def test_summary_pass_criteria(self):
        """Check all PASS criteria in summary"""
        summary_path = "/app/artifacts/faz8_canary_summary.json"
        
        with open(summary_path, "r") as f:
            summary = json.load(f)
        
        # All criteria must pass
        assert summary.get("phase") == "FAZ-8", "Phase mismatch"
        assert summary.get("canary_test") == "PASS", "canary_test not PASS"
        assert summary.get("duration_minutes") >= 60, "Duration less than 60 minutes"
        assert summary.get("reject_anomaly") == False, "reject_anomaly should be False"
        assert summary.get("kill_switch_test") == "PASS", "kill_switch_test not PASS"
        
        # Error rate should be acceptable (< 5%)
        error_rate = summary.get("error_rate", 0)
        assert error_rate < 0.05, f"Error rate {error_rate} exceeds 5% threshold"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
