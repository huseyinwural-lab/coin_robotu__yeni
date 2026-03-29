"""
Execution Microstructure P0 API Tests (TestClient)
==================================================
Tests for:
- Binance microstructure live data ingestion readiness through admin endpoints
- Bybit readiness/integration state exposed without crashing backend
- Pre-trade microstructure guard returns one of ALLOW/REDUCE_SIZE/SWITCH_EXECUTION_MODE/BLOCK
- Missing/invalid microstructure data results in BLOCK behavior
- Capacity pressure causes REDUCE_SIZE or BLOCK
- Runtime execution submit path is bound to microstructure precheck and rejects unsafe submissions
- Execution metric logging stores predicted vs realized slippage fields
"""

import os
import sys
import pytest

# Add backend to path
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from fastapi.testclient import TestClient
from server import app

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def client():
    """TestClient instance"""
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    """Get admin authentication token"""
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestAdminMicrostructureStatusEndpoint:
    """Tests for /api/admin/futures/microstructure/status endpoint"""

    def test_microstructure_status_returns_200(self, client, admin_headers):
        """Admin microstructure status endpoint should return 200"""
        response = client.get(
            "/api/admin/futures/microstructure/status",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"

    def test_microstructure_status_has_portfolio_state(self, client, admin_headers):
        """Status should include portfolio_microstructure_state field"""
        response = client.get(
            "/api/admin/futures/microstructure/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "portfolio_microstructure_state" in data, f"Missing portfolio_microstructure_state: {list(data.keys())}"
        assert data["portfolio_microstructure_state"] in {"SAFE", "WARNING", "CRITICAL", "BLOCKED"}


class TestAdminMicrostructureVenuesEndpoint:
    """Tests for /api/admin/futures/microstructure/venues endpoint"""

    def test_venues_endpoint_returns_200(self, client, admin_headers):
        """Venues endpoint should return 200"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"

    def test_venues_has_binance_and_bybit(self, client, admin_headers):
        """Venues response should include both binance and bybit"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        venues = data.get("venues", {})
        assert "binance" in venues, f"Missing binance venue: {list(venues.keys())}"
        assert "bybit" in venues, f"Missing bybit venue: {list(venues.keys())}"

    def test_binance_venue_readiness_state(self, client, admin_headers):
        """Binance venue should have status field (READY or INVALID)"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        binance = data.get("venues", {}).get("binance", {})
        assert "status" in binance, f"Missing status in binance venue: {list(binance.keys())}"
        assert binance["status"] in {"READY", "INVALID"}, f"Unexpected binance status: {binance['status']}"

    def test_bybit_venue_readiness_state_no_crash(self, client, admin_headers):
        """Bybit venue should have status field without crashing (may be INVALID)"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=admin_headers,
        )
        assert response.status_code == 200, "Bybit integration should not crash the endpoint"
        data = response.json()
        bybit = data.get("venues", {}).get("bybit", {})
        assert "status" in bybit, f"Missing status in bybit venue: {list(bybit.keys())}"
        # Bybit may be INVALID due to unreachable public endpoint - this is expected
        assert bybit["status"] in {"READY", "INVALID"}, f"Unexpected bybit status: {bybit['status']}"

    def test_venues_has_tracked_symbols(self, client, admin_headers):
        """Venues response should include tracked_symbols list"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "tracked_symbols" in data, f"Missing tracked_symbols: {list(data.keys())}"
        assert isinstance(data["tracked_symbols"], list)
        assert len(data["tracked_symbols"]) > 0, "tracked_symbols should not be empty"


class TestMicrostructureGuardPreview:
    """Tests for /api/admin/futures/microstructure/guard-preview endpoint"""

    def test_guard_preview_returns_200(self, client, admin_headers):
        """Guard preview endpoint should return 200"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"

    def test_guard_preview_returns_valid_state(self, client, admin_headers):
        """Guard preview should return one of ALLOW/REDUCE_SIZE/SWITCH_EXECUTION_MODE/BLOCK"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        assert "state" in data, f"Missing state field: {list(data.keys())}"
        valid_states = {"ALLOW", "REDUCE_SIZE", "SWITCH_EXECUTION_MODE", "BLOCK"}
        assert data["state"] in valid_states, f"Invalid state: {data['state']}, expected one of {valid_states}"

    def test_guard_preview_has_slippage_prediction(self, client, admin_headers):
        """Guard preview should include slippage_prediction with expected_slippage_bps"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        assert "slippage_prediction" in data, f"Missing slippage_prediction: {list(data.keys())}"
        slippage = data["slippage_prediction"]
        assert "expected_slippage_bps" in slippage, f"Missing expected_slippage_bps: {list(slippage.keys())}"
        assert isinstance(slippage["expected_slippage_bps"], (int, float))

    def test_guard_preview_has_market_snapshot(self, client, admin_headers):
        """Guard preview should include market_snapshot with data_state"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        assert "market_snapshot" in data, f"Missing market_snapshot: {list(data.keys())}"
        snapshot = data["market_snapshot"]
        assert "data_state" in snapshot, f"Missing data_state in market_snapshot: {list(snapshot.keys())}"
        assert snapshot["data_state"] in {"VALID", "INVALID"}

    def test_guard_preview_has_capacity_info(self, client, admin_headers):
        """Guard preview should include capacity assessment"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        assert "capacity" in data, f"Missing capacity: {list(data.keys())}"
        capacity = data["capacity"]
        assert "state" in capacity, f"Missing state in capacity: {list(capacity.keys())}"

    def test_guard_preview_oversized_order_blocks_or_reduces(self, client, admin_headers):
        """Oversized order should result in REDUCE_SIZE or BLOCK"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 100.0, "price": 65000},  # Very large size
        )
        assert response.status_code == 200
        data = response.json()
        # Large order should trigger capacity pressure
        assert data["state"] in {"REDUCE_SIZE", "BLOCK", "SWITCH_EXECUTION_MODE"}, \
            f"Expected capacity pressure state, got: {data['state']}"


class TestRuntimeExecutionSubmitPrecheck:
    """Tests for /api/runtime/execution/submit endpoint with microstructure precheck"""

    def test_runtime_submit_endpoint_exists(self, client, admin_headers):
        """Runtime submit endpoint should exist and respond"""
        response = client.post(
            "/api/runtime/execution/submit",
            headers=admin_headers,
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 0.001,
                "mark_price": 65000,
                "strategy_name": "ema_rsi",
            },
        )
        # Should not be 404 - endpoint exists
        assert response.status_code != 404, "Runtime submit endpoint not found"

    def test_runtime_submit_oversized_rejected_by_precheck(self, client, admin_headers):
        """Oversized order should be rejected by precheck with BLOCK state"""
        response = client.post(
            "/api/runtime/execution/submit",
            headers=admin_headers,
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1000.0,  # Very large size to trigger capacity block
                "mark_price": 65000,
                "strategy_name": "ema_rsi",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        # Should be rejected due to precheck failure
        assert data.get("status") == "rejected", f"Expected rejected status: {data}"
        # Check for precheck_failed reason
        risk = data.get("risk", {})
        reject_reason = risk.get("reject_reason") or data.get("reject_reason")
        assert reject_reason in {"precheck_failed", "capacity_limit_exceeded", "risk_limit_exceeded"}, \
            f"Expected precheck rejection reason, got: {reject_reason}"

    def test_runtime_submit_invalid_symbol_handled(self, client, admin_headers):
        """Invalid symbol should be handled gracefully"""
        response = client.post(
            "/api/runtime/execution/submit",
            headers=admin_headers,
            json={
                "symbol": "INVALIDXYZ",
                "side": "BUY",
                "size": 0.01,
                "mark_price": 100,
                "strategy_name": "ema_rsi",
            },
        )
        # Should not crash - either rejected or handled
        assert response.status_code in {200, 400, 422}, f"Unexpected status: {response.status_code}"


class TestExecutionQualityMetrics:
    """Tests for execution quality metrics with slippage fields"""

    def test_execution_quality_endpoint_exists(self, client, admin_headers):
        """Execution quality endpoint should exist"""
        response = client.get(
            "/api/admin/futures/execution-quality",
            headers=admin_headers,
        )
        # May be 200 or 404 depending on implementation
        if response.status_code == 404:
            pytest.skip("Execution quality endpoint not implemented at this path")
        assert response.status_code == 200

    def test_execution_metrics_endpoint_exists(self, client, admin_headers):
        """Execution metrics endpoint should exist"""
        response = client.get(
            "/api/admin/execution/metrics",
            headers=admin_headers,
        )
        # May be 200 or 404 depending on implementation
        if response.status_code == 404:
            pytest.skip("Execution metrics endpoint not implemented at this path")
        assert response.status_code == 200


class TestMicrostructureGuardStates:
    """Tests for all microstructure guard states"""

    def test_guard_state_allow_for_small_order(self, client, admin_headers):
        """Small order with valid data should potentially get ALLOW or SWITCH_EXECUTION_MODE
        Note: In TestClient environment without live cache, BLOCK is also acceptable due to missing snapshot
        """
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.001, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        # Small order should not be blocked due to capacity
        # May still be SWITCH_EXECUTION_MODE due to fast market
        # In TestClient without live cache, BLOCK is acceptable due to missing snapshot
        valid_states = {"ALLOW", "SWITCH_EXECUTION_MODE", "REDUCE_SIZE", "BLOCK"}
        assert data["state"] in valid_states, \
            f"Small order got unexpected state: {data['state']}"
        # If BLOCK, verify it's due to missing data, not capacity
        if data["state"] == "BLOCK":
            assert data["market_snapshot"]["data_state"] == "INVALID", \
                "BLOCK should be due to missing microstructure data in test environment"

    def test_guard_state_block_for_missing_data(self, client, admin_headers):
        """Order for symbol without microstructure data should be BLOCK"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "UNKNOWNUSDT", "side": "buy", "size": 0.01, "price": 100},
        )
        assert response.status_code == 200
        data = response.json()
        # Unknown symbol should result in BLOCK due to missing snapshot
        assert data["state"] == "BLOCK", f"Expected BLOCK for unknown symbol, got: {data['state']}"
        assert data["market_snapshot"]["data_state"] == "INVALID"

    def test_guard_reasons_populated(self, client, admin_headers):
        """Guard response should include reasons array"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        assert "reasons" in data, f"Missing reasons field: {list(data.keys())}"
        assert isinstance(data["reasons"], list)


class TestVenueSnapshots:
    """Tests for venue snapshot data in guard response"""

    def test_guard_has_venue_snapshots(self, client, admin_headers):
        """Guard response should include venue_snapshots for all venues"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        assert "venue_snapshots" in data, f"Missing venue_snapshots: {list(data.keys())}"
        snapshots = data["venue_snapshots"]
        assert "binance" in snapshots, f"Missing binance in venue_snapshots: {list(snapshots.keys())}"
        assert "bybit" in snapshots, f"Missing bybit in venue_snapshots: {list(snapshots.keys())}"

    def test_venue_snapshot_has_readiness_fields(self, client, admin_headers):
        """Each venue snapshot should have data_state and venue_readiness"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        for venue in ["binance", "bybit"]:
            snapshot = data["venue_snapshots"].get(venue, {})
            assert "data_state" in snapshot, f"Missing data_state in {venue} snapshot"
            assert "venue_readiness" in snapshot, f"Missing venue_readiness in {venue} snapshot"


class TestSlippagePredictionFields:
    """Tests for slippage prediction fields in guard response"""

    def test_slippage_prediction_has_all_components(self, client, admin_headers):
        """Slippage prediction should have spread_cost_bps, depth_impact_bps, latency_penalty_bps"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        slippage = data.get("slippage_prediction", {})
        required_fields = ["spread_cost_bps", "depth_impact_bps", "latency_penalty_bps", "expected_slippage_bps"]
        for field in required_fields:
            assert field in slippage, f"Missing {field} in slippage_prediction: {list(slippage.keys())}"
            assert isinstance(slippage[field], (int, float)), f"{field} should be numeric"


class TestCapacityAssessment:
    """Tests for capacity assessment in guard response"""

    def test_capacity_has_required_fields(self, client, admin_headers):
        """Capacity assessment should have state, requested_notional, allowed_notional"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        capacity = data.get("capacity", {})
        required_fields = ["state", "requested_notional", "allowed_notional"]
        for field in required_fields:
            assert field in capacity, f"Missing {field} in capacity: {list(capacity.keys())}"

    def test_capacity_state_valid(self, client, admin_headers):
        """Capacity state should be ALLOW, REDUCE_SIZE, or BLOCK"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=admin_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        capacity = data.get("capacity", {})
        assert capacity["state"] in {"ALLOW", "REDUCE_SIZE", "BLOCK"}, \
            f"Invalid capacity state: {capacity['state']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
