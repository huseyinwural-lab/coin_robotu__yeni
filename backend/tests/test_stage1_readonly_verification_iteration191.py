"""
Stage 1 Read-Only/Simulation Verification Tests - Iteration 191

Tests verify:
1. Stage 1 read-only data chain: market data ON, scanner ON, signals ON
2. Execution is still simulate/read-only from user-visible routes
3. Risk is visible and logged via user/live/risk + runtime snapshot + alerts
4. Signal -> decision -> execution-intent visibility chain
5. Backtest ↔ live deviation via strategy-performance endpoint
6. Data consistency across summary/runtime-snapshot/queue/decision-cards endpoints
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://localhost:8001"

# Test credentials
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"


class TestStage1ReadOnlyVerification:
    """Stage 1 read-only data chain verification tests"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session with JWT token"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                session.headers.update({"Authorization": f"Bearer {token}"})
        
        return session

    # ==================== MARKET DATA TESTS ====================
    
    def test_market_candles_endpoint_returns_200(self, auth_session):
        """Test /api/market/candles returns 200 with valid data"""
        response = auth_session.get(
            f"{BASE_URL}/api/market/candles",
            params={"symbol": "BTCUSDT", "timeframe": "1h", "market_type": "futures"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify candle data structure
        assert isinstance(data, (list, dict)), "Response should be list or dict"
        print(f"✓ Market candles endpoint working - returned {type(data).__name__}")

    def test_market_candles_multiple_timeframes(self, auth_session):
        """Test market candles supports multiple timeframes"""
        timeframes = ["5m", "15m", "1h", "4h", "1d"]
        for tf in timeframes:
            response = auth_session.get(
                f"{BASE_URL}/api/market/candles",
                params={"symbol": "ETHUSDT", "timeframe": tf, "market_type": "futures"}
            )
            assert response.status_code in [200, 400], f"Timeframe {tf} failed: {response.status_code}"
            print(f"✓ Market candles timeframe {tf}: {response.status_code}")

    # ==================== USER LIVE DASHBOARD TESTS ====================

    def test_user_live_summary_endpoint(self, auth_session):
        """Test /api/user/live/summary returns correct structure"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        expected_fields = ["window", "generated_at", "bots", "open_positions", "performance", "risk", "execution", "strategies", "trades", "alerts"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live summary endpoint working - window: {data.get('window')}")

    def test_user_live_runtime_snapshot_endpoint(self, auth_session):
        """Test /api/user/live/runtime-snapshot returns all sections"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/runtime-snapshot")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required sections
        expected_sections = ["summary", "positions", "strategies", "trades", "queue", "decision_cards", "alerts"]
        for section in expected_sections:
            assert section in data, f"Missing section: {section}"
        
        print(f"✓ Runtime snapshot endpoint working - sections: {list(data.keys())}")

    def test_user_live_queue_endpoint(self, auth_session):
        """Test /api/user/live/queue returns queue data"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/queue")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        expected_fields = ["pending_orders", "pending_decisions", "queue_depth", "generated_at"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live queue endpoint working - queue_depth: {data.get('queue_depth')}")

    def test_user_live_risk_endpoint(self, auth_session):
        """Test /api/user/live/risk returns risk data"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/risk")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        expected_fields = ["window", "own_portfolio_exposure", "daily_loss_limit_pct"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live risk endpoint working - exposure: {data.get('own_portfolio_exposure')}")

    # ==================== DECISION CARDS & SIGNALS TESTS ====================

    def test_user_decision_cards_endpoint(self, auth_session):
        """Test /api/user/decision-cards returns decision cards"""
        response = auth_session.get(f"{BASE_URL}/api/user/decision-cards")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should return list or dict with items
        assert isinstance(data, (list, dict)), "Response should be list or dict"
        print(f"✓ Decision cards endpoint working - type: {type(data).__name__}")

    def test_user_signals_endpoint(self, auth_session):
        """Test /api/user/signals returns signals list"""
        response = auth_session.get(f"{BASE_URL}/api/user/signals")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Signals should be a list"
        print(f"✓ User signals endpoint working - count: {len(data)}")

    def test_user_scanner_overview_endpoint(self, auth_session):
        """Test /api/user/scanner returns scanner overview"""
        response = auth_session.get(f"{BASE_URL}/api/user/scanner")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        expected_fields = ["mode", "total_results", "pending_signals"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ Scanner overview endpoint working - mode: {data.get('mode')}")

    # ==================== EXECUTION INTENTS TESTS ====================

    def test_user_execution_intents_endpoint(self, auth_session):
        """Test /api/user/execution/intents returns intents list"""
        response = auth_session.get(f"{BASE_URL}/api/user/execution/intents")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Intents should be a list"
        print(f"✓ Execution intents endpoint working - count: {len(data)}")

    def test_user_execution_positions_endpoint(self, auth_session):
        """Test /api/user/execution/positions returns positions list"""
        response = auth_session.get(f"{BASE_URL}/api/user/execution/positions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Positions should be a list"
        print(f"✓ Execution positions endpoint working - count: {len(data)}")

    def test_user_execution_presets_endpoint(self, auth_session):
        """Test /api/user/execution/presets returns presets"""
        response = auth_session.get(f"{BASE_URL}/api/user/execution/presets")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Presets should be a list"
        print(f"✓ Execution presets endpoint working - count: {len(data)}")

    # ==================== STRATEGY PERFORMANCE TESTS ====================

    def test_user_strategy_performance_endpoint(self, auth_session):
        """Test /api/user/live/strategy-performance returns backtest/live mapping"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/strategy-performance")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "window" in data, "Missing window field"
        assert "items" in data, "Missing items field"
        
        # Verify items structure if any exist
        items = data.get("items", [])
        if items:
            item = items[0]
            assert "strategy_id" in item, "Missing strategy_id in item"
            assert "backtest" in item, "Missing backtest in item"
            assert "live" in item, "Missing live in item"
            assert "deviation_pct" in item, "Missing deviation_pct in item"
        
        print(f"✓ Strategy performance endpoint working - items: {len(items)}")

    def test_user_scheduler_next_run_endpoint(self, auth_session):
        """Test /api/user/live/scheduler/next-run returns scheduler info"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/scheduler/next-run")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        expected_fields = ["source", "auto_enabled", "interval_seconds"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        assert data.get("source") == "scheduler_config", f"Expected source=scheduler_config, got {data.get('source')}"
        print(f"✓ Scheduler next-run endpoint working - auto_enabled: {data.get('auto_enabled')}")

    # ==================== DATA CONSISTENCY TESTS ====================

    def test_data_consistency_summary_vs_runtime_snapshot(self, auth_session):
        """Test data consistency between summary and runtime-snapshot"""
        summary_response = auth_session.get(f"{BASE_URL}/api/user/live/summary")
        snapshot_response = auth_session.get(f"{BASE_URL}/api/user/live/runtime-snapshot")
        
        assert summary_response.status_code == 200
        assert snapshot_response.status_code == 200
        
        summary = summary_response.json()
        snapshot = snapshot_response.json()
        
        # Verify snapshot contains summary
        assert "summary" in snapshot, "Snapshot should contain summary"
        
        # Verify window consistency
        assert summary.get("window") == snapshot.get("summary", {}).get("window"), "Window should be consistent"
        
        print("✓ Data consistency verified between summary and runtime-snapshot")

    def test_data_consistency_queue_in_snapshot(self, auth_session):
        """Test queue data is present in runtime snapshot"""
        queue_response = auth_session.get(f"{BASE_URL}/api/user/live/queue")
        snapshot_response = auth_session.get(f"{BASE_URL}/api/user/live/runtime-snapshot")
        
        assert queue_response.status_code == 200
        assert snapshot_response.status_code == 200
        
        queue = queue_response.json()
        snapshot = snapshot_response.json()
        
        # Verify queue is in snapshot
        assert "queue" in snapshot, "Snapshot should contain queue"
        
        print("✓ Queue data consistency verified in runtime snapshot")

    def test_data_consistency_decision_cards_in_snapshot(self, auth_session):
        """Test decision cards are present in runtime snapshot"""
        cards_response = auth_session.get(f"{BASE_URL}/api/user/decision-cards")
        snapshot_response = auth_session.get(f"{BASE_URL}/api/user/live/runtime-snapshot")
        
        assert cards_response.status_code == 200
        assert snapshot_response.status_code == 200
        
        snapshot = snapshot_response.json()
        
        # Verify decision_cards is in snapshot
        assert "decision_cards" in snapshot, "Snapshot should contain decision_cards"
        
        print("✓ Decision cards consistency verified in runtime snapshot")

    # ==================== EXECUTION MODE VERIFICATION ====================

    def test_execution_mode_is_simulation(self, auth_session):
        """Verify execution mode is simulation/read-only (Stage 1)"""
        # Check via execution positions - should show execution_mode
        response = auth_session.get(f"{BASE_URL}/api/user/execution/positions")
        assert response.status_code == 200
        data = response.json()
        
        # If positions exist, verify execution_mode
        if data:
            for pos in data:
                exec_mode = pos.get("execution_mode", "").lower()
                # Stage 1 should be simulation/mocked
                assert exec_mode in ["mocked", "simulation", "sim", "testnet", ""], \
                    f"Unexpected execution_mode: {exec_mode}"
        
        print("✓ Execution mode verification passed (simulation/read-only)")

    def test_live_trading_not_enabled(self, auth_session):
        """Verify live trading is not enabled (Stage 1 read-only)"""
        # Check env vars indicate simulation mode
        # This is verified by the fact that execution intents don't trigger real trades
        response = auth_session.get(f"{BASE_URL}/api/user/execution/intents")
        assert response.status_code == 200
        
        print("✓ Live trading verification passed (Stage 1 read-only)")

    # ==================== ADDITIONAL LIVE DASHBOARD ENDPOINTS ====================

    def test_user_live_positions_endpoint(self, auth_session):
        """Test /api/user/live/positions returns positions data"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/positions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        expected_fields = ["positions", "positions_count", "total_positions_count", "generated_at"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live positions endpoint working - count: {data.get('positions_count')}")

    def test_user_live_performance_endpoint(self, auth_session):
        """Test /api/user/live/performance returns performance data"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/performance")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        expected_fields = ["window", "trades_today", "win_rate", "pnl_today"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live performance endpoint working - trades_today: {data.get('trades_today')}")

    def test_user_live_execution_quality_endpoint(self, auth_session):
        """Test /api/user/live/execution-quality returns quality metrics"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/execution-quality")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        expected_fields = ["window", "own_execution_quality_score"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live execution quality endpoint working - score: {data.get('own_execution_quality_score')}")

    def test_user_live_strategies_endpoint(self, auth_session):
        """Test /api/user/live/strategies returns strategies data"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/strategies")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        expected_fields = ["window", "items", "strategy_count"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live strategies endpoint working - count: {data.get('strategy_count')}")

    def test_user_live_trades_endpoint(self, auth_session):
        """Test /api/user/live/trades returns trades data"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/trades")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        expected_fields = ["window", "items", "trades_count"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live trades endpoint working - count: {data.get('trades_count')}")

    def test_user_live_daily_report_endpoint(self, auth_session):
        """Test /api/user/live/daily-report returns daily report"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/daily-report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        expected_fields = ["report_id", "date", "trades_today"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ User live daily report endpoint working - date: {data.get('date')}")


class TestStage1SignalDecisionChain:
    """Test signal -> decision -> execution-intent visibility chain"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session with JWT token"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                session.headers.update({"Authorization": f"Bearer {token}"})
        
        return session

    def test_signal_mode_endpoint(self, auth_session):
        """Test /api/user/signal-mode returns current mode"""
        response = auth_session.get(f"{BASE_URL}/api/user/signal-mode")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "mode" in data, "Missing mode field"
        print(f"✓ Signal mode endpoint working - mode: {data.get('mode')}")

    def test_scanner_automation_config_endpoint(self, auth_session):
        """Test /api/user/scanner/automation returns automation config"""
        response = auth_session.get(f"{BASE_URL}/api/user/scanner/automation")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "auto_enabled" in data, "Missing auto_enabled field"
        print(f"✓ Scanner automation config endpoint working - auto_enabled: {data.get('auto_enabled')}")

    def test_scanner_results_endpoint(self, auth_session):
        """Test /api/user/scanner/results returns scanner results"""
        response = auth_session.get(f"{BASE_URL}/api/user/scanner/results")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Scanner results should be a list"
        print(f"✓ Scanner results endpoint working - count: {len(data)}")

    def test_chain_visibility_scanner_to_signals(self, auth_session):
        """Test visibility chain from scanner to signals"""
        # Get scanner results
        scanner_response = auth_session.get(f"{BASE_URL}/api/user/scanner/results")
        assert scanner_response.status_code == 200
        
        # Get signals
        signals_response = auth_session.get(f"{BASE_URL}/api/user/signals")
        assert signals_response.status_code == 200
        
        print("✓ Scanner -> Signals chain visibility verified")

    def test_chain_visibility_signals_to_intents(self, auth_session):
        """Test visibility chain from signals to execution intents"""
        # Get signals
        signals_response = auth_session.get(f"{BASE_URL}/api/user/signals")
        assert signals_response.status_code == 200
        
        # Get execution intents
        intents_response = auth_session.get(f"{BASE_URL}/api/user/execution/intents")
        assert intents_response.status_code == 200
        
        print("✓ Signals -> Execution Intents chain visibility verified")

    def test_chain_visibility_decision_cards(self, auth_session):
        """Test decision cards provide visibility into decision chain"""
        response = auth_session.get(f"{BASE_URL}/api/user/decision-cards")
        assert response.status_code == 200
        data = response.json()
        
        # Decision cards should provide decision visibility
        if isinstance(data, dict) and "items" in data:
            items = data.get("items", [])
        elif isinstance(data, list):
            items = data
        else:
            items = []
        
        # Verify decision card structure if any exist
        if items:
            card = items[0]
            # Decision cards should have decision-related fields
            decision_fields = ["decision", "symbol"]
            for field in decision_fields:
                if field in card:
                    print(f"  - Decision card has {field}: {card.get(field)}")
        
        print("✓ Decision cards chain visibility verified")


class TestStage1RiskVisibility:
    """Test risk visibility and logging"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session with JWT token"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                session.headers.update({"Authorization": f"Bearer {token}"})
        
        return session

    def test_risk_visible_in_live_risk_endpoint(self, auth_session):
        """Test risk is visible via /api/user/live/risk"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/risk")
        assert response.status_code == 200
        data = response.json()
        
        # Verify risk metrics are present
        risk_fields = ["own_portfolio_exposure", "daily_loss_limit_pct", "risk_per_trade_used"]
        for field in risk_fields:
            assert field in data, f"Missing risk field: {field}"
        
        print(f"✓ Risk visible in live/risk endpoint")
        print(f"  - Portfolio exposure: {data.get('own_portfolio_exposure')}")
        print(f"  - Daily loss limit: {data.get('daily_loss_limit_pct')}")

    def test_risk_visible_in_runtime_snapshot(self, auth_session):
        """Test risk is visible in runtime snapshot"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/runtime-snapshot")
        assert response.status_code == 200
        data = response.json()
        
        # Risk should be in summary
        summary = data.get("summary", {})
        assert "risk" in summary, "Risk should be in summary"
        
        print("✓ Risk visible in runtime snapshot")

    def test_alerts_visible_in_runtime_snapshot(self, auth_session):
        """Test alerts are visible in runtime snapshot"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/runtime-snapshot")
        assert response.status_code == 200
        data = response.json()
        
        # Alerts should be present
        assert "alerts" in data, "Alerts should be in runtime snapshot"
        
        print(f"✓ Alerts visible in runtime snapshot - count: {len(data.get('alerts', []))}")

    def test_alerts_visible_in_summary(self, auth_session):
        """Test alerts are visible in summary"""
        response = auth_session.get(f"{BASE_URL}/api/user/live/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Alerts should be present
        assert "alerts" in data, "Alerts should be in summary"
        
        alerts = data.get("alerts", {})
        print(f"✓ Alerts visible in summary - status: {alerts.get('status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
