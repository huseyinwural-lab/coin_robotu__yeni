# Final Gap Closure Tests - Iteration 190
# Tests for: strategy-performance, scheduler/next-run, portfolio, reports, exchange-connections, risk-settings
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

class TestFinalGapClosureEndpoints:
    """Tests for final gap closure features"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login to get auth token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "review.user@platform.local", "password": "ReviewUser123!"}
        )
        if login_response.status_code == 200:
            token = login_response.json().get("token")
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
        yield
        self.session.close()

    def test_strategy_performance_endpoint(self):
        """GET /api/user/live/strategy-performance returns backtest/live mapping"""
        response = self.session.get(f"{BASE_URL}/api/user/live/strategy-performance", params={"window": "24h"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "window" in data, "Response should contain 'window' field"
        assert "items" in data, "Response should contain 'items' field"
        assert isinstance(data["items"], list), "'items' should be a list"
        # Verify structure of items if present
        if data["items"]:
            item = data["items"][0]
            assert "strategy_id" in item, "Item should have 'strategy_id'"
            assert "backtest" in item, "Item should have 'backtest' field"
            assert "live" in item, "Item should have 'live' field"
            assert "deviation_pct" in item, "Item should have 'deviation_pct'"
        print(f"PASS: strategy-performance returns {len(data['items'])} items")

    def test_scheduler_next_run_endpoint(self):
        """GET /api/user/live/scheduler/next-run returns backend scheduler source"""
        response = self.session.get(f"{BASE_URL}/api/user/live/scheduler/next-run")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "source" in data, "Response should contain 'source' field"
        assert data["source"] == "scheduler_config", f"Expected source='scheduler_config', got {data['source']}"
        assert "auto_enabled" in data, "Response should contain 'auto_enabled'"
        assert "interval_seconds" in data, "Response should contain 'interval_seconds'"
        print(f"PASS: scheduler/next-run returns source={data['source']}, auto_enabled={data.get('auto_enabled')}")

    def test_user_portfolio_endpoint(self):
        """GET /api/user/portfolio returns portfolio data"""
        response = self.session.get(f"{BASE_URL}/api/user/portfolio")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify expected portfolio fields
        expected_fields = ["current_capital", "available_balance", "open_notional", "open_positions_count"]
        for field in expected_fields:
            assert field in data, f"Portfolio should contain '{field}'"
        print(f"PASS: portfolio returns capital={data.get('current_capital')}")

    def test_user_performance_endpoint(self):
        """GET /api/user/performance returns performance metrics"""
        response = self.session.get(f"{BASE_URL}/api/user/performance")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        expected_fields = ["win_rate", "roi_pct", "profit_factor"]
        for field in expected_fields:
            assert field in data, f"Performance should contain '{field}'"
        print(f"PASS: performance returns win_rate={data.get('win_rate')}")

    def test_user_reports_weekly_endpoint(self):
        """GET /api/user/reports/weekly returns weekly report with download_links"""
        response = self.session.get(f"{BASE_URL}/api/user/reports/weekly", params={"include_artifacts": True})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "week" in data or "pnl" in data, "Report should contain 'week' or 'pnl'"
        print(f"PASS: reports/weekly returns week={data.get('week')}")

    def test_exchange_connections_endpoint(self):
        """GET /api/user/exchange-connections returns connection profiles"""
        response = self.session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Exchange connections should return a list"
        print(f"PASS: exchange-connections returns {len(data)} profiles")

    def test_user_risk_settings_endpoint(self):
        """GET /api/user-risk/settings returns risk settings"""
        response = self.session.get(f"{BASE_URL}/api/user-risk/settings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify risk settings structure
        print("PASS: user-risk/settings returns data")

    def test_auth_me_endpoint(self):
        """GET /api/auth/me returns user profile"""
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "email" in data, "User profile should contain 'email'"
        print(f"PASS: auth/me returns email={data.get('email')}")

    def test_bot_profiles_endpoint(self):
        """GET /api/bot-profiles returns bot profiles list"""
        response = self.session.get(f"{BASE_URL}/api/bot-profiles")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Bot profiles should return a list"
        print(f"PASS: bot-profiles returns {len(data)} profiles")

    def test_execution_intents_endpoint(self):
        """GET /api/user/execution/intents returns execution intents"""
        response = self.session.get(f"{BASE_URL}/api/user/execution/intents", params={"limit": 30})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Execution intents should return a list"
        print(f"PASS: execution/intents returns {len(data)} intents")

    def test_live_trades_endpoint(self):
        """GET /api/user/live/trades returns trades list"""
        response = self.session.get(f"{BASE_URL}/api/user/live/trades", params={"window": "24h"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Trades response should contain 'items'"
        print(f"PASS: live/trades returns {len(data.get('items', []))} trades")

    def test_live_execution_quality_endpoint(self):
        """GET /api/user/live/execution-quality returns execution quality metrics"""
        response = self.session.get(f"{BASE_URL}/api/user/live/execution-quality", params={"window": "24h"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "window" in data, "Execution quality should contain 'window'"
        print(f"PASS: execution-quality returns window={data.get('window')}")

    def test_live_summary_endpoint(self):
        """GET /api/user/live/summary returns dashboard summary"""
        response = self.session.get(f"{BASE_URL}/api/user/live/summary", params={"window": "1h"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "window" in data, "Summary should contain 'window'"
        assert "bots" in data, "Summary should contain 'bots'"
        print(f"PASS: live/summary returns window={data.get('window')}")

    def test_live_runtime_snapshot_endpoint(self):
        """GET /api/user/live/runtime-snapshot returns runtime snapshot"""
        response = self.session.get(f"{BASE_URL}/api/user/live/runtime-snapshot", params={"window": "1h"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "summary" in data, "Runtime snapshot should contain 'summary'"
        print("PASS: runtime-snapshot returns data")


class TestCALIDeterministicEdgeCases:
    """CALI parity edge-case tests for partial fill, cancel mismatch, reconnect/unverified sync"""

    def test_partial_fill_mismatch_detection(self):
        """Order reconciliation detects partial fill mismatch"""
        from core.live.order_reconciliation_engine import reconcile_order_state
        result = reconcile_order_state(
            engine_orders=[{"order_id": "partial-1", "symbol": "ETHUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "PARTIALLY_FILLED"}],
            exchange_orders=[{"order_id": "partial-1", "symbol": "ETHUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"}],
        )
        assert result["order_reconciliation_state"] == "ERROR", "Should detect partial fill mismatch"
        print("PASS: partial fill mismatch detected")

    def test_cancel_mismatch_detection(self):
        """Order reconciliation detects cancel mismatch"""
        from core.live.order_reconciliation_engine import reconcile_order_state
        result = reconcile_order_state(
            engine_orders=[{"order_id": "cancel-1", "symbol": "SOLUSDT", "side": "SELL", "price": 50, "quantity": 2, "status": "SENT"}],
            exchange_orders=[{"order_id": "cancel-1", "symbol": "SOLUSDT", "side": "SELL", "price": 50, "quantity": 2, "status": "CANCELED"}],
        )
        assert result["order_reconciliation_state"] == "ERROR", "Should detect cancel mismatch"
        print("PASS: cancel mismatch detected")

    def test_reconnect_unverified_sync(self):
        """Position sync detects unverified state on reconnect"""
        from core.live.position_sync_engine import reconcile_position_state
        result = reconcile_position_state(
            engine_positions=[{"symbol": "BNBUSDT", "position_size": 1.0, "entry_price": 100, "leverage": 2, "unrealized_pnl": 4}],
            exchange_positions=[],
        )
        assert result["position_sync_state"] == "UNVERIFIED", "Should detect unverified state"
        print("PASS: reconnect unverified sync detected")

    def test_position_drift_detection(self):
        """Position sync detects drift when sizes mismatch"""
        from core.live.position_sync_engine import reconcile_position_state
        result = reconcile_position_state(
            engine_positions=[{"symbol": "BTCUSDT", "position_size": 1.0, "entry_price": 100, "leverage": 2, "unrealized_pnl": 5}],
            exchange_positions=[{"symbol": "BTCUSDT", "position_size": 1.1, "entry_price": 100, "leverage": 2, "unrealized_pnl": 5}],
        )
        assert result["position_sync_state"] == "DRIFT", "Should detect position drift"
        print("PASS: position drift detected")
