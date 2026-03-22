"""
Execution Control P1 Tests - Advanced Filters, Analytics Route, Incident Snapshot ZIP Export
Tests for:
- GET /api/admin-phase3/execution-analytics/summary (200, snapshot/filter metadata)
- GET /api/admin-phase3/execution-analytics/state-latency (200, rows/totals)
- GET /api/admin-phase3/execution-analytics/failure-trends (200, daily_trend/top_failure_classes)
- POST /api/admin-phase3/incident-snapshots/export (ZIP with required files)
- Empty data scenario for export (deterministic output)
- summary.json filter_scope, selected_scope_priority, scope_priority_order, scope_identifiers
- Multiple scope validation (422 when correlation_id + execution_event_id sent together)
"""

import io
import json
import os
import zipfile
from datetime import datetime, timezone

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
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for API requests"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestExecutionAnalyticsSummary:
    """Tests for GET /api/admin-phase3/execution-analytics/summary"""

    def test_summary_returns_200(self, auth_headers):
        """Summary endpoint returns 200 with snapshot/filter metadata"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify snapshot metadata
        assert "snapshot_at" in data, "Missing snapshot_at field"
        assert "filters" in data, "Missing filters field"
        assert "totals" in data, "Missing totals field"
        
        # Verify filter metadata structure
        filters = data["filters"]
        assert "state" in filters
        assert "source_type" in filters
        assert "symbol" in filters
        assert "strategy" in filters
        assert "status" in filters
        assert "correlation_id" in filters
        assert "time_from" in filters
        assert "time_to" in filters
        assert "snapshot_at" in filters
        
        # Verify totals structure
        totals = data["totals"]
        assert "transitions" in totals
        assert "events" in totals
        assert "failures" in totals
        
        # Verify metrics
        assert "latency_per_state" in data
        assert "timeout_metrics" in data
        assert "retry_metrics" in data
        assert "failure_metrics" in data

    def test_summary_with_filters(self, auth_headers):
        """Summary endpoint accepts filter parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
            params={
                "source_type": "simulation",
                "symbol": "BTCUSDT",
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify filters are reflected in response
        assert data["filters"]["source_type"] == "simulation"
        assert data["filters"]["symbol"] == "BTCUSDT"


class TestExecutionAnalyticsStateLatency:
    """Tests for GET /api/admin-phase3/execution-analytics/state-latency"""

    def test_state_latency_returns_200(self, auth_headers):
        """State latency endpoint returns 200 with rows/totals"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "snapshot_at" in data, "Missing snapshot_at field"
        assert "filters" in data, "Missing filters field"
        assert "totals" in data, "Missing totals field"
        assert "rows" in data, "Missing rows field"
        
        # Verify totals structure
        totals = data["totals"]
        assert "transitions" in totals
        assert "states" in totals
        
        # Verify rows structure (if any)
        if data["rows"]:
            row = data["rows"][0]
            assert "state" in row
            assert "count" in row
            assert "avg_latency_ms" in row
            assert "min_latency_ms" in row
            assert "max_latency_ms" in row


class TestExecutionAnalyticsFailureTrends:
    """Tests for GET /api/admin-phase3/execution-analytics/failure-trends"""

    def test_failure_trends_returns_200(self, auth_headers):
        """Failure trends endpoint returns 200 with daily_trend/top_failure_classes"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "snapshot_at" in data, "Missing snapshot_at field"
        assert "filters" in data, "Missing filters field"
        assert "totals" in data, "Missing totals field"
        assert "daily_trend" in data, "Missing daily_trend field"
        assert "top_failure_classes" in data, "Missing top_failure_classes field"
        
        # Verify totals structure
        totals = data["totals"]
        assert "failures" in totals
        assert "dead_letter_total" in totals
        assert "resolved_total" in totals
        
        # Verify daily_trend structure (if any)
        if data["daily_trend"]:
            trend = data["daily_trend"][0]
            assert "date" in trend
            assert "total_failures" in trend
            assert "dead_letter_count" in trend
            assert "resolved_count" in trend
            assert "open_count" in trend
        
        # Verify top_failure_classes structure (if any)
        if data["top_failure_classes"]:
            fc = data["top_failure_classes"][0]
            assert "failure_class" in fc
            assert "count" in fc


class TestIncidentSnapshotExport:
    """Tests for POST /api/admin-phase3/incident-snapshots/export"""

    def test_export_with_correlation_id_returns_zip(self, auth_headers):
        """Export with correlation_id scope returns valid ZIP"""
        # First create a simulation to get a correlation_id
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate",
            headers=auth_headers,
            params={
                "strategy_type": "breakout",
                "symbol": "BTCUSDT",
                "side": "long",
                "outcome": "filled",
                "source_type": "simulation",
                "environment": "simulation",
            },
        )
        
        if sim_response.status_code == 200:
            correlation_id = sim_response.json().get("correlation_id")
        else:
            correlation_id = "test-correlation-id-p1"
        
        # Export with correlation_id scope
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": correlation_id},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/zip"
        
        # Verify ZIP contents
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            
            # Required files
            required_files = [
                "summary.json",
                "trace.json",
                "events.csv",
                "transitions.csv",
                "failed_events.csv",
                "manual_actions.csv",
                "idempotency_collisions.csv",
            ]
            
            for required_file in required_files:
                assert required_file in file_names, f"Missing required file: {required_file}"
            
            # Verify summary.json structure
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            
            assert "filter_scope" in summary, "Missing filter_scope in summary.json"
            assert "selected_scope_priority" in summary, "Missing selected_scope_priority in summary.json"
            assert "scope_priority_order" in summary, "Missing scope_priority_order in summary.json"
            assert "scope_identifiers" in summary, "Missing scope_identifiers in summary.json"
            
            # Verify scope priority order
            assert summary["scope_priority_order"] == ["correlation_id", "execution_event_id", "time_range"]
            assert summary["selected_scope_priority"] == "correlation_id"

    def test_export_with_execution_event_id_returns_zip(self, auth_headers):
        """Export with execution_event_id scope returns valid ZIP"""
        # First create a simulation to get an execution_event_id
        sim_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate",
            headers=auth_headers,
            params={
                "strategy_type": "breakout",
                "symbol": "ETHUSDT",
                "side": "short",
                "outcome": "timeout",
                "source_type": "simulation",
                "environment": "simulation",
            },
        )
        
        if sim_response.status_code == 200:
            execution_event_id = sim_response.json().get("execution_event_id")
        else:
            execution_event_id = "test-event-id-p1"
        
        # Export with execution_event_id scope
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"execution_event_id": execution_event_id},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify ZIP contents
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            
            assert summary["selected_scope_priority"] == "execution_event_id"

    def test_export_with_time_range_returns_zip(self, auth_headers):
        """Export with time_range scope returns valid ZIP"""
        now = datetime.now(timezone.utc)
        time_from = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_to = now.isoformat()
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "time_from": time_from,
                "time_to": time_to,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify ZIP contents
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            
            assert summary["selected_scope_priority"] == "time_range"

    def test_export_empty_data_deterministic(self, auth_headers):
        """Export with non-existent correlation_id returns deterministic output"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": "non-existent-correlation-id-xyz"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify ZIP contents - files should exist with headers
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            
            # All required files should exist
            required_files = [
                "summary.json",
                "trace.json",
                "events.csv",
                "transitions.csv",
                "failed_events.csv",
                "manual_actions.csv",
                "idempotency_collisions.csv",
            ]
            
            for required_file in required_files:
                assert required_file in file_names, f"Missing required file in empty export: {required_file}"
            
            # CSV files should have headers even if empty
            events_csv = zf.read("events.csv").decode("utf-8")
            assert events_csv.strip(), "events.csv should have at least headers"
            
            transitions_csv = zf.read("transitions.csv").decode("utf-8")
            assert transitions_csv.strip(), "transitions.csv should have at least headers"

    def test_export_multiple_scopes_returns_422(self, auth_headers):
        """Export with multiple scopes (correlation_id + execution_event_id) returns 422"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": "test-correlation-id",
                "execution_event_id": "test-event-id",
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        
        # Verify error message
        data = response.json()
        assert "detail" in data
        assert "scope" in data["detail"].lower() or "tek" in data["detail"].lower()

    def test_export_correlation_id_and_time_range_returns_422(self, auth_headers):
        """Export with correlation_id + time_range returns 422"""
        now = datetime.now(timezone.utc)
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": "test-correlation-id",
                "time_from": now.isoformat(),
                "time_to": now.isoformat(),
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"

    def test_export_execution_event_id_and_time_range_returns_422(self, auth_headers):
        """Export with execution_event_id + time_range returns 422"""
        now = datetime.now(timezone.utc)
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "execution_event_id": "test-event-id",
                "time_from": now.isoformat(),
                "time_to": now.isoformat(),
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"

    def test_export_no_scope_returns_400(self, auth_headers):
        """Export without any scope returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"


class TestSummaryJsonFields:
    """Tests for summary.json field requirements"""

    def test_summary_json_has_all_required_fields(self, auth_headers):
        """summary.json contains filter_scope, selected_scope_priority, scope_priority_order, scope_identifiers"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": "test-summary-fields-check"},
        )
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            
            # Required fields
            assert "filter_scope" in summary, "Missing filter_scope"
            assert "selected_scope_priority" in summary, "Missing selected_scope_priority"
            assert "scope_priority_order" in summary, "Missing scope_priority_order"
            assert "scope_identifiers" in summary, "Missing scope_identifiers"
            
            # Verify scope_priority_order is correct
            expected_order = ["correlation_id", "execution_event_id", "time_range"]
            assert summary["scope_priority_order"] == expected_order, f"Wrong scope_priority_order: {summary['scope_priority_order']}"
            
            # Verify scope_identifiers structure
            identifiers = summary["scope_identifiers"]
            assert isinstance(identifiers, dict)


class TestScopePriorityValidation:
    """Tests for scope priority validation (correlation_id > execution_event_id > time_range)"""

    def test_scope_priority_correlation_id_first(self, auth_headers):
        """correlation_id has highest priority"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": "priority-test-corr"},
        )
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary = json.loads(zf.read("summary.json").decode("utf-8"))
            assert summary["selected_scope_priority"] == "correlation_id"

    def test_scope_priority_execution_event_id_second(self, auth_headers):
        """execution_event_id has second priority"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"execution_event_id": "priority-test-event"},
        )
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary = json.loads(zf.read("summary.json").decode("utf-8"))
            assert summary["selected_scope_priority"] == "execution_event_id"

    def test_scope_priority_time_range_third(self, auth_headers):
        """time_range has third priority"""
        now = datetime.now(timezone.utc)
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "time_from": now.replace(hour=0).isoformat(),
                "time_to": now.isoformat(),
            },
        )
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary = json.loads(zf.read("summary.json").decode("utf-8"))
            assert summary["selected_scope_priority"] == "time_range"


class TestAuthorizationGuards:
    """Tests for authorization requirements"""

    def test_analytics_summary_requires_auth(self):
        """Analytics summary requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin-phase3/execution-analytics/summary")
        assert response.status_code in [401, 403]

    def test_analytics_state_latency_requires_auth(self):
        """Analytics state latency requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency")
        assert response.status_code in [401, 403]

    def test_analytics_failure_trends_requires_auth(self):
        """Analytics failure trends requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends")
        assert response.status_code in [401, 403]

    def test_incident_export_requires_auth(self):
        """Incident export requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            json={"correlation_id": "test"},
        )
        assert response.status_code in [401, 403]
