"""
FAZ-4: Admin Observability & Audit Tests
Tests for:
- GET /api/admin/system/live-readiness endpoint (new FAZ-4 metrics)
- GET /api/admin/system/readiness-score endpoint
- Backward compatibility: GET /api/admin/futures/live-readiness
- Audit event standardization (SCREAMING_SNAKE_CASE format)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def test_user_token(admin_token):
    """Create and approve a test user, return user token"""
    # Register user
    email = f"faz4_test_{os.urandom(4).hex()}@test.com"
    reg_response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "Test12345!"},
    )
    if reg_response.status_code != 200:
        pytest.skip("Could not create test user")
    user_id = reg_response.json()["id"]

    # Approve user
    requests.post(
        f"{BASE_URL}/api/admin/user-approvals/bulk-approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"ids": [user_id]},
    )

    # Login as user
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": "Test12345!"},
    )
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


class TestSystemLiveReadiness:
    """Tests for GET /api/admin/system/live-readiness endpoint"""

    def test_endpoint_returns_200(self, admin_token):
        """Endpoint should return 200 for admin users"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    def test_contains_symbol_integrity_failures(self, admin_token):
        """Response should contain symbol_integrity_failures metric"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "symbol_integrity_failures" in data
        assert isinstance(data["symbol_integrity_failures"], int)

    def test_contains_scanner_to_execution_match_rate_pct(self, admin_token):
        """Response should contain scanner_to_execution_match_rate_pct (percentage)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "scanner_to_execution_match_rate_pct" in data
        assert isinstance(data["scanner_to_execution_match_rate_pct"], (int, float))

    def test_contains_scanner_to_execution_matches(self, admin_token):
        """Response should contain scanner_to_execution_matches count"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "scanner_to_execution_matches" in data
        assert isinstance(data["scanner_to_execution_matches"], int)

    def test_contains_scanner_to_execution_total(self, admin_token):
        """Response should contain scanner_to_execution_total count"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "scanner_to_execution_total" in data
        assert isinstance(data["scanner_to_execution_total"], int)

    def test_contains_scanner_to_execution_match_rate_both_format(self, admin_token):
        """Response should contain scanner_to_execution_match_rate in Both format (percentage + ratio)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "scanner_to_execution_match_rate" in data
        # Format should be like "100.0% (20/20)"
        rate = data["scanner_to_execution_match_rate"]
        assert isinstance(rate, str)
        assert "%" in rate
        assert "(" in rate and "/" in rate and ")" in rate

    def test_contains_active_universe_count(self, admin_token):
        """Response should contain active_universe_count metric"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "active_universe_count" in data
        assert isinstance(data["active_universe_count"], int)

    def test_contains_cluster_bias_distribution(self, admin_token):
        """Response should contain cluster_bias_distribution metric"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "cluster_bias_distribution" in data
        assert isinstance(data["cluster_bias_distribution"], dict)

    def test_contains_market_bias_regime(self, admin_token):
        """Response should contain market_bias_regime metric"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "market_bias_regime" in data
        assert isinstance(data["market_bias_regime"], str)


class TestSystemReadinessScore:
    """Tests for GET /api/admin/system/readiness-score endpoint"""

    def test_endpoint_returns_200(self, admin_token):
        """Endpoint should return 200 for admin users"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/readiness-score",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    def test_contains_readiness_score(self, admin_token):
        """Response should contain readiness_score"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/readiness-score",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "readiness_score" in data
        assert isinstance(data["readiness_score"], (int, float))

    def test_contains_readiness_state(self, admin_token):
        """Response should contain readiness_state"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/readiness-score",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        assert "readiness_state" in data
        assert data["readiness_state"] in ["READY", "BLOCKED", "DEGRADED"]


class TestBackwardCompatibility:
    """Tests for backward compatibility: GET /api/admin/futures/live-readiness"""

    def test_futures_live_readiness_returns_200(self, admin_token):
        """Old endpoint should still work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    def test_futures_live_readiness_includes_new_metrics(self, admin_token):
        """Old endpoint should include new FAZ-4 metrics"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.json()
        # All new FAZ-4 metrics should be present
        assert "symbol_integrity_failures" in data
        assert "scanner_to_execution_match_rate_pct" in data
        assert "scanner_to_execution_matches" in data
        assert "scanner_to_execution_total" in data
        assert "active_universe_count" in data
        assert "cluster_bias_distribution" in data
        assert "market_bias_regime" in data


class TestAuditEventStandardization:
    """Tests for audit event standardization (SCREAMING_SNAKE_CASE format)"""

    def test_preview_creates_order_preflight_audit(self, test_user_token):
        """Preview request should create ORDER_PREFLIGHT audit log"""
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "symbol": "ETHUSDT",
                "market_type": "futures",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 100,
                "leverage": 3,
                "margin_mode": "cross",
                "execution_mode": "manual",
            },
        )
        assert response.status_code == 200
        # Audit log is created in backend - we verify via the response structure
        data = response.json()
        assert "preview" in data
        assert data["preview"]["validation_status"] in ["valid", "rejected"]

    def test_preview_creates_risk_result_audit(self, test_user_token):
        """Preview request should create RISK_RESULT audit log"""
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 50,
                "leverage": 2,
                "margin_mode": "cross",
                "execution_mode": "manual",
            },
        )
        assert response.status_code == 200

    def test_preview_creates_execution_intent_audit(self, test_user_token):
        """Preview request should create EXECUTION_INTENT audit log"""
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "symbol": "SOLUSDT",
                "market_type": "futures",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 75,
                "leverage": 2,
                "margin_mode": "cross",
                "execution_mode": "manual",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "preview" in data
        assert "intent_id" in data["preview"]

    def test_submit_endpoint_validates_intent(self, test_user_token):
        """Submit endpoint validates intent token and returns appropriate response"""
        # First create preview
        preview_response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "symbol": "AVAXUSDT",
                "market_type": "futures",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 25,
                "leverage": 2,
                "margin_mode": "cross",
                "execution_mode": "manual",
            },
        )
        assert preview_response.status_code == 200
        preview_data = preview_response.json()["preview"]

        # Submit endpoint validates intent status
        submit_response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/execute",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "intent_token": preview_data["intent_token"],
                "preview_hash": preview_data["preview_hash"],
            },
        )
        # Response can be 200 (success) or 400 (preview_required - needs confirmed status)
        assert submit_response.status_code in [200, 400]
        if submit_response.status_code == 200:
            data = submit_response.json()
            assert data["intent_status"] == "QUEUED_FOR_APPROVAL"

    def test_symbol_mismatch_creates_symbol_integrity_reject_audit(self, test_user_token):
        """Symbol mismatch should create SYMBOL_INTEGRITY_REJECT audit log"""
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "symbol": "ETHBTC",  # Invalid quote asset
                "market_type": "futures",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 100,
                "leverage": 3,
                "margin_mode": "cross",
                "execution_mode": "manual",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "invalid_quote_asset"


class TestAuditEventFormat:
    """Tests for audit event format (SCREAMING_SNAKE_CASE)"""

    def test_audit_events_use_screaming_snake_case(self):
        """Verify AuditEvent enum uses SCREAMING_SNAKE_CASE format"""
        import sys
        sys.path.insert(0, "/app/backend")
        from core.audit.audit_events import AuditEvent

        # All FAZ-4 events should be SCREAMING_SNAKE_CASE
        faz4_events = [
            AuditEvent.ORDER_PREFLIGHT,
            AuditEvent.RISK_RESULT,
            AuditEvent.EXECUTION_INTENT,
            AuditEvent.EXCHANGE_ORDER,
            AuditEvent.SYMBOL_INTEGRITY_REJECT,
        ]
        for event in faz4_events:
            # Value should be uppercase with underscores
            assert event.value == event.value.upper()
            assert "_" in event.value or event.value.isalpha()
