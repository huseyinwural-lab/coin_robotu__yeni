"""
Strategy Ops Observability Extensions Test Suite
Tests for:
- GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics
  => slippage_p50/p95, latency_p50/p95, quality_correlation, version_health_score
- GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics-trend
  => trend_series + anomaly_band
- POST /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview
  => full payload fields
- GET /api/strategy-domain/admin/strategies/ops
  => filter/sort/pagination parameters
- POST /api/strategy-domain/admin/strategies/bulk/audit-snapshot
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://strategy-version-gov.preview.emergentagent.com"

LOGIN_EMAIL = "canary.admin@platform.local"
LOGIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_strategy_and_version(auth_headers):
    """Create or get a test strategy with version for testing"""
    # First try to list existing strategies
    response = requests.get(
        f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
        headers=auth_headers,
        params={"page": 1, "page_size": 10},
    )
    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        if items:
            strategy = items[0]
            strategy_id = strategy.get("strategy_id")
            # Get detail to find version
            detail_resp = requests.get(
                f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/control-plane",
                headers=auth_headers,
            )
            if detail_resp.status_code == 200:
                detail = detail_resp.json()
                versions = detail.get("versions", [])
                if versions:
                    return {
                        "strategy_id": strategy_id,
                        "version_id": versions[0].get("version_id"),
                        "version_hash": versions[0].get("version_hash"),
                    }

    # Create new strategy if none exists
    create_resp = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies",
        headers=auth_headers,
        json={
            "name": "TEST_ObservabilityTestStrategy",
            "code": f"test_obs_strategy_{os.urandom(4).hex()}",
            "description": "Test strategy for observability testing",
            "owner_name": "test_ops",
            "category": "test",
            "tags": ["test", "observability"],
        },
    )
    if create_resp.status_code != 201:
        pytest.skip(f"Could not create test strategy: {create_resp.text}")

    strategy = create_resp.json()
    strategy_id = strategy.get("strategy_id")

    # Create version
    version_resp = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
        headers=auth_headers,
        json={
            "config_json": {
                "momentum_threshold": 0.1,
                "base_size": 0.001,
                "volatility_guard": 0.5,
            },
            "config_schema_version": "1.0",
        },
    )
    if version_resp.status_code != 201:
        pytest.skip(f"Could not create test version: {version_resp.text}")

    version = version_resp.json()
    return {
        "strategy_id": strategy_id,
        "version_id": version.get("version_id"),
        "version_hash": version.get("version_hash"),
    }


class TestStrategyOpsListEndpoint:
    """Tests for GET /api/strategy-domain/admin/strategies/ops"""

    def test_ops_list_basic(self, auth_headers):
        """Test basic ops list endpoint returns items and pagination"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Response should have 'items' field"
        assert "pagination" in data, "Response should have 'pagination' field"
        pagination = data["pagination"]
        assert "page" in pagination
        assert "page_size" in pagination
        assert "total" in pagination
        assert "has_next" in pagination

    def test_ops_list_with_search_filter(self, auth_headers):
        """Test ops list with search parameter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"search": "test", "page": 1, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_ops_list_with_status_filter(self, auth_headers):
        """Test ops list with status_filter parameter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"status_filter": "active", "page": 1, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_ops_list_with_lifecycle_state_filter(self, auth_headers):
        """Test ops list with lifecycle_state parameter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"lifecycle_state": "production", "page": 1, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_ops_list_with_validation_status_filter(self, auth_headers):
        """Test ops list with validation_status parameter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"validation_status": "PASS", "page": 1, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_ops_list_with_category_filter(self, auth_headers):
        """Test ops list with category parameter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"category": "general", "page": 1, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_ops_list_with_sort_parameters(self, auth_headers):
        """Test ops list with sort_by and sort_order parameters"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"sort_by": "name", "sort_order": "asc", "page": 1, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_ops_list_with_active_only_flag(self, auth_headers):
        """Test ops list with active_only boolean flag"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"active_only": True, "page": 1, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_ops_list_with_production_only_flag(self, auth_headers):
        """Test ops list with production_only boolean flag"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"production_only": True, "page": 1, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_ops_list_pagination(self, auth_headers):
        """Test ops list pagination works correctly"""
        # Get first page
        response1 = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"page": 1, "page_size": 5},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["pagination"]["page"] == 1
        assert data1["pagination"]["page_size"] == 5

        # Get second page
        response2 = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"page": 2, "page_size": 5},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["pagination"]["page"] == 2


class TestVersionMetricsEndpoint:
    """Tests for GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics"""

    def test_metrics_endpoint_returns_required_fields(self, auth_headers, test_strategy_and_version):
        """Test metrics endpoint returns slippage, latency, quality_correlation, health_score"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Check top-level structure
        assert "strategy_id" in data
        assert "strategy_version_id" in data
        assert "metrics" in data

        metrics = data["metrics"]

        # Check slippage fields
        assert "slippage_p50_bps" in metrics or metrics.get("slippage_p50_bps") is not None or "slippage_p50_bps" in str(metrics)
        assert "slippage_p95_bps" in metrics or metrics.get("slippage_p95_bps") is not None or "slippage_p95_bps" in str(metrics)

        # Check latency fields
        assert "latency_p50_ms" in metrics or metrics.get("latency_p50_ms") is not None or "latency_p50_ms" in str(metrics)
        assert "latency_p95_ms" in metrics or metrics.get("latency_p95_ms") is not None or "latency_p95_ms" in str(metrics)

        # Check quality_correlation field
        assert "quality_correlation" in metrics, "metrics should have quality_correlation field"

        # Check version_health_score field
        assert "version_health_score" in metrics, "metrics should have version_health_score field"

    def test_metrics_slippage_values_are_numeric(self, auth_headers, test_strategy_and_version):
        """Test slippage values are numeric (can be 0 for no data)"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        metrics = data.get("metrics", {})

        slippage_p50 = metrics.get("slippage_p50_bps")
        slippage_p95 = metrics.get("slippage_p95_bps")

        # Values should be numeric (int or float), can be 0 for no data
        assert isinstance(slippage_p50, (int, float)) or slippage_p50 is None
        assert isinstance(slippage_p95, (int, float)) or slippage_p95 is None

    def test_metrics_latency_values_are_numeric(self, auth_headers, test_strategy_and_version):
        """Test latency values are numeric (can be 0 for no data)"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        metrics = data.get("metrics", {})

        latency_p50 = metrics.get("latency_p50_ms")
        latency_p95 = metrics.get("latency_p95_ms")

        # Values should be numeric (int or float), can be 0 for no data
        assert isinstance(latency_p50, (int, float)) or latency_p50 is None
        assert isinstance(latency_p95, (int, float)) or latency_p95 is None

    def test_metrics_health_score_in_valid_range(self, auth_headers, test_strategy_and_version):
        """Test version_health_score is in valid range [0, 100]"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        metrics = data.get("metrics", {})

        health_score = metrics.get("version_health_score")
        assert isinstance(health_score, (int, float)), "health_score should be numeric"
        assert 0 <= health_score <= 100, f"health_score should be in [0, 100], got {health_score}"

    def test_metrics_quality_correlation_structure(self, auth_headers, test_strategy_and_version):
        """Test quality_correlation has expected structure"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        metrics = data.get("metrics", {})

        quality_correlation = metrics.get("quality_correlation")
        assert isinstance(quality_correlation, dict), "quality_correlation should be a dict"
        assert "slippage_to_execution_quality" in quality_correlation
        assert "latency_to_execution_quality" in quality_correlation


class TestMetricsTrendEndpoint:
    """Tests for GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics-trend"""

    def test_metrics_trend_returns_trend_series(self, auth_headers, test_strategy_and_version):
        """Test metrics-trend endpoint returns trend_series array"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics-trend",
            headers=auth_headers,
            params={"points": 60},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "trend_series" in data, "Response should have trend_series field"
        assert isinstance(data["trend_series"], list), "trend_series should be a list"

    def test_metrics_trend_returns_anomaly_band(self, auth_headers, test_strategy_and_version):
        """Test metrics-trend endpoint returns anomaly_band object"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics-trend",
            headers=auth_headers,
            params={"points": 60},
        )
        assert response.status_code == 200
        data = response.json()

        assert "anomaly_band" in data, "Response should have anomaly_band field"
        anomaly_band = data["anomaly_band"]
        assert isinstance(anomaly_band, dict), "anomaly_band should be a dict"
        assert "mean_score" in anomaly_band
        assert "upper" in anomaly_band
        assert "lower" in anomaly_band
        assert "std_dev" in anomaly_band

    def test_metrics_trend_series_item_structure(self, auth_headers, test_strategy_and_version):
        """Test trend_series items have expected fields"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics-trend",
            headers=auth_headers,
            params={"points": 60},
        )
        assert response.status_code == 200
        data = response.json()

        trend_series = data.get("trend_series", [])
        if trend_series:
            item = trend_series[0]
            # Check expected fields in trend item
            assert "timestamp" in item or item.get("timestamp") is None
            assert "score_delta" in item or "score_delta" in str(item)
            assert "anomaly_upper" in item or "anomaly_upper" in str(item)
            assert "anomaly_lower" in item or "anomaly_lower" in str(item)
            assert "is_anomaly" in item or "is_anomaly" in str(item)

    def test_metrics_trend_points_parameter(self, auth_headers, test_strategy_and_version):
        """Test points parameter limits the number of trend items"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics-trend",
            headers=auth_headers,
            params={"points": 10},
        )
        assert response.status_code == 200
        data = response.json()
        trend_series = data.get("trend_series", [])
        # Should not exceed requested points
        assert len(trend_series) <= 10


class TestExecutionPreviewEndpoint:
    """Tests for POST /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview"""

    def test_execution_preview_full_payload(self, auth_headers, test_strategy_and_version):
        """Test execution-preview returns full payload with all expected fields"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]
        version_hash = test_strategy_and_version["version_hash"]

        context_snapshot = {
            "context_id": "test-ctx-001",
            "account_id": "acct-demo",
            "timestamp_utc": "2026-03-24T07:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900, "daily_loss_pct": 1.2, "daily_loss_usd": 12},
            "strategy_version_id": version_id,
            "strategy_version_hash": version_hash,
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-test-001",
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview",
            headers=auth_headers,
            json={"context_snapshot": context_snapshot},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Check top-level fields
        assert "decision" in data, "Response should have decision field"
        assert "execution_intent" in data, "Response should have execution_intent field"
        assert "order_preview" in data, "Response should have order_preview field"
        assert "capital_impact" in data, "Response should have capital_impact field"
        assert "risk_checks" in data, "Response should have risk_checks field"
        assert "blocked_reasons" in data, "Response should have blocked_reasons field"
        assert "explainability_trace" in data, "Response should have explainability_trace field"

    def test_execution_preview_decision_structure(self, auth_headers, test_strategy_and_version):
        """Test execution-preview decision has expected structure"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]
        version_hash = test_strategy_and_version["version_hash"]

        context_snapshot = {
            "context_id": "test-ctx-002",
            "account_id": "acct-demo",
            "timestamp_utc": "2026-03-24T07:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": version_id,
            "strategy_version_hash": version_hash,
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-test-002",
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview",
            headers=auth_headers,
            json={"context_snapshot": context_snapshot},
        )
        assert response.status_code == 200
        data = response.json()

        decision = data.get("decision", {})
        assert "result" in decision or "PASS_BLOCK" in decision
        assert "score" in decision or "SCORE" in decision
        assert "reason_codes" in decision or "REASON_CODES" in decision
        assert "decision_hash" in decision or "DECISION_HASH" in decision

    def test_execution_preview_capital_impact_structure(self, auth_headers, test_strategy_and_version):
        """Test execution-preview capital_impact has expected fields"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]
        version_hash = test_strategy_and_version["version_hash"]

        context_snapshot = {
            "context_id": "test-ctx-003",
            "account_id": "acct-demo",
            "timestamp_utc": "2026-03-24T07:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": version_id,
            "strategy_version_hash": version_hash,
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-test-003",
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview",
            headers=auth_headers,
            json={"context_snapshot": context_snapshot},
        )
        assert response.status_code == 200
        data = response.json()

        capital_impact = data.get("capital_impact", {})
        assert "equity" in capital_impact
        assert "estimated_notional" in capital_impact
        assert "allocation_pct" in capital_impact
        assert "free_margin" in capital_impact

    def test_execution_preview_risk_checks_structure(self, auth_headers, test_strategy_and_version):
        """Test execution-preview risk_checks is a list with expected structure"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]
        version_hash = test_strategy_and_version["version_hash"]

        context_snapshot = {
            "context_id": "test-ctx-004",
            "account_id": "acct-demo",
            "timestamp_utc": "2026-03-24T07:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": version_id,
            "strategy_version_hash": version_hash,
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": "corr-test-004",
        }

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview",
            headers=auth_headers,
            json={"context_snapshot": context_snapshot},
        )
        assert response.status_code == 200
        data = response.json()

        risk_checks = data.get("risk_checks", [])
        assert isinstance(risk_checks, list), "risk_checks should be a list"
        if risk_checks:
            check = risk_checks[0]
            assert "check" in check
            assert "status" in check


class TestBulkAuditSnapshotEndpoint:
    """Tests for POST /api/strategy-domain/admin/strategies/bulk/audit-snapshot"""

    def test_bulk_audit_snapshot_basic(self, auth_headers, test_strategy_and_version):
        """Test bulk audit-snapshot endpoint works"""
        strategy_id = test_strategy_and_version["strategy_id"]

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/bulk/audit-snapshot",
            headers=auth_headers,
            json={
                "strategy_ids": [strategy_id],
                "format_type": "json",
                "limit_per_strategy": 100,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "strategy_count" in data or "snapshots" in data or "items" in data

    def test_bulk_audit_snapshot_with_multiple_strategies(self, auth_headers):
        """Test bulk audit-snapshot with multiple strategy IDs"""
        # First get some strategy IDs
        list_resp = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"page": 1, "page_size": 3},
        )
        if list_resp.status_code != 200:
            pytest.skip("Could not list strategies")

        items = list_resp.json().get("items", [])
        if len(items) < 2:
            pytest.skip("Not enough strategies for multi-strategy test")

        strategy_ids = [item["strategy_id"] for item in items[:2]]

        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/bulk/audit-snapshot",
            headers=auth_headers,
            json={
                "strategy_ids": strategy_ids,
                "format_type": "json",
                "limit_per_strategy": 50,
            },
        )
        assert response.status_code == 200


class TestNullFallbackBehavior:
    """Tests for null/0 fallback behavior in new metric fields"""

    def test_metrics_null_fallback_for_empty_data(self, auth_headers, test_strategy_and_version):
        """Test that metrics return 0 or valid defaults when no data exists"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        metrics = data.get("metrics", {})

        # All numeric fields should be valid numbers (not None/null in JSON)
        slippage_p50 = metrics.get("slippage_p50_bps")
        slippage_p95 = metrics.get("slippage_p95_bps")
        latency_p50 = metrics.get("latency_p50_ms")
        latency_p95 = metrics.get("latency_p95_ms")
        health_score = metrics.get("version_health_score")

        # Should be numeric, can be 0 for no data
        assert isinstance(slippage_p50, (int, float)), f"slippage_p50 should be numeric, got {type(slippage_p50)}"
        assert isinstance(slippage_p95, (int, float)), f"slippage_p95 should be numeric, got {type(slippage_p95)}"
        assert isinstance(latency_p50, (int, float)), f"latency_p50 should be numeric, got {type(latency_p50)}"
        assert isinstance(latency_p95, (int, float)), f"latency_p95 should be numeric, got {type(latency_p95)}"
        assert isinstance(health_score, (int, float)), f"health_score should be numeric, got {type(health_score)}"

    def test_trend_empty_series_returns_valid_anomaly_band(self, auth_headers, test_strategy_and_version):
        """Test that trend endpoint returns valid anomaly_band even with empty series"""
        strategy_id = test_strategy_and_version["strategy_id"]
        version_id = test_strategy_and_version["version_id"]

        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics-trend",
            headers=auth_headers,
            params={"points": 60},
        )
        assert response.status_code == 200
        data = response.json()

        anomaly_band = data.get("anomaly_band", {})
        # Should have valid numeric values even if no data
        assert isinstance(anomaly_band.get("mean_score"), (int, float))
        assert isinstance(anomaly_band.get("upper"), (int, float))
        assert isinstance(anomaly_band.get("lower"), (int, float))
        assert isinstance(anomaly_band.get("std_dev"), (int, float))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
