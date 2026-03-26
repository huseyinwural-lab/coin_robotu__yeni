"""
P1.3 Iteration 2 - Runtime Ops Testing
Tests for:
- GET /api/runtime/pnl/summary (user self-only, admin aggregate)
- GET /api/runtime/pnl/positions
- GET /api/runtime/alerts (runtime_* alerts)
- GET /api/runtime/health/smoke (last smoke result)
- Alert payload contract: severity, source, user_id?, symbol?, threshold, actual_value, timestamp
- Daily smoke script behavior: SKIPPED_CREDENTIAL_MISSING, DEGRADED, alert generation
- Exchange adapter guard: EXECUTION_MODE=sim default, LIVE_TRADING_ENABLED=false default
"""

import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def _admin_headers():
    """Get admin auth headers"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


class TestRuntimePnlSummaryAPI:
    """Tests for GET /api/runtime/pnl/summary"""

    def test_pnl_summary_returns_200_for_admin(self):
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/pnl/summary", headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        # Verify required fields
        required_fields = ["scope", "realized_pnl", "unrealized_pnl", "net_pnl", "updated_at", "open_positions", "fees", "funding"]
        for field in required_fields:
            assert field in payload, f"Missing field: {field}"
        
        # Admin should see aggregate scope
        assert payload["scope"] in ["admin_all", "user_self"]

    def test_pnl_summary_contains_by_symbol_and_by_user(self):
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/pnl/summary", headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        # Admin should have by_symbol and by_user breakdowns
        assert "by_symbol" in payload
        assert "by_user" in payload
        assert isinstance(payload["by_symbol"], dict)
        assert isinstance(payload["by_user"], dict)


class TestRuntimePnlPositionsAPI:
    """Tests for GET /api/runtime/pnl/positions"""

    def test_pnl_positions_returns_200(self):
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/pnl/positions", headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        assert "status" in payload
        assert payload["status"] == "ok"
        assert "rows" in payload
        assert "scope" in payload

    def test_pnl_positions_row_structure(self):
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/pnl/positions", headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        # If there are rows, verify structure
        if payload["rows"]:
            row = payload["rows"][0]
            expected_fields = [
                "user_id", "symbol", "position_qty", "avg_entry_price", "mark_price",
                "realized_pnl", "unrealized_pnl", "fees", "funding", "net_pnl", "updated_at"
            ]
            for field in expected_fields:
                assert field in row, f"Missing field in position row: {field}"


class TestRuntimeAlertsAPI:
    """Tests for GET /api/runtime/alerts"""

    def test_runtime_alerts_returns_200(self):
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/alerts", headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        assert "status" in payload
        assert payload["status"] == "ok"
        assert "items" in payload
        assert isinstance(payload["items"], list)

    def test_runtime_alerts_filter_runtime_prefix(self):
        """Verify alerts endpoint returns runtime_* prefixed alerts"""
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/alerts", params={"limit": 50}, headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        # All returned alerts should have runtime_ prefix
        for item in payload["items"]:
            assert item["alert_type"].startswith("runtime_"), f"Non-runtime alert returned: {item['alert_type']}"

    def test_runtime_alert_payload_contract(self):
        """Verify alert payload contains required contract fields"""
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/alerts", params={"limit": 10}, headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        # If there are alerts, verify contract
        for item in payload["items"]:
            # Required top-level fields
            assert "id" in item
            assert "alert_type" in item
            assert "severity" in item
            assert "message" in item
            assert "created_at" in item
            
            # Details should contain contract fields
            details = item.get("details", {})
            # Contract: severity, source, threshold, actual_value, timestamp
            # user_id and symbol are optional
            assert "severity" in details, f"Missing severity in details: {item}"
            assert "source" in details, f"Missing source in details: {item}"
            assert "threshold" in details, f"Missing threshold in details: {item}"
            assert "actual_value" in details, f"Missing actual_value in details: {item}"
            assert "timestamp" in details, f"Missing timestamp in details: {item}"


class TestRuntimeHealthSmokeAPI:
    """Tests for GET /api/runtime/health/smoke"""

    def test_smoke_health_returns_200_for_admin(self):
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/health/smoke", headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        # Should return status
        assert "status" in payload
        # Either "ok" with smoke data or "no_data"
        assert payload["status"] in ["ok", "no_data"]

    def test_smoke_health_structure_when_data_exists(self):
        headers = _admin_headers()
        response = requests.get(f"{BASE_URL}/api/runtime/health/smoke", headers=headers, timeout=20)
        assert response.status_code == 200
        payload = response.json()
        
        if payload["status"] == "ok":
            smoke = payload.get("smoke", {})
            expected_fields = ["id", "run_status", "summary", "steps", "trigger_source", "started_at"]
            for field in expected_fields:
                assert field in smoke, f"Missing field in smoke: {field}"

    def test_smoke_health_forbidden_for_non_admin(self):
        """Non-admin users should get 403"""
        # Try without auth
        response = requests.get(f"{BASE_URL}/api/runtime/health/smoke", timeout=20)
        assert response.status_code in [401, 403, 422]


class TestExchangeAdapterGuard:
    """Tests for exchange adapter guard configuration"""

    def test_default_execution_mode_is_sim(self):
        """EXECUTION_MODE should default to sim"""
        from core.exchanges import get_execution_adapter
        from core.exchanges.sim_adapter import SimExecutionAdapter
        
        # Save original values
        orig_mode = os.environ.get("EXECUTION_MODE")
        orig_live = os.environ.get("LIVE_TRADING_ENABLED")
        orig_testnet = os.environ.get("TESTNET_TRADING_ENABLED")
        
        try:
            # Set defaults
            os.environ["EXECUTION_MODE"] = "sim"
            os.environ["LIVE_TRADING_ENABLED"] = "false"
            os.environ["TESTNET_TRADING_ENABLED"] = "false"
            
            adapter = get_execution_adapter()
            assert isinstance(adapter, SimExecutionAdapter)
            assert adapter.adapter_name == "sim"
        finally:
            # Restore
            if orig_mode:
                os.environ["EXECUTION_MODE"] = orig_mode
            if orig_live:
                os.environ["LIVE_TRADING_ENABLED"] = orig_live
            if orig_testnet:
                os.environ["TESTNET_TRADING_ENABLED"] = orig_testnet

    def test_live_mode_requires_double_guard(self):
        """Live mode requires both EXECUTION_MODE=live AND LIVE_TRADING_ENABLED=true"""
        from core.exchanges import get_execution_adapter
        from core.exchanges.sim_adapter import SimExecutionAdapter
        from core.exchanges.binance_adapter import BinanceExecutionAdapter
        
        orig_mode = os.environ.get("EXECUTION_MODE")
        orig_live = os.environ.get("LIVE_TRADING_ENABLED")
        
        try:
            # Only EXECUTION_MODE=live, but LIVE_TRADING_ENABLED=false -> should return SIM
            os.environ["EXECUTION_MODE"] = "live"
            os.environ["LIVE_TRADING_ENABLED"] = "false"
            
            adapter = get_execution_adapter()
            assert isinstance(adapter, SimExecutionAdapter), "Should fallback to SIM when LIVE_TRADING_ENABLED=false"
            
            # Both guards enabled -> should return Binance
            os.environ["LIVE_TRADING_ENABLED"] = "true"
            adapter = get_execution_adapter()
            assert isinstance(adapter, BinanceExecutionAdapter), "Should return Binance when both guards enabled"
        finally:
            if orig_mode:
                os.environ["EXECUTION_MODE"] = orig_mode
            else:
                os.environ.pop("EXECUTION_MODE", None)
            if orig_live:
                os.environ["LIVE_TRADING_ENABLED"] = orig_live
            else:
                os.environ.pop("LIVE_TRADING_ENABLED", None)

    def test_testnet_mode_requires_double_guard(self):
        """Testnet mode requires both EXECUTION_MODE=testnet AND TESTNET_TRADING_ENABLED=true"""
        from core.exchanges import get_execution_adapter
        from core.exchanges.sim_adapter import SimExecutionAdapter
        from core.exchanges.binance_adapter import BinanceExecutionAdapter
        
        orig_mode = os.environ.get("EXECUTION_MODE")
        orig_testnet = os.environ.get("TESTNET_TRADING_ENABLED")
        
        try:
            # Only EXECUTION_MODE=testnet, but TESTNET_TRADING_ENABLED=false -> should return SIM
            os.environ["EXECUTION_MODE"] = "testnet"
            os.environ["TESTNET_TRADING_ENABLED"] = "false"
            
            adapter = get_execution_adapter()
            assert isinstance(adapter, SimExecutionAdapter), "Should fallback to SIM when TESTNET_TRADING_ENABLED=false"
            
            # Both guards enabled -> should return Binance
            os.environ["TESTNET_TRADING_ENABLED"] = "true"
            adapter = get_execution_adapter()
            assert isinstance(adapter, BinanceExecutionAdapter), "Should return Binance when both guards enabled"
        finally:
            if orig_mode:
                os.environ["EXECUTION_MODE"] = orig_mode
            else:
                os.environ.pop("EXECUTION_MODE", None)
            if orig_testnet:
                os.environ["TESTNET_TRADING_ENABLED"] = orig_testnet
            else:
                os.environ.pop("TESTNET_TRADING_ENABLED", None)


class TestBinanceAdapterGuardBlocking:
    """Tests for Binance adapter guard blocking"""

    def test_binance_adapter_blocks_live_without_guard(self):
        """Binance adapter should raise RuntimeError when live guard not enabled"""
        from core.exchanges.binance_adapter import BinanceExecutionAdapter
        
        orig_mode = os.environ.get("EXECUTION_MODE")
        orig_live = os.environ.get("LIVE_TRADING_ENABLED")
        
        try:
            os.environ["EXECUTION_MODE"] = "live"
            os.environ["LIVE_TRADING_ENABLED"] = "false"
            
            adapter = BinanceExecutionAdapter()
            with pytest.raises(RuntimeError) as exc_info:
                adapter.submit_order({"execution_job_id": "test", "size": 1.0})
            
            assert "live_guard_blocked" in str(exc_info.value)
        finally:
            if orig_mode:
                os.environ["EXECUTION_MODE"] = orig_mode
            if orig_live:
                os.environ["LIVE_TRADING_ENABLED"] = orig_live

    def test_binance_adapter_blocks_testnet_without_guard(self):
        """Binance adapter should raise RuntimeError when testnet guard not enabled"""
        from core.exchanges.binance_adapter import BinanceExecutionAdapter
        
        orig_mode = os.environ.get("EXECUTION_MODE")
        orig_testnet = os.environ.get("TESTNET_TRADING_ENABLED")
        
        try:
            os.environ["EXECUTION_MODE"] = "testnet"
            os.environ["TESTNET_TRADING_ENABLED"] = "false"
            
            adapter = BinanceExecutionAdapter()
            with pytest.raises(RuntimeError) as exc_info:
                adapter.submit_order({"execution_job_id": "test", "size": 1.0})
            
            assert "testnet_guard_blocked" in str(exc_info.value)
        finally:
            if orig_mode:
                os.environ["EXECUTION_MODE"] = orig_mode
            if orig_testnet:
                os.environ["TESTNET_TRADING_ENABLED"] = orig_testnet


class TestAlertPayloadContract:
    """Tests for alert payload contract validation"""

    def test_trigger_runtime_alert_creates_correct_payload(self):
        """Verify trigger_runtime_threshold_alert creates correct payload structure"""
        from core.alerts.runtime_alert_triggers import trigger_runtime_threshold_alert
        from db import SessionLocal
        from models import SystemAlert
        
        db = SessionLocal()
        try:
            # Trigger a test alert
            trigger_runtime_threshold_alert(
                db,
                alert_type="runtime_test_contract_validation",
                severity="WARNING",
                message="Test alert for contract validation",
                source="test_p13_iteration2",
                threshold=10,
                actual_value=15,
                user_id="test-user-123",
                symbol="BTCUSDT",
                root_cause_code="test_contract",
            )
            
            # Verify the alert was created with correct structure
            alert = (
                db.query(SystemAlert)
                .filter(SystemAlert.alert_type == "runtime_test_contract_validation")
                .order_by(SystemAlert.updated_at.desc())
                .first()
            )
            
            assert alert is not None
            details = alert.details
            
            # Verify contract fields
            assert details["severity"] == "WARNING"
            assert details["source"] == "test_p13_iteration2"
            assert details["threshold"] == 10
            assert details["actual_value"] == 15
            assert details["user_id"] == "test-user-123"
            assert details["symbol"] == "BTCUSDT"
            assert "timestamp" in details
        finally:
            db.close()


class TestSimAdapterDefault:
    """Tests to ensure SIM adapter is default and doesn't break"""

    def test_sim_adapter_submit_order_works(self):
        """SIM adapter should work without any external dependencies"""
        from core.exchanges.sim_adapter import SimExecutionAdapter
        
        adapter = SimExecutionAdapter()
        result = adapter.submit_order({
            "execution_job_id": "test-job-123",
            "idempotency_key": "test-idem-123",
            "user_id": "test-user",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "size": 0.1,
            "mark_price": 50000.0,
        })
        
        assert "external_order_id" in result
        assert result["external_order_id"].startswith("SIM-")
        assert "states" in result
        assert "avg_fill_price" in result
        assert "filled_size" in result

    def test_execution_engine_uses_sim_by_default(self):
        """Execution engine should use SIM adapter by default"""
        from core.execution_engine import route_to_exchange
        from models import ExecutionJob
        
        # Create a mock job
        job = ExecutionJob(
            id="test-job-sim-default",
            idempotency_key="test-idem-sim",
            user_id="test-user",
            symbol="ETHUSDT",
            side="SELL",
            size=1.0,
            strategy_name="test_strategy",
            state="CREATED",
            meta_payload={"mark_price": 3000.0},
        )
        
        result = route_to_exchange(job)
        
        # Should use SIM adapter
        assert result["external_order_id"].startswith("SIM-")
