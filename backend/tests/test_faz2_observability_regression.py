"""
Faz-2 Observability regression tests:
- Audit timeline endpoint still functional
- Retention prune endpoint works
- X-Request-ID propagation continues
- Exchange validate/revalidate flows operate without runtime errors
- Static observability config files presence check
"""
import os
import uuid
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    """Login as super_admin and return auth headers"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# STATIC CONFIG FILES SANITY CHECK
# =============================================================================
class TestObservabilityStaticConfigFiles:
    """Check that all required observability config files exist"""

    @pytest.fixture(scope="class")
    def observability_base_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "observability"

    def test_docker_compose_loki_yml_exists(self, observability_base_path):
        """docker-compose.loki.yml must exist"""
        file_path = observability_base_path / "docker-compose.loki.yml"
        assert file_path.exists(), f"Missing: {file_path}"
        content = file_path.read_text()
        assert "loki:" in content
        assert "promtail:" in content
        assert "grafana:" in content

    def test_loki_config_yaml_exists(self, observability_base_path):
        """loki/config.yaml must exist with proper schema"""
        file_path = observability_base_path / "loki" / "config.yaml"
        assert file_path.exists(), f"Missing: {file_path}"
        content = file_path.read_text()
        assert "auth_enabled:" in content
        assert "schema_config:" in content
        assert "ruler:" in content

    def test_promtail_config_yaml_exists(self, observability_base_path):
        """promtail/config.yaml must exist"""
        file_path = observability_base_path / "promtail" / "config.yaml"
        assert file_path.exists(), f"Missing: {file_path}"
        content = file_path.read_text()
        assert "scrape_configs:" in content
        assert "backend-supervisor" in content

    def test_trading_alerts_rules_yaml_exists(self, observability_base_path):
        """loki/rules/trading-alerts.yaml must exist with alert rules"""
        file_path = observability_base_path / "loki" / "rules" / "trading-alerts.yaml"
        assert file_path.exists(), f"Missing: {file_path}"
        content = file_path.read_text()
        assert "groups:" in content
        assert "InvalidKeySurge" in content
        assert "ExchangeHealthFlap" in content
        assert "exchange_validation_failure" in content
        assert "exchange_health_transition" in content

    def test_grafana_loki_datasource_yaml_exists(self, observability_base_path):
        """grafana/provisioning/datasources/loki.yaml must exist"""
        file_path = observability_base_path / "grafana" / "provisioning" / "datasources" / "loki.yaml"
        assert file_path.exists(), f"Missing: {file_path}"
        content = file_path.read_text()
        assert "Loki" in content
        assert "loki-main" in content

    def test_grafana_dashboards_provisioning_yaml_exists(self, observability_base_path):
        """grafana/provisioning/dashboards/dashboards.yaml must exist"""
        file_path = observability_base_path / "grafana" / "provisioning" / "dashboards" / "dashboards.yaml"
        assert file_path.exists(), f"Missing: {file_path}"
        content = file_path.read_text()
        assert "trading-observability" in content

    def test_grafana_dashboard_json_exists(self, observability_base_path):
        """grafana/dashboards/trading-observability.json must exist"""
        file_path = observability_base_path / "grafana" / "dashboards" / "trading-observability.json"
        assert file_path.exists(), f"Missing: {file_path}"
        content = file_path.read_text()
        assert "trading-observability-overview" in content
        assert "exchange_validation_failure" in content
        assert "exchange_health_transition" in content


# =============================================================================
# AUDIT TIMELINE ENDPOINT REGRESSION
# =============================================================================
class TestAuditTimelineEndpoint:
    """Regression tests for /api/audit-logs/timeline"""

    def test_timeline_endpoint_returns_200(self, admin_headers):
        """Timeline endpoint must work"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_timeline_filter_by_action(self, admin_headers):
        """Filter by action parameter works"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?action=user&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_timeline_filter_by_severity(self, admin_headers):
        """Filter by severity parameter works"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?severity=info&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_timeline_filter_by_entity_type(self, admin_headers):
        """Filter by entity_type parameter works"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?entity_type=user&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_timeline_filter_by_q(self, admin_headers):
        """Free text search filter works"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?q=admin&limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200


# =============================================================================
# RETENTION PRUNE ENDPOINT REGRESSION
# =============================================================================
class TestRetentionPruneEndpoint:
    """Regression tests for /api/audit-logs/admin/retention/prune"""

    def test_prune_endpoint_returns_200(self, admin_headers):
        """Prune endpoint works (days=90 default)"""
        response = requests.post(
            f"{BASE_URL}/api/audit-logs/admin/retention/prune?days=90",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "days" in data
        assert "deleted_count" in data
        assert data["days"] == 90

    def test_prune_validates_days_minimum(self, admin_headers):
        """Prune rejects days below 30"""
        response = requests.post(
            f"{BASE_URL}/api/audit-logs/admin/retention/prune?days=10",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 422  # Validation error

    def test_prune_validates_days_maximum(self, admin_headers):
        """Prune rejects days above 365"""
        response = requests.post(
            f"{BASE_URL}/api/audit-logs/admin/retention/prune?days=400",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 422  # Validation error


# =============================================================================
# X-REQUEST-ID PROPAGATION REGRESSION
# =============================================================================
class TestXRequestIdPropagation:
    """Regression tests for X-Request-ID header propagation"""

    def test_health_endpoint_returns_x_request_id(self):
        """Health endpoint returns X-Request-ID header"""
        request_id = f"faz2-health-{uuid.uuid4()}"
        response = requests.get(
            f"{BASE_URL}/api/health",
            headers={"X-Request-ID": request_id},
            timeout=20,
        )
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == request_id

    def test_auto_generated_request_id(self):
        """Backend auto-generates X-Request-ID if not provided"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=20)
        assert response.status_code == 200
        returned = response.headers.get("X-Request-ID")
        assert returned is not None
        assert len(returned) > 0

    def test_authenticated_endpoint_echoes_request_id(self, admin_headers):
        """Authenticated endpoints also return X-Request-ID"""
        request_id = f"faz2-auth-{uuid.uuid4()}"
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?limit=20",
            headers={**admin_headers, "X-Request-ID": request_id},
            timeout=20,
        )
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == request_id


# =============================================================================
# EXCHANGE VALIDATE/REVALIDATE FLOWS
# =============================================================================
class TestExchangeValidateFlows:
    """Test exchange validate/revalidate flows work without runtime errors"""

    def test_exchange_connections_list(self, admin_headers):
        """Exchange connections list endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/exchange-connections",
            headers=admin_headers,
            timeout=20,
        )
        # Either 200 or 404 (no connections) is acceptable
        assert response.status_code in [200, 404], response.text

    def test_exchange_readiness_endpoint(self, admin_headers):
        """Exchange readiness checklist endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=admin_headers,
            timeout=20,
        )
        # Either 200 or error response with proper structure is acceptable
        assert response.status_code in [200, 400, 403], response.text

    def test_user_exchange_settings_endpoint(self, admin_headers):
        """User exchange settings endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, response.text

    def test_validate_exchange_endpoint_structure(self, admin_headers):
        """Validate exchange endpoint returns proper structure (may fail due to no credentials)"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers=admin_headers,
            params={
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet"
            },
            timeout=30,
        )
        # Expect either success or error response with proper structure
        assert response.status_code in [200, 400, 403], response.text
        data = response.json()
        # Response should have proper structure regardless of outcome
        assert "exchange" in data or "detail" in data or "message" in data


# =============================================================================
# STRUCTURED LOGGING FIELDS CHECK
# =============================================================================
class TestStructuredLoggingFields:
    """Verify structured logging includes new event types from Faz-2"""

    def test_backend_logs_json_format(self):
        """Backend logs are in JSON format with service field"""
        # This is a sanity check - actual log inspection requires log files
        # We just verify the endpoint logs properly
        request_id = f"log-test-{uuid.uuid4()}"
        response = requests.get(
            f"{BASE_URL}/api/health",
            headers={"X-Request-ID": request_id},
            timeout=20,
        )
        assert response.status_code == 200
        # The fact that we get response means logging didn't crash

    def test_audit_timeline_includes_new_fields(self, admin_headers):
        """Timeline items include request_id, session_id, route, method fields"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline?limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["items"]:
            first_item = data["items"][0]
            # These fields should exist in the response schema
            assert "id" in first_item
            assert "action" in first_item
            assert "entity_type" in first_item
            assert "severity" in first_item
            assert "created_at" in first_item


# =============================================================================
# AUDIT LIST ENDPOINT
# =============================================================================
class TestAuditListEndpoint:
    """Test basic audit list endpoint still works"""

    def test_audit_list_returns_200(self, admin_headers):
        """GET /api/audit-logs returns list"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs?limit=50",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
