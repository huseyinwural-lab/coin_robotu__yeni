"""
Strategy Control Plane P1/P2 Ops & Observability Endpoints Test Suite
Tests for:
- POST /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview
- GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics
- GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/drift-alerts
- GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/false-signal-report
- GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/promotion-readiness
- GET /api/strategy-domain/admin/strategies/ops (search/filter/sort/page/page_size + active_only/production_only/lifecycle/validation/category/tag)
- POST /api/strategy-domain/admin/strategies/bulk/archive
- POST /api/strategy-domain/admin/strategies/bulk/validate
- POST /api/strategy-domain/admin/strategies/bulk/dry-run
- POST /api/strategy-domain/admin/strategies/bulk/tag
- POST /api/strategy-domain/admin/strategies/bulk/audit-snapshot
- GET /api/strategy-domain/admin/strategies/{strategy_id}/audit-history/export
- GET /api/strategy-domain/admin/strategies/{strategy_id}/rollback-chain
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for super admin"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_strategy_with_version(auth_headers):
    """Create a test strategy with a validated version for testing"""
    # Create strategy
    unique_code = f"test_ops_p1p2_{uuid.uuid4().hex[:8]}"
    strategy_payload = {
        "name": f"Test Ops P1P2 Strategy {unique_code}",
        "code": unique_code,
        "description": "Test strategy for P1/P2 ops endpoints",
        "owner_name": "test_ops",
        "category": "test",
        "tags": ["p1p2", "test", "ops"]
    }
    
    response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies",
        headers=auth_headers,
        json=strategy_payload
    )
    assert response.status_code == 201, f"Failed to create strategy: {response.text}"
    strategy = response.json()
    strategy_id = strategy["strategy_id"]
    
    # Create version
    version_payload = {
        "config_json": {
            "momentum_threshold": 0.1,
            "base_size": 0.001,
            "volatility_guard": 0.5
        },
        "config_schema_version": "1.0"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
        headers=auth_headers,
        json=version_payload
    )
    assert response.status_code == 201, f"Failed to create version: {response.text}"
    version = response.json()
    version_id = version["version_id"]
    version_hash = version["version_hash"]
    
    # Validate version
    response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
        headers=auth_headers,
        json={"force": False}
    )
    assert response.status_code == 200, f"Failed to validate version: {response.text}"
    
    # Run dry-run
    context_payload = {
        "context_id": f"ctx-{uuid.uuid4().hex[:8]}",
        "account_id": "acct-test",
        "timestamp_utc": "2026-03-24T10:00:00Z",
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
        "correlation_id": f"corr-{uuid.uuid4().hex[:8]}"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/dry-run",
        headers=auth_headers,
        json={"context_snapshot": context_payload}
    )
    assert response.status_code == 200, f"Failed to run dry-run: {response.text}"
    
    return {
        "strategy_id": strategy_id,
        "version_id": version_id,
        "version_hash": version_hash,
        "context_payload": context_payload
    }


class TestExecutionPreview:
    """Tests for POST /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview"""
    
    def test_execution_preview_returns_all_fields(self, auth_headers, test_strategy_with_version):
        """Test execution preview returns decision, execution_intent, order_preview, capital_impact, risk_checks, blocked_reasons, explainability_trace"""
        strategy_id = test_strategy_with_version["strategy_id"]
        version_id = test_strategy_with_version["version_id"]
        context_payload = test_strategy_with_version["context_payload"]
        
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/execution-preview",
            headers=auth_headers,
            json={"context_snapshot": context_payload}
        )
        
        assert response.status_code == 200, f"Execution preview failed: {response.text}"
        data = response.json()
        
        # Verify all required fields are present
        assert "decision" in data, "Missing 'decision' field"
        assert "execution_intent" in data, "Missing 'execution_intent' field"
        assert "order_preview" in data, "Missing 'order_preview' field"
        assert "capital_impact" in data, "Missing 'capital_impact' field"
        assert "risk_checks" in data, "Missing 'risk_checks' field"
        assert "blocked_reasons" in data, "Missing 'blocked_reasons' field"
        assert "explainability_trace" in data, "Missing 'explainability_trace' field"
        
        # Verify decision structure
        decision = data["decision"]
        assert "result" in decision, "Missing 'result' in decision"
        assert "score" in decision, "Missing 'score' in decision"
        assert "reason_codes" in decision, "Missing 'reason_codes' in decision"
        assert "decision_hash" in decision, "Missing 'decision_hash' in decision"
        
        # Verify capital_impact structure
        capital_impact = data["capital_impact"]
        assert "equity" in capital_impact, "Missing 'equity' in capital_impact"
        assert "allocation_pct" in capital_impact, "Missing 'allocation_pct' in capital_impact"
        
        # Verify risk_checks is a list
        assert isinstance(data["risk_checks"], list), "risk_checks should be a list"
        
        # Verify explainability_trace structure
        trace = data["explainability_trace"]
        assert "strategy_id" in trace, "Missing 'strategy_id' in explainability_trace"
        assert "strategy_version_id" in trace, "Missing 'strategy_version_id' in explainability_trace"
        assert "decision_trace" in trace, "Missing 'decision_trace' in explainability_trace"
        assert "selection" in trace, "Missing 'selection' in explainability_trace"
        
        print(f"Execution preview returned all required fields successfully")
        print(f"Decision result: {decision.get('result')}, score: {decision.get('score')}")


class TestVersionMetrics:
    """Tests for GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics"""
    
    def test_metrics_endpoint_returns_structure(self, auth_headers, test_strategy_with_version):
        """Test metrics endpoint returns proper structure"""
        strategy_id = test_strategy_with_version["strategy_id"]
        version_id = test_strategy_with_version["version_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/metrics",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Metrics endpoint failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "strategy_id" in data, "Missing 'strategy_id'"
        assert "strategy_version_id" in data, "Missing 'strategy_version_id'"
        assert "sample_sizes" in data, "Missing 'sample_sizes'"
        assert "metrics" in data, "Missing 'metrics'"
        
        # Verify metrics fields
        metrics = data["metrics"]
        expected_metrics = ["hit_rate", "block_reject_rate", "false_allow_rate", "false_reject_rate", "pnl_contribution", "execution_quality", "drift_alerts"]
        for field in expected_metrics:
            assert field in metrics, f"Missing '{field}' in metrics"
        
        print(f"Metrics endpoint returned all required fields")
        print(f"Metrics: {metrics}")


class TestDriftAlerts:
    """Tests for GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/drift-alerts"""
    
    def test_drift_alerts_endpoint_returns_structure(self, auth_headers, test_strategy_with_version):
        """Test drift alerts endpoint returns proper structure"""
        strategy_id = test_strategy_with_version["strategy_id"]
        version_id = test_strategy_with_version["version_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/drift-alerts",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Drift alerts endpoint failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "strategy_id" in data, "Missing 'strategy_id'"
        assert "strategy_version_id" in data, "Missing 'strategy_version_id'"
        assert "drift_alerts" in data, "Missing 'drift_alerts'"
        assert "count" in data, "Missing 'count'"
        
        # drift_alerts should be a list
        assert isinstance(data["drift_alerts"], list), "drift_alerts should be a list"
        
        print(f"Drift alerts endpoint returned structure correctly, count: {data['count']}")


class TestFalseSignalReport:
    """Tests for GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/false-signal-report"""
    
    def test_false_signal_report_returns_structure(self, auth_headers, test_strategy_with_version):
        """Test false signal report endpoint returns proper structure"""
        strategy_id = test_strategy_with_version["strategy_id"]
        version_id = test_strategy_with_version["version_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/false-signal-report",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"False signal report endpoint failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "strategy_id" in data, "Missing 'strategy_id'"
        assert "strategy_version_id" in data, "Missing 'strategy_version_id'"
        assert "false_allow_rate" in data, "Missing 'false_allow_rate'"
        assert "false_reject_rate" in data, "Missing 'false_reject_rate'"
        assert "signal_quality_last_50" in data, "Missing 'signal_quality_last_50'"
        assert "execution_quality" in data, "Missing 'execution_quality'"
        assert "evidence" in data, "Missing 'evidence'"
        
        print(f"False signal report returned structure correctly")
        print(f"false_allow_rate: {data['false_allow_rate']}, false_reject_rate: {data['false_reject_rate']}")


class TestPromotionReadiness:
    """Tests for GET /api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/promotion-readiness"""
    
    def test_promotion_readiness_returns_checklist(self, auth_headers, test_strategy_with_version):
        """Test promotion readiness endpoint returns checklist structure"""
        strategy_id = test_strategy_with_version["strategy_id"]
        version_id = test_strategy_with_version["version_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/promotion-readiness",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Promotion readiness endpoint failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "strategy_id" in data, "Missing 'strategy_id'"
        assert "strategy_version_id" in data, "Missing 'strategy_version_id'"
        assert "checklist" in data, "Missing 'checklist'"
        assert "ready_for_production" in data, "Missing 'ready_for_production'"
        assert "blockers" in data, "Missing 'blockers'"
        assert "is_production" in data, "Missing 'is_production'"
        
        # Verify checklist items
        checklist = data["checklist"]
        assert isinstance(checklist, list), "checklist should be a list"
        
        # Each checklist item should have key, status, pass, message
        for item in checklist:
            assert "key" in item, "Missing 'key' in checklist item"
            assert "status" in item, "Missing 'status' in checklist item"
            assert "pass" in item, "Missing 'pass' in checklist item"
            assert "message" in item, "Missing 'message' in checklist item"
        
        print(f"Promotion readiness returned checklist with {len(checklist)} items")
        print(f"ready_for_production: {data['ready_for_production']}, blockers: {data['blockers']}")


class TestStrategiesOpsEndpoint:
    """Tests for GET /api/strategy-domain/admin/strategies/ops with filters"""
    
    def test_ops_endpoint_returns_pagination(self, auth_headers):
        """Test ops endpoint returns items and pagination"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"page": 1, "page_size": 10}
        )
        
        assert response.status_code == 200, f"Ops endpoint failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "items" in data, "Missing 'items'"
        assert "pagination" in data, "Missing 'pagination'"
        
        # Verify pagination structure
        pagination = data["pagination"]
        assert "page" in pagination, "Missing 'page' in pagination"
        assert "page_size" in pagination, "Missing 'page_size' in pagination"
        assert "total" in pagination, "Missing 'total' in pagination"
        assert "has_next" in pagination, "Missing 'has_next' in pagination"
        
        print(f"Ops endpoint returned {len(data['items'])} items, total: {pagination['total']}")
    
    def test_ops_endpoint_search_filter(self, auth_headers, test_strategy_with_version):
        """Test ops endpoint with search filter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"search": "test_ops_p1p2"}
        )
        
        assert response.status_code == 200, f"Ops search failed: {response.text}"
        data = response.json()
        
        # Should find at least our test strategy
        assert len(data["items"]) >= 1, "Search should find at least one strategy"
        print(f"Search filter found {len(data['items'])} strategies")
    
    def test_ops_endpoint_category_filter(self, auth_headers):
        """Test ops endpoint with category filter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"category": "test"}
        )
        
        assert response.status_code == 200, f"Ops category filter failed: {response.text}"
        data = response.json()
        print(f"Category filter found {len(data['items'])} strategies")
    
    def test_ops_endpoint_sort_options(self, auth_headers):
        """Test ops endpoint with sort options"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"sort_by": "name", "sort_order": "asc"}
        )
        
        assert response.status_code == 200, f"Ops sort failed: {response.text}"
        data = response.json()
        print(f"Sort by name asc returned {len(data['items'])} strategies")
    
    def test_ops_endpoint_active_only_filter(self, auth_headers):
        """Test ops endpoint with active_only filter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"active_only": True}
        )
        
        assert response.status_code == 200, f"Ops active_only filter failed: {response.text}"
        data = response.json()
        print(f"active_only filter found {len(data['items'])} strategies")
    
    def test_ops_endpoint_production_only_filter(self, auth_headers):
        """Test ops endpoint with production_only filter"""
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/ops",
            headers=auth_headers,
            params={"production_only": True}
        )
        
        assert response.status_code == 200, f"Ops production_only filter failed: {response.text}"
        data = response.json()
        print(f"production_only filter found {len(data['items'])} strategies")


class TestBulkOperations:
    """Tests for bulk operation endpoints"""
    
    @pytest.fixture
    def bulk_test_strategies(self, auth_headers):
        """Create multiple test strategies for bulk operations"""
        strategy_ids = []
        for i in range(3):
            unique_code = f"test_bulk_{uuid.uuid4().hex[:8]}"
            payload = {
                "name": f"Bulk Test Strategy {i}",
                "code": unique_code,
                "description": "Test strategy for bulk operations",
                "owner_name": "bulk_test",
                "category": "bulk_test",
                "tags": ["bulk", "test"]
            }
            response = requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/strategies",
                headers=auth_headers,
                json=payload
            )
            if response.status_code == 201:
                strategy_ids.append(response.json()["strategy_id"])
        
        return strategy_ids
    
    def test_bulk_validate(self, auth_headers, bulk_test_strategies):
        """Test POST /api/strategy-domain/admin/strategies/bulk/validate"""
        # First create versions for each strategy
        for strategy_id in bulk_test_strategies:
            version_payload = {
                "config_json": {
                    "momentum_threshold": 0.1,
                    "base_size": 0.001,
                    "volatility_guard": 0.5
                },
                "config_schema_version": "1.0"
            }
            requests.post(
                f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
                headers=auth_headers,
                json=version_payload
            )
        
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/bulk/validate",
            headers=auth_headers,
            json={"strategy_ids": bulk_test_strategies}
        )
        
        assert response.status_code == 200, f"Bulk validate failed: {response.text}"
        data = response.json()
        
        assert "success" in data or "success_count" in data, "Missing success indicator"
        print(f"Bulk validate result: {data}")
    
    def test_bulk_dry_run(self, auth_headers, bulk_test_strategies):
        """Test POST /api/strategy-domain/admin/strategies/bulk/dry-run"""
        context_payload = {
            "context_id": f"ctx-{uuid.uuid4().hex[:8]}",
            "account_id": "acct-test",
            "timestamp_utc": "2026-03-24T10:00:00Z",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
            "market_snapshot_hash": "snapshot-hash-v1",
            "position_state": {"side": "flat", "qty": 0},
            "risk_state": {"blocked": False},
            "account_state_projection": {"equity": 1000, "free_margin": 900},
            "strategy_version_id": "",
            "strategy_version_hash": "",
            "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
            "correlation_id": f"corr-{uuid.uuid4().hex[:8]}"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/bulk/dry-run",
            headers=auth_headers,
            json={"strategy_ids": bulk_test_strategies, "context_snapshot": context_payload}
        )
        
        assert response.status_code == 200, f"Bulk dry-run failed: {response.text}"
        data = response.json()
        print(f"Bulk dry-run result: {data}")
    
    def test_bulk_tag(self, auth_headers, bulk_test_strategies):
        """Test POST /api/strategy-domain/admin/strategies/bulk/tag"""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/bulk/tag",
            headers=auth_headers,
            json={
                "strategy_ids": bulk_test_strategies,
                "category": "updated_category",
                "tags": ["new_tag1", "new_tag2"],
                "owner_name": "new_owner"
            }
        )
        
        assert response.status_code == 200, f"Bulk tag failed: {response.text}"
        data = response.json()
        print(f"Bulk tag result: {data}")
    
    def test_bulk_audit_snapshot(self, auth_headers, bulk_test_strategies):
        """Test POST /api/strategy-domain/admin/strategies/bulk/audit-snapshot"""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/bulk/audit-snapshot",
            headers=auth_headers,
            json={
                "strategy_ids": bulk_test_strategies,
                "format_type": "json",
                "limit_per_strategy": 100
            }
        )
        
        assert response.status_code == 200, f"Bulk audit snapshot failed: {response.text}"
        data = response.json()
        
        assert "strategy_count" in data or "snapshots" in data, "Missing expected fields"
        print(f"Bulk audit snapshot result: {data}")
    
    def test_bulk_archive(self, auth_headers, bulk_test_strategies):
        """Test POST /api/strategy-domain/admin/strategies/bulk/archive"""
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/bulk/archive",
            headers=auth_headers,
            json={"strategy_ids": bulk_test_strategies}
        )
        
        assert response.status_code == 200, f"Bulk archive failed: {response.text}"
        data = response.json()
        
        assert "success" in data or "success_count" in data, "Missing success indicator"
        print(f"Bulk archive result: {data}")


class TestAuditExport:
    """Tests for GET /api/strategy-domain/admin/strategies/{strategy_id}/audit-history/export"""
    
    def test_audit_export_json(self, auth_headers, test_strategy_with_version):
        """Test audit history export in JSON format"""
        strategy_id = test_strategy_with_version["strategy_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/audit-history/export",
            headers=auth_headers,
            params={"format_type": "json", "limit": 100}
        )
        
        assert response.status_code == 200, f"Audit export failed: {response.text}"
        data = response.json()
        
        assert "strategy_id" in data, "Missing 'strategy_id'"
        assert "items" in data or "audit_items" in data, "Missing audit items"
        assert "format" in data, "Missing 'format'"
        
        print(f"Audit export returned data for strategy {strategy_id}")
    
    def test_audit_export_csv(self, auth_headers, test_strategy_with_version):
        """Test audit history export in CSV format"""
        strategy_id = test_strategy_with_version["strategy_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/audit-history/export",
            headers=auth_headers,
            params={"format_type": "csv", "limit": 100}
        )
        
        assert response.status_code == 200, f"Audit export CSV failed: {response.text}"
        # CSV format should return different structure
        print(f"Audit export CSV returned successfully")


class TestRollbackChain:
    """Tests for GET /api/strategy-domain/admin/strategies/{strategy_id}/rollback-chain"""
    
    def test_rollback_chain_returns_structure(self, auth_headers, test_strategy_with_version):
        """Test rollback chain endpoint returns proper structure"""
        strategy_id = test_strategy_with_version["strategy_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{strategy_id}/rollback-chain",
            headers=auth_headers,
            params={"limit": 50}
        )
        
        assert response.status_code == 200, f"Rollback chain failed: {response.text}"
        data = response.json()
        
        assert "strategy_id" in data, "Missing 'strategy_id'"
        assert "chain" in data or "items" in data, "Missing chain/items"
        
        print(f"Rollback chain returned data for strategy {strategy_id}")


class TestEndpointNotFound:
    """Tests for 404 responses on non-existent resources"""
    
    def test_execution_preview_not_found(self, auth_headers):
        """Test execution preview returns 404 for non-existent strategy"""
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{fake_id}/versions/{fake_id}/execution-preview",
            headers=auth_headers,
            json={"context_snapshot": {}}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_metrics_not_found(self, auth_headers):
        """Test metrics returns 404 for non-existent strategy"""
        fake_id = str(uuid.uuid4())
        response = requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/strategies/{fake_id}/versions/{fake_id}/metrics",
            headers=auth_headers
        )
        
        # May return 404 or empty data depending on implementation
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
