"""
P1.2 User Economics Testing - Iteration 132
Tests for:
- Migration/model: user_economics_aggregates table creation and no runtime crash
- GET /api/admin/users/economics endpoint returns 200 and deterministic
- Filters: environment/start_date/end_date/user_email/symbol/churn_inactive_days/cohort_month/top_limit
- KPI validation: LTV, ARPU, ARPPU, churn, total_users/paying_users
- Payload lists: top_users, churn_list, top_symbols, cohorts
- Regression: ingest/pnl/reconciliation/data-quality/live-gate not broken
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    data = response.json()
    token = data.get("access_token")
    if not token:
        pytest.skip("No access_token in login response")
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


class TestUserEconomicsEndpoint:
    """Tests for GET /api/admin/users/economics endpoint"""

    def test_economics_endpoint_returns_200(self, admin_headers):
        """Endpoint should return 200 with default parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"

    def test_economics_response_structure(self, admin_headers):
        """Response should have all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Check top-level fields
        assert "status" in data
        assert "environment" in data
        assert "filters" in data
        assert "sync" in data
        assert "kpis" in data
        assert "top_users" in data
        assert "churn_list" in data
        assert "top_symbols" in data
        assert "cohorts" in data
        assert "rows" in data
        assert "generated_at" in data

    def test_economics_kpis_structure(self, admin_headers):
        """KPIs should have all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        kpis = data.get("kpis", {})

        # Check KPI fields
        assert "total_users" in kpis
        assert "paying_users" in kpis
        assert "churned_users" in kpis
        assert "churn_rate_pct" in kpis
        assert "total_revenue_usd" in kpis
        assert "arpu_usd" in kpis
        assert "arppu_usd" in kpis
        assert "avg_ltv_usd" in kpis

        # Validate types
        assert isinstance(kpis["total_users"], int)
        assert isinstance(kpis["paying_users"], int)
        assert isinstance(kpis["churned_users"], int)
        assert isinstance(kpis["churn_rate_pct"], (int, float))
        assert isinstance(kpis["total_revenue_usd"], (int, float))
        assert isinstance(kpis["arpu_usd"], (int, float))
        assert isinstance(kpis["arppu_usd"], (int, float))
        assert isinstance(kpis["avg_ltv_usd"], (int, float))


class TestUserEconomicsFilters:
    """Tests for filter parameters"""

    def test_filter_environment_live(self, admin_headers):
        """Filter by environment=live"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"environment": "live"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("environment") == "live"
        assert data.get("filters", {}).get("environment") is None or data.get("environment") == "live"

    def test_filter_environment_testnet(self, admin_headers):
        """Filter by environment=testnet"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"environment": "testnet"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("environment") == "testnet"

    def test_filter_churn_inactive_days(self, admin_headers):
        """Filter by churn_inactive_days"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"churn_inactive_days": 14},
        )
        assert response.status_code == 200
        data = response.json()
        filters = data.get("filters", {})
        assert filters.get("churn_inactive_days") == 14

    def test_filter_top_limit(self, admin_headers):
        """Filter by top_limit"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"top_limit": 5},
        )
        assert response.status_code == 200
        data = response.json()
        filters = data.get("filters", {})
        assert filters.get("top_limit") == 5
        # top_users should have at most 5 items
        assert len(data.get("top_users", [])) <= 5

    def test_filter_start_date(self, admin_headers):
        """Filter by start_date"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"start_date": "2026-01-01T00:00:00Z"},
        )
        assert response.status_code == 200
        data = response.json()
        filters = data.get("filters", {})
        assert filters.get("start_date") == "2026-01-01T00:00:00Z"

    def test_filter_end_date(self, admin_headers):
        """Filter by end_date"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"end_date": "2026-12-31T23:59:59Z"},
        )
        assert response.status_code == 200
        data = response.json()
        filters = data.get("filters", {})
        assert filters.get("end_date") == "2026-12-31T23:59:59Z"

    def test_filter_symbol(self, admin_headers):
        """Filter by symbol"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"symbol": "BTCUSDT"},
        )
        assert response.status_code == 200
        data = response.json()
        filters = data.get("filters", {})
        assert filters.get("symbol") == "BTCUSDT"

    def test_filter_cohort_month(self, admin_headers):
        """Filter by cohort_month"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"cohort_month": "2026-03"},
        )
        assert response.status_code == 200
        data = response.json()
        filters = data.get("filters", {})
        assert filters.get("cohort_month") == "2026-03"

    def test_filter_user_email_not_found(self, admin_headers):
        """Filter by non-existent user_email should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"user_email": "nonexistent@example.com"},
        )
        assert response.status_code == 404
        data = response.json()
        assert data.get("detail") == "target_user_not_found"


class TestUserEconomicsDeterminism:
    """Tests for deterministic response"""

    def test_consecutive_calls_consistent(self, admin_headers):
        """Two consecutive calls should return consistent KPIs"""
        response1 = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"environment": "testnet"},
        )
        assert response1.status_code == 200
        data1 = response1.json()

        response2 = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
            params={"environment": "testnet"},
        )
        assert response2.status_code == 200
        data2 = response2.json()

        # KPIs should be consistent
        kpis1 = data1.get("kpis", {})
        kpis2 = data2.get("kpis", {})
        assert kpis1.get("total_users") == kpis2.get("total_users")
        assert kpis1.get("paying_users") == kpis2.get("paying_users")
        assert kpis1.get("total_revenue_usd") == kpis2.get("total_revenue_usd")


class TestUserEconomicsPayloadLists:
    """Tests for payload lists: top_users, churn_list, top_symbols, cohorts"""

    def test_top_users_structure(self, admin_headers):
        """top_users should have correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        top_users = data.get("top_users", [])

        if len(top_users) > 0:
            user = top_users[0]
            assert "user_id" in user
            assert "email" in user
            assert "ltv_usd" in user
            assert "revenue_contribution_usd" in user
            assert "realized_pnl_usd" in user
            assert "inactive_days" in user
            assert "churned" in user

    def test_churn_list_structure(self, admin_headers):
        """churn_list should have correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        churn_list = data.get("churn_list", [])

        if len(churn_list) > 0:
            user = churn_list[0]
            assert "user_id" in user
            assert "email" in user
            assert "inactive_days" in user
            assert "churned" in user
            # All users in churn_list should be churned
            assert user.get("churned") is True

    def test_top_symbols_structure(self, admin_headers):
        """top_symbols should have correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        top_symbols = data.get("top_symbols", [])

        if len(top_symbols) > 0:
            symbol = top_symbols[0]
            assert "symbol" in symbol
            assert "revenue_usd" in symbol

    def test_cohorts_structure(self, admin_headers):
        """cohorts should have correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        cohorts = data.get("cohorts", [])

        if len(cohorts) > 0:
            cohort = cohorts[0]
            assert "cohort_month" in cohort
            assert "users" in cohort
            assert "paying_users" in cohort
            assert "churned_users" in cohort
            assert "total_revenue_usd" in cohort
            assert "avg_ltv_usd" in cohort


class TestUserEconomicsSync:
    """Tests for sync field in response"""

    def test_sync_field_present(self, admin_headers):
        """sync field should be present and have status"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        sync = data.get("sync", {})
        assert "status" in sync
        assert sync.get("status") == "ok"


class TestRegressionExistingFlows:
    """Regression tests: existing flows should not be broken"""

    def test_ingest_rest_run_available(self, admin_headers):
        """Ingest REST run endpoint should be available"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial-ops/ingest/rest/run",
            headers=admin_headers,
            json={"environment": "testnet", "market_types": ["spot"]},
        )
        # Should not return 500
        assert response.status_code != 500, f"Ingest endpoint returned 500: {response.text}"

    def test_pnl_latest_available(self, admin_headers):
        """PnL latest endpoint should be available"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial-ops/pnl/latest",
            headers=admin_headers,
            params={"environment": "testnet"},
        )
        # Should not return 500
        assert response.status_code != 500, f"PnL endpoint returned 500: {response.text}"

    def test_reconciliation_run_available(self, admin_headers):
        """Reconciliation run endpoint should be available"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial-ops/reconciliation/run",
            headers=admin_headers,
            json={"environment": "testnet"},
        )
        # Should not return 500
        assert response.status_code != 500, f"Reconciliation endpoint returned 500: {response.text}"

    def test_data_quality_available(self, admin_headers):
        """Data quality endpoint should be available"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial-ops/data-quality",
            headers=admin_headers,
            params={"environment": "testnet"},
        )
        # Should not return 500
        assert response.status_code != 500, f"Data quality endpoint returned 500: {response.text}"

    def test_live_gate_available(self, admin_headers):
        """Live gate endpoint should be available"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial-ops/live-gate",
            headers=admin_headers,
            params={"environment": "testnet"},
        )
        # Should not return 500
        assert response.status_code != 500, f"Live gate endpoint returned 500: {response.text}"

    def test_revenue_summary_available(self, admin_headers):
        """Revenue summary endpoint should be available"""
        response = requests.get(
            f"{BASE_URL}/api/admin/revenue/summary",
            headers=admin_headers,
            params={"environment": "testnet"},
        )
        # Should not return 500
        assert response.status_code != 500, f"Revenue summary endpoint returned 500: {response.text}"


class TestUserEconomicsAuthorization:
    """Tests for authorization"""

    def test_unauthorized_access_rejected(self):
        """Endpoint should reject unauthorized access"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_invalid_token_rejected(self):
        """Endpoint should reject invalid token"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
