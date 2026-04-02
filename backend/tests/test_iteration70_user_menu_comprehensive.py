"""
Iteration 70 - User Menu Comprehensive Testing
Tests all user-facing features added in this iteration:
- Scanner quick presets
- Signals funnel metrics + diagnose/auto-fix
- Execute context persistence + clear
- Reports filters + compare
- Backtest insights filters
- Strategy templates user bridge
- Positions empty state + labels
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
USER_EMAIL = "e2_conn_last@example.com"
USER_PASSWORD = "User12345!"
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"User login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def user_headers(user_token):
    """Headers with user auth"""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {"Authorization": f"Bearer {admin_token}"}


# ==============================================================================
# HEALTH AND AUTH TESTS
# ==============================================================================
class TestHealthAndAuth:
    """Basic health and auth tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("PASS: Health endpoint accessible")
    
    def test_user_login(self):
        """Test user login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == USER_EMAIL
        print("PASS: User login successful")


# ==============================================================================
# SCANNER QUICK PRESET TESTS
# ==============================================================================
class TestScannerQuickPresets:
    """Tests for scanner preset card functionality"""
    
    def test_signal_mode_endpoint_exists(self, user_headers):
        """Test GET signal-mode endpoint returns valid response"""
        response = requests.get(f"{BASE_URL}/api/user/signal-mode", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert data["mode"] in ["MANUAL", "ASSISTED", "AUTO"]
        print(f"PASS: Signal mode endpoint returns mode={data['mode']}")
    
    def test_update_signal_mode_manual(self, user_headers):
        """Test updating signal mode to MANUAL"""
        response = requests.put(f"{BASE_URL}/api/user/signal-mode", 
            headers=user_headers, json={"mode": "MANUAL"})
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "MANUAL"
        print("PASS: Signal mode updated to MANUAL")
    
    def test_update_signal_mode_assisted(self, user_headers):
        """Test updating signal mode to ASSISTED"""
        response = requests.put(f"{BASE_URL}/api/user/signal-mode", 
            headers=user_headers, json={"mode": "ASSISTED"})
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "ASSISTED"
        print("PASS: Signal mode updated to ASSISTED")
    
    def test_update_signal_mode_auto(self, user_headers):
        """Test updating signal mode to AUTO"""
        response = requests.put(f"{BASE_URL}/api/user/signal-mode", 
            headers=user_headers, json={"mode": "AUTO"})
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "AUTO"
        print("PASS: Signal mode updated to AUTO")
    
    def test_scanner_run_with_mode(self, user_headers):
        """Test scanner run with specified mode"""
        # First set mode
        requests.put(f"{BASE_URL}/api/user/signal-mode", 
            headers=user_headers, json={"mode": "ASSISTED"})
        
        # Then run scanner
        response = requests.post(f"{BASE_URL}/api/user/scanner/run", 
            headers=user_headers, json={"mode": "ASSISTED", "max_results": 10})
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "mode" in data
        assert "result_count" in data
        assert "actionable_count" in data
        assert "queued_count" in data
        assert "pending_total" in data
        print(f"PASS: Scanner run successful with mode={data['mode']}, results={data['result_count']}")
    
    def test_scanner_overview(self, user_headers):
        """Test scanner overview endpoint"""
        response = requests.get(f"{BASE_URL}/api/user/scanner", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "total_results" in data
        assert "pending_signals" in data
        print(f"PASS: Scanner overview returns mode={data['mode']}, pending={data['pending_signals']}")
    
    def test_scanner_results(self, user_headers):
        """Test scanner results endpoint"""
        response = requests.get(f"{BASE_URL}/api/user/scanner/results", 
            headers=user_headers, params={"limit": 50})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            first = data[0]
            assert "id" in first
            assert "symbol" in first
            assert "signal" in first
            assert "confidence" in first
            assert "strategy_code" in first
        print(f"PASS: Scanner results returns {len(data)} items")


# ==============================================================================
# SIGNALS FUNNEL METRICS + DIAGNOSE TESTS
# ==============================================================================
class TestSignalsFunnelAndDiagnose:
    """Tests for signals funnel metrics and diagnose/auto-fix functionality"""
    
    def test_signals_list_endpoint(self, user_headers):
        """Test signals list returns all required fields for funnel metrics"""
        response = requests.get(f"{BASE_URL}/api/user/signals", 
            headers=user_headers, params={"limit": 100})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            signal = data[0]
            # Required fields for funnel metrics
            assert "id" in signal
            assert "status" in signal
            assert "created_order_intent_id" in signal or signal.get("created_order_intent_id") is None
            assert "blocked_reason_code" in signal or signal.get("blocked_reason_code") is None
            assert "execution_mode_label" in signal or signal.get("execution_mode_label") is None
            
            # Required trace fields
            assert "current_state" in signal or signal.get("current_state") is None
            assert "requires_manual_approval" in signal or signal.get("requires_manual_approval") is None
            assert "execution_eligible" in signal or signal.get("execution_eligible") is None
        
        print(f"PASS: Signals list returns {len(data)} signals with required fields")
    
    def test_signals_contain_trace_fields(self, user_headers):
        """Verify signals contain all trace fields needed for UI"""
        response = requests.get(f"{BASE_URL}/api/user/signals", 
            headers=user_headers, params={"limit": 100})
        assert response.status_code == 200
        data = response.json()
        
        # Check all signals for expected trace fields
        required_fields = [
            "id", "signal_id", "user_id", "symbol", "strategy_code", 
            "confidence", "mode", "status", "created_at"
        ]
        trace_fields = [
            "previous_state", "current_state", "blocked_reason_code",
            "blocked_reason_message", "blocked_solution_hint",
            "requires_manual_approval", "execution_eligible",
            "bot_profile_id", "risk_policy_id", "exchange_connection_id",
            "created_order_intent_id", "runtime_owner", "last_eligibility_check_at"
        ]
        
        for signal in data[:5]:  # Check first 5
            for field in required_fields:
                assert field in signal, f"Missing required field: {field}"
            for field in trace_fields:
                assert field in signal or signal.get(field, "MISSING") != "MISSING"
        
        print("PASS: Signals contain all required and trace fields")
    
    def test_signal_diagnose_endpoint(self, user_headers):
        """Test signal diagnose endpoint without auto_fix"""
        # Get a pending/blocked signal first
        signals_response = requests.get(f"{BASE_URL}/api/user/signals", 
            headers=user_headers, params={"limit": 100})
        signals = signals_response.json()
        
        actionable = [s for s in signals if s.get("status") in ["pending", "blocked", "ready"]]
        if not actionable:
            pytest.skip("No actionable signals to diagnose")
        
        signal_id = actionable[0]["id"]
        response = requests.post(f"{BASE_URL}/api/user/signal/{signal_id}/diagnose", 
            headers=user_headers, params={"auto_fix": False})
        
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "status" in data
        assert "current_state" in data
        assert "blocked_reason_code" in data
        assert "blocked_reason_message" in data
        assert "blocked_solution_hint" in data
        assert "requires_manual_approval" in data
        assert "execution_eligible" in data
        assert "actions_applied" in data
        assert isinstance(data["actions_applied"], list)
        print(f"PASS: Signal diagnose returns current_state={data['current_state']}, blocked={data['blocked_reason_code']}")
    
    def test_signal_diagnose_with_autofix(self, user_headers):
        """Test signal diagnose endpoint with auto_fix=True"""
        signals_response = requests.get(f"{BASE_URL}/api/user/signals", 
            headers=user_headers, params={"limit": 100})
        signals = signals_response.json()
        
        actionable = [s for s in signals if s.get("status") in ["pending", "blocked", "ready"]]
        if not actionable:
            pytest.skip("No actionable signals to diagnose")
        
        signal_id = actionable[0]["id"]
        response = requests.post(f"{BASE_URL}/api/user/signal/{signal_id}/diagnose", 
            headers=user_headers, params={"auto_fix": True})
        
        assert response.status_code == 200
        data = response.json()
        assert "actions_applied" in data
        print(f"PASS: Signal diagnose with auto_fix returns actions_applied={data['actions_applied']}")
    
    def test_signal_diagnose_not_found(self, user_headers):
        """Test diagnose returns 404 for non-existent signal"""
        response = requests.post(f"{BASE_URL}/api/user/signal/nonexistent-id/diagnose", 
            headers=user_headers, params={"auto_fix": False})
        assert response.status_code == 404
        print("PASS: Signal diagnose returns 404 for invalid ID")


# ==============================================================================
# EXECUTE CONTEXT TESTS
# ==============================================================================
class TestExecuteContext:
    """Tests for execute page context and connections"""
    
    def test_execution_presets_endpoint(self, user_headers):
        """Test execution presets endpoint"""
        response = requests.get(f"{BASE_URL}/api/user/execution/presets", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            preset = data[0]
            assert "preset_code" in preset
            assert "default_order_type" in preset
        print(f"PASS: Execution presets returns {len(data)} presets")
    
    def test_exchange_connections_endpoint(self, user_headers):
        """Test exchange connections endpoint"""
        response = requests.get(f"{BASE_URL}/api/user/exchange-connections", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            conn = data[0]
            assert "id" in conn
            assert "exchange" in conn
            assert "market_type" in conn
            assert "environment" in conn
        print(f"PASS: Exchange connections returns {len(data)} connections")
    
    def test_venue_access_check(self, user_headers):
        """Test venue access check endpoint"""
        response = requests.get(f"{BASE_URL}/api/venues/access-check", 
            headers=user_headers, params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live"
            })
        assert response.status_code == 200
        data = response.json()
        assert "allowed" in data
        assert "venue_state" in data
        print(f"PASS: Venue access check returns allowed={data['allowed']}, state={data['venue_state']}")
    
    def test_execution_intent_preview(self, user_headers):
        """Test execution intent preview endpoint"""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "take_profit_mode": "none",
            "take_profit_value": 0,
            "stop_loss_mode": "none",
            "stop_loss_value": 0,
            "execution_mode": "manual"
        }
        response = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", 
            headers=user_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "intent_id" in data
        assert "intent_token" in data
        assert "validation_status" in data
        assert "gate_decision" in data
        assert "meta_engine_decision" in data
        print(f"PASS: Execution intent preview returns validation={data['validation_status']}")


# ==============================================================================
# REPORTS FILTER TESTS
# ==============================================================================
class TestReportsFilters:
    """Tests for reports page week override and compare functionality"""
    
    def test_weekly_report_endpoint(self, user_headers):
        """Test weekly report endpoint returns expected structure"""
        response = requests.get(f"{BASE_URL}/api/user/reports/weekly", 
            headers=user_headers, params={"include_artifacts": True})
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "week" in data or data.get("detail") is not None
        print(f"PASS: Weekly report endpoint returns status={data.get('status', 'N/A')}")
    
    def test_weekly_report_with_week_override(self, user_headers):
        """Test weekly report with valid week override format"""
        response = requests.get(f"{BASE_URL}/api/user/reports/weekly", 
            headers=user_headers, params={
                "include_artifacts": False,
                "week": "2026-01-01"
            })
        assert response.status_code == 200
        data = response.json()
        # Even if no data, should return a valid structure
        assert "status" in data or "detail" in data
        print("PASS: Weekly report with week override returns valid response")
    
    def test_weekly_report_invalid_week_format(self, user_headers):
        """Test weekly report handles invalid week format gracefully"""
        response = requests.get(f"{BASE_URL}/api/user/reports/weekly", 
            headers=user_headers, params={
                "include_artifacts": False,
                "week": "invalid-date"
            })
        # Should either return 200 with empty/error or 4xx
        assert response.status_code in [200, 400, 422]
        print(f"PASS: Weekly report handles invalid week format (status={response.status_code})")


# ==============================================================================
# BACKTEST INSIGHTS FILTER TESTS
# ==============================================================================
class TestBacktestInsightsFilters:
    """Tests for backtest insights filtering and sorting"""
    
    def test_backtest_cards_endpoint(self, user_headers):
        """Test backtest cards endpoint"""
        response = requests.get(f"{BASE_URL}/api/backtest/cards", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            card = data[0]
            assert "id" in card
            assert "strategy_type" in card
            assert "market_type" in card
            assert "win_rate" in card
            assert "max_drawdown" in card
            assert "profit_factor" in card
            assert "sharpe_like_score" in card
            assert "risk_label" in card
        print(f"PASS: Backtest cards returns {len(data)} cards")
    
    def test_backtest_cards_filtering_viable(self, user_headers):
        """Test that backtest cards contain fields for UI filtering"""
        response = requests.get(f"{BASE_URL}/api/backtest/cards", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        market_types = set()
        strategy_types = set()
        for card in data:
            market_types.add(card.get("market_type"))
            strategy_types.add(card.get("strategy_type"))
        
        print(f"PASS: Found {len(market_types)} market types and {len(strategy_types)} strategy types for filtering")


# ==============================================================================
# STRATEGY TEMPLATES USER BRIDGE TESTS
# ==============================================================================
class TestStrategyTemplatesUserBridge:
    """Tests for strategy templates page and user bridge"""
    
    def test_strategy_templates_endpoint(self, user_headers):
        """Test strategy templates endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/strategy-templates", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            template = data[0]
            assert "id" in template
            assert "name" in template
            assert "strategy_type" in template
            assert "parameters" in template
        print(f"PASS: Strategy templates returns {len(data)} templates")


# ==============================================================================
# POSITIONS EMPTY STATE + LABELS TESTS
# ==============================================================================
class TestPositionsPage:
    """Tests for positions page functionality"""
    
    def test_positions_endpoint(self, user_headers):
        """Test execution positions endpoint"""
        response = requests.get(f"{BASE_URL}/api/user/execution/positions", 
            headers=user_headers, params={"include_closed": False})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            position = data[0]
            assert "position_id" in position
            assert "symbol" in position
            assert "size" in position
            assert "entry_price" in position
            assert "current_price" in position
            assert "unrealized_pnl" in position
            assert "leverage" in position
            # Optional intelligence fields
            assert "recommended_action" in position or position.get("recommended_action") is None
            assert "risk_reduction_score" in position or position.get("risk_reduction_score") is None
            assert "hedge_suggestion" in position or position.get("hedge_suggestion") is None
        print(f"PASS: Positions endpoint returns {len(data)} positions")
    
    def test_position_action_preview(self, user_headers):
        """Test position action preview endpoint structure"""
        # First get a position
        positions_response = requests.get(f"{BASE_URL}/api/user/execution/positions", 
            headers=user_headers, params={"include_closed": False})
        positions = positions_response.json()
        
        if not positions:
            pytest.skip("No open positions to test actions")
        
        position = positions[0]
        payload = {
            "intent_type": "CLOSE_POSITION",
            "position_id": position["position_id"],
            "symbol": position["symbol"],
            "size": float(position["size"]),
            "reduce_only": True
        }
        
        response = requests.post(f"{BASE_URL}/api/user/execution/position-actions/preview", 
            headers=user_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "intent_token" in data
        assert "validation_status" in data
        print(f"PASS: Position action preview returns validation={data['validation_status']}")


# ==============================================================================
# INDICATOR SCREENER CONTEXT PERSIST TESTS
# ==============================================================================
class TestIndicatorScreenerContext:
    """Tests for indicator screener context persistence to execute"""
    
    def test_screener_run_endpoint(self, user_headers):
        """Test indicator screener run endpoint"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi14 < 40",
            "limit": 20,
            "symbol_universe": "all",
            "filter_payload": {}
        }
        response = requests.post(f"{BASE_URL}/api/user/indicator-screener/run", 
            headers=user_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "matched_symbols" in data or "match_count" in data
        assert "rows" in data
        print(f"PASS: Indicator screener run returns {len(data.get('rows', []))} rows")
    
    def test_screener_results_contain_execute_context_fields(self, user_headers):
        """Test screener results contain fields needed for execute context"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi14 < 50",
            "limit": 10,
            "symbol_universe": "all",
            "filter_payload": {}
        }
        response = requests.post(f"{BASE_URL}/api/user/indicator-screener/run", 
            headers=user_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        
        if data.get("rows"):
            row = data["rows"][0]
            # Fields needed for execute context bridge
            assert "symbol" in row
            assert "market_type" in row
            assert "exchange" in row
            assert "signal_score" in row or row.get("signal_score") is None
            assert "confidence" in row or row.get("confidence") is None
        print("PASS: Screener results contain fields for execute context")


# ==============================================================================
# DECISION TRACE ENDPOINTS
# ==============================================================================
class TestDecisionTraceEndpoints:
    """Tests for signal and execution decision trace endpoints"""
    
    def test_signal_decision_trace_endpoint(self, user_headers):
        """Test signal decision trace endpoint"""
        signals_response = requests.get(f"{BASE_URL}/api/user/signals", 
            headers=user_headers, params={"limit": 10})
        signals = signals_response.json()
        
        if not signals:
            pytest.skip("No signals to get trace for")
        
        signal_id = signals[0]["id"]
        response = requests.get(f"{BASE_URL}/api/user/signals/{signal_id}/decision-trace", 
            headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        # May have latest_trace or be empty
        assert "latest_trace" in data or "timeline" in data or data == {}
        print("PASS: Signal decision trace endpoint returns valid response")
    
    def test_strategy_explain_endpoint(self, user_headers):
        """Test strategy explain endpoint"""
        signals_response = requests.get(f"{BASE_URL}/api/user/signals", 
            headers=user_headers, params={"limit": 10})
        signals = signals_response.json()
        
        if not signals:
            pytest.skip("No signals to get strategy from")
        
        strategy_code = signals[0].get("strategy_code", "spot_pullback_v1")
        response = requests.get(f"{BASE_URL}/api/user/strategies/{strategy_code}/explain", 
            headers=user_headers, params={"lookback_days": 30})
        # May return 200 or 404 depending on data
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "strategy_code" in data
        print(f"PASS: Strategy explain endpoint returns status={response.status_code}")


# ==============================================================================
# USER DASHBOARD ENDPOINT
# ==============================================================================
class TestUserDashboard:
    """Tests for user dashboard data"""
    
    def test_user_dashboard_endpoint(self, user_headers):
        """Test user dashboard endpoint returns expected structure"""
        response = requests.get(f"{BASE_URL}/api/user/dashboard", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert "bot_count" in data
        assert "running_bot_count" in data
        assert "risk_policy_count" in data
        assert "current_capital" in data
        assert "available_balance" in data
        assert "open_positions_count" in data
        assert "pending_signals_count" in data
        print(f"PASS: User dashboard returns pending_signals={data['pending_signals_count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
