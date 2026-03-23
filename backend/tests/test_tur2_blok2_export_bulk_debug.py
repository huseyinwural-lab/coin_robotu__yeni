"""
Tur-2 / Blok-2 Test Suite:
- Export API: POST /api/admin/universe-monitor/export/job, GET /export/job/{id}, GET /export/jobs, GET /export/job/{id}/download, POST /export/job/{id}/retry
- Export contract: status/trace_id/message/state_snapshot + audit-first behavior
- Export async status lifecycle: pending->running->done/failed
- Bulk import preview/apply API: POST /universe/symbols/bulk-import/preview, POST /universe/symbols/bulk-import/apply, GET /universe/symbols/bulk-import/{preview_id}/errors.csv
- Bulk validation: invalid symbol, duplicate, blacklist conflict; partial success summary
- Debug policy backend: /api/debug/effective-universe super_admin only
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://exec-tuning.preview.emergentagent.com").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "quote.user@platform.local"
USER_PASSWORD = "QuoteUser123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def user_token():
    """Get regular user auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"User login failed: {response.status_code} - {response.text}")


@pytest.fixture
def admin_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


class TestExportJobAPI:
    """Export Job API Tests - POST /api/admin/universe-monitor/export/job and related endpoints"""

    def test_create_export_job_success(self, admin_headers):
        """Test creating an export job with valid parameters"""
        response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/export/job", headers=admin_headers, json={
            "range": "24h",
            "output_format": "csv",
            "metrics": ["latency_avg_ms", "pnl_sum"],
            "reason": "test_export_job_creation",
            "confirmation_phrase": "CREATE EXPORT JOB"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify contract fields
        assert "status" in data, "Missing status field"
        assert "trace_id" in data, "Missing trace_id field"
        assert "message" in data, "Missing message field"
        assert "state_snapshot" in data, "Missing state_snapshot field"
        assert "job_id" in data, "Missing job_id field"
        
        assert data["status"] == "success"
        assert data["state_snapshot"]["status"] == "pending"
        return data["job_id"]

    def test_create_export_job_wrong_phrase(self, admin_headers):
        """Test export job creation with wrong confirmation phrase"""
        response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/export/job", headers=admin_headers, json={
            "range": "24h",
            "output_format": "csv",
            "metrics": [],
            "reason": "test_wrong_phrase",
            "confirmation_phrase": "WRONG PHRASE"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    def test_list_export_jobs(self, admin_headers):
        """Test listing export jobs"""
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/export/jobs", headers=admin_headers, params={"limit": 30})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "count" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        
        # Verify item structure if items exist
        if data["items"]:
            item = data["items"][0]
            assert "job_id" in item
            assert "trace_id" in item
            assert "status" in item
            assert "params" in item
            assert "created_at" in item

    def test_get_export_job_by_id(self, admin_headers):
        """Test getting a specific export job by ID"""
        # First create a job
        create_response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/export/job", headers=admin_headers, json={
            "range": "1h",
            "output_format": "json",
            "metrics": [],
            "reason": "test_get_job_by_id",
            "confirmation_phrase": "CREATE EXPORT JOB"
        })
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]
        
        # Get the job
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/export/job/{job_id}", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data["job_id"] == job_id
        assert "trace_id" in data
        assert "status" in data
        assert data["status"] in ["pending", "running", "done", "failed"]

    def test_get_export_job_not_found(self, admin_headers):
        """Test getting a non-existent export job"""
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/export/job/non-existent-job-id", headers=admin_headers)
        assert response.status_code == 404

    def test_export_job_lifecycle(self, admin_headers):
        """Test export job status lifecycle: pending -> running -> done/failed"""
        # Create job
        create_response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/export/job", headers=admin_headers, json={
            "range": "1h",
            "output_format": "csv",
            "metrics": [],
            "reason": "test_lifecycle",
            "confirmation_phrase": "CREATE EXPORT JOB"
        })
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]
        
        # Initial status should be pending
        initial_status = create_response.json()["state_snapshot"]["status"]
        assert initial_status == "pending", f"Expected pending, got {initial_status}"
        
        # Wait for job to complete (async processing)
        time.sleep(3)
        
        # Check final status
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/export/job/{job_id}", headers=admin_headers)
        assert response.status_code == 200
        final_status = response.json()["status"]
        assert final_status in ["done", "failed", "running"], f"Unexpected status: {final_status}"

    def test_retry_export_job(self, admin_headers):
        """Test retrying an export job"""
        # Create a job first
        create_response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/export/job", headers=admin_headers, json={
            "range": "24h",
            "output_format": "csv",
            "metrics": [],
            "reason": "test_retry",
            "confirmation_phrase": "CREATE EXPORT JOB"
        })
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]
        
        # Wait for job to complete
        time.sleep(2)
        
        # Retry the job
        retry_response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/export/job/{job_id}/retry", headers=admin_headers, json={
            "reason": "test_retry_action",
            "confirmation_phrase": "CREATE EXPORT JOB"
        })
        assert retry_response.status_code == 200, f"Expected 200, got {retry_response.status_code}: {retry_response.text}"
        data = retry_response.json()
        
        assert data["status"] == "success"
        assert data["state_snapshot"]["status"] == "pending"

    def test_download_export_job(self, admin_headers):
        """Test downloading export job result"""
        # Create and wait for job
        create_response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/export/job", headers=admin_headers, json={
            "range": "1h",
            "output_format": "csv",
            "metrics": [],
            "reason": "test_download",
            "confirmation_phrase": "CREATE EXPORT JOB"
        })
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]
        
        # Wait for job to complete
        time.sleep(3)
        
        # Check if job is done
        status_response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/export/job/{job_id}", headers=admin_headers)
        job_status = status_response.json()["status"]
        
        if job_status == "done":
            # Try to download
            download_response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/export/job/{job_id}/download", headers=admin_headers)
            assert download_response.status_code == 200, f"Expected 200, got {download_response.status_code}"
            assert "text/csv" in download_response.headers.get("content-type", "")
        elif job_status == "failed":
            # Download should fail for failed jobs
            download_response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/export/job/{job_id}/download", headers=admin_headers)
            assert download_response.status_code == 409  # Conflict - job not ready


class TestBulkImportAPI:
    """Bulk Import Preview/Apply API Tests"""

    def test_bulk_import_preview_success(self, admin_headers):
        """Test bulk import preview with valid CSV"""
        csv_text = "BTCUSDT\nETHUSDT\nSOLUSDT"
        response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/preview", headers=admin_headers, json={
            "csv_text": csv_text,
            "reason": "test_bulk_preview",
            "confirmation_phrase": "PREVIEW BULK IMPORT"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify contract fields
        assert "status" in data
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "preview" in data
        
        preview = data["preview"]
        assert "total_input" in preview
        assert "valid_count" in preview
        assert "invalid_count" in preview
        assert "reason_counts" in preview
        assert "valid_symbols" in preview
        assert "invalid_items" in preview
        assert "preview_id" in preview
        
        return preview["preview_id"]

    def test_bulk_import_preview_invalid_symbols(self, admin_headers):
        """Test bulk import preview with invalid symbols"""
        csv_text = "BTC\nINVALID123456789012345\nETHUSDT"  # BTC too short, second too long
        response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/preview", headers=admin_headers, json={
            "csv_text": csv_text,
            "reason": "test_invalid_symbols",
            "confirmation_phrase": "PREVIEW BULK IMPORT"
        })
        assert response.status_code == 200
        data = response.json()
        preview = data["preview"]
        
        # Should have invalid symbols
        assert preview["invalid_count"] > 0
        assert "invalid_symbol" in preview["reason_counts"]

    def test_bulk_import_preview_duplicates(self, admin_headers):
        """Test bulk import preview with duplicate symbols"""
        csv_text = "BTCUSDT\nBTCUSDT\nETHUSDT"
        response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/preview", headers=admin_headers, json={
            "csv_text": csv_text,
            "reason": "test_duplicates",
            "confirmation_phrase": "PREVIEW BULK IMPORT"
        })
        assert response.status_code == 200
        data = response.json()
        preview = data["preview"]
        
        # Should detect duplicate
        assert preview["invalid_count"] >= 1
        assert "duplicate" in preview["reason_counts"]

    def test_bulk_import_apply_valid_only(self, admin_headers):
        """Test bulk import apply with apply_valid_only mode"""
        # First create a preview
        csv_text = "TESTUSDT1\nTESTUSDT2"
        preview_response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/preview", headers=admin_headers, json={
            "csv_text": csv_text,
            "reason": "test_apply_valid",
            "confirmation_phrase": "PREVIEW BULK IMPORT"
        })
        assert preview_response.status_code == 200
        preview_id = preview_response.json()["preview"]["preview_id"]
        
        # Apply the preview
        apply_response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/apply", headers=admin_headers, json={
            "preview_id": preview_id,
            "apply_mode": "apply_valid_only",
            "reason": "test_apply",
            "confirmation_phrase": "APPLY BULK IMPORT"
        })
        assert apply_response.status_code == 200, f"Expected 200, got {apply_response.status_code}: {apply_response.text}"
        data = apply_response.json()
        
        # Verify contract
        assert "status" in data
        assert "trace_id" in data
        assert "summary" in data
        
        summary = data["summary"]
        assert "processed_count" in summary
        assert "applied_count" in summary
        assert "rejected_count" in summary
        assert "reason_counts" in summary

    def test_bulk_import_apply_not_found(self, admin_headers):
        """Test bulk import apply with non-existent preview_id"""
        response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/apply", headers=admin_headers, json={
            "preview_id": "non-existent-preview-id",
            "apply_mode": "apply_valid_only",
            "reason": "test_not_found",
            "confirmation_phrase": "APPLY BULK IMPORT"
        })
        assert response.status_code == 404

    def test_bulk_import_errors_csv(self, admin_headers):
        """Test downloading errors CSV from bulk import"""
        # Create a preview with some invalid symbols
        csv_text = "BTC\nETHUSDT\nINVALID"
        preview_response = requests.post(f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/preview", headers=admin_headers, json={
            "csv_text": csv_text,
            "reason": "test_errors_csv",
            "confirmation_phrase": "PREVIEW BULK IMPORT"
        })
        assert preview_response.status_code == 200
        preview_id = preview_response.json()["preview"]["preview_id"]
        
        # Get errors CSV
        errors_response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/{preview_id}/errors.csv", headers=admin_headers)
        assert errors_response.status_code == 200, f"Expected 200, got {errors_response.status_code}"
        assert "text/csv" in errors_response.headers.get("content-type", "")
        
        # Verify CSV content
        content = errors_response.text
        assert "symbol" in content
        assert "reason" in content


class TestDebugPolicyAPI:
    """Debug Policy API Tests - /api/debug/effective-universe super_admin only"""

    def test_debug_effective_universe_super_admin_access(self, admin_headers):
        """Test that super_admin can access debug effective universe"""
        response = requests.get(f"{BASE_URL}/api/debug/effective-universe", headers=admin_headers, params={
            "market_type": "spot",
            "scanner_mode": "ALL_MARKET_SYMBOLS",
            "top_n": 100
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "market_symbols_count" in data or "scanner_mode" in data
        assert "generated_at" in data

    def test_debug_effective_universe_regular_user_denied(self, user_headers):
        """Test that regular user cannot access debug effective universe"""
        response = requests.get(f"{BASE_URL}/api/debug/effective-universe", headers=user_headers, params={
            "market_type": "spot",
            "scanner_mode": "ALL_MARKET_SYMBOLS",
            "top_n": 100
        })
        # Should be 403 Forbidden for non-super_admin
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_debug_effective_universe_no_auth(self):
        """Test that unauthenticated request is denied"""
        response = requests.get(f"{BASE_URL}/api/debug/effective-universe", params={
            "market_type": "spot",
            "scanner_mode": "ALL_MARKET_SYMBOLS",
            "top_n": 100
        })
        assert response.status_code == 401


class TestFreshnessAndKPIEndpoints:
    """Freshness SLA and KPI Recommendation endpoints"""

    def test_freshness_stale_list_empty_reason(self, admin_headers):
        """Test freshness stale list returns reason_if_empty when no stale entities"""
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/freshness/stale-list", headers=admin_headers, params={"limit": 200})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "items" in data
        assert "count" in data
        # If empty, should have reason_if_empty
        if data["count"] == 0:
            assert "reason_if_empty" in data
            assert data["reason_if_empty"] is not None

    def test_kpi_recommendation_active(self, admin_headers):
        """Test KPI active recommendations endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/recommendation/active", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "count" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_kpi_recommendation_history(self, admin_headers):
        """Test KPI recommendation history endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/recommendation/history", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "count" in data
        assert "items" in data


class TestMetricsHistoryEndpoint:
    """Metrics History / Trend endpoint tests"""

    def test_metrics_history_default(self, admin_headers):
        """Test metrics history with default parameters"""
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/metrics/history", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "latency_series" in data
        assert "pnl_series" in data
        assert "risk_veto_series" in data
        assert "overlays" in data

    def test_metrics_history_with_filters(self, admin_headers):
        """Test metrics history with symbol and strategy filters"""
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor/metrics/history", headers=admin_headers, params={
            "range": "7d",
            "symbol": "BTCUSDT",
            "strategy": "spot_pullback_v1"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestAutoRefreshAndGlobalError:
    """Tests for auto-refresh interval selector and global error banner behavior"""

    def test_universe_monitor_summary_endpoint(self, admin_headers):
        """Test main universe monitor summary endpoint for auto-refresh"""
        response = requests.get(f"{BASE_URL}/api/admin/universe-monitor", headers=admin_headers, params={
            "market_type": "spot",
            "scanner_mode": "ALL_MARKET_SYMBOLS",
            "top_n": 200
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify key fields for auto-refresh
        assert "market_type" in data
        assert "scanner_mode" in data
        assert "generated_at" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
