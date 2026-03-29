"""
Iteration 63 - User P1 Closure Validation Tests

U-01: Primary Trading Flow (Scanner -> Signals -> Execute -> Queue -> Trade -> Position)
U-02: Execute Screen Professionalization
U-03: Signals Completion (explainability, allocation/confidence/meta/status, approve/reject/open-in-execute/preview intent)
U-04: Positions & Paper Positions (required columns and action intents)
U-05: Portfolio/Dashboard/Reports Integrity
U-06: User Form Quality (Risk Policy, Bot Profile, Exchange Settings)
U-07/U-08/U-09: Exchange Connection Model, Execute Venue Awareness, Bridge Context
U-10/U-11/U-12: Screener Filter Layer, End-to-End, Freshness Visibility Regression
"""

import os
import pytest
import requests

# Read BASE_URL from frontend/.env
def get_base_url():
    env_path = "/app/frontend/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.strip().split("=", 1)[1].strip('"').rstrip('/')
    return "https://unified-orchestrator.preview.emergentagent.com"

BASE_URL = get_base_url()

USER_EMAIL = "e2_conn_last@example.com"
USER_PASSWORD = "User12345!"
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def user_token():
    """Authenticate as user and get token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"User auth failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token():
    """Authenticate as admin and get token"""
    response = requests.post(f"{BASE_URL}/api/auth/login/admin", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin auth failed: {response.status_code} - {response.text}")


@pytest.fixture
def user_client(user_token):
    """Session with user auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_token}"
    })
    return session


@pytest.fixture
def admin_client(admin_token):
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    })
    return session


class TestU01PrimaryTradingFlow:
    """U-01: Scanner -> Signals -> Execute -> Queue -> Trade -> Position end-to-end"""

    def test_scanner_overview_endpoint(self, user_client):
        """Test /user/scanner overview returns valid structure"""
        response = user_client.get(f"{BASE_URL}/api/user/scanner")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "total_results" in data
        assert "pending_signals" in data

    def test_scanner_results_endpoint(self, user_client):
        """Test /user/scanner/results returns list"""
        response = user_client.get(f"{BASE_URL}/api/user/scanner/results?limit=20")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_signals_endpoint(self, user_client):
        """Test /user/signals returns signals with required fields"""
        response = user_client.get(f"{BASE_URL}/api/user/signals?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Check signal structure if any exist
        if data:
            signal = data[0]
            assert "id" in signal
            assert "symbol" in signal
            assert "status" in signal
            assert "strategy_code" in signal

    def test_execution_presets_endpoint(self, user_client):
        """Test /user/execution/presets returns presets"""
        response = user_client.get(f"{BASE_URL}/api/user/execution/presets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_execution_intents_endpoint(self, user_client):
        """Test /user/execution/intents returns queue items"""
        response = user_client.get(f"{BASE_URL}/api/user/execution/intents?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_positions_endpoint(self, user_client):
        """Test /user/execution/positions returns position list"""
        response = user_client.get(f"{BASE_URL}/api/user/execution/positions?include_closed=false")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestU02ExecuteScreenProfessionalization:
    """U-02: Execute form fields, preview requirement, invalid submit block, risk summary"""

    def test_execution_intent_preview_with_venue_context(self, user_client):
        """Test execution preview returns venue_context and risk summary"""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "execution_mode": "manual"
        }
        response = user_client.post(f"{BASE_URL}/api/user/execution/intent/preview", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "intent_id" in data
        assert "intent_token" in data
        assert "validation_status" in data
        assert "venue_context" in data
        assert "portfolio_risk_impact" in data
        assert "meta_strategy_summary" in data
        assert "gate_decision" in data
        assert "meta_engine_decision" in data
        
        # Check venue_context structure
        venue = data.get("venue_context", {})
        assert "exchange" in venue or venue == {}
        
        # Check risk impact structure
        risk = data.get("portfolio_risk_impact", {})
        if risk:
            assert "risk_score" in risk or risk == {}

    def test_execution_intent_preview_futures(self, user_client):
        """Test futures preview with leverage and margin mode"""
        payload = {
            "source_type": "manual",
            "market_type": "futures",
            "symbol": "BTCUSDT",
            "side": "long",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "margin_mode": "isolated",
            "leverage": 3,
            "execution_mode": "manual"
        }
        response = user_client.post(f"{BASE_URL}/api/user/execution/intent/preview", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "validation_status" in data


class TestU03SignalsCompletion:
    """U-03: Signals with explainability, allocation/confidence/meta/status, approve/reject flows"""

    def test_signals_have_meta_fields(self, user_client):
        """Test signals include allocation, confidence, meta_engine_decision"""
        response = user_client.get(f"{BASE_URL}/api/user/signals?limit=50")
        assert response.status_code == 200
        data = response.json()
        
        if data:
            signal = data[0]
            # These fields should exist (may be null but key should exist)
            expected_fields = ["strategy_code", "confidence", "status", "created_at"]
            for field in expected_fields:
                assert field in signal, f"Missing field: {field}"

    def test_signal_decision_trace_endpoint(self, user_client):
        """Test signal decision trace for explainability"""
        # First get a signal (minimum limit is 5)
        response = user_client.get(f"{BASE_URL}/api/user/signals?limit=5")
        assert response.status_code == 200
        data = response.json()
        
        if data:
            signal_id = data[0]["id"]
            trace_response = user_client.get(f"{BASE_URL}/api/user/signals/{signal_id}/decision-trace")
            # Should return 200 even if no trace exists
            assert trace_response.status_code in [200, 404]

    def test_strategy_explain_endpoint(self, user_client):
        """Test strategy explain endpoint"""
        response = user_client.get(f"{BASE_URL}/api/user/strategies/spot_scalp/explain?lookback_days=30")
        # May return 200 with data or 404 if no strategy
        assert response.status_code in [200, 404]


class TestU04PositionsAndActions:
    """U-04: Positions & Paper Positions with required columns and action intents"""

    def test_positions_have_required_columns(self, user_client):
        """Test positions include all required columns"""
        response = user_client.get(f"{BASE_URL}/api/user/execution/positions?include_closed=false")
        assert response.status_code == 200
        data = response.json()
        
        if data:
            pos = data[0]
            required_cols = [
                "position_id", "symbol", "size", "entry_price", "current_price",
                "unrealized_pnl", "leverage", "status"
            ]
            for col in required_cols:
                assert col in pos, f"Missing position column: {col}"
            
            # Check intelligence fields
            assert "recommended_action" in pos
            assert "risk_reduction_score" in pos
            assert "hedge_suggestion" in pos

    def test_position_action_close_preview(self, user_client):
        """Test position close action preview"""
        # Get a position first
        response = user_client.get(f"{BASE_URL}/api/user/execution/positions?include_closed=false")
        assert response.status_code == 200
        positions = response.json()
        
        if positions:
            pos = positions[0]
            payload = {
                "intent_type": "CLOSE_POSITION",
                "position_id": pos["position_id"],
                "symbol": pos["symbol"],
                "size": pos["size"],
                "reduce_only": True
            }
            preview_response = user_client.post(f"{BASE_URL}/api/user/execution/position-actions/preview", json=payload)
            assert preview_response.status_code == 200
            data = preview_response.json()
            assert "validation_status" in data


class TestU05PortfolioDashboardReports:
    """U-05: Portfolio/Dashboard/Reports integrity - capital/balance/pnl/win rate/profit factor"""

    def test_user_dashboard_endpoint(self, user_client):
        """Test /user/dashboard returns consistent metrics"""
        response = user_client.get(f"{BASE_URL}/api/user/dashboard")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        expected = ["current_capital", "available_balance", "open_positions_count"]
        for field in expected:
            assert field in data, f"Missing dashboard field: {field}"

    def test_user_portfolio_endpoint(self, user_client):
        """Test /user/portfolio returns portfolio metrics"""
        response = user_client.get(f"{BASE_URL}/api/user/portfolio")
        assert response.status_code == 200
        data = response.json()
        
        expected = ["current_capital", "available_balance", "open_notional", "closed_pnl"]
        for field in expected:
            assert field in data, f"Missing portfolio field: {field}"

    def test_user_performance_endpoint(self, user_client):
        """Test /user/performance returns performance metrics"""
        response = user_client.get(f"{BASE_URL}/api/user/performance")
        assert response.status_code == 200
        data = response.json()
        
        expected = ["win_rate", "roi_pct", "profit_factor"]
        for field in expected:
            assert field in data, f"Missing performance field: {field}"

    def test_user_trades_endpoint(self, user_client):
        """Test /user/trades returns trade history"""
        response = user_client.get(f"{BASE_URL}/api/user/trades?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestU06UserFormQuality:
    """U-06: User form quality - Risk Policy, Bot Profile, Exchange Settings"""

    def test_user_risk_settings_endpoint(self, user_client):
        """Test /user-risk/settings returns risk configuration"""
        response = user_client.get(f"{BASE_URL}/api/user-risk/settings")
        assert response.status_code == 200
        data = response.json()
        
        expected = ["allocation_pct", "trade_risk_pct", "daily_loss_limit_pct", "compounding_enabled"]
        for field in expected:
            assert field in data, f"Missing risk setting: {field}"

    def test_user_risk_preview_endpoint(self, user_client):
        """Test /user-risk/preview returns live preview"""
        response = user_client.get(f"{BASE_URL}/api/user-risk/preview?market_type=spot&leverage=1&margin_mode=cross&position_side=BOTH")
        assert response.status_code == 200
        data = response.json()
        
        assert "current_capital" in data
        assert "position_size" in data

    def test_phase4_exchange_settings_endpoint(self, user_client):
        """Test /phase4/exchange-settings returns exchange config"""
        response = user_client.get(f"{BASE_URL}/api/phase4/exchange-settings")
        assert response.status_code == 200
        data = response.json()
        
        assert "exchange" in data or data is None or data == {}


class TestU07U08U09ExchangeVenueBridge:
    """U-07/U-08/U-09: Exchange Connection Model, Execute Venue Awareness, Bridge Context"""

    def test_exchange_connections_list(self, user_client):
        """Test /user/exchange-connections returns connection profiles"""
        response = user_client.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            conn = data[0]
            assert "id" in conn
            assert "account_label" in conn
            assert "exchange" in conn
            assert "market_type" in conn
            assert "environment" in conn

    def test_venues_options_endpoint(self, user_client):
        """Test /venues/options returns available venues"""
        response = user_client.get(f"{BASE_URL}/api/venues/options")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_venues_access_check(self, user_client):
        """Test /venues/access-check returns access status"""
        response = user_client.get(f"{BASE_URL}/api/venues/access-check?exchange=binance&market_type=spot&environment=testnet")
        assert response.status_code == 200
        data = response.json()
        
        assert "allowed" in data
        assert "venue_state" in data

    def test_execution_preview_includes_venue_context(self, user_client):
        """Test execution preview includes venue_context for bridge awareness"""
        payload = {
            "source_type": "indicator-screener",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "execution_mode": "manual"
        }
        response = user_client.post(f"{BASE_URL}/api/user/execution/intent/preview", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # venue_context should exist in response
        assert "venue_context" in data


class TestU10U11U12ScreenerFilterFreshness:
    """U-10/U-11/U-12: Screener Filter Layer, End-to-End, Freshness Visibility"""

    def test_indicator_screener_presets(self, user_client):
        """Test /user/indicator-screener/presets returns presets"""
        response = user_client.get(f"{BASE_URL}/api/user/indicator-screener/presets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_indicator_screener_saved_queries(self, user_client):
        """Test /user/indicator-screener/saved-queries returns saved queries"""
        response = user_client.get(f"{BASE_URL}/api/user/indicator-screener/saved-queries")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_indicator_screener_run_with_filters(self, user_client):
        """Test /user/indicator-screener/run with filter layer returns freshness fields"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi14 < 50",
            "limit": 10,
            "symbol_universe": "all",
            "filter_payload": {
                "symbol_universe_mode": "all_tradable",
                "min_24h_volume": 100000,
                "market_participation": "spot_only",
                "only_tradable_pairs": True
            }
        }
        response = user_client.post(f"{BASE_URL}/api/user/indicator-screener/run", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Check meta fields
        assert "query_valid" in data
        assert "result_state" in data
        assert "match_count" in data
        
        # Check freshness fields in rows if any exist
        rows = data.get("rows", [])
        if rows:
            row = rows[0]
            # Freshness visibility fields
            freshness_fields = ["last_candle_time", "evaluated_at", "data_source"]
            for field in freshness_fields:
                assert field in row, f"Missing freshness field: {field}"

    def test_indicator_screener_watchlist(self, user_client):
        """Test /user/indicator-screener/watchlist endpoint"""
        response = user_client.get(f"{BASE_URL}/api/user/indicator-screener/watchlist")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestDecisionTraceExplainability:
    """Test decision trace and explainability endpoints"""

    def test_execution_intent_decision_trace(self, user_client):
        """Test decision trace for execution intents"""
        # First create a preview to get an intent
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "execution_mode": "manual"
        }
        preview_response = user_client.post(f"{BASE_URL}/api/user/execution/intent/preview", json=payload)
        assert preview_response.status_code == 200
        intent_id = preview_response.json().get("intent_id")
        
        if intent_id:
            trace_response = user_client.get(f"{BASE_URL}/api/user/execution/intents/{intent_id}/decision-trace")
            assert trace_response.status_code in [200, 404]


class TestHealthAndAuth:
    """Basic health and auth tests"""

    def test_health_endpoint(self):
        """Test /api/health returns ok"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_user_auth_login(self):
        """Test user login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    def test_admin_auth_login(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login/admin", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
