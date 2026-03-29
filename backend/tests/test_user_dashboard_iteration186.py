"""
Test suite for User Dashboard P0 features - Iteration 186
Tests: /api/market/candles, /api/user/live/runtime-snapshot, /api/user/live/queue,
       /api/user/execution/positions, /api/user/execution/intents
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def user_session():
    """Login as review user and return session with auth token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"User login failed: {login_response.status_code} - {login_response.text}")
    
    data = login_response.json()
    token = data.get("token") or data.get("access_token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestMarketCandles:
    """Tests for GET /api/market/candles endpoint"""
    
    def test_candles_btcusdt_1h(self, user_session):
        """Test candles endpoint returns valid data for BTCUSDT 1h"""
        response = user_session.get(
            f"{BASE_URL}/api/market/candles",
            params={"symbol": "BTCUSDT", "timeframe": "1h", "market_type": "futures", "limit": 100}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "candles" in data, "Response should contain 'candles' key"
        assert isinstance(data["candles"], list), "Candles should be a list"
        
        if len(data["candles"]) > 0:
            candle = data["candles"][0]
            assert "open" in candle, "Candle should have 'open'"
            assert "high" in candle, "Candle should have 'high'"
            assert "low" in candle, "Candle should have 'low'"
            assert "close" in candle, "Candle should have 'close'"
    
    def test_candles_different_timeframes(self, user_session):
        """Test candles endpoint with different timeframes"""
        for tf in ["5m", "15m", "1h", "4h", "1d"]:
            response = user_session.get(
                f"{BASE_URL}/api/market/candles",
                params={"symbol": "ETHUSDT", "timeframe": tf, "market_type": "futures", "limit": 50}
            )
            assert response.status_code == 200, f"Timeframe {tf} failed: {response.status_code}"
    
    def test_candles_invalid_symbol(self, user_session):
        """Test candles endpoint with invalid symbol returns 400"""
        response = user_session.get(
            f"{BASE_URL}/api/market/candles",
            params={"symbol": "INVALID123", "timeframe": "1h"}
        )
        assert response.status_code == 400, f"Expected 400 for invalid symbol, got {response.status_code}"


class TestUserLiveRuntimeSnapshot:
    """Tests for GET /api/user/live/runtime-snapshot endpoint"""
    
    def test_runtime_snapshot_returns_all_sections(self, user_session):
        """Test runtime-snapshot returns all required sections"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/runtime-snapshot",
            params={"window": "1h"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify all required sections exist
        required_sections = ["summary", "positions", "strategies", "trades", "queue", "decision_cards", "alerts"]
        for section in required_sections:
            assert section in data, f"Missing required section: {section}"
        
        # Verify generated_at timestamp
        assert "generated_at" in data, "Should have generated_at timestamp"
    
    def test_runtime_snapshot_summary_structure(self, user_session):
        """Test runtime-snapshot summary has correct structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/runtime-snapshot",
            params={"window": "1h"}
        )
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        
        # Check summary sub-sections
        assert "bots" in summary or summary == {}, "Summary should have bots or be empty"
        assert "open_positions" in summary or summary == {}, "Summary should have open_positions or be empty"
    
    def test_runtime_snapshot_different_windows(self, user_session):
        """Test runtime-snapshot with different window sizes"""
        for window in ["1h", "6h", "24h"]:
            response = user_session.get(
                f"{BASE_URL}/api/user/live/runtime-snapshot",
                params={"window": window}
            )
            assert response.status_code == 200, f"Window {window} failed: {response.status_code}"


class TestUserLiveQueue:
    """Tests for GET /api/user/live/queue endpoint"""
    
    def test_queue_returns_required_fields(self, user_session):
        """Test queue endpoint returns required fields"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/queue",
            params={"limit": 20}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "pending_orders" in data, "Should have pending_orders"
        assert "pending_decisions" in data, "Should have pending_decisions"
        assert "queue_depth" in data, "Should have queue_depth"
        assert "generated_at" in data, "Should have generated_at"
        
        # Verify types
        assert isinstance(data["pending_orders"], list), "pending_orders should be a list"
        assert isinstance(data["pending_decisions"], list), "pending_decisions should be a list"
        assert isinstance(data["queue_depth"], int), "queue_depth should be an integer"


class TestUserLiveSummary:
    """Tests for GET /api/user/live/summary endpoint"""
    
    def test_summary_returns_all_sections(self, user_session):
        """Test summary endpoint returns all required sections"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/summary",
            params={"window": "1h"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required sections
        required_sections = ["window", "generated_at", "bots", "open_positions", "performance", "risk", "execution", "strategies", "trades", "alerts"]
        for section in required_sections:
            assert section in data, f"Missing required section: {section}"


class TestUserLivePositions:
    """Tests for GET /api/user/live/positions endpoint"""
    
    def test_positions_returns_valid_structure(self, user_session):
        """Test positions endpoint returns valid structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/positions",
            params={"limit": 50, "offset": 0}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "positions" in data, "Should have positions"
        assert "positions_count" in data, "Should have positions_count"
        assert "total_positions_count" in data, "Should have total_positions_count"
        assert "generated_at" in data, "Should have generated_at"


class TestUserLivePerformance:
    """Tests for GET /api/user/live/performance endpoint"""
    
    def test_performance_returns_valid_structure(self, user_session):
        """Test performance endpoint returns valid structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/performance",
            params={"window": "24h"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "window" in data, "Should have window"
        assert "trades_today" in data, "Should have trades_today"
        assert "win_rate" in data, "Should have win_rate"
        assert "pnl_today" in data, "Should have pnl_today"


class TestUserLiveRisk:
    """Tests for GET /api/user/live/risk endpoint"""
    
    def test_risk_returns_valid_structure(self, user_session):
        """Test risk endpoint returns valid structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/risk",
            params={"window": "24h"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "window" in data, "Should have window"
        assert "own_portfolio_exposure" in data, "Should have own_portfolio_exposure"
        assert "daily_loss_limit_pct" in data, "Should have daily_loss_limit_pct"


class TestUserLiveExecutionQuality:
    """Tests for GET /api/user/live/execution-quality endpoint"""
    
    def test_execution_quality_returns_valid_structure(self, user_session):
        """Test execution-quality endpoint returns valid structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/execution-quality",
            params={"window": "24h"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "window" in data, "Should have window"
        assert "own_execution_quality_score" in data, "Should have own_execution_quality_score"


class TestUserLiveStrategies:
    """Tests for GET /api/user/live/strategies endpoint"""
    
    def test_strategies_returns_valid_structure(self, user_session):
        """Test strategies endpoint returns valid structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/strategies",
            params={"window": "24h", "limit": 20, "offset": 0}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "window" in data, "Should have window"
        assert "items" in data, "Should have items"
        assert "strategy_count" in data, "Should have strategy_count"


class TestUserLiveTrades:
    """Tests for GET /api/user/live/trades endpoint"""
    
    def test_trades_returns_valid_structure(self, user_session):
        """Test trades endpoint returns valid structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/trades",
            params={"window": "24h", "limit": 30, "offset": 0}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "window" in data, "Should have window"
        assert "items" in data, "Should have items"
        assert "trades_count" in data, "Should have trades_count"


class TestUserExecutionPositions:
    """Tests for GET /api/user/execution/positions endpoint"""
    
    def test_execution_positions_returns_list(self, user_session):
        """Test execution positions endpoint returns a list"""
        response = user_session.get(
            f"{BASE_URL}/api/user/execution/positions",
            params={"include_closed": False}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Should return a list of positions"


class TestUserExecutionIntents:
    """Tests for GET /api/user/execution/intents endpoint"""
    
    def test_execution_intents_returns_list(self, user_session):
        """Test execution intents endpoint returns a list"""
        response = user_session.get(
            f"{BASE_URL}/api/user/execution/intents",
            params={"limit": 30}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Should return a list of intents"


class TestUserDecisionCards:
    """Tests for GET /api/user/decision-cards endpoint"""
    
    def test_decision_cards_returns_valid_structure(self, user_session):
        """Test decision-cards endpoint returns valid structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/decision-cards",
            params={"limit": 8}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Should have items key"
        assert isinstance(data["items"], list), "items should be a list"


class TestUserDailyReport:
    """Tests for GET /api/user/live/daily-report endpoint"""
    
    def test_daily_report_returns_valid_structure(self, user_session):
        """Test daily-report endpoint returns valid structure"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/daily-report",
            params={"window": "24h"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "report_id" in data, "Should have report_id"
        assert "date" in data, "Should have date"
        assert "trades_today" in data, "Should have trades_today"


class TestUserDailyReportExport:
    """Tests for GET /api/user/live/daily-report/export endpoint"""
    
    def test_daily_report_export_json(self, user_session):
        """Test daily-report export as JSON"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": "json", "window": "24h"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "report_id" in data, "Should have report_id"
    
    def test_daily_report_export_csv(self, user_session):
        """Test daily-report export as CSV"""
        response = user_session.get(
            f"{BASE_URL}/api/user/live/daily-report/export",
            params={"format": "csv", "window": "24h"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert "text/csv" in response.headers.get("content-type", ""), "Should return CSV content type"
