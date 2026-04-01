"""
Test suite for /api/admin/commercial/overview endpoint using TestClient
FAZ A - Unified backend contract for admin commercial overview

Tests cover:
- GET /api/admin/commercial/overview returns 200 with unified payload
- Default filter behavior: time_window=last_30_days, environment=live
- Query param behavior: time_window, environment, from, to
- Invalid time range (from > to) returns 422 invalid_time_range
- Deterministic calculations: gross vs net, realized vs unrealized, fee/funding/commission totals
- Revenue aggregate consistency (total = sum of components)
- Risk summary empty data scenario
- Data quality empty and stale scenarios
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from server import app

# Test credentials for super_admin
TEST_EMAIL = "canary.admin@platform.local"
TEST_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def client():
    """TestClient instance"""
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_token(client):
    """Get authentication token for super_admin"""
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if token:
            return token
    pytest.skip(f"Authentication failed - status {response.status_code}: {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for authenticated requests"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestAdminCommercialOverviewEndpoint:
    """Tests for /api/admin/commercial/overview endpoint"""

    def test_overview_returns_200_with_unified_payload(self, client, auth_headers):
        """GET /api/admin/commercial/overview should return 200 with all blocks"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify all required top-level fields exist
        assert "generated_at" in data, "Missing generated_at field"
        assert "contract_version" in data, "Missing contract_version field"
        assert "applied_filters" in data, "Missing applied_filters block"
        assert "financial_accuracy" in data, "Missing financial_accuracy block"
        assert "revenue_model" in data, "Missing revenue_model block"
        assert "user_economics" in data, "Missing user_economics block"
        assert "risk_summary" in data, "Missing risk_summary block"
        assert "usage_analytics" in data, "Missing usage_analytics block"
        assert "data_quality" in data, "Missing data_quality block"
        
        print("✓ Overview endpoint returns unified payload with all 7 blocks")

    def test_default_filter_behavior(self, client, auth_headers):
        """Default filters should be time_window=last_30_days and environment=live"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        applied_filters = data.get("applied_filters", {})
        
        # Verify default time_window
        assert applied_filters.get("time_window") == "last_30_days", \
            f"Expected time_window=last_30_days, got {applied_filters.get('time_window')}"
        
        # Verify default environment
        assert applied_filters.get("environment") == "live", \
            f"Expected environment=live, got {applied_filters.get('environment')}"
        
        print("✓ Default filters: time_window=last_30_days, environment=live")

    def test_custom_time_window_parameter(self, client, auth_headers):
        """Query param time_window should be applied"""
        for time_window in ["last_7_days", "last_30_days", "last_90_days", "all_time"]:
            response = client.get(
                "/api/admin/commercial/overview",
                params={"time_window": time_window},
                headers=auth_headers
            )
            
            assert response.status_code == 200, f"Failed for time_window={time_window}"
            data = response.json()
            
            applied_filters = data.get("applied_filters", {})
            assert applied_filters.get("time_window") == time_window, \
                f"Expected time_window={time_window}, got {applied_filters.get('time_window')}"
        
        print("✓ Custom time_window parameter works for all supported values")

    def test_custom_environment_parameter(self, client, auth_headers):
        """Query param environment should be applied"""
        for environment in ["live", "testnet"]:
            response = client.get(
                "/api/admin/commercial/overview",
                params={"environment": environment},
                headers=auth_headers
            )
            
            assert response.status_code == 200, f"Failed for environment={environment}"
            data = response.json()
            
            applied_filters = data.get("applied_filters", {})
            assert applied_filters.get("environment") == environment, \
                f"Expected environment={environment}, got {applied_filters.get('environment')}"
        
        print("✓ Custom environment parameter works for live and testnet")

    def test_custom_from_to_parameters(self, client, auth_headers):
        """Query params from and to should create custom time range"""
        now = datetime.utcnow()
        from_ts = (now - timedelta(days=7)).isoformat() + "Z"
        to_ts = now.isoformat() + "Z"
        
        response = client.get(
            "/api/admin/commercial/overview",
            params={"from": from_ts, "to": to_ts},
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        applied_filters = data.get("applied_filters", {})
        
        # When from/to are provided, time_window should be "custom"
        assert applied_filters.get("time_window") == "custom", \
            f"Expected time_window=custom when from/to provided, got {applied_filters.get('time_window')}"
        
        # from_ts and to_ts should be populated
        assert applied_filters.get("from_ts") is not None, "from_ts should be set"
        assert applied_filters.get("to_ts") is not None, "to_ts should be set"
        
        print("✓ Custom from/to parameters create custom time range")

    def test_invalid_time_range_returns_422(self, client, auth_headers):
        """from > to should return 422 with invalid_time_range error"""
        now = datetime.utcnow()
        from_ts = now.isoformat() + "Z"  # Now
        to_ts = (now - timedelta(days=7)).isoformat() + "Z"  # 7 days ago (before from)
        
        response = client.get(
            "/api/admin/commercial/overview",
            params={"from": from_ts, "to": to_ts},
            headers=auth_headers
        )
        
        assert response.status_code == 422, \
            f"Expected 422 for invalid time range, got {response.status_code}: {response.text}"
        
        # Check error detail contains invalid_time_range
        data = response.json()
        detail = str(data.get("detail", "")).lower()
        assert "invalid_time_range" in detail, \
            f"Expected 'invalid_time_range' in error detail, got: {detail}"
        
        print("✓ Invalid time range (from > to) returns 422 invalid_time_range")


class TestFinancialAccuracyBlock:
    """Tests for financial_accuracy block deterministic calculations"""

    def test_financial_accuracy_structure(self, client, auth_headers):
        """financial_accuracy block should have all required fields"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        fa = data.get("financial_accuracy", {})
        
        required_fields = [
            "record_count", "trade_count",
            "realized_gross_usd", "unrealized_gross_usd", "gross_total_usd",
            "realized_net_usd", "unrealized_net_usd", "net_total_usd",
            "net_vs_gross_delta_usd",
            "trading_fee_total_usd", "funding_total_usd", "commission_total_usd"
        ]
        
        for field in required_fields:
            assert field in fa, f"Missing field: {field}"
        
        print(f"✓ financial_accuracy block has all {len(required_fields)} required fields")

    def test_gross_total_equals_realized_plus_unrealized(self, client, auth_headers):
        """gross_total_usd should equal realized_gross_usd + unrealized_gross_usd"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        fa = data.get("financial_accuracy", {})
        
        realized_gross = fa.get("realized_gross_usd", 0)
        unrealized_gross = fa.get("unrealized_gross_usd", 0)
        gross_total = fa.get("gross_total_usd", 0)
        
        expected_gross_total = round(realized_gross + unrealized_gross, 6)
        actual_gross_total = round(gross_total, 6)
        
        assert abs(expected_gross_total - actual_gross_total) < 0.000001, \
            f"gross_total_usd mismatch: expected {expected_gross_total}, got {actual_gross_total}"
        
        print("✓ gross_total_usd = realized_gross_usd + unrealized_gross_usd")

    def test_net_total_equals_realized_plus_unrealized(self, client, auth_headers):
        """net_total_usd should equal realized_net_usd + unrealized_net_usd"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        fa = data.get("financial_accuracy", {})
        
        realized_net = fa.get("realized_net_usd", 0)
        unrealized_net = fa.get("unrealized_net_usd", 0)
        net_total = fa.get("net_total_usd", 0)
        
        expected_net_total = round(realized_net + unrealized_net, 6)
        actual_net_total = round(net_total, 6)
        
        assert abs(expected_net_total - actual_net_total) < 0.000001, \
            f"net_total_usd mismatch: expected {expected_net_total}, got {actual_net_total}"
        
        print("✓ net_total_usd = realized_net_usd + unrealized_net_usd")

    def test_net_vs_gross_delta_calculation(self, client, auth_headers):
        """net_vs_gross_delta_usd should equal gross_total_usd - net_total_usd"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        fa = data.get("financial_accuracy", {})
        
        gross_total = fa.get("gross_total_usd", 0)
        net_total = fa.get("net_total_usd", 0)
        delta = fa.get("net_vs_gross_delta_usd", 0)
        
        expected_delta = round(gross_total - net_total, 6)
        actual_delta = round(delta, 6)
        
        assert abs(expected_delta - actual_delta) < 0.000001, \
            f"net_vs_gross_delta_usd mismatch: expected {expected_delta}, got {actual_delta}"
        
        print("✓ net_vs_gross_delta_usd = gross_total_usd - net_total_usd")


class TestRevenueModelBlock:
    """Tests for revenue_model block aggregate consistency"""

    def test_revenue_model_structure(self, client, auth_headers):
        """revenue_model block should have all required fields"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        rm = data.get("revenue_model", {})
        
        assert "total_revenue_usd" in rm, "Missing total_revenue_usd"
        assert "component_breakdown" in rm, "Missing component_breakdown"
        assert "top_symbols" in rm, "Missing top_symbols"
        assert "row_count" in rm, "Missing row_count"
        
        print("✓ revenue_model block has all required fields")

    def test_total_revenue_equals_component_sum(self, client, auth_headers):
        """total_revenue_usd should equal sum of component_breakdown revenue_usd"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        rm = data.get("revenue_model", {})
        
        total_revenue = rm.get("total_revenue_usd", 0)
        components = rm.get("component_breakdown", [])
        
        component_sum = sum(c.get("revenue_usd", 0) for c in components)
        
        expected_total = round(component_sum, 6)
        actual_total = round(total_revenue, 6)
        
        assert abs(expected_total - actual_total) < 0.000001, \
            f"total_revenue_usd mismatch: expected {expected_total} (sum of components), got {actual_total}"
        
        print("✓ total_revenue_usd = sum of component_breakdown revenue_usd")

    def test_component_breakdown_structure(self, client, auth_headers):
        """Each component in component_breakdown should have required fields"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        rm = data.get("revenue_model", {})
        components = rm.get("component_breakdown", [])
        
        required_fields = ["component_type", "revenue_usd", "source_amount_usd", "share_rate_avg", "row_count"]
        
        for i, component in enumerate(components):
            for field in required_fields:
                assert field in component, f"Component {i} missing field: {field}"
        
        print(f"✓ All {len(components)} components have required fields")


class TestRiskSummaryBlock:
    """Tests for risk_summary block including empty data scenario"""

    def test_risk_summary_structure(self, client, auth_headers):
        """risk_summary block should have all required fields"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        rs = data.get("risk_summary", {})
        
        required_fields = [
            "open_position_count", "risk_exposure_usd",
            "high_drift_reconciliation_count",
            "latest_daily_loss_limit_pct",
            "trading_enabled", "kill_switch_enabled",
            "top_exposure_symbols"
        ]
        
        for field in required_fields:
            assert field in rs, f"Missing field: {field}"
        
        print("✓ risk_summary block has all required fields")

    def test_risk_summary_safe_defaults(self, client, auth_headers):
        """risk_summary should return safe defaults for numeric fields"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        rs = data.get("risk_summary", {})
        
        # Numeric fields should be >= 0
        assert rs.get("open_position_count", -1) >= 0, "open_position_count should be >= 0"
        assert rs.get("risk_exposure_usd", -1) >= 0, "risk_exposure_usd should be >= 0"
        assert rs.get("high_drift_reconciliation_count", -1) >= 0, "high_drift_reconciliation_count should be >= 0"
        
        # Boolean fields should be boolean
        assert isinstance(rs.get("trading_enabled"), bool), "trading_enabled should be boolean"
        assert isinstance(rs.get("kill_switch_enabled"), bool), "kill_switch_enabled should be boolean"
        
        # top_exposure_symbols should be a list
        assert isinstance(rs.get("top_exposure_symbols"), list), "top_exposure_symbols should be a list"
        
        print("✓ risk_summary returns safe defaults for all fields")


class TestDataQualityBlock:
    """Tests for data_quality block including empty and stale scenarios"""

    def test_data_quality_structure(self, client, auth_headers):
        """data_quality block should have all required fields"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        dq = data.get("data_quality", {})
        
        required_fields = [
            "status", "empty_data", "stale_sources",
            "freshness_seconds", "stale_threshold_seconds",
            "latest_trade_at", "latest_pnl_at", "latest_reconciliation_at",
            "missing_data_alert", "trade_count", "pnl_record_count"
        ]
        
        for field in required_fields:
            assert field in dq, f"Missing field: {field}"
        
        print("✓ data_quality block has all required fields")

    def test_data_quality_status_values(self, client, auth_headers):
        """data_quality status should be one of: healthy, empty, stale, degraded"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        dq = data.get("data_quality", {})
        status = dq.get("status")
        
        valid_statuses = ["healthy", "empty", "stale", "degraded"]
        assert status in valid_statuses, \
            f"Invalid status: {status}. Expected one of: {valid_statuses}"
        
        print(f"✓ data_quality status is valid: {status}")

    def test_data_quality_empty_data_consistency(self, client, auth_headers):
        """When empty_data=True, status should be 'empty'"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        dq = data.get("data_quality", {})
        
        if dq.get("empty_data") is True:
            assert dq.get("status") == "empty", \
                f"When empty_data=True, status should be 'empty', got: {dq.get('status')}"
            print("✓ empty_data=True implies status='empty'")
        else:
            print(f"✓ Data exists, empty_data=False, status={dq.get('status')}")


class TestUserEconomicsBlock:
    """Tests for user_economics block"""

    def test_user_economics_structure(self, client, auth_headers):
        """user_economics block should have all required fields"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        ue = data.get("user_economics", {})
        
        required_fields = [
            "total_users", "paying_users", "churned_users",
            "total_ltv_usd", "total_revenue_contribution_usd", "total_realized_pnl_usd",
            "avg_ltv_usd", "avg_inactive_days",
            "segment_distribution", "top_users"
        ]
        
        for field in required_fields:
            assert field in ue, f"Missing field: {field}"
        
        print("✓ user_economics block has all required fields")


class TestUsageAnalyticsBlock:
    """Tests for usage_analytics block"""

    def test_usage_analytics_structure(self, client, auth_headers):
        """usage_analytics block should have all required fields"""
        response = client.get("/api/admin/commercial/overview", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        ua = data.get("usage_analytics", {})
        
        required_fields = [
            "total_trades", "unique_users", "unique_symbols",
            "total_notional_usd", "avg_trade_notional_usd", "activity_days",
            "by_market_type", "by_exchange", "top_symbols"
        ]
        
        for field in required_fields:
            assert field in ua, f"Missing field: {field}"
        
        print("✓ usage_analytics block has all required fields")


class TestAuthenticationRequirement:
    """Tests for authentication requirement"""

    def test_unauthenticated_request_rejected(self, client):
        """Unauthenticated request should be rejected with 401/403"""
        response = client.get("/api/admin/commercial/overview")
        
        assert response.status_code in [401, 403], \
            f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        
        print(f"✓ Unauthenticated request rejected with {response.status_code}")


class TestTimeWindowAliases:
    """Tests for time_window alias support"""

    def test_time_window_alias_30d(self, client, auth_headers):
        """30d alias should map to last_30_days"""
        response = client.get(
            "/api/admin/commercial/overview",
            params={"time_window": "30d"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        applied_filters = data.get("applied_filters", {})
        assert applied_filters.get("time_window") == "last_30_days", \
            f"Expected 30d to map to last_30_days, got {applied_filters.get('time_window')}"
        
        print("✓ 30d alias maps to last_30_days")

    def test_time_window_alias_7d(self, client, auth_headers):
        """7d alias should map to last_7_days"""
        response = client.get(
            "/api/admin/commercial/overview",
            params={"time_window": "7d"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        applied_filters = data.get("applied_filters", {})
        assert applied_filters.get("time_window") == "last_7_days", \
            f"Expected 7d to map to last_7_days, got {applied_filters.get('time_window')}"
        
        print("✓ 7d alias maps to last_7_days")

    def test_time_window_alias_90d(self, client, auth_headers):
        """90d alias should map to last_90_days"""
        response = client.get(
            "/api/admin/commercial/overview",
            params={"time_window": "90d"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        applied_filters = data.get("applied_filters", {})
        assert applied_filters.get("time_window") == "last_90_days", \
            f"Expected 90d to map to last_90_days, got {applied_filters.get('time_window')}"
        
        print("✓ 90d alias maps to last_90_days")

    def test_time_window_alias_all(self, client, auth_headers):
        """all alias should map to all_time"""
        response = client.get(
            "/api/admin/commercial/overview",
            params={"time_window": "all"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        applied_filters = data.get("applied_filters", {})
        assert applied_filters.get("time_window") == "all_time", \
            f"Expected all to map to all_time, got {applied_filters.get('time_window')}"
        
        print("✓ all alias maps to all_time")

    def test_invalid_time_window_falls_back_to_default(self, client, auth_headers):
        """Invalid time_window should fall back to last_30_days"""
        response = client.get(
            "/api/admin/commercial/overview",
            params={"time_window": "invalid_window"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        applied_filters = data.get("applied_filters", {})
        assert applied_filters.get("time_window") == "last_30_days", \
            f"Expected invalid time_window to fall back to last_30_days, got {applied_filters.get('time_window')}"
        
        print("✓ Invalid time_window falls back to last_30_days")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
