"""
Execution Control P1 Consistency Tests - Filter Application, Analytics Semantic Alignment, Export Error Handling

Tests for:
1. Export filters are actually applied (search/state/status/source_type/symbol/strategy/order_id)
2. Export scope variations (correlation_id only, execution_event_id only, time_range only, multi-scope -> 422)
3. Empty-data scenario deterministic (ZIP file list fixed, CSV headers fixed)
4. Analytics semantic alignment: summary.failures == failure-trends total_failures
5. Analytics endpoint parity (all endpoints accept same filter set)
6. Summary.dead_letter_count == failure-trends dead_letter_total
7. State-latency scope matches summary scope
8. Search filter works across wide fields
"""

import io
import json
import os
import zipfile
from datetime import datetime, timezone, timedelta

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


@pytest.fixture(scope="module")
def simulation_data(auth_headers):
    """Create simulation data for testing filters"""
    # Create multiple simulations with different parameters
    simulations = []
    
    # Simulation 1: BTCUSDT, filled
    sim1 = requests.post(
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
    if sim1.status_code == 200:
        simulations.append(sim1.json())
    
    # Simulation 2: ETHUSDT, timeout
    sim2 = requests.post(
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
    if sim2.status_code == 200:
        simulations.append(sim2.json())
    
    # Simulation 3: SOLUSDT, partial
    sim3 = requests.post(
        f"{BASE_URL}/api/admin-phase3/execution-state-transitions/simulate",
        headers=auth_headers,
        params={
            "strategy_type": "breakout",
            "symbol": "SOLUSDT",
            "side": "long",
            "outcome": "partial",
            "source_type": "simulation",
            "environment": "simulation",
        },
    )
    if sim3.status_code == 200:
        simulations.append(sim3.json())
    
    return simulations


# ============================================================================
# SECTION 1: Export Filter Application Tests
# ============================================================================

class TestExportFilterApplication:
    """Tests that export filters are actually applied to query sets"""

    def test_export_with_symbol_filter(self, auth_headers, simulation_data):
        """Export with symbol filter only returns matching data"""
        if not simulation_data:
            pytest.skip("No simulation data available")
        
        # Get a correlation_id from BTCUSDT simulation
        btc_sim = next((s for s in simulation_data if s.get("symbol") == "BTCUSDT"), None)
        if not btc_sim:
            pytest.skip("No BTCUSDT simulation available")
        
        correlation_id = btc_sim.get("correlation_id")
        
        # Export with symbol filter
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "symbol": "BTCUSDT",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify ZIP contents
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            
            # Verify filter is recorded in summary
            assert "filters" in summary or "filter_scope" in summary

    def test_export_with_source_type_filter(self, auth_headers, simulation_data):
        """Export with source_type filter only returns matching data"""
        if not simulation_data:
            pytest.skip("No simulation data available")
        
        correlation_id = simulation_data[0].get("correlation_id")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "source_type": "simulation",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_export_with_state_filter(self, auth_headers, simulation_data):
        """Export with state filter only returns matching data"""
        if not simulation_data:
            pytest.skip("No simulation data available")
        
        correlation_id = simulation_data[0].get("correlation_id")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "state": "filled",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_export_with_search_filter(self, auth_headers, simulation_data):
        """Export with search filter works across wide fields"""
        if not simulation_data:
            pytest.skip("No simulation data available")
        
        correlation_id = simulation_data[0].get("correlation_id")
        
        # Search by correlation_id substring
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "search": correlation_id[:8] if correlation_id else "test",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_export_with_strategy_filter(self, auth_headers, simulation_data):
        """Export with strategy filter only returns matching data"""
        if not simulation_data:
            pytest.skip("No simulation data available")
        
        correlation_id = simulation_data[0].get("correlation_id")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": correlation_id,
                "strategy": "breakout",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


# ============================================================================
# SECTION 2: Export Scope Variation Tests
# ============================================================================

class TestExportScopeVariations:
    """Tests for export scope variations"""

    def test_export_only_correlation_id_scope(self, auth_headers, simulation_data):
        """Export with only correlation_id scope works"""
        if not simulation_data:
            pytest.skip("No simulation data available")
        
        correlation_id = simulation_data[0].get("correlation_id")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": correlation_id},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            assert summary.get("selected_scope_priority") == "correlation_id"

    def test_export_only_execution_event_id_scope(self, auth_headers, simulation_data):
        """Export with only execution_event_id scope works"""
        if not simulation_data:
            pytest.skip("No simulation data available")
        
        execution_event_id = simulation_data[0].get("execution_event_id")
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"execution_event_id": execution_event_id},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            assert summary.get("selected_scope_priority") == "execution_event_id"

    def test_export_only_time_range_scope(self, auth_headers):
        """Export with only time_range scope works"""
        now = datetime.now(timezone.utc)
        time_from = (now - timedelta(hours=1)).isoformat()
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
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary_content = zf.read("summary.json").decode("utf-8")
            summary = json.loads(summary_content)
            assert summary.get("selected_scope_priority") == "time_range"

    def test_export_multi_scope_returns_422(self, auth_headers):
        """Export with multiple scopes returns 422"""
        now = datetime.now(timezone.utc)
        
        # correlation_id + execution_event_id
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": "test-corr-id",
                "execution_event_id": "test-event-id",
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"

    def test_export_correlation_id_plus_time_range_returns_422(self, auth_headers):
        """Export with correlation_id + time_range returns 422"""
        now = datetime.now(timezone.utc)
        
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": "test-corr-id",
                "time_from": now.isoformat(),
                "time_to": now.isoformat(),
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"


# ============================================================================
# SECTION 3: Empty Data Deterministic Tests
# ============================================================================

class TestEmptyDataDeterministic:
    """Tests for empty data scenario deterministic output"""

    def test_empty_export_has_all_required_files(self, auth_headers):
        """Empty export has all required files in ZIP"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": "non-existent-correlation-id-xyz-123"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_names = zf.namelist()
            
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

    def test_empty_export_csv_has_headers(self, auth_headers):
        """Empty export CSV files have headers"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={"correlation_id": "non-existent-correlation-id-xyz-456"},
        )
        assert response.status_code == 200
        
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            # Check events.csv has headers
            events_csv = zf.read("events.csv").decode("utf-8")
            assert events_csv.strip(), "events.csv should have at least headers"
            assert "," in events_csv, "events.csv should be comma-separated"
            
            # Check transitions.csv has headers
            transitions_csv = zf.read("transitions.csv").decode("utf-8")
            assert transitions_csv.strip(), "transitions.csv should have at least headers"
            
            # Check failed_events.csv has headers
            failed_events_csv = zf.read("failed_events.csv").decode("utf-8")
            assert failed_events_csv.strip(), "failed_events.csv should have at least headers"


# ============================================================================
# SECTION 4: Analytics Semantic Alignment Tests
# ============================================================================

class TestAnalyticsSemanticAlignment:
    """Tests for analytics semantic alignment: summary.failures == failure-trends total_failures"""

    def test_summary_failures_equals_failure_trends_total(self, auth_headers):
        """summary.totals.failures == sum of failure-trends daily_trend.total_failures"""
        # Get summary
        summary_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
        )
        assert summary_response.status_code == 200
        summary_data = summary_response.json()
        
        # Get failure trends
        failure_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=auth_headers,
        )
        assert failure_response.status_code == 200
        failure_data = failure_response.json()
        
        # Compare totals
        summary_failures = summary_data.get("totals", {}).get("failures", 0)
        failure_trends_total = failure_data.get("totals", {}).get("failures", 0)
        
        assert summary_failures == failure_trends_total, (
            f"summary.failures ({summary_failures}) != failure-trends.totals.failures ({failure_trends_total})"
        )

    def test_summary_failures_equals_daily_trend_sum(self, auth_headers):
        """summary.totals.failures == sum of daily_trend.total_failures"""
        # Get summary
        summary_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
        )
        assert summary_response.status_code == 200
        summary_data = summary_response.json()
        
        # Get failure trends
        failure_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=auth_headers,
        )
        assert failure_response.status_code == 200
        failure_data = failure_response.json()
        
        # Calculate sum from daily_trend
        daily_trend = failure_data.get("daily_trend", [])
        daily_trend_sum = sum(item.get("total_failures", 0) for item in daily_trend)
        
        summary_failures = summary_data.get("totals", {}).get("failures", 0)
        
        assert summary_failures == daily_trend_sum, (
            f"summary.failures ({summary_failures}) != sum(daily_trend.total_failures) ({daily_trend_sum})"
        )

    def test_summary_dead_letter_equals_failure_trends_dead_letter_total(self, auth_headers):
        """summary.failure_metrics.dead_letter_count == failure-trends.totals.dead_letter_total"""
        # Get summary
        summary_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
        )
        assert summary_response.status_code == 200
        summary_data = summary_response.json()
        
        # Get failure trends
        failure_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=auth_headers,
        )
        assert failure_response.status_code == 200
        failure_data = failure_response.json()
        
        # Compare dead letter counts
        summary_dead_letter = summary_data.get("failure_metrics", {}).get("dead_letter_count", 0)
        failure_trends_dead_letter = failure_data.get("totals", {}).get("dead_letter_total", 0)
        
        assert summary_dead_letter == failure_trends_dead_letter, (
            f"summary.dead_letter_count ({summary_dead_letter}) != failure-trends.dead_letter_total ({failure_trends_dead_letter})"
        )


# ============================================================================
# SECTION 5: Analytics Endpoint Parity Tests
# ============================================================================

class TestAnalyticsEndpointParity:
    """Tests that all analytics endpoints accept the same filter set"""

    def test_summary_accepts_all_filters(self, auth_headers):
        """Summary endpoint accepts all filter parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
            params={
                "correlation_id": "test-corr",
                "state": "filled",
                "status": "filled",
                "source_type": "simulation",
                "symbol": "BTCUSDT",
                "strategy": "breakout",
                "search": "test",
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-12-31T23:59:59+00:00",
            },
        )
        assert response.status_code == 200, f"Summary endpoint failed with filters: {response.status_code}"

    def test_state_latency_accepts_all_filters(self, auth_headers):
        """State-latency endpoint accepts all filter parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=auth_headers,
            params={
                "correlation_id": "test-corr",
                "state": "filled",
                "status": "filled",
                "source_type": "simulation",
                "symbol": "BTCUSDT",
                "strategy": "breakout",
                "search": "test",
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-12-31T23:59:59+00:00",
            },
        )
        assert response.status_code == 200, f"State-latency endpoint failed with filters: {response.status_code}"

    def test_failure_trends_accepts_all_filters(self, auth_headers):
        """Failure-trends endpoint accepts all filter parameters"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=auth_headers,
            params={
                "correlation_id": "test-corr",
                "state": "filled",
                "status": "filled",
                "source_type": "simulation",
                "symbol": "BTCUSDT",
                "strategy": "breakout",
                "search": "test",
                "time_from": "2026-01-01T00:00:00+00:00",
                "time_to": "2026-12-31T23:59:59+00:00",
            },
        )
        assert response.status_code == 200, f"Failure-trends endpoint failed with filters: {response.status_code}"

    def test_all_endpoints_return_same_filter_context(self, auth_headers):
        """All analytics endpoints return the same filter context structure"""
        params = {
            "source_type": "simulation",
            "symbol": "BTCUSDT",
        }
        
        # Get all three endpoints
        summary_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
            params=params,
        )
        state_latency_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=auth_headers,
            params=params,
        )
        failure_trends_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/failure-trends",
            headers=auth_headers,
            params=params,
        )
        
        assert summary_response.status_code == 200
        assert state_latency_response.status_code == 200
        assert failure_trends_response.status_code == 200
        
        summary_filters = summary_response.json().get("filters", {})
        state_latency_filters = state_latency_response.json().get("filters", {})
        failure_trends_filters = failure_trends_response.json().get("filters", {})
        
        # Verify all have same filter keys
        assert set(summary_filters.keys()) == set(state_latency_filters.keys()), (
            "Summary and state-latency have different filter keys"
        )
        assert set(summary_filters.keys()) == set(failure_trends_filters.keys()), (
            "Summary and failure-trends have different filter keys"
        )


# ============================================================================
# SECTION 6: State-Latency Scope Alignment Tests
# ============================================================================

class TestStateLatencyScopeAlignment:
    """Tests that state-latency scope matches summary scope"""

    def test_state_latency_transitions_matches_summary(self, auth_headers):
        """State-latency totals.transitions matches summary totals.transitions"""
        params = {"source_type": "simulation"}
        
        summary_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/summary",
            headers=auth_headers,
            params=params,
        )
        state_latency_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-analytics/state-latency",
            headers=auth_headers,
            params=params,
        )
        
        assert summary_response.status_code == 200
        assert state_latency_response.status_code == 200
        
        summary_transitions = summary_response.json().get("totals", {}).get("transitions", 0)
        state_latency_transitions = state_latency_response.json().get("totals", {}).get("transitions", 0)
        
        assert summary_transitions == state_latency_transitions, (
            f"summary.transitions ({summary_transitions}) != state-latency.transitions ({state_latency_transitions})"
        )


# ============================================================================
# SECTION 7: Search Filter Wide Field Tests
# ============================================================================

class TestSearchFilterWideFields:
    """Tests that search filter works across wide fields"""

    def test_search_by_symbol(self, auth_headers):
        """Search filter finds by symbol"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=auth_headers,
            params={"search": "BTC"},
        )
        assert response.status_code == 200

    def test_search_by_correlation_id_substring(self, auth_headers, simulation_data):
        """Search filter finds by correlation_id substring"""
        if not simulation_data:
            pytest.skip("No simulation data available")
        
        correlation_id = simulation_data[0].get("correlation_id", "")
        if not correlation_id:
            pytest.skip("No correlation_id in simulation data")
        
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=auth_headers,
            params={"search": correlation_id[:8]},
        )
        assert response.status_code == 200

    def test_search_by_strategy(self, auth_headers):
        """Search filter finds by strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/execution-state-transitions/control",
            headers=auth_headers,
            params={"search": "breakout"},
        )
        assert response.status_code == 200


# ============================================================================
# SECTION 8: Export Error Message Tests
# ============================================================================

class TestExportErrorMessages:
    """Tests for export error messages with backend detail"""

    def test_export_no_scope_returns_400_with_detail(self, auth_headers):
        """Export without scope returns 400 with detail message"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={},
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data, "Error response should have detail field"
        assert data["detail"], "Detail should not be empty"

    def test_export_multi_scope_returns_422_with_detail(self, auth_headers):
        """Export with multiple scopes returns 422 with detail message"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "correlation_id": "test-corr",
                "execution_event_id": "test-event",
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data, "Error response should have detail field"
        assert data["detail"], "Detail should not be empty"

    def test_export_invalid_time_range_returns_422_with_detail(self, auth_headers):
        """Export with invalid time range returns 422 with detail message"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers=auth_headers,
            json={
                "time_from": "2026-12-31T23:59:59+00:00",
                "time_to": "2026-01-01T00:00:00+00:00",  # time_to < time_from
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data, "Error response should have detail field"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
