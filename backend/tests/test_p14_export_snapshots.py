"""
P1.4 Export & Snapshot Layer Backend Tests
Tests for:
- /api/health endpoint (database connectivity)
- /api/admin/export/revenue (CSV/XLSX)
- /api/admin/export/user-economics (CSV/XLSX)
- /api/admin/snapshots (list)
- /api/admin/snapshots/run (create/update)
- /api/admin/snapshots/compare (delta comparison)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": "canary.admin@platform.local",
            "password": "CanaryAdmin123!"
        }
    )
    if response.status_code != 200:
        pytest.skip("Admin login failed - cannot proceed with authenticated tests")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestHealthEndpoint:
    """FAZ1: Health endpoint tests - database connectivity"""

    def test_health_returns_200(self):
        """Health endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_health_database_reachable(self):
        """Database should be reachable (not database_unavailable)"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        db_check = data.get("checks", {}).get("database", {})
        assert db_check.get("reachable") is True, "Database should be reachable"
        assert db_check.get("last_error") is None, "Database should have no errors"


class TestExportRevenue:
    """FAZ3: Revenue export endpoint tests"""

    def test_export_revenue_csv_returns_200(self, auth_headers):
        """GET /api/admin/export/revenue?output=csv should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/export/revenue",
            params={"environment": "live", "output": "csv"},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    def test_export_revenue_csv_has_headers(self, auth_headers):
        """Revenue CSV should have correct column headers"""
        response = requests.get(
            f"{BASE_URL}/api/admin/export/revenue",
            params={"environment": "live", "output": "csv"},
            headers=auth_headers
        )
        assert response.status_code == 200
        content = response.text
        first_line = content.split("\n")[0]
        expected_columns = ["trade_time", "environment", "exchange", "symbol", "user_email", "revenue_amount_usd"]
        for col in expected_columns:
            assert col in first_line, f"Column {col} should be in CSV headers"

    def test_export_revenue_xlsx_returns_200(self, auth_headers):
        """GET /api/admin/export/revenue?output=xlsx should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/export/revenue",
            params={"environment": "live", "output": "xlsx"},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "spreadsheetml" in response.headers.get("content-type", "")

    def test_export_revenue_requires_auth(self):
        """Revenue export should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/export/revenue",
            params={"environment": "live", "output": "csv"}
        )
        assert response.status_code == 401


class TestExportUserEconomics:
    """FAZ3: User economics export endpoint tests"""

    def test_export_user_economics_csv_returns_200(self, auth_headers):
        """GET /api/admin/export/user-economics?output=csv should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/export/user-economics",
            params={"environment": "live", "output": "csv"},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    def test_export_user_economics_csv_has_headers(self, auth_headers):
        """User economics CSV should have correct column headers"""
        response = requests.get(
            f"{BASE_URL}/api/admin/export/user-economics",
            params={"environment": "live", "output": "csv"},
            headers=auth_headers
        )
        assert response.status_code == 200
        content = response.text
        first_line = content.split("\n")[0]
        expected_columns = ["user_id", "email", "ltv_usd", "revenue_contribution_usd", "churned"]
        for col in expected_columns:
            assert col in first_line, f"Column {col} should be in CSV headers"

    def test_export_user_economics_xlsx_returns_200(self, auth_headers):
        """GET /api/admin/export/user-economics?output=xlsx should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/export/user-economics",
            params={"environment": "live", "output": "xlsx"},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "spreadsheetml" in response.headers.get("content-type", "")

    def test_export_user_economics_requires_auth(self):
        """User economics export should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/export/user-economics",
            params={"environment": "live", "output": "csv"}
        )
        assert response.status_code == 401


class TestSnapshotsList:
    """FAZ3: Snapshots list endpoint tests"""

    def test_snapshots_list_returns_200(self, auth_headers):
        """GET /api/admin/snapshots should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots",
            params={"environment": "live", "snapshot_type": "daily", "limit": 50},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_snapshots_list_has_items(self, auth_headers):
        """Snapshots list should have at least 1 item"""
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots",
            params={"environment": "live", "snapshot_type": "daily", "limit": 50},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        assert len(items) >= 1, "Should have at least 1 snapshot"

    def test_snapshots_list_item_structure(self, auth_headers):
        """Snapshot items should have correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots",
            params={"environment": "live", "snapshot_type": "daily", "limit": 50},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        if items:
            item = items[0]
            assert "id" in item
            assert "snapshot_type" in item
            assert "environment" in item
            assert "snapshot_date" in item
            assert "kpis" in item

    def test_snapshots_list_requires_auth(self):
        """Snapshots list should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots",
            params={"environment": "live", "snapshot_type": "daily"}
        )
        assert response.status_code == 401


class TestSnapshotsRun:
    """FAZ3: Snapshot run endpoint tests"""

    def test_snapshots_run_returns_200(self, auth_headers):
        """POST /api/admin/snapshots/run should return 200"""
        response = requests.post(
            f"{BASE_URL}/api/admin/snapshots/run",
            params={
                "environment": "live",
                "snapshot_type": "daily",
                "churn_inactive_days": 30,
                "top_limit": 20
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_snapshots_run_returns_snapshot_id(self, auth_headers):
        """Snapshot run should return snapshot_id"""
        response = requests.post(
            f"{BASE_URL}/api/admin/snapshots/run",
            params={
                "environment": "live",
                "snapshot_type": "daily",
                "churn_inactive_days": 30,
                "top_limit": 20
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "snapshot_id" in data
        assert data.get("snapshot_type") == "daily"
        assert data.get("environment") == "live"

    def test_snapshots_run_returns_kpis(self, auth_headers):
        """Snapshot run should return KPIs in payload"""
        response = requests.post(
            f"{BASE_URL}/api/admin/snapshots/run",
            params={
                "environment": "live",
                "snapshot_type": "daily",
                "churn_inactive_days": 30,
                "top_limit": 20
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        payload = data.get("payload", {})
        kpis = payload.get("kpis", {})
        assert "total_revenue_usd" in kpis
        assert "total_users" in kpis

    def test_snapshots_run_requires_auth(self):
        """Snapshot run should require authentication"""
        response = requests.post(
            f"{BASE_URL}/api/admin/snapshots/run",
            params={"environment": "live", "snapshot_type": "daily"}
        )
        assert response.status_code == 401


class TestSnapshotsCompare:
    """FAZ3: Snapshot compare endpoint tests"""

    @pytest.fixture(scope="class")
    def snapshot_ids(self, auth_headers):
        """Get two snapshot IDs for comparison"""
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots",
            params={"environment": "live", "snapshot_type": "daily", "limit": 10},
            headers=auth_headers
        )
        if response.status_code != 200:
            pytest.skip("Cannot get snapshots for comparison")
        items = response.json().get("items", [])
        if len(items) < 2:
            pytest.skip("Need at least 2 snapshots for comparison")
        return items[1]["id"], items[0]["id"]  # base, target

    def test_snapshots_compare_returns_200(self, auth_headers, snapshot_ids):
        """GET /api/admin/snapshots/compare should return 200"""
        base_id, target_id = snapshot_ids
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots/compare",
            params={"base_snapshot_id": base_id, "target_snapshot_id": target_id},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_snapshots_compare_has_kpi_delta(self, auth_headers, snapshot_ids):
        """Compare should return KPI delta"""
        base_id, target_id = snapshot_ids
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots/compare",
            params={"base_snapshot_id": base_id, "target_snapshot_id": target_id},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        delta = data.get("delta", {})
        kpis = delta.get("kpis", [])
        assert len(kpis) > 0, "Should have KPI delta items"
        # Check KPI structure
        kpi = kpis[0]
        assert "metric" in kpi
        assert "from" in kpi
        assert "to" in kpi
        assert "delta" in kpi

    def test_snapshots_compare_has_top_users_delta(self, auth_headers, snapshot_ids):
        """Compare should return top users delta"""
        base_id, target_id = snapshot_ids
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots/compare",
            params={"base_snapshot_id": base_id, "target_snapshot_id": target_id},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        delta = data.get("delta", {})
        top_users = delta.get("top_users", [])
        # May be empty if no users, but structure should exist
        assert "top_users" in delta

    def test_snapshots_compare_has_segment_delta(self, auth_headers, snapshot_ids):
        """Compare should return segment delta"""
        base_id, target_id = snapshot_ids
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots/compare",
            params={"base_snapshot_id": base_id, "target_snapshot_id": target_id},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        delta = data.get("delta", {})
        segments = delta.get("segments", [])
        assert "segments" in delta

    def test_snapshots_compare_requires_auth(self):
        """Snapshot compare should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/snapshots/compare",
            params={"base_snapshot_id": "test", "target_snapshot_id": "test"}
        )
        assert response.status_code == 401
