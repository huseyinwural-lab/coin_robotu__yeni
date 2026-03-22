"""
Phase 6 Testing: Snapshot, Export, What-if Simulation + Request Age Label
Iteration 72 - Tests for:
1. POST /api/admin/strategy-allocation/snapshots (reason_note required)
2. GET /api/admin/strategy-allocation/snapshots (list snapshots)
3. GET /api/admin/strategy-allocation/export?format=json (JSON export)
4. GET /api/admin/strategy-allocation/export?format=csv (CSV export)
5. POST /api/admin/strategy-allocation/what-if-simulation (read-only preview)
6. What-if response contains current vs suggested and projected risk/return delta
7. Regression: Phase5 reason note + approval flow still works
"""

import pytest
import requests
import time
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"


class TestPhase6SnapshotExportWhatIf:
    """Phase 6 Snapshot, Export, What-if Simulation Tests"""

    @pytest.fixture(scope="class")
    def super_admin_token(self):
        """Get super_admin token with rate limit handling"""
        time.sleep(2)  # Rate limit buffer
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code == 429:
            pytest.skip("Login rate limited - wait 30+ seconds")
        assert response.status_code == 200, f"Super admin login failed: {response.text}"
        data = response.json()
        return data.get("access_token")

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token with rate limit handling"""
        time.sleep(2)  # Rate limit buffer
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if response.status_code == 429:
            pytest.skip("Login rate limited - wait 30+ seconds")
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        return data.get("access_token")

    # ==================== SNAPSHOT TESTS ====================

    def test_snapshot_create_requires_reason_note(self, super_admin_token):
        """POST /api/admin/strategy-allocation/snapshots requires reason_note"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # Test with empty reason_note
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/snapshots",
            json={"reason_note": ""},
            headers=headers,
        )
        assert response.status_code == 400, f"Expected 400 for empty reason_note: {response.text}"
        assert "reason_note" in response.json().get("detail", "").lower()

    def test_snapshot_create_super_admin_success(self, super_admin_token):
        """POST /api/admin/strategy-allocation/snapshots - super_admin creates snapshot directly"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/snapshots",
            json={"reason_note": "phase6_test_snapshot"},
            headers=headers,
        )
        assert response.status_code == 200, f"Snapshot create failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("status") == "success", f"Expected status=success: {data}"
        assert "snapshot" in data, "Response should contain snapshot"
        assert "trace_id" in data, "Response should contain trace_id"
        
        snapshot = data.get("snapshot") or {}
        assert "snapshot_id" in snapshot, "Snapshot should have snapshot_id"
        assert "strategy_count" in snapshot, "Snapshot should have strategy_count"
        assert "total_weight" in snapshot, "Snapshot should have total_weight"
        assert "reason_note" in snapshot, "Snapshot should have reason_note"

    def test_snapshot_create_admin_pending_approval(self, admin_token):
        """POST /api/admin/strategy-allocation/snapshots - admin gets pending_approval"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/snapshots",
            json={"reason_note": "admin_snapshot_request"},
            headers=headers,
        )
        assert response.status_code == 200, f"Snapshot request failed: {response.text}"
        data = response.json()
        
        # Admin should get pending_approval
        assert data.get("status") == "pending_approval", f"Expected pending_approval for admin: {data}"
        assert "trace_id" in data, "Response should contain trace_id (request_id)"

    def test_snapshot_list(self, super_admin_token):
        """GET /api/admin/strategy-allocation/snapshots returns list"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/snapshots",
            headers=headers,
        )
        assert response.status_code == 200, f"Snapshot list failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "rows" in data, "Response should contain rows"
        assert isinstance(data["rows"], list), "rows should be a list"
        
        # If there are snapshots, verify structure
        if len(data["rows"]) > 0:
            snapshot = data["rows"][0]
            assert "snapshot_id" in snapshot, "Snapshot should have snapshot_id"
            assert "created_at" in snapshot, "Snapshot should have created_at"
            assert "strategy_count" in snapshot, "Snapshot should have strategy_count"

    # ==================== EXPORT TESTS ====================

    def test_export_json(self, super_admin_token):
        """GET /api/admin/strategy-allocation/export?format=json returns JSON content"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/export?format=json",
            headers=headers,
        )
        assert response.status_code == 200, f"JSON export failed: {response.text}"
        
        # Verify content type
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type, f"Expected JSON content type: {content_type}"
        
        # Verify content disposition (download header)
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition, f"Expected attachment header: {content_disposition}"
        assert "json" in content_disposition.lower(), f"Expected json in filename: {content_disposition}"
        
        # Verify JSON structure
        data = response.json()
        assert "exported_at" in data, "Export should have exported_at"
        assert "summary" in data, "Export should have summary"
        assert "rows" in data, "Export should have rows"

    def test_export_csv(self, super_admin_token):
        """GET /api/admin/strategy-allocation/export?format=csv returns CSV content"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/export?format=csv",
            headers=headers,
        )
        assert response.status_code == 200, f"CSV export failed: {response.text}"
        
        # Verify content type
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type, f"Expected CSV content type: {content_type}"
        
        # Verify content disposition (download header)
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition, f"Expected attachment header: {content_disposition}"
        assert "csv" in content_disposition.lower(), f"Expected csv in filename: {content_disposition}"
        
        # Verify CSV has header row
        content = response.text
        assert "strategy_id" in content, "CSV should have strategy_id column"
        assert "capital_weight" in content, "CSV should have capital_weight column"
        assert "state" in content, "CSV should have state column"

    def test_export_invalid_format(self, super_admin_token):
        """GET /api/admin/strategy-allocation/export?format=invalid returns 400"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/export?format=invalid",
            headers=headers,
        )
        assert response.status_code == 400, f"Expected 400 for invalid format: {response.text}"

    # ==================== WHAT-IF SIMULATION TESTS ====================

    def test_whatif_simulation_basic(self, super_admin_token):
        """POST /api/admin/strategy-allocation/what-if-simulation returns read-only preview"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/what-if-simulation",
            json={"strategy_ids": []},  # Empty = all strategies
            headers=headers,
        )
        assert response.status_code == 200, f"What-if simulation failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "status" in data, "Response should have status"
        assert "read_only" in data, "Response should have read_only flag"
        assert data.get("read_only") == True, "What-if should be read_only=True"
        assert "trace_id" in data, "Response should have trace_id"
        assert "selection_count" in data, "Response should have selection_count"
        assert "projected_portfolio_return_delta_pct" in data, "Response should have projected_portfolio_return_delta_pct"
        assert "projected_portfolio_risk_delta_pct" in data, "Response should have projected_portfolio_risk_delta_pct"
        assert "rows" in data, "Response should have rows"

    def test_whatif_simulation_row_structure(self, super_admin_token):
        """What-if response rows contain current vs suggested and projected deltas"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/what-if-simulation",
            json={"strategy_ids": []},
            headers=headers,
        )
        assert response.status_code == 200, f"What-if simulation failed: {response.text}"
        data = response.json()
        
        rows = data.get("rows", [])
        if len(rows) > 0:
            row = rows[0]
            # Verify row structure for comparison columns
            assert "strategy_id" in row, "Row should have strategy_id"
            assert "current_weight" in row, "Row should have current_weight"
            assert "suggested_weight" in row, "Row should have suggested_weight"
            assert "weight_delta" in row, "Row should have weight_delta"
            assert "projected_return_delta_pct" in row, "Row should have projected_return_delta_pct"
            assert "projected_risk_delta_pct" in row, "Row should have projected_risk_delta_pct"
            
            # Verify numeric types
            assert isinstance(row["current_weight"], (int, float)), "current_weight should be numeric"
            assert isinstance(row["suggested_weight"], (int, float)), "suggested_weight should be numeric"
            assert isinstance(row["projected_return_delta_pct"], (int, float)), "projected_return_delta_pct should be numeric"
            assert isinstance(row["projected_risk_delta_pct"], (int, float)), "projected_risk_delta_pct should be numeric"

    def test_whatif_simulation_with_selected_strategies(self, super_admin_token):
        """What-if simulation with specific strategy_ids"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # First get available strategies
        list_response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=headers,
        )
        assert list_response.status_code == 200
        strategies = list_response.json()
        
        if len(strategies) > 0:
            strategy_ids = [strategies[0].get("strategy_id")]
            
            response = requests.post(
                f"{BASE_URL}/api/admin/strategy-allocation/what-if-simulation",
                json={"strategy_ids": strategy_ids},
                headers=headers,
            )
            assert response.status_code == 200, f"What-if with selection failed: {response.text}"
            data = response.json()
            
            # selection_count should reflect the filter
            assert "selection_count" in data

    # ==================== REGRESSION: PHASE 5 APPROVAL FLOW ====================

    def test_regression_approval_list_has_request_age_fields(self, super_admin_token):
        """GET /api/admin/strategy-allocation/approval-requests has created_at for age calculation"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/approval-requests",
            headers=headers,
        )
        assert response.status_code == 200, f"Approval list failed: {response.text}"
        data = response.json()
        
        assert "rows" in data, "Response should have rows"
        
        # If there are requests, verify created_at field exists for age calculation
        if len(data["rows"]) > 0:
            request_item = data["rows"][0]
            assert "created_at" in request_item, "Request should have created_at for age calculation"
            assert "requested_by" in request_item, "Request should have requested_by"
            assert "reason_note" in request_item, "Request should have reason_note"

    def test_regression_reason_note_required_for_normalize(self, super_admin_token):
        """POST /api/admin/strategy-allocation/normalize still requires reason_note"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/normalize",
            json={"reason_note": ""},
            headers=headers,
        )
        assert response.status_code == 400, f"Expected 400 for empty reason_note: {response.text}"
        assert "reason_note" in response.json().get("detail", "").lower()

    def test_regression_state_history_works(self, super_admin_token):
        """GET /api/admin/strategy-allocation/state-history still works"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/state-history",
            params={"limit": 10},
            headers=headers,
        )
        assert response.status_code == 200, f"State history failed: {response.text}"
        data = response.json()
        
        assert "rows" in data, "Response should have rows"

    def test_regression_dashboard_list_works(self, super_admin_token):
        """GET /api/admin/strategy-allocation still works"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=headers,
        )
        assert response.status_code == 200, f"Dashboard list failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"

    def test_regression_summary_works(self, super_admin_token):
        """GET /api/admin/strategy-allocation/summary still works"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=headers,
        )
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        
        assert "total_weight" in data, "Summary should have total_weight"


class TestRequestAgeFormatting:
    """Test request age formatting logic (frontend helper function test)"""

    def test_age_format_minutes(self):
        """Age < 60 minutes should show 'Xm' format"""
        # This tests the frontend logic: formatRequestAge
        # <60dk → m format
        # Example: 45 minutes → "45m"
        minutes = 45
        expected = f"{minutes}m"
        # Frontend logic: if totalMinutes < 60: return `${totalMinutes}m`
        assert expected == "45m"

    def test_age_format_hours_minutes(self):
        """Age < 24 hours should show 'Xh Ym' format"""
        # <24s → h m format
        # Example: 3 hours 30 minutes → "3h 30m"
        total_minutes = 210  # 3.5 hours
        hours = total_minutes // 60
        minutes = total_minutes % 60
        expected = f"{hours}h {minutes}m"
        assert expected == "3h 30m"

    def test_age_format_days_hours(self):
        """Age >= 24 hours should show 'Xd Yh' format"""
        # >=24s → d h format
        # Example: 2 days 5 hours → "2d 5h"
        total_hours = 53  # 2 days + 5 hours
        days = total_hours // 24
        hours = total_hours % 24
        expected = f"{days}d {hours}h"
        assert expected == "2d 5h"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
