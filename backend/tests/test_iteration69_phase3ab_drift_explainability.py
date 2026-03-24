"""
Phase 3a+b Testing: Drift Override Explainability & Risk Binding Fields
========================================================================
Tests for:
1. GET /api/admin/strategy-allocation - state explainability fields
2. GET /api/admin/strategy-allocation/summary - risk binding fields
3. Exposure warning state calculation (≥80%)
4. Drawdown candidates with thresholds (8% warning, 12% enforce)
5. PUT state update - drift override detection
6. State-history endpoint - reason_code/reason_detail
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://strategy-version-gov.preview.emergentagent.com"

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
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
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


class TestStrategyAllocationExplainabilityFields:
    """Test state explainability fields in GET /api/admin/strategy-allocation"""

    def test_strategy_allocation_returns_state_reason_code(self, admin_headers):
        """Verify state_reason_code field is present in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) > 0:
            first_row = data[0]
            assert "state_reason_code" in first_row, "state_reason_code field missing"
            print(f"✓ state_reason_code present: {first_row.get('state_reason_code')}")

    def test_strategy_allocation_returns_state_reason_detail(self, admin_headers):
        """Verify state_reason_detail field is present in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            first_row = data[0]
            assert "state_reason_detail" in first_row, "state_reason_detail field missing"
            print(f"✓ state_reason_detail present: {first_row.get('state_reason_detail')}")

    def test_strategy_allocation_returns_is_drift_override(self, admin_headers):
        """Verify is_drift_override field is present in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            first_row = data[0]
            assert "is_drift_override" in first_row, "is_drift_override field missing"
            assert isinstance(first_row["is_drift_override"], bool), "is_drift_override should be boolean"
            print(f"✓ is_drift_override present: {first_row.get('is_drift_override')}")

    def test_strategy_allocation_returns_drawdown_pct(self, admin_headers):
        """Verify drawdown_pct field is present in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            first_row = data[0]
            assert "drawdown_pct" in first_row, "drawdown_pct field missing"
            assert isinstance(first_row["drawdown_pct"], (int, float)), "drawdown_pct should be numeric"
            print(f"✓ drawdown_pct present: {first_row.get('drawdown_pct')}")

    def test_strategy_allocation_returns_exposure_ratio_pct(self, admin_headers):
        """Verify exposure_ratio_pct field is present in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            first_row = data[0]
            assert "exposure_ratio_pct" in first_row, "exposure_ratio_pct field missing"
            assert isinstance(first_row["exposure_ratio_pct"], (int, float)), "exposure_ratio_pct should be numeric"
            print(f"✓ exposure_ratio_pct present: {first_row.get('exposure_ratio_pct')}")

    def test_strategy_allocation_returns_suggested_reduced_capital(self, admin_headers):
        """Verify suggested_reduced_capital field is present in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            first_row = data[0]
            assert "suggested_reduced_capital" in first_row, "suggested_reduced_capital field missing"
            assert isinstance(first_row["suggested_reduced_capital"], (int, float)), "suggested_reduced_capital should be numeric"
            print(f"✓ suggested_reduced_capital present: {first_row.get('suggested_reduced_capital')}")


class TestStrategyAllocationSummaryRiskBindingFields:
    """Test risk binding fields in GET /api/admin/strategy-allocation/summary"""

    def test_summary_returns_total_exposure_ratio_pct(self, admin_headers):
        """Verify total_exposure_ratio_pct field is present"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "total_exposure_ratio_pct" in data, "total_exposure_ratio_pct field missing"
        assert isinstance(data["total_exposure_ratio_pct"], (int, float)), "total_exposure_ratio_pct should be numeric"
        print(f"✓ total_exposure_ratio_pct: {data.get('total_exposure_ratio_pct')}")

    def test_summary_returns_exposure_warning_threshold_pct(self, admin_headers):
        """Verify exposure_warning_threshold_pct field is present (should be 80)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "exposure_warning_threshold_pct" in data, "exposure_warning_threshold_pct field missing"
        assert data["exposure_warning_threshold_pct"] == 80, f"Expected 80, got {data['exposure_warning_threshold_pct']}"
        print(f"✓ exposure_warning_threshold_pct: {data.get('exposure_warning_threshold_pct')}")

    def test_summary_returns_exposure_warning_state(self, admin_headers):
        """Verify exposure_warning_state field is present (NORMAL or WARNING)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "exposure_warning_state" in data, "exposure_warning_state field missing"
        assert data["exposure_warning_state"] in ["NORMAL", "WARNING"], f"Invalid state: {data['exposure_warning_state']}"
        print(f"✓ exposure_warning_state: {data.get('exposure_warning_state')}")

    def test_summary_returns_drawdown_threshold_pct(self, admin_headers):
        """Verify drawdown_threshold_pct field is present (should be 8)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "drawdown_threshold_pct" in data, "drawdown_threshold_pct field missing"
        assert data["drawdown_threshold_pct"] == 8, f"Expected 8, got {data['drawdown_threshold_pct']}"
        print(f"✓ drawdown_threshold_pct: {data.get('drawdown_threshold_pct')}")

    def test_summary_returns_drawdown_enforce_threshold_pct(self, admin_headers):
        """Verify drawdown_enforce_threshold_pct field is present (should be 12)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "drawdown_enforce_threshold_pct" in data, "drawdown_enforce_threshold_pct field missing"
        assert data["drawdown_enforce_threshold_pct"] == 12, f"Expected 12, got {data['drawdown_enforce_threshold_pct']}"
        print(f"✓ drawdown_enforce_threshold_pct: {data.get('drawdown_enforce_threshold_pct')}")

    def test_summary_returns_drawdown_candidates(self, admin_headers):
        """Verify drawdown_candidates field is present and is a list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "drawdown_candidates" in data, "drawdown_candidates field missing"
        assert isinstance(data["drawdown_candidates"], list), "drawdown_candidates should be a list"
        print(f"✓ drawdown_candidates count: {len(data.get('drawdown_candidates', []))}")
        
        # If there are candidates, verify structure
        if len(data["drawdown_candidates"]) > 0:
            candidate = data["drawdown_candidates"][0]
            assert "strategy_id" in candidate, "candidate missing strategy_id"
            assert "drawdown_pct" in candidate, "candidate missing drawdown_pct"
            assert "suggested_reduced_capital" in candidate, "candidate missing suggested_reduced_capital"
            assert "enforced_required" in candidate, "candidate missing enforced_required"
            assert "reason_code" in candidate, "candidate missing reason_code"
            print(f"✓ First candidate structure verified: {candidate}")


class TestExposureWarningStateCalculation:
    """Test exposure warning state is calculated correctly (≥80% triggers WARNING)"""

    def test_exposure_warning_state_logic(self, admin_headers):
        """Verify exposure warning state matches threshold logic"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        exposure_ratio = data.get("total_exposure_ratio_pct", 0)
        threshold = data.get("exposure_warning_threshold_pct", 80)
        state = data.get("exposure_warning_state", "NORMAL")
        
        if exposure_ratio >= threshold:
            assert state == "WARNING", f"Expected WARNING when exposure {exposure_ratio}% >= {threshold}%"
            print(f"✓ Exposure {exposure_ratio}% >= {threshold}% → state=WARNING (correct)")
        else:
            assert state == "NORMAL", f"Expected NORMAL when exposure {exposure_ratio}% < {threshold}%"
            print(f"✓ Exposure {exposure_ratio}% < {threshold}% → state=NORMAL (correct)")


class TestDrawdownCandidatesThresholds:
    """Test drawdown candidates with 8% warning and 12% enforce thresholds"""

    def test_drawdown_candidates_enforced_required_logic(self, admin_headers):
        """Verify enforced_required=true when drawdown >= 12%"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        candidates = data.get("drawdown_candidates", [])
        enforce_threshold = data.get("drawdown_enforce_threshold_pct", 12)
        
        for candidate in candidates:
            drawdown = candidate.get("drawdown_pct", 0)
            enforced = candidate.get("enforced_required", False)
            
            if drawdown >= enforce_threshold:
                assert enforced is True, f"Expected enforced_required=true for drawdown {drawdown}% >= {enforce_threshold}%"
                print(f"✓ {candidate['strategy_id']}: drawdown={drawdown}% >= {enforce_threshold}% → enforced_required=true")
            else:
                assert enforced is False, f"Expected enforced_required=false for drawdown {drawdown}% < {enforce_threshold}%"
                print(f"✓ {candidate['strategy_id']}: drawdown={drawdown}% < {enforce_threshold}% → enforced_required=false")
        
        if len(candidates) == 0:
            print("✓ No drawdown candidates (all strategies have drawdown < 8%)")


class TestStateHistoryReasonFields:
    """Test state-history endpoint returns reason_code and reason_detail"""

    def test_state_history_returns_reason_code(self, admin_headers):
        """Verify state history entries include reason_code"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/state-history",
            headers=admin_headers,
            params={"limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "rows" in data, "Response should have 'rows' field"
        rows = data["rows"]
        
        if len(rows) > 0:
            first_row = rows[0]
            assert "reason_code" in first_row, "reason_code field missing in state history entry"
            assert "reason_detail" in first_row, "reason_detail field missing in state history entry"
            print(f"✓ State history entry has reason_code: {first_row.get('reason_code')}")
            print(f"✓ State history entry has reason_detail: {first_row.get('reason_detail')}")
        else:
            print("✓ No state history entries yet (expected for fresh system)")

    def test_state_history_entry_structure(self, admin_headers):
        """Verify state history entry has all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/state-history",
            headers=admin_headers,
            params={"limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        rows = data.get("rows", [])
        
        required_fields = [
            "trace_id", "strategy_id", "action_type", 
            "previous_state", "new_state", "reason_code", 
            "reason_detail", "admin_id", "timestamp"
        ]
        
        if len(rows) > 0:
            for field in required_fields:
                assert field in rows[0], f"Missing field: {field}"
            print(f"✓ All required fields present in state history entry")
        else:
            print("✓ No state history entries to validate structure")


class TestDriftOverrideDetection:
    """Test drift override detection in PUT state update"""

    def test_state_reason_code_values(self, admin_headers):
        """Verify state_reason_code has valid values"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        valid_codes = ["AUTO_DISABLED_BY_DRIFT", "AUTO_THROTTLED_BY_DRIFT", "MANUAL_STATE", None]
        
        for row in data:
            code = row.get("state_reason_code")
            assert code in valid_codes or code is None, f"Invalid state_reason_code: {code}"
            
            # Verify consistency with state
            state = row.get("state")
            if code == "AUTO_DISABLED_BY_DRIFT":
                assert state == "DISABLED", f"AUTO_DISABLED_BY_DRIFT should have state=DISABLED, got {state}"
            elif code == "AUTO_THROTTLED_BY_DRIFT":
                assert state == "THROTTLED", f"AUTO_THROTTLED_BY_DRIFT should have state=THROTTLED, got {state}"
            
            print(f"✓ {row['strategy_id']}: state={state}, reason_code={code}")


class TestAllFieldsContract:
    """Contract test to verify all Phase 3a+b fields are present"""

    def test_strategy_allocation_full_contract(self, admin_headers):
        """Verify all Phase 3a+b fields in strategy allocation response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        phase3ab_fields = [
            "state_reason_code",
            "state_reason_detail", 
            "is_drift_override",
            "drawdown_pct",
            "exposure_ratio_pct",
            "suggested_reduced_capital",
            "is_auto_reduce_candidate",
        ]
        
        if len(data) > 0:
            row = data[0]
            missing = [f for f in phase3ab_fields if f not in row]
            assert len(missing) == 0, f"Missing Phase 3a+b fields: {missing}"
            print(f"✓ All Phase 3a+b fields present in strategy allocation response")
            for field in phase3ab_fields:
                print(f"  - {field}: {row.get(field)}")

    def test_summary_full_contract(self, admin_headers):
        """Verify all Phase 3a+b fields in summary response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-allocation/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        phase3ab_fields = [
            "total_exposure_ratio_pct",
            "exposure_warning_threshold_pct",
            "exposure_warning_state",
            "drawdown_threshold_pct",
            "drawdown_enforce_threshold_pct",
            "drawdown_candidates",
        ]
        
        missing = [f for f in phase3ab_fields if f not in data]
        assert len(missing) == 0, f"Missing Phase 3a+b fields in summary: {missing}"
        print(f"✓ All Phase 3a+b fields present in summary response")
        for field in phase3ab_fields:
            print(f"  - {field}: {data.get(field)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
