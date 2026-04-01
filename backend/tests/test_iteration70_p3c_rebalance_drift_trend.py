"""
Iteration 70 - P3.c Testing: Rebalance Suggestions + 5g Drift Trend Tooltip

Features to test:
1. POST /api/admin/strategy-allocation/rebalance-suggestions endpoint
2. Rebalance suggestion response: suggestions list, current_weight, suggested_weight, delta, score, selection_count, applied_budget
3. Selection yokken suggestion preview üretiliyor ama otomatik apply/save yok
4. GET /api/admin/strategy-allocation satırlarında trend_5d_line ve trend_5d_available alanları dönüyor
5. P3.a+b regresyon kontrolü: state reason badge/inline/tooltip ve risk binding panel bozulmamış
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
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


class TestRebalanceSuggestionsEndpoint:
    """Test POST /api/admin/strategy-allocation/rebalance-suggestions"""

    def test_rebalance_suggestions_endpoint_exists(self, admin_headers):
        """Verify rebalance-suggestions endpoint returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions",
            headers=admin_headers,
            json={"strategy_ids": []},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: POST /api/admin/strategy-allocation/rebalance-suggestions returns 200")

    def test_rebalance_suggestions_response_structure(self, admin_headers):
        """Verify response contains required fields"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions",
            headers=admin_headers,
            json={"strategy_ids": []},
        )
        assert response.status_code == 200
        data = response.json()

        # Required fields in response
        assert "status" in data, "Missing 'status' field"
        assert "message" in data, "Missing 'message' field"
        assert "trace_id" in data, "Missing 'trace_id' field"
        assert "selection_count" in data, "Missing 'selection_count' field"
        assert "applied_budget" in data, "Missing 'applied_budget' field"
        assert "suggestions" in data, "Missing 'suggestions' field"

        print(f"PASS: Response structure valid - status={data['status']}, selection_count={data['selection_count']}, applied_budget={data['applied_budget']}")

    def test_rebalance_suggestions_without_selection(self, admin_headers):
        """When no strategy_ids provided, should return preview for all strategies"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions",
            headers=admin_headers,
            json={"strategy_ids": []},
        )
        assert response.status_code == 200
        data = response.json()

        # selection_count should be 0 when no selection
        assert data["selection_count"] == 0, f"Expected selection_count=0, got {data['selection_count']}"

        # applied_budget should be 1.0 when no selection (full budget)
        if data["suggestions"]:
            assert data["applied_budget"] == 1.0, f"Expected applied_budget=1.0, got {data['applied_budget']}"

        print(f"PASS: No selection returns preview with selection_count=0, applied_budget={data['applied_budget']}")

    def test_rebalance_suggestions_row_structure(self, admin_headers):
        """Verify each suggestion row has required fields"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions",
            headers=admin_headers,
            json={"strategy_ids": []},
        )
        assert response.status_code == 200
        data = response.json()

        if not data["suggestions"]:
            pytest.skip("No suggestions returned - no strategies in database")

        for row in data["suggestions"]:
            assert "strategy_id" in row, "Missing 'strategy_id' in suggestion row"
            assert "current_weight" in row, "Missing 'current_weight' in suggestion row"
            assert "suggested_weight" in row, "Missing 'suggested_weight' in suggestion row"
            assert "delta" in row, "Missing 'delta' in suggestion row"
            assert "score" in row, "Missing 'score' in suggestion row"
            assert "confidence" in row, "Missing 'confidence' in suggestion row"
            assert "performance_norm" in row, "Missing 'performance_norm' in suggestion row"
            assert "decay" in row, "Missing 'decay' in suggestion row"

        print(f"PASS: All {len(data['suggestions'])} suggestion rows have required fields")

    def test_rebalance_suggestions_with_selection(self, admin_headers):
        """When strategy_ids provided, should return suggestions only for selected"""
        # First get available strategies
        list_response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert list_response.status_code == 200
        strategies = list_response.json()

        if len(strategies) < 1:
            pytest.skip("No strategies available for selection test")

        # Select first strategy
        selected_ids = [strategies[0]["strategy_id"]]

        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions",
            headers=admin_headers,
            json={"strategy_ids": selected_ids},
        )
        assert response.status_code == 200
        data = response.json()

        # selection_count should match selected count
        assert data["selection_count"] == len(selected_ids), f"Expected selection_count={len(selected_ids)}, got {data['selection_count']}"

        print(f"PASS: Selection with {len(selected_ids)} strategies returns selection_count={data['selection_count']}")


class TestTrend5dFields:
    """Test trend_5d_line and trend_5d_available fields in strategy allocation"""

    def test_strategy_allocation_has_trend_fields(self, admin_headers):
        """Verify GET /api/admin/strategy-allocation returns trend_5d_line and trend_5d_available"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        if not data:
            pytest.skip("No strategies in database")

        for row in data:
            assert "trend_5d_line" in row, f"Missing 'trend_5d_line' in strategy {row.get('strategy_id')}"
            assert "trend_5d_available" in row, f"Missing 'trend_5d_available' in strategy {row.get('strategy_id')}"

            # trend_5d_available should be boolean
            assert isinstance(row["trend_5d_available"], bool), f"trend_5d_available should be boolean, got {type(row['trend_5d_available'])}"

            # trend_5d_line should be string
            assert isinstance(row["trend_5d_line"], str), f"trend_5d_line should be string, got {type(row['trend_5d_line'])}"

        print(f"PASS: All {len(data)} strategies have trend_5d_line and trend_5d_available fields")

    def test_trend_5d_line_format(self, admin_headers):
        """Verify trend_5d_line format is correct"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        if not data:
            pytest.skip("No strategies in database")

        for row in data:
            trend_line = row["trend_5d_line"]
            trend_available = row["trend_5d_available"]

            if trend_available:
                # When available, should contain "5g trend →" format
                assert "5g trend" in trend_line, f"Expected '5g trend' in trend_line when available, got: {trend_line}"
                # Should contain quality, perf, decay with arrows
                assert "quality" in trend_line.lower() or "perf" in trend_line.lower() or "decay" in trend_line.lower(), f"Expected metrics in trend_line: {trend_line}"
            else:
                # When not available, should be "5g trend unavailable"
                assert trend_line == "5g trend unavailable", f"Expected '5g trend unavailable' when not available, got: {trend_line}"

        print("PASS: trend_5d_line format is correct for all strategies")


class TestP3abRegression:
    """Regression tests for P3.a+b features - state reason and risk binding"""

    def test_state_reason_fields_present(self, admin_headers):
        """Verify state_reason_code, state_reason_detail, is_drift_override fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        if not data:
            pytest.skip("No strategies in database")

        for row in data:
            assert "state_reason_code" in row, f"Missing 'state_reason_code' in strategy {row.get('strategy_id')}"
            assert "state_reason_detail" in row, f"Missing 'state_reason_detail' in strategy {row.get('strategy_id')}"
            assert "is_drift_override" in row, f"Missing 'is_drift_override' in strategy {row.get('strategy_id')}"

            # Validate state_reason_code values
            valid_codes = ["AUTO_DISABLED_BY_DRIFT", "AUTO_THROTTLED_BY_DRIFT", "MANUAL_STATE"]
            assert row["state_reason_code"] in valid_codes, f"Invalid state_reason_code: {row['state_reason_code']}"

        print(f"PASS: All {len(data)} strategies have state reason fields (P3.a regression OK)")

    def test_risk_binding_fields_present(self, admin_headers):
        """Verify drawdown_pct, exposure_ratio_pct, suggested_reduced_capital fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        if not data:
            pytest.skip("No strategies in database")

        for row in data:
            assert "drawdown_pct" in row, f"Missing 'drawdown_pct' in strategy {row.get('strategy_id')}"
            assert "exposure_ratio_pct" in row, f"Missing 'exposure_ratio_pct' in strategy {row.get('strategy_id')}"
            assert "suggested_reduced_capital" in row, f"Missing 'suggested_reduced_capital' in strategy {row.get('strategy_id')}"
            assert "is_auto_reduce_candidate" in row, f"Missing 'is_auto_reduce_candidate' in strategy {row.get('strategy_id')}"

        print(f"PASS: All {len(data)} strategies have risk binding fields (P3.b regression OK)")

    def test_summary_risk_binding_fields(self, admin_headers):
        """Verify summary endpoint has risk binding fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Required risk binding fields in summary
        assert "total_exposure_ratio_pct" in data, "Missing 'total_exposure_ratio_pct' in summary"
        assert "exposure_warning_threshold_pct" in data, "Missing 'exposure_warning_threshold_pct' in summary"
        assert "exposure_warning_state" in data, "Missing 'exposure_warning_state' in summary"
        assert "drawdown_threshold_pct" in data, "Missing 'drawdown_threshold_pct' in summary"
        assert "drawdown_enforce_threshold_pct" in data, "Missing 'drawdown_enforce_threshold_pct' in summary"
        assert "drawdown_candidates" in data, "Missing 'drawdown_candidates' in summary"

        # Validate threshold values
        assert data["exposure_warning_threshold_pct"] == 80.0, f"Expected exposure_warning_threshold_pct=80.0, got {data['exposure_warning_threshold_pct']}"
        assert data["drawdown_threshold_pct"] == 8.0, f"Expected drawdown_threshold_pct=8.0, got {data['drawdown_threshold_pct']}"
        assert data["drawdown_enforce_threshold_pct"] == 12.0, f"Expected drawdown_enforce_threshold_pct=12.0, got {data['drawdown_enforce_threshold_pct']}"

        print("PASS: Summary has all risk binding fields with correct thresholds (P3.b regression OK)")

    def test_state_history_has_reason_fields(self, admin_headers):
        """Verify state history entries have reason_code and reason_detail"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/state-history",
            headers=admin_headers,
            params={"limit": 10},
        )
        assert response.status_code == 200
        data = response.json()

        if not data.get("rows"):
            pytest.skip("No state history entries")

        for entry in data["rows"]:
            assert "reason_code" in entry, "Missing 'reason_code' in state history entry"
            assert "reason_detail" in entry, "Missing 'reason_detail' in state history entry"

        print("PASS: State history entries have reason fields (P3.a regression OK)")


class TestRebalanceSuggestionNoAutoSave:
    """Test that rebalance suggestions don't auto-save"""

    def test_rebalance_suggestion_is_preview_only(self, admin_headers):
        """Verify rebalance suggestion doesn't modify database"""
        # Get current state
        before_response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert before_response.status_code == 200
        before_data = before_response.json()

        if not before_data:
            pytest.skip("No strategies in database")

        # Store original weights
        original_weights = {row["strategy_id"]: row["capital_weight"] for row in before_data}

        # Generate rebalance suggestion
        suggestion_response = requests.post(
            f"{BASE_URL}/api/admin/strategy-allocation/rebalance-suggestions",
            headers=admin_headers,
            json={"strategy_ids": []},
        )
        assert suggestion_response.status_code == 200

        # Get state after suggestion
        after_response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert after_response.status_code == 200
        after_data = after_response.json()

        # Verify weights unchanged
        for row in after_data:
            strategy_id = row["strategy_id"]
            if strategy_id in original_weights:
                assert row["capital_weight"] == original_weights[strategy_id], f"Weight changed for {strategy_id} after suggestion (should be preview only)"

        print("PASS: Rebalance suggestion is preview only - no auto-save")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
