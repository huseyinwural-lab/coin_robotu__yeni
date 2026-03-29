# P1 Execution Microstructure API Tests using TestClient
# Tests: L2/L3 slippage decomposition, regime-aware execution policy, venue health/liquidity stress, replay endpoints

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient

from server import app
from db import SessionLocal
from core.security import hash_password
from models import User, UserRole, UserExchangeConnection, UserRiskSetting
import uuid


@pytest.fixture(scope="module")
def client():
    """TestClient for API calls"""
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_user():
    """Create or get admin user for testing"""
    db = SessionLocal()
    try:
        # Check if canary admin exists
        user = db.query(User).filter(User.email == "canary.admin@platform.local").first()
        if user:
            return user
        
        # Create test admin
        user = User(
            email=f"p1-test-admin-{uuid.uuid4().hex[:8]}@test.local",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.SUPER_ADMIN,
            is_active=True,
            approval_status="approved",
        )
        db.add(user)
        db.flush()
        
        # Add exchange connection
        db.add(UserExchangeConnection(
            user_id=user.id,
            account_label="default",
            exchange="binance",
            market_type="futures",
            environment="paper",
            is_default=True,
            readiness_snapshot={"connection_health": "online", "can_trade": True},
            permission_snapshot=["trade"],
            api_key_encrypted="x",
            api_secret_encrypted="y",
        ))
        
        # Add risk settings
        db.add(UserRiskSetting(
            user_id=user.id,
            allocation_pct=20,
            trade_risk_pct=10,
            daily_loss_limit_pct=3,
            compounding_enabled=True,
            base_capital=10000
        ))
        
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture(scope="module")
def auth_headers(client, admin_user):
    """Get auth headers using login"""
    response = client.post(
        "/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    return {"Authorization": f"Bearer {token}"}


class TestP1GuardPreviewSlippageDecomposition:
    """P1.1: Guard preview exposes L2/L3-aware slippage decomposition fields"""

    def test_guard_preview_returns_slippage_decomposition(self, client, auth_headers):
        """Verify slippage_decomposition contains spread_bps, impact_bps, timing_bps, retry_cost_bps"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify slippage_decomposition exists and has required fields
        assert "slippage_decomposition" in data, "Missing slippage_decomposition field"
        decomp = data["slippage_decomposition"]
        required_fields = {"spread_bps", "impact_bps", "timing_bps", "retry_cost_bps"}
        assert set(decomp.keys()) == required_fields, f"Expected {required_fields}, got {set(decomp.keys())}"
        
        # Verify all values are numeric
        for field in required_fields:
            assert isinstance(decomp[field], (int, float)), f"{field} should be numeric"

    def test_guard_preview_slippage_prediction_consistency(self, client, auth_headers):
        """Verify slippage_prediction.expected_slippage_bps equals sum of decomposition components"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        
        decomp = data.get("slippage_decomposition", {})
        prediction = data.get("slippage_prediction", {})
        
        # Sum of decomposition should approximately equal expected_slippage_bps
        decomp_sum = sum([
            decomp.get("spread_bps", 0),
            decomp.get("impact_bps", 0),
            decomp.get("timing_bps", 0),
            decomp.get("retry_cost_bps", 0),
        ])
        expected = prediction.get("expected_slippage_bps", 0)
        
        # Allow small floating point tolerance
        assert abs(decomp_sum - expected) < 0.001, f"Decomposition sum {decomp_sum} != expected {expected}"


class TestP1MarketRegimeAndExecutionRecommendation:
    """P1.2: Guard preview exposes market_regime and execution_recommendation outputs"""

    def test_guard_preview_returns_market_regime(self, client, auth_headers):
        """Verify market_regime contains trend, liquidity, market_speed, momentum_pct"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "market_regime" in data, "Missing market_regime field"
        regime = data["market_regime"]
        
        # Verify required fields
        assert "trend" in regime, "Missing trend in market_regime"
        assert "liquidity" in regime, "Missing liquidity in market_regime"
        assert "market_speed" in regime, "Missing market_speed in market_regime"
        assert "momentum_pct" in regime, "Missing momentum_pct in market_regime"
        
        # Verify trend is one of expected values
        assert regime["trend"] in {"bull", "bear", "chop"}, f"Unexpected trend: {regime['trend']}"
        
        # Verify liquidity is one of expected values
        assert regime["liquidity"] in {"high_liquidity", "low_liquidity"}, f"Unexpected liquidity: {regime['liquidity']}"
        
        # Verify market_speed is one of expected values
        assert regime["market_speed"] in {"fast", "normal"}, f"Unexpected market_speed: {regime['market_speed']}"

    def test_guard_preview_returns_execution_recommendation(self, client, auth_headers):
        """Verify execution_recommendation contains primary, all, venue_switch_candidates"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "execution_recommendation" in data, "Missing execution_recommendation field"
        rec = data["execution_recommendation"]
        
        # Verify required fields
        assert "primary" in rec, "Missing primary in execution_recommendation"
        assert "all" in rec, "Missing all in execution_recommendation"
        assert "venue_switch_candidates" in rec, "Missing venue_switch_candidates in execution_recommendation"
        
        # Verify primary is a valid recommendation
        valid_primaries = {"passive", "aggressive", "reduce-size", "slice"}
        assert rec["primary"] in valid_primaries, f"Unexpected primary: {rec['primary']}"
        
        # Verify all is a list
        assert isinstance(rec["all"], list), "all should be a list"
        
        # Verify venue_switch_candidates is a list
        assert isinstance(rec["venue_switch_candidates"], list), "venue_switch_candidates should be a list"


class TestP1VenueHealthAndLiquidityStress:
    """P1.3: Venue summary exposes venue_health_score and liquidity_stress_score"""

    def test_venues_endpoint_returns_health_scores(self, client, auth_headers):
        """Verify venues endpoint returns venue_health_score and liquidity_stress_score"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "venues" in data, "Missing venues field"
        venues = data["venues"]
        
        # Check binance venue (should be available)
        assert "binance" in venues, "Missing binance venue"
        binance = venues["binance"]
        
        assert "venue_health_score" in binance, "Missing venue_health_score in binance"
        assert "liquidity_stress_score" in binance, "Missing liquidity_stress_score in binance"
        
        # Verify scores are numeric and in valid range
        assert isinstance(binance["venue_health_score"], (int, float)), "venue_health_score should be numeric"
        assert isinstance(binance["liquidity_stress_score"], (int, float)), "liquidity_stress_score should be numeric"
        assert 0 <= binance["venue_health_score"] <= 100, f"venue_health_score out of range: {binance['venue_health_score']}"
        assert 0 <= binance["liquidity_stress_score"] <= 100, f"liquidity_stress_score out of range: {binance['liquidity_stress_score']}"

    def test_venues_endpoint_symbol_level_health(self, client, auth_headers):
        """Verify symbol-level venue_health is exposed in venues endpoint"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        binance = data.get("venues", {}).get("binance", {})
        symbols = binance.get("symbols", [])
        
        # At least one symbol should have venue_health
        if symbols:
            for sym in symbols:
                if sym.get("data_state") == "VALID":
                    assert "venue_health" in sym, f"Missing venue_health for symbol {sym.get('symbol')}"
                    vh = sym["venue_health"]
                    assert "venue_health_score" in vh, "Missing venue_health_score in symbol venue_health"
                    assert "liquidity_stress_score" in vh, "Missing liquidity_stress_score in symbol venue_health"
                    break

    def test_guard_preview_returns_venue_health(self, client, auth_headers):
        """Verify guard-preview also returns venue_health with scores"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "venue_health" in data, "Missing venue_health in guard-preview"
        vh = data["venue_health"]
        
        required_fields = {
            "venue_health_score", "liquidity_stress_score", "latency_score",
            "retry_score", "spread_instability", "depth_instability",
            "avg_transport_latency_ms", "retry_ratio"
        }
        for field in required_fields:
            assert field in vh, f"Missing {field} in venue_health"


class TestP1MicrostructureReplay:
    """P1.4: Microstructure replay endpoint returns historical rows"""

    def test_replay_endpoint_returns_items(self, client, auth_headers):
        """Verify replay endpoint returns items array"""
        response = client.get(
            "/api/admin/futures/microstructure/replay",
            headers=auth_headers,
            params={"limit": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "items" in data, "Missing items field in replay response"
        assert isinstance(data["items"], list), "items should be a list"

    def test_replay_endpoint_filters_by_symbol(self, client, auth_headers):
        """Verify replay endpoint filters by symbol parameter"""
        response = client.get(
            "/api/admin/futures/microstructure/replay",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        # If items exist, verify they match the filter
        for item in items:
            assert item.get("symbol") == "BTCUSDT", f"Item symbol mismatch: {item.get('symbol')}"

    def test_replay_endpoint_filters_by_venue(self, client, auth_headers):
        """Verify replay endpoint filters by venue parameter"""
        response = client.get(
            "/api/admin/futures/microstructure/replay",
            headers=auth_headers,
            params={"venue": "binance", "limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        # If items exist, verify they match the filter
        for item in items:
            assert item.get("venue") == "binance", f"Item venue mismatch: {item.get('venue')}"

    def test_replay_item_structure(self, client, auth_headers):
        """Verify replay items have expected structure"""
        response = client.get(
            "/api/admin/futures/microstructure/replay",
            headers=auth_headers,
            params={"limit": 5},
        )
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        if items:
            item = items[0]
            # Verify expected fields in replay item
            expected_fields = {"captured_at", "venue", "symbol", "data_state"}
            for field in expected_fields:
                assert field in item, f"Missing {field} in replay item"


class TestP1ExecutionReplayLatest:
    """P1.4: Execution replay latest endpoint explains root_cause for latest execution metric"""

    def test_execution_replay_latest_endpoint_exists(self, client, auth_headers):
        """Verify execution-replay/latest endpoint returns 200"""
        response = client.get(
            "/api/admin/futures/microstructure/execution-replay/latest",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should have status field
        assert "status" in data, "Missing status field"

    def test_execution_replay_latest_with_symbol_filter(self, client, auth_headers):
        """Verify execution-replay/latest accepts symbol filter"""
        response = client.get(
            "/api/admin/futures/microstructure/execution-replay/latest",
            headers=auth_headers,
            params={"symbol": "BTCUSDT"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # If status is ok, verify structure
        if data.get("status") == "ok":
            assert "root_cause" in data, "Missing root_cause when status is ok"
            assert "symbol" in data, "Missing symbol when status is ok"
            assert "predicted_slippage_bps" in data, "Missing predicted_slippage_bps"
            assert "realized_slippage_bps" in data, "Missing realized_slippage_bps"
            assert "slippage_error_bps" in data, "Missing slippage_error_bps"
            
            # Verify root_cause is one of expected values
            valid_causes = {"prediction_match", "market_impact", "fast_market", "timing_delay"}
            assert data["root_cause"] in valid_causes, f"Unexpected root_cause: {data['root_cause']}"

    def test_execution_replay_latest_empty_state(self, client, auth_headers):
        """Verify execution-replay/latest handles empty state gracefully"""
        response = client.get(
            "/api/admin/futures/microstructure/execution-replay/latest",
            headers=auth_headers,
            params={"symbol": "NONEXISTENT_SYMBOL_XYZ"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return empty status or reason
        if data.get("status") == "empty":
            assert "reason" in data, "Missing reason when status is empty"


class TestP0RegressionNoBreakingChanges:
    """Verify no regressions on existing P0 microstructure endpoints"""

    def test_microstructure_status_endpoint(self, client, auth_headers):
        """Verify /status endpoint still works"""
        response = client.get(
            "/api/admin/futures/microstructure/status",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "portfolio_microstructure_state" in data, "Missing portfolio_microstructure_state"

    def test_microstructure_venues_endpoint(self, client, auth_headers):
        """Verify /venues endpoint still works"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "tracked_symbols" in data, "Missing tracked_symbols"
        assert "venues" in data, "Missing venues"

    def test_guard_preview_state_field(self, client, auth_headers):
        """Verify guard-preview still returns state field"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        
        # P0 fields should still exist
        assert "state" in data, "Missing state field"
        assert "selected_venue" in data, "Missing selected_venue field"
        assert "slippage_prediction" in data, "Missing slippage_prediction field"
        assert "market_snapshot" in data, "Missing market_snapshot field"
        assert "capacity" in data, "Missing capacity field"

    def test_guard_preview_market_snapshot_structure(self, client, auth_headers):
        """Verify market_snapshot structure is preserved"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000},
        )
        assert response.status_code == 200
        data = response.json()
        
        snapshot = data.get("market_snapshot", {})
        required_fields = {"data_state", "venue_readiness", "best_bid", "best_ask", "mid_price", "spread_bps", "quote_age_ms"}
        for field in required_fields:
            assert field in snapshot, f"Missing {field} in market_snapshot"


class TestBybitVenueGracefulHandling:
    """Verify Bybit venue returns INVALID gracefully without crash"""

    def test_bybit_venue_in_venues_response(self, client, auth_headers):
        """Verify Bybit venue is present and handled gracefully"""
        response = client.get(
            "/api/admin/futures/microstructure/venues",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        venues = data.get("venues", {})
        assert "bybit" in venues, "Missing bybit venue"
        
        bybit = venues["bybit"]
        # Bybit may be INVALID due to 403, but should not crash
        assert "status" in bybit, "Missing status in bybit venue"
        assert "venue_health_score" in bybit, "Missing venue_health_score in bybit"
        assert "liquidity_stress_score" in bybit, "Missing liquidity_stress_score in bybit"

    def test_guard_preview_with_bybit_venue(self, client, auth_headers):
        """Verify guard-preview handles bybit venue parameter"""
        response = client.get(
            "/api/admin/futures/microstructure/guard-preview",
            headers=auth_headers,
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.01, "price": 65000, "venue": "bybit"},
        )
        # Should not crash, may return BLOCK due to INVALID data
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "state" in data, "Missing state field"
        assert "selected_venue" in data, "Missing selected_venue field"
