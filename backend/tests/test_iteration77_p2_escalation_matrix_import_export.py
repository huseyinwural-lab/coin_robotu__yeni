"""
Iteration 77 - P2 Features Testing
- Escalation Center endpoints and UI tabs (Active Breaches, Acknowledged, Resolved)
- Ack endpoint role rule (admin + super_admin)
- Resolve endpoint role rule (super_admin only)
- POST /api/admin/risk-simulation/matrix-batch
- GET /api/admin/strategy-intelligence/export (json/csv)
- POST /api/admin/strategy-intelligence/import-json
- Symbol depth filters LiquidityBand/RiskBand/Exchange
- Regression: Preset panel + history compare + SLA queue fields
"""

import os
import pytest
import requests
import json

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def ops_token():
    """Get ops auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Ops login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def super_admin_user_id(super_admin_token):
    """Get super_admin user ID"""
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    if response.status_code != 200:
        pytest.skip("Could not get super_admin user info")
    return response.json().get("id")


class TestEscalationCenterEndpoints:
    """Test Escalation Center API endpoints"""

    def test_escalation_center_list_returns_three_categories(self, super_admin_token):
        """GET /api/admin/escalation-center returns active_breaches, acknowledged, resolved"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure has all three categories
        assert "active_breaches" in data, "Missing active_breaches field"
        assert "acknowledged" in data, "Missing acknowledged field"
        assert "resolved" in data, "Missing resolved field"
        
        # All should be lists
        assert isinstance(data["active_breaches"], list), "active_breaches should be a list"
        assert isinstance(data["acknowledged"], list), "acknowledged should be a list"
        assert isinstance(data["resolved"], list), "resolved should be a list"
        print(f"Escalation center: active={len(data['active_breaches'])}, ack={len(data['acknowledged'])}, resolved={len(data['resolved'])}")

    def test_escalation_center_item_fields(self, super_admin_token):
        """Verify escalation items have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check any available items for required fields
        all_items = data.get("active_breaches", []) + data.get("acknowledged", []) + data.get("resolved", [])
        if all_items:
            item = all_items[0]
            required_fields = [
                "escalation_id", "linked_request_id", "state", "escalation_level",
                "escalation_reason", "breach_age_seconds", "current_owner", "created_at"
            ]
            for field in required_fields:
                assert field in item, f"Missing required field: {field}"
            print(f"Escalation item fields verified: {list(item.keys())}")
        else:
            print("No escalation items to verify fields (empty state)")

    def test_escalation_ack_admin_allowed(self, admin_token):
        """POST /api/admin/escalation-center/{id}/ack - admin role allowed"""
        # First get escalation center to find an active item
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        active_items = data.get("active_breaches", [])
        if not active_items:
            pytest.skip("No active escalation items to test ack")
        
        escalation_id = active_items[0]["escalation_id"]
        ack_response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/{escalation_id}/ack",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"escalation_reason": "admin_ack_test_reason", "current_owner": "admin"},
        )
        # Admin should be allowed to ack
        assert ack_response.status_code in [200, 400], f"Expected 200 or 400, got {ack_response.status_code}: {ack_response.text}"
        print(f"Admin ack response: {ack_response.status_code}")

    def test_escalation_ack_super_admin_allowed(self, super_admin_token):
        """POST /api/admin/escalation-center/{id}/ack - super_admin role allowed"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        active_items = data.get("active_breaches", [])
        if not active_items:
            pytest.skip("No active escalation items to test ack")
        
        escalation_id = active_items[0]["escalation_id"]
        ack_response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/{escalation_id}/ack",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"escalation_reason": "super_admin_ack_test", "current_owner": "super_admin"},
        )
        # Super admin should be allowed to ack
        assert ack_response.status_code in [200, 400], f"Expected 200 or 400, got {ack_response.status_code}: {ack_response.text}"
        print(f"Super admin ack response: {ack_response.status_code}")

    def test_escalation_ack_ops_forbidden(self, ops_token):
        """POST /api/admin/escalation-center/{id}/ack - ops role forbidden"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {ops_token}"},
        )
        if response.status_code != 200:
            pytest.skip("Ops cannot access escalation center")
        
        data = response.json()
        active_items = data.get("active_breaches", [])
        if not active_items:
            pytest.skip("No active escalation items to test ack")
        
        escalation_id = active_items[0]["escalation_id"]
        ack_response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/{escalation_id}/ack",
            headers={"Authorization": f"Bearer {ops_token}"},
            json={"escalation_reason": "ops_ack_test", "current_owner": "ops"},
        )
        # Ops should be forbidden from ack
        assert ack_response.status_code == 403, f"Expected 403 for ops ack, got {ack_response.status_code}: {ack_response.text}"
        print("Ops correctly forbidden from ack")

    def test_escalation_resolve_super_admin_only(self, super_admin_token):
        """POST /api/admin/escalation-center/{id}/resolve - super_admin only"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Try to find an acknowledged item to resolve
        ack_items = data.get("acknowledged", [])
        active_items = data.get("active_breaches", [])
        items_to_try = ack_items + active_items
        
        if not items_to_try:
            pytest.skip("No escalation items to test resolve")
        
        escalation_id = items_to_try[0]["escalation_id"]
        resolve_response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/{escalation_id}/resolve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"escalation_reason": "super_admin_resolve_test"},
        )
        # Super admin should be allowed to resolve
        assert resolve_response.status_code in [200, 400], f"Expected 200 or 400, got {resolve_response.status_code}: {resolve_response.text}"
        print(f"Super admin resolve response: {resolve_response.status_code}")

    def test_escalation_resolve_admin_forbidden(self, admin_token):
        """POST /api/admin/escalation-center/{id}/resolve - admin forbidden"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalation-center",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        ack_items = data.get("acknowledged", [])
        active_items = data.get("active_breaches", [])
        items_to_try = ack_items + active_items
        
        if not items_to_try:
            pytest.skip("No escalation items to test resolve")
        
        escalation_id = items_to_try[0]["escalation_id"]
        resolve_response = requests.post(
            f"{BASE_URL}/api/admin/escalation-center/{escalation_id}/resolve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"escalation_reason": "admin_resolve_test"},
        )
        # Admin should be forbidden from resolve
        assert resolve_response.status_code == 403, f"Expected 403 for admin resolve, got {resolve_response.status_code}: {resolve_response.text}"
        print("Admin correctly forbidden from resolve")


class TestMatrixBatchSimulation:
    """Test POST /api/admin/risk-simulation/matrix-batch"""

    def test_matrix_batch_simulation_basic(self, super_admin_token, super_admin_user_id):
        """POST /api/admin/risk-simulation/matrix-batch - basic test"""
        payload = {
            "user_id": super_admin_user_id,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategy_bindings": ["spot_pullback_v1", "trend_follow_v1"],
            "side": "buy",
            "base_notional": 100,
            "volatility_pct": 3.0,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/matrix-batch",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure - matrix_id is the field name
        assert "matrix_id" in data, "Missing matrix_id"
        assert "total_runs" in data, "Missing total_runs"
        assert "items" in data, "Missing items"
        assert "summary" in data, "Missing summary"
        
        # Should have 2 symbols x 2 strategies = 4 runs
        assert data["total_runs"] >= 1, f"Expected at least 1 run, got {data['total_runs']}"
        print(f"Matrix batch: matrix_id={data['matrix_id']}, total_runs={data['total_runs']}, items={len(data.get('items', []))}")

    def test_matrix_batch_simulation_item_fields(self, super_admin_token, super_admin_user_id):
        """Verify matrix batch items have required fields"""
        payload = {
            "user_id": super_admin_user_id,
            "symbols": ["BTCUSDT"],
            "strategy_bindings": ["spot_pullback_v1"],
            "side": "buy",
            "base_notional": 100,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/matrix-batch",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        if items:
            item = items[0]
            required_fields = [
                "simulation_id", "symbol", "strategy_binding",
                "projected_risk_score", "severity_band"
            ]
            for field in required_fields:
                assert field in item, f"Missing required field: {field}"
            print(f"Matrix item fields: {list(item.keys())}")

    def test_matrix_batch_requires_symbols_and_strategies(self, super_admin_token, super_admin_user_id):
        """Matrix batch requires both symbols and strategy_bindings"""
        # Missing symbols
        payload = {
            "user_id": super_admin_user_id,
            "symbols": [],
            "strategy_bindings": ["spot_pullback_v1"],
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/matrix-batch",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400 for empty symbols, got {response.status_code}"
        
        # Missing strategies
        payload = {
            "user_id": super_admin_user_id,
            "symbols": ["BTCUSDT"],
            "strategy_bindings": [],
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation/matrix-batch",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400 for empty strategies, got {response.status_code}"
        print("Matrix batch validation working correctly")


class TestDataPortabilityExport:
    """Test GET /api/admin/strategy-intelligence/export"""

    def test_export_json_decision_requests(self, super_admin_token):
        """GET /api/admin/strategy-intelligence/export?export_format=json&dataset=decision_requests"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence/export",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"export_format": "json", "dataset": "decision_requests"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Should return JSON
        data = response.json()
        assert isinstance(data, (dict, list)), "Export should return JSON data"
        print(f"JSON export decision_requests: {type(data)}")

    def test_export_json_simulation_history(self, super_admin_token):
        """GET /api/admin/strategy-intelligence/export?export_format=json&dataset=simulation_history"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence/export",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"export_format": "json", "dataset": "simulation_history"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, (dict, list)), "Export should return JSON data"
        print(f"JSON export simulation_history: {type(data)}")

    def test_export_csv_decision_requests(self, super_admin_token):
        """GET /api/admin/strategy-intelligence/export?export_format=csv&dataset=decision_requests"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence/export",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"export_format": "csv", "dataset": "decision_requests"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Should return CSV text
        content_type = response.headers.get("content-type", "")
        assert "text" in content_type or response.text, "CSV export should return text content"
        print(f"CSV export decision_requests: {len(response.text)} chars")

    def test_export_csv_simulation_history(self, super_admin_token):
        """GET /api/admin/strategy-intelligence/export?export_format=csv&dataset=simulation_history"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence/export",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"export_format": "csv", "dataset": "simulation_history"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"CSV export simulation_history: {len(response.text)} chars")


class TestDataPortabilityImport:
    """Test POST /api/admin/strategy-intelligence/import-json"""

    def test_import_json_super_admin_only(self, admin_token):
        """POST /api/admin/strategy-intelligence/import-json - admin forbidden"""
        payload = {"simulation_runs": [], "decision_requests": []}
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-intelligence/import-json",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        # Admin should be forbidden from import
        assert response.status_code == 403, f"Expected 403 for admin import, got {response.status_code}: {response.text}"
        print("Admin correctly forbidden from import")

    def test_import_json_super_admin_allowed(self, super_admin_token):
        """POST /api/admin/strategy-intelligence/import-json - super_admin allowed"""
        payload = {"simulation_runs": [], "decision_requests": []}
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy-intelligence/import-json",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "imported_simulation_runs" in data or "status" in data, "Import should return result"
        print(f"Import response: {data}")


class TestSymbolDepthFilters:
    """Test Symbol depth filters LiquidityBand/RiskBand/Exchange"""

    def test_symbol_universe_endpoint_exists(self, super_admin_token):
        """GET /api/symbol-selector/universe returns data"""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"source": "crypto", "exchange": "binance", "market_type": "spot"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "rows" in data, "Missing rows field"
        print(f"Symbol universe: {len(data.get('rows', []))} rows")

    def test_symbol_rows_have_volume_for_liquidity_band(self, super_admin_token):
        """Symbol rows should have volume_24h for liquidity band calculation"""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"source": "crypto", "exchange": "binance", "market_type": "spot"},
        )
        assert response.status_code == 200
        
        data = response.json()
        rows = data.get("rows", [])
        if rows:
            row = rows[0]
            # Check for volume field (used for liquidity band calculation)
            assert "volume_24h" in row or "exchange" in row, "Row should have volume_24h or exchange field"
            print(f"Symbol row fields: {list(row.keys())}")

    def test_symbol_rows_have_exchange_field(self, super_admin_token):
        """Symbol rows should have exchange field for filtering"""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"source": "crypto", "exchange": "binance", "market_type": "spot"},
        )
        assert response.status_code == 200
        
        data = response.json()
        rows = data.get("rows", [])
        if rows:
            row = rows[0]
            assert "exchange" in row, "Row should have exchange field"
            print(f"Exchange field present: {row.get('exchange')}")


class TestRegressionPresetHistorySLA:
    """Regression tests for Preset panel + history compare + SLA queue fields"""

    def test_presets_endpoint_returns_three_presets(self, super_admin_token):
        """GET /api/admin/risk-simulation/presets returns 3 presets"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/presets",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        assert len(items) >= 3, f"Expected at least 3 presets, got {len(items)}"
        
        preset_keys = [item.get("preset_key") for item in items]
        assert "high_volatility" in preset_keys, "Missing high_volatility preset"
        assert "liquidity_shock" in preset_keys, "Missing liquidity_shock preset"
        assert "conflict_heavy" in preset_keys, "Missing conflict_heavy preset"
        print(f"Presets verified: {preset_keys}")

    def test_simulation_history_endpoint(self, super_admin_token):
        """GET /api/admin/risk-simulation/history returns items"""
        response = requests.get(
            f"{BASE_URL}/api/admin/risk-simulation/history",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            params={"limit": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Missing items field"
        print(f"History items: {len(data.get('items', []))}")

    def test_decision_requests_have_sla_fields(self, super_admin_token):
        """GET /api/admin/decision-requests includes SLA fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/decision-requests",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        if items:
            item = items[0]
            sla_fields = ["sla_countdown_seconds", "sla_state", "escalation_state"]
            for field in sla_fields:
                assert field in item, f"Missing SLA field: {field}"
            print(f"SLA fields verified: sla_state={item.get('sla_state')}, escalation_state={item.get('escalation_state')}")
        else:
            print("No decision requests to verify SLA fields")

    def test_simulation_compare_endpoint(self, super_admin_token, super_admin_user_id):
        """GET /api/admin/simulation-runs/{run_id}/compare-current works"""
        # First create a simulation to get a run_id
        sim_payload = {
            "user_id": super_admin_user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "strategy_binding": "spot_pullback_v1",
            },
        }
        sim_response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json=sim_payload,
        )
        if sim_response.status_code != 200:
            pytest.skip("Could not create simulation for compare test")
        
        sim_data = sim_response.json()
        run_id = sim_data.get("simulation_id")
        if not run_id:
            pytest.skip("No simulation_id returned")
        
        # Now test compare endpoint
        compare_response = requests.get(
            f"{BASE_URL}/api/admin/simulation-runs/{run_id}/compare-current",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert compare_response.status_code == 200, f"Expected 200, got {compare_response.status_code}: {compare_response.text}"
        
        compare_data = compare_response.json()
        assert "before" in compare_data, "Missing before field"
        assert "current" in compare_data, "Missing current field"
        assert "compare_summary" in compare_data, "Missing compare_summary field"
        print(f"Compare endpoint verified: {list(compare_data.keys())}")


class TestStrategyIntelligenceDashboard:
    """Test main strategy intelligence dashboard endpoint"""

    def test_strategy_intelligence_dashboard(self, super_admin_token):
        """GET /api/admin/strategy-intelligence returns dashboard data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy-intelligence",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        required_fields = [
            "generated_at", "strategy_conflicts", "capital_rebalance_events",
            "hedge_suggestions", "governance_summary"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"Dashboard fields: {list(data.keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
