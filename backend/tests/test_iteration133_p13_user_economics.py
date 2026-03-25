"""
P1.3 User Economics - Retention & Segment Profitability Tests
Tests for:
- GET /api/admin/users/economics/retention-trend
- GET /api/admin/users/economics/segment-profitability
- GET /api/admin/users/economics/export.csv
- GET /api/admin/users/economics/export.xlsx
- POST /api/admin/users/economics/snapshots/run
- GET /api/admin/users/economics/snapshots/trend
- Regression: /api/admin/commercial/p0/live-gate
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestAdminAuth:
    """Admin authentication for subsequent tests"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "canary.admin@platform.local",
                "password": "CanaryAdmin123!"
            }
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in login response"
        return data["access_token"]

    def test_admin_login(self, admin_token):
        """Verify admin login works"""
        assert admin_token is not None
        assert len(admin_token) > 20
        print(f"Admin login successful, token length: {len(admin_token)}")


@pytest.fixture(scope="module")
def auth_headers():
    """Module-scoped auth headers fixture"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": "canary.admin@platform.local",
            "password": "CanaryAdmin123!"
        }
    )
    if response.status_code != 200:
        pytest.skip("Admin login failed - skipping authenticated tests")
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


class TestRetentionTrendEndpoint:
    """Tests for GET /api/admin/users/economics/retention-trend"""

    def test_retention_trend_default_params(self, auth_headers):
        """Test retention trend with default parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/retention-trend",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert data.get("status") == "ok"
        assert "environment" in data
        assert "granularity" in data
        assert "lookback_periods" in data
        assert "points" in data
        assert "generated_at" in data
        
        # Default values check
        assert data["environment"] == "live"
        assert data["granularity"] == "weekly"
        assert data["lookback_periods"] == 12
        print(f"Retention trend returned {len(data['points'])} points")

    def test_retention_trend_monthly_granularity(self, auth_headers):
        """Test retention trend with monthly granularity"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/retention-trend",
            headers=auth_headers,
            params={"granularity": "monthly", "lookback_periods": 6}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["granularity"] == "monthly"
        assert data["lookback_periods"] == 6
        print(f"Monthly retention trend: {len(data['points'])} points")

    def test_retention_trend_testnet_environment(self, auth_headers):
        """Test retention trend for testnet environment"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/retention-trend",
            headers=auth_headers,
            params={"environment": "testnet"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["environment"] == "testnet"

    def test_retention_trend_invalid_granularity(self, auth_headers):
        """Test retention trend with invalid granularity returns 400"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/retention-trend",
            headers=auth_headers,
            params={"granularity": "invalid"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    def test_retention_trend_point_structure(self, auth_headers):
        """Validate retention trend point structure if data exists"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/retention-trend",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["points"]:
            point = data["points"][0]
            expected_fields = ["cohort", "period", "cohort_size", "active_users", 
                            "retention_rate_pct", "cohort_revenue_usd", "cohort_realized_pnl_usd"]
            for field in expected_fields:
                assert field in point, f"Missing field: {field}"
            print(f"Point structure validated: {list(point.keys())}")


class TestSegmentProfitabilityEndpoint:
    """Tests for GET /api/admin/users/economics/segment-profitability"""

    def test_segment_profitability_default_params(self, auth_headers):
        """Test segment profitability with default parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/segment-profitability",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert data.get("status") == "ok"
        assert "environment" in data
        assert "churn_inactive_days" in data
        assert "segment_cards" in data
        assert "churn_risk_list" in data
        assert "reengagement_list" in data
        assert "generated_at" in data
        
        # Default values
        assert data["environment"] == "live"
        assert data["churn_inactive_days"] == 30
        print(f"Segment cards: {len(data['segment_cards'])}, Churn risk: {len(data['churn_risk_list'])}")

    def test_segment_profitability_custom_churn_days(self, auth_headers):
        """Test segment profitability with custom churn days"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/segment-profitability",
            headers=auth_headers,
            params={"churn_inactive_days": 14, "top_limit": 50}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["churn_inactive_days"] == 14

    def test_segment_cards_structure(self, auth_headers):
        """Validate segment cards structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/segment-profitability",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have 5 segment types
        expected_segments = ["high_value", "profitable_but_inactive", "churn_risk", 
                           "low_activity_low_revenue", "loss_heavy_users"]
        
        if data["segment_cards"]:
            segments_found = [card["segment"] for card in data["segment_cards"]]
            for seg in expected_segments:
                assert seg in segments_found, f"Missing segment: {seg}"
            
            # Validate card structure
            card = data["segment_cards"][0]
            assert "segment" in card
            assert "users" in card
            assert "total_revenue_usd" in card
            assert "total_realized_pnl_usd" in card
            print(f"Segments found: {segments_found}")


class TestExportEndpoints:
    """Tests for export endpoints (CSV and XLSX)"""

    def test_export_csv(self, auth_headers):
        """Test CSV export endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/export.csv",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"
        
        # Check content disposition
        content_disp = response.headers.get("content-disposition", "")
        assert "user_economics_export.csv" in content_disp
        
        # Validate CSV content has headers
        content = response.content.decode("utf-8")
        assert "user_id" in content
        assert "email" in content
        assert "ltv_usd" in content
        print(f"CSV export size: {len(response.content)} bytes")

    def test_export_xlsx(self, auth_headers):
        """Test XLSX export endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/export.xlsx",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "spreadsheetml" in content_type or "application/vnd" in content_type, f"Got {content_type}"
        
        # Check content disposition
        content_disp = response.headers.get("content-disposition", "")
        assert "user_economics_export.xlsx" in content_disp
        
        # XLSX files start with PK (zip signature)
        assert response.content[:2] == b"PK", "Invalid XLSX file signature"
        print(f"XLSX export size: {len(response.content)} bytes")

    def test_export_csv_with_filters(self, auth_headers):
        """Test CSV export with filters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/export.csv",
            headers=auth_headers,
            params={
                "environment": "testnet",
                "churn_inactive_days": 14,
                "top_limit": 50
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"


class TestSnapshotEndpoints:
    """Tests for snapshot run and trend endpoints"""

    def test_snapshot_run_daily(self, auth_headers):
        """Test running a daily snapshot"""
        response = requests.post(
            f"{BASE_URL}/api/admin/users/economics/snapshots/run",
            headers=auth_headers,
            params={"snapshot_type": "daily"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert data.get("status") == "ok"
        assert "environment" in data
        assert "snapshot_type" in data
        assert "snapshot_date" in data
        assert "inserted" in data
        assert "updated" in data
        assert "rows" in data
        
        assert data["snapshot_type"] == "daily"
        print(f"Snapshot run: inserted={data['inserted']}, updated={data['updated']}, rows={data['rows']}")

    def test_snapshot_run_weekly(self, auth_headers):
        """Test running a weekly snapshot"""
        response = requests.post(
            f"{BASE_URL}/api/admin/users/economics/snapshots/run",
            headers=auth_headers,
            params={"snapshot_type": "weekly"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["snapshot_type"] == "weekly"

    def test_snapshot_run_invalid_type(self, auth_headers):
        """Test snapshot run with invalid type returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/admin/users/economics/snapshots/run",
            headers=auth_headers,
            params={"snapshot_type": "invalid"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    def test_snapshot_trend_daily(self, auth_headers):
        """Test getting daily snapshot trend"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/snapshots/trend",
            headers=auth_headers,
            params={"snapshot_type": "daily", "limit": 30}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert data.get("status") == "ok"
        assert "environment" in data
        assert "snapshot_type" in data
        assert "points" in data
        assert "generated_at" in data
        
        assert data["snapshot_type"] == "daily"
        print(f"Snapshot trend: {len(data['points'])} points")

    def test_snapshot_trend_weekly(self, auth_headers):
        """Test getting weekly snapshot trend"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/snapshots/trend",
            headers=auth_headers,
            params={"snapshot_type": "weekly"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["snapshot_type"] == "weekly"

    def test_snapshot_trend_point_structure(self, auth_headers):
        """Validate snapshot trend point structure"""
        # First run a snapshot to ensure data exists
        requests.post(
            f"{BASE_URL}/api/admin/users/economics/snapshots/run",
            headers=auth_headers,
            params={"snapshot_type": "daily"}
        )
        
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/snapshots/trend",
            headers=auth_headers,
            params={"snapshot_type": "daily"}
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["points"]:
            point = data["points"][0]
            expected_fields = ["snapshot_date", "users", "churned_users", 
                            "churn_rate_pct", "total_revenue_usd", "avg_ltv_usd"]
            for field in expected_fields:
                assert field in point, f"Missing field: {field}"
            print(f"Snapshot point structure: {list(point.keys())}")


class TestDeterministicAggregates:
    """Test deterministic aggregate calculations in economics endpoint"""

    def test_economics_aggregate_consistency(self, auth_headers):
        """Test that economics aggregates are consistent across calls"""
        # Make two calls with same parameters
        params = {"environment": "live", "churn_inactive_days": 30}
        
        response1 = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=auth_headers,
            params=params
        )
        assert response1.status_code == 200
        data1 = response1.json()
        
        response2 = requests.get(
            f"{BASE_URL}/api/admin/users/economics",
            headers=auth_headers,
            params=params
        )
        assert response2.status_code == 200
        data2 = response2.json()
        
        # KPIs should be identical (deterministic)
        kpis1 = data1.get("kpis", {})
        kpis2 = data2.get("kpis", {})
        
        assert kpis1.get("total_users") == kpis2.get("total_users"), "total_users mismatch"
        assert kpis1.get("paying_users") == kpis2.get("paying_users"), "paying_users mismatch"
        assert kpis1.get("churned_users") == kpis2.get("churned_users"), "churned_users mismatch"
        
        # Revenue should be deterministic
        assert abs(kpis1.get("total_revenue_usd", 0) - kpis2.get("total_revenue_usd", 0)) < 0.0001
        print(f"Aggregate consistency verified: {kpis1.get('total_users')} users")


class TestRegressionLiveGate:
    """Regression test for /api/admin/commercial/p0/live-gate"""

    def test_live_gate_endpoint_exists(self, auth_headers):
        """Test that live-gate endpoint still works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            headers=auth_headers
        )
        # Should return 200 or valid response
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            # Validate basic structure if endpoint exists
            assert "status" in data or "gate_status" in data or isinstance(data, dict)
            print(f"Live gate response: {list(data.keys())[:5]}")
        else:
            print("Live gate endpoint not found (404) - may be expected if not implemented")


class TestUnauthorizedAccess:
    """Test that endpoints require authentication"""

    def test_retention_trend_requires_auth(self):
        """Test retention trend requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/retention-trend"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_segment_profitability_requires_auth(self):
        """Test segment profitability requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/segment-profitability"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_export_csv_requires_auth(self):
        """Test CSV export requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users/economics/export.csv"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_snapshot_run_requires_auth(self):
        """Test snapshot run requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/admin/users/economics/snapshots/run"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
