# Phase 5 Observability P0 Package - Comprehensive Tests
# Tests: structured logging, masking, metrics, health/ready, alert channels, fake error/queue/ready scenarios

import os
import json
import pytest
import requests
from pathlib import Path

# Use public URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://risk-orchestrator-p0.preview.emergentagent.com").rstrip("/")
ARTIFACT_DIR = Path("/app/artifacts")

pytestmark = pytest.mark.skip(reason="Manual exploratory suite; CI gate uses deterministic phase5 verifier tests.")

# Test credentials
ADMIN_EMAIL = "test-phase5-admin@example.local"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin access token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text[:200]}")
    token = response.json().get("access_token")
    if not token:
        pytest.skip("No access token returned")
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for admin requests"""
    return {"Authorization": f"Bearer {admin_token}"}


# =====================================================
# T-5.1: Structured Logging Tests
# =====================================================

class TestStructuredLogging:
    """Test structured logging with stdout+file and sensitive masking"""
    
    def test_logging_contract_files_exist(self):
        """Verify required logging contract files exist"""
        required_files = [
            "/app/backend/core/structured_logging.py",
            "/app/backend/core/observability/http_logging_middleware.py",
            "/app/backend/services/observability_service.py",
        ]
        for file_path in required_files:
            assert Path(file_path).exists(), f"Missing logging file: {file_path}"
        print("PASS: All logging contract files exist")
    
    def test_logging_contract_tokens_present(self):
        """Verify required tokens in structured logging module"""
        content = Path("/app/backend/core/structured_logging.py").read_text(encoding="utf-8")
        required_tokens = ["StructuredJsonFormatter", "FileHandler", "StreamHandler", "event_name", "component"]
        for token in required_tokens:
            assert token in content, f"Missing token in structured_logging.py: {token}"
        print("PASS: All required tokens present in structured logging")
    
    def test_sensitive_masking_in_log_file(self):
        """Verify sensitive fields are masked in log output"""
        log_path = Path(
            os.environ.get("OBSERVABILITY_LOG_FILE")
            or "/app/backend/logs/backend_observability.log"
        )
        if not log_path.exists():
            pytest.skip("Log file not yet created")
        
        content = log_path.read_text(encoding="utf-8")
        # Should NOT contain raw sensitive values from probe
        assert "SG.very-sensitive-key-for-mask-check" not in content, "Raw API key found in logs"
        assert "SuperSecretPassword!" not in content, "Raw password found in logs"
        
        # Check for masked pattern (***) in log lines
        lines = [line for line in content.splitlines() if "phase5_logging_probe" in line]
        if lines:
            last_probe = lines[-1]
            parsed = json.loads(last_probe)
            # Verify masking pattern exists
            if parsed.get("api_key"):
                assert "***" in str(parsed["api_key"]), "API key not masked"
            if parsed.get("password"):
                assert "***" in str(parsed["password"]), "Password not masked"
        print("PASS: Sensitive fields are properly masked")


# =====================================================
# T-5.2: Metrics Endpoint Tests
# =====================================================

class TestMetricsEndpoint:
    """Test /api/metrics exposes error_rate, latency, queue_size and categories"""
    
    def test_metrics_endpoint_accessible(self):
        """Test that metrics endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/metrics", timeout=15)
        assert response.status_code == 200, f"Metrics endpoint failed: {response.text[:200]}"
        print("PASS: Metrics endpoint accessible")
    
    def test_metrics_contains_required_metrics(self):
        """Test that all required metrics are exposed"""
        response = requests.get(f"{BASE_URL}/api/metrics", timeout=15)
        assert response.status_code == 200
        
        text = response.text
        required_metrics = [
            "observability_error_rate_ratio",
            "observability_latency_ms_p95",
            "observability_latency_ms_avg",
            "observability_queue_size",
        ]
        for metric in required_metrics:
            assert metric in text, f"Missing required metric: {metric}"
        print("PASS: All required metrics present")
    
    def test_metrics_contains_endpoint_categories(self):
        """Test that endpoint categories are exposed in metrics"""
        # First trigger some requests to populate categories
        requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": "bad@example.com", "password": "bad"},
            timeout=15,
        )
        
        response = requests.get(f"{BASE_URL}/api/metrics", timeout=15)
        assert response.status_code == 200
        
        text = response.text
        # Check for endpoint categories
        expected_categories = ["auth_login", "other"]
        for category in expected_categories:
            assert f'endpoint="{category}"' in text or category in text, f"Missing category: {category}"
        print("PASS: Endpoint categories present in metrics")


# =====================================================
# T-5.3: Health and Ready Endpoints Tests
# =====================================================

class TestHealthReadyEndpoints:
    """Test /api/health lightweight and /api/ready dependency-aware"""
    
    def test_health_endpoint_lightweight(self):
        """Test that /api/health returns lightweight response"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert response.status_code == 200, f"Health endpoint failed: {response.text}"
        
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "backend-api"
        assert "checks" in data
        assert "process" in data["checks"]
        assert data["checks"]["process"]["status"] == "up"
        assert "timestamp" in data
        print("PASS: Health endpoint returns lightweight response")
    
    def test_ready_endpoint_dependency_aware(self):
        """Test that /api/ready checks dependencies"""
        response = requests.get(f"{BASE_URL}/api/ready", timeout=15)
        # Can be 200 (ready) or 503 (not ready)
        assert response.status_code in [200, 503], f"Ready endpoint unexpected status: {response.status_code}"
        
        data = response.json()
        assert data.get("status") in ["ready", "not_ready"]
        assert data.get("service") == "backend-api"
        assert "checks" in data
        
        # Verify dependency checks exist
        expected_checks = ["database", "redis", "execution_queue", "ready_override"]
        for check in expected_checks:
            assert check in data["checks"], f"Missing dependency check: {check}"
        print("PASS: Ready endpoint is dependency-aware")
    
    def test_ready_endpoint_status_codes(self):
        """Test ready endpoint returns correct status codes"""
        response = requests.get(f"{BASE_URL}/api/ready", timeout=15)
        data = response.json()
        
        if data.get("status") == "ready":
            assert response.status_code == 200
        else:
            assert response.status_code == 503
        print(f"PASS: Ready endpoint returns correct status code ({response.status_code})")


# =====================================================
# T-5.4: Alert Channel Configuration Tests
# =====================================================

class TestAlertChannelConfig:
    """Test alert config supports SendGrid + Telegram fields"""
    
    def test_alert_config_endpoint_accessible(self, auth_headers):
        """Test alert config endpoint is accessible"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Alert config failed: {response.text[:200]}"
        print("PASS: Alert config endpoint accessible")
    
    def test_alert_config_has_channel_fields(self, auth_headers):
        """Test alert config exposes channel fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Check channels status
        assert "channels" in data
        channels = data["channels"]
        assert "email" in channels
        assert "telegram" in channels
        
        # Check config fields
        assert "config" in data
        config = data["config"]
        assert "has_sendgrid_api_key" in config or "has_resend_api_key" in config
        assert "has_telegram_bot_token" in config
        assert "has_telegram_chat_id" in config
        assert "test_mode" in config
        print("PASS: Alert config has all channel fields")
    
    def test_alert_channel_status_reflects_readiness(self, auth_headers):
        """Test channel status reflects config readiness"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-alerts/config",
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200
        
        data = response.json()
        channels = data.get("channels", {})
        config = data.get("config", {})
        
        # In test mode, channels should be READY
        if config.get("test_mode"):
            # Test mode makes channels ready even without real credentials
            assert channels.get("email") in ["READY", "CONFIG_MISSING"]
            assert channels.get("telegram") in ["READY", "CONFIG_MISSING"]
        
        print("PASS: Channel status reflects readiness")
    
    def test_alert_config_update(self, auth_headers):
        """Test updating alert config"""
        # Update with test values
        update_payload = {
            "alert_from": "phase5-test@example.com",
            "alert_to": "test-recipient@example.com",
            "telegram_chat_id": "123456789",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin/system-alerts/config",
            json=update_payload,
            headers=auth_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Config update failed: {response.text[:200]}"
        
        data = response.json()
        config = data.get("config", {})
        assert config.get("alert_from") == "phase5-test@example.com"
        print("PASS: Alert config update works")


# =====================================================
# T-5.5: Fake Error Scenario Tests
# =====================================================

class TestFakeErrorScenario:
    """Test fake error scenario triggers error log/metric/alert evidence"""
    
    def test_fake_error_endpoint_accessible(self, auth_headers):
        """Test fake error endpoint is accessible"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/fake-error",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Fake error endpoint failed: {response.text[:200]}"
        print("PASS: Fake error endpoint accessible")
    
    def test_fake_error_returns_alert_id(self, auth_headers):
        """Test fake error returns alert_id"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/fake-error",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "alert_id" in data, "Missing alert_id in fake error response"
        assert data["alert_id"], "Empty alert_id"
        print(f"PASS: Fake error returned alert_id: {data['alert_id']}")
    
    def test_fake_error_delivery_status(self, auth_headers):
        """Test fake error has delivery status"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/fake-error",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "delivery_status" in data
        
        delivery = data["delivery_status"]
        # In test mode, should have SENT_TEST_SINK or other acceptable status
        acceptable_statuses = {"SENT", "SENT_TEST_SINK", "RATE_LIMITED", "CHANNEL_DISABLED", "CONFIG_MISSING"}
        
        for channel in ["email", "telegram"]:
            if channel in delivery:
                status = (delivery[channel].get("status") or "").upper()
                assert status in acceptable_statuses, f"Unexpected {channel} status: {status}"
        
        print("PASS: Fake error has valid delivery status")


# =====================================================
# T-5.6: Queue Pressure Scenario Tests
# =====================================================

class TestQueuePressureScenario:
    """Test queue pressure scenario triggers alert path"""
    
    def test_queue_pressure_endpoint_accessible(self, auth_headers):
        """Test queue pressure endpoint is accessible"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/queue-pressure",
            params={"queue_size": 45},
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Queue pressure endpoint failed: {response.text[:200]}"
        print("PASS: Queue pressure endpoint accessible")
    
    def test_queue_pressure_returns_correct_size(self, auth_headers):
        """Test queue pressure returns specified size"""
        test_queue_size = 50
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/queue-pressure",
            params={"queue_size": test_queue_size},
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("queue_size") == test_queue_size
        assert "threshold" in data
        assert isinstance(data.get("alert_ids"), list)
        print(f"PASS: Queue pressure returned size={data['queue_size']}, alert_ids={data['alert_ids']}")


# =====================================================
# T-5.7: Ready-Fail Scenario Tests
# =====================================================

class TestReadyFailScenario:
    """Test ready-fail scenario forces /ready non-200 and emits alert"""
    
    def test_ready_fail_endpoint_accessible(self, auth_headers):
        """Test ready-fail endpoint is accessible"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/ready-fail",
            params={"duration_seconds": 10},
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Ready-fail endpoint failed: {response.text[:200]}"
        print("PASS: Ready-fail endpoint accessible")
    
    def test_ready_fail_forces_not_ready(self, auth_headers):
        """Test ready-fail forces /ready to return 503"""
        # Trigger ready-fail with short duration
        fail_response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/ready-fail",
            params={"duration_seconds": 30},
            headers=auth_headers,
            timeout=30,
        )
        assert fail_response.status_code == 200
        
        data = fail_response.json()
        assert data.get("alert_id"), "Missing alert_id in ready-fail response"
        
        # Now check /ready - should be 503
        ready_response = requests.get(f"{BASE_URL}/api/ready", timeout=15)
        assert ready_response.status_code == 503, f"Expected 503, got {ready_response.status_code}"
        
        ready_data = ready_response.json()
        assert ready_data.get("status") == "not_ready"
        assert "ready_override" in ready_data.get("checks", {})
        assert ready_data["checks"]["ready_override"].get("status") == "not_ready"
        print("PASS: Ready-fail forces /ready to return 503")
    
    def test_ready_fail_emits_alert(self, auth_headers):
        """Test ready-fail emits alert"""
        response = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/ready-fail",
            params={"duration_seconds": 10},
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "alert_id" in data
        assert "delivery_status" in data
        print(f"PASS: Ready-fail emitted alert_id: {data['alert_id']}")


# =====================================================
# T-5.8: CI Gate Integration Tests
# =====================================================

class TestCIGateIntegration:
    """Test CI workflow contains phase5-observability-gate"""
    
    def test_ci_workflow_file_exists(self):
        """Test CI workflow file exists"""
        workflow_path = Path("/app/.github/workflows/deploy-gate.yml")
        assert workflow_path.exists(), "CI workflow file missing"
        print("PASS: CI workflow file exists")
    
    def test_ci_workflow_has_phase5_gate(self):
        """Test CI workflow contains phase5-observability-gate job"""
        workflow_path = Path("/app/.github/workflows/deploy-gate.yml")
        content = workflow_path.read_text(encoding="utf-8")
        
        assert "phase5-observability-gate:" in content, "Missing phase5-observability-gate job"
        assert "verify_phase5_observability.sh" in content, "Missing verify script call"
        print("PASS: CI workflow has phase5-observability-gate")
    
    def test_verify_script_exists(self):
        """Test verify script exists"""
        script_path = Path("/app/scripts/verify_phase5_observability.sh")
        assert script_path.exists(), "Verify script missing"
        print("PASS: Verify script exists")


# =====================================================
# Integration Tests - Full Workflow
# =====================================================

class TestFullObservabilityWorkflow:
    """Integration tests covering full observability workflow"""
    
    def test_full_observability_flow(self, auth_headers):
        """Test complete observability flow: health -> metrics -> fake-error -> ready"""
        # 1. Health check
        health = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert health.status_code == 200
        health_data = health.json()
        assert health_data.get("status") == "ok"
        
        # 2. Get initial metrics
        metrics1 = requests.get(f"{BASE_URL}/api/metrics", timeout=15)
        assert metrics1.status_code == 200
        assert "observability_error_rate_ratio" in metrics1.text
        
        # 3. Trigger fake error
        fake_error = requests.post(
            f"{BASE_URL}/api/ops-alerts/simulate/fake-error",
            headers=auth_headers,
            timeout=30,
        )
        assert fake_error.status_code == 200
        
        # 4. Get updated metrics
        metrics2 = requests.get(f"{BASE_URL}/api/metrics", timeout=15)
        assert metrics2.status_code == 200
        
        # 5. Ready check (should be 200 or 503 depending on state)
        ready = requests.get(f"{BASE_URL}/api/ready", timeout=15)
        assert ready.status_code in [200, 503]
        
        print("PASS: Full observability workflow completed")
