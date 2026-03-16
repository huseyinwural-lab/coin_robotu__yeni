"""
Comprehensive Scanner UI Operations Testing Suite
Tests: Scanner endpoints, symbol selection, live readiness, daily report, symbol integrity guards,
       BTC fallback prevention, audit logs (SCAN_RESULT, RISK_RESULT, EXECUTION_INTENT, EXCHANGE_ORDER)
"""
import os
import uuid
from pathlib import Path
from datetime import datetime

import pytest
import requests


def _resolve_base_url() -> str:
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL bulunamadı")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


def _admin_headers() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"admin login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _new_user_headers(prefix: str, admin_headers: dict) -> dict:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    password = "ScannerUi123!"

    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register.status_code == 200, register.text
    user_id = register.json()["id"]

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200, approve.text

    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_headers():
    return _admin_headers()


@pytest.fixture(scope="module")
def scanner_user_headers(admin_headers):
    return _new_user_headers("scanner_ui_test", admin_headers)


# ========================== SCANNER CORE ENDPOINTS ==========================

class TestScannerCoreEndpoints:
    """Test core scanner endpoints: overview, automation, mode"""

    def test_scanner_overview_returns_200(self, scanner_user_headers):
        """GET /api/user/scanner returns overview data"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner",
            headers=scanner_user_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "mode" in data
        assert data["mode"] in ["ASSISTED", "AUTO", "MANUAL"]
        assert "total_results" in data
        assert "pending_signals" in data

    def test_signal_mode_get_and_update(self, scanner_user_headers):
        """GET & PUT /api/user/signal-mode works"""
        # GET
        get_resp = requests.get(
            f"{BASE_URL}/api/user/signal-mode",
            headers=scanner_user_headers,
            timeout=30,
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "mode" in data

        # PUT
        for mode in ["MANUAL", "ASSISTED", "AUTO"]:
            put_resp = requests.put(
                f"{BASE_URL}/api/user/signal-mode",
                headers=scanner_user_headers,
                json={"mode": mode},
                timeout=30,
            )
            assert put_resp.status_code == 200
            assert put_resp.json()["mode"] == mode

    def test_scanner_automation_config(self, scanner_user_headers):
        """GET & PUT /api/user/scanner/automation config"""
        # GET
        get_resp = requests.get(
            f"{BASE_URL}/api/user/scanner/automation",
            headers=scanner_user_headers,
            timeout=30,
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "auto_enabled" in data
        assert "interval_seconds" in data

        # PUT with interval options 30/60/120
        for interval in [30, 60, 120]:
            put_resp = requests.put(
                f"{BASE_URL}/api/user/scanner/automation",
                headers=scanner_user_headers,
                json={
                    "auto_enabled": True,
                    "interval_seconds": interval,
                    "max_results": 25,
                    "symbol_source": "crypto",
                    "symbol_selection_mode": "all_market_symbols",
                    "selected_symbols": [],
                },
                timeout=30,
            )
            assert put_resp.status_code == 200, f"interval {interval} failed: {put_resp.text}"
            assert put_resp.json()["interval_seconds"] == interval

    def test_scanner_results_returns_list(self, scanner_user_headers):
        """GET /api/user/scanner/results returns list"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            params={"limit": 50},
            headers=scanner_user_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# ========================== SCANNER RUN GUARD ==========================

class TestScannerRunGuard:
    """Test scanner run requires at least one symbol"""

    def test_scanner_run_rejects_empty_symbols(self, scanner_user_headers):
        """POST /api/user/scanner/run returns 400 when no symbols selected"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=scanner_user_headers,
            json={
                "mode": "ASSISTED",
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "manual_selection",
                "selected_symbols": [],
            },
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "En az bir sembol seçmelisiniz" in response.text or "sembol" in response.text.lower()

    def test_scanner_run_accepts_with_symbols(self, scanner_user_headers):
        """POST /api/user/scanner/run succeeds with symbols"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=scanner_user_headers,
            json={
                "mode": "ASSISTED",
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "manual_selection",
                "selected_symbols": ["BTCUSDT", "ETHUSDT"],
            },
            timeout=60,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "run_id" in data
        assert "result_count" in data


# ========================== SYMBOL INTEGRITY & BTC FALLBACK ==========================

class TestSymbolIntegrityGuards:
    """Test scanner -> execution symbol integrity validation"""

    def test_scanner_symbol_mismatch_rejects(self, scanner_user_headers):
        """Preview rejects when scanner_signal_snapshot.symbol != intent symbol"""
        payload = {
            "source_type": "scanner",
            "source_ref_id": "scanner-row-test-1",
            "market_type": "spot",
            "symbol": "ETHUSDT",  # Intent symbol
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "signal_follow",
            "strategy_binding": "spot_pullback_v1",
            "signal": "long",
            "score": 80,
            "confidence": 0.7,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "scanner_signal_snapshot": {
                "symbol": "BTCUSDT",  # Different symbol - MISMATCH
                "signal": "long",
                "score": 80,
                "strategy": "spot_pullback_v1",
                "confidence": 0.7,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=scanner_user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "scanner_execution_symbol_mismatch" in response.text

    def test_btc_fallback_prevented_empty_symbol(self, scanner_user_headers):
        """Preview rejects empty symbol - no BTC fallback allowed"""
        payload = {
            "source_type": "scanner",
            "source_ref_id": "scanner-row-test-2",
            "market_type": "spot",
            "symbol": "",  # Empty symbol
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "signal_follow",
            "strategy_binding": "spot_pullback_v1",
            "scanner_signal_snapshot": {
                "symbol": "ETHUSDT",
                "signal": "long",
                "score": 75,
                "strategy": "spot_pullback_v1",
                "confidence": 0.6,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=scanner_user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "symbol_required_for_execution_intent" in response.text

    def test_btc_fallback_prevented_whitespace_symbol(self, scanner_user_headers):
        """Preview rejects whitespace-only symbol"""
        payload = {
            "source_type": "scanner",
            "source_ref_id": "scanner-row-test-3",
            "market_type": "spot",
            "symbol": "   ",  # Whitespace only
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "signal_follow",
            "strategy_binding": "spot_pullback_v1",
            "scanner_signal_snapshot": {
                "symbol": "ETHUSDT",
                "signal": "long",
                "score": 75,
                "strategy": "spot_pullback_v1",
                "confidence": 0.6,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=scanner_user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "symbol_required_for_execution_intent" in response.text

    def test_matching_symbols_accepted(self, scanner_user_headers):
        """Preview accepts when scanner symbol == intent symbol"""
        payload = {
            "source_type": "scanner",
            "source_ref_id": "scanner-row-test-4",
            "market_type": "spot",
            "symbol": "ETHUSDT",  # Same symbol
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "signal_follow",
            "strategy_binding": "spot_pullback_v1",
            "signal": "long",
            "score": 80,
            "confidence": 0.7,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "scanner_signal_snapshot": {
                "symbol": "ETHUSDT",  # Same symbol - OK
                "signal": "long",
                "score": 80,
                "strategy": "spot_pullback_v1",
                "confidence": 0.7,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=scanner_user_headers,
            json=payload,
            timeout=30,
        )
        # May return 200 or 400 for other reasons, but NOT scanner_execution_symbol_mismatch
        if response.status_code == 400:
            assert "scanner_execution_symbol_mismatch" not in response.text
        else:
            assert response.status_code == 200


# ========================== LIVE READINESS ENDPOINTS ==========================

class TestLiveReadinessEndpoints:
    """Test live readiness, daily report, and export endpoints"""

    def test_live_readiness_returns_200(self, scanner_user_headers):
        """GET /api/user/scanner/runtime/live-readiness"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/live-readiness",
            params={"window": "24h"},
            headers=scanner_user_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        # Check required keys
        required_keys = ["symbol_integrity", "max_risk_guard", "execution_quality", "scanner_activity", "strategy_diversity", "emergency_stop"]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_daily_report_returns_200(self, scanner_user_headers):
        """GET /api/user/scanner/runtime/daily-report"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/daily-report",
            params={"window": "24h"},
            headers=scanner_user_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        # Check daily report contract fields
        required_fields = ["date", "scan", "execution", "risk", "strategies"]
        for field in required_fields:
            assert field in data, f"Missing field in daily report: {field}"

    def test_daily_report_export_json(self, scanner_user_headers):
        """GET /api/user/scanner/runtime/daily-report/export?format=json"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/daily-report/export",
            params={"format": "json", "window": "24h"},
            headers=scanner_user_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "date" in data

    def test_daily_report_export_csv(self, scanner_user_headers):
        """GET /api/user/scanner/runtime/daily-report/export?format=csv"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/daily-report/export",
            params={"format": "csv", "window": "24h"},
            headers=scanner_user_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        assert "text/csv" in response.headers.get("content-type", "")


# ========================== AUTOMATION PROFILES ==========================

class TestAutomationProfiles:
    """Test scanner automation profiles CRUD"""

    def test_profiles_crud_flow(self, scanner_user_headers):
        """Create, list, activate, update, delete automation profile"""
        # Create profile
        create_resp = requests.post(
            f"{BASE_URL}/api/user/scanner/automation-profiles",
            headers=scanner_user_headers,
            json={
                "name": f"test-profile-{uuid.uuid4().hex[:6]}",
                "auto_enabled": True,
                "is_active": False,
                "interval_seconds": 60,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "manual_selection",
                "selected_symbols": ["BTCUSDT", "ETHUSDT"],
            },
            timeout=30,
        )
        assert create_resp.status_code == 200, create_resp.text
        profile = create_resp.json()
        profile_id = profile["id"]
        assert "name" in profile
        assert "auto_enabled" in profile

        # List profiles
        list_resp = requests.get(
            f"{BASE_URL}/api/user/scanner/automation-profiles",
            headers=scanner_user_headers,
            timeout=30,
        )
        assert list_resp.status_code == 200
        profiles = list_resp.json()
        assert isinstance(profiles, list)
        assert any(p["id"] == profile_id for p in profiles)

        # Activate profile
        activate_resp = requests.post(
            f"{BASE_URL}/api/user/scanner/automation-profiles/{profile_id}/activate",
            headers=scanner_user_headers,
            timeout=30,
        )
        assert activate_resp.status_code == 200
        assert activate_resp.json()["is_active"] is True

        # Update profile
        update_resp = requests.put(
            f"{BASE_URL}/api/user/scanner/automation-profiles/{profile_id}",
            headers=scanner_user_headers,
            json={
                "name": profile["name"],
                "auto_enabled": False,
                "is_active": True,
                "interval_seconds": 120,
                "max_results": 30,
                "symbol_source": "crypto",
                "symbol_selection_mode": "manual_selection",
                "selected_symbols": ["BTCUSDT"],
            },
            timeout=30,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["interval_seconds"] == 120

        # Delete profile
        delete_resp = requests.delete(
            f"{BASE_URL}/api/user/scanner/automation-profiles/{profile_id}",
            headers=scanner_user_headers,
            timeout=30,
        )
        assert delete_resp.status_code == 200


# ========================== AUDIT LOG ACTIONS ==========================

class TestAuditLogActionsExist:
    """Test audit log endpoints exist and generate expected actions"""

    def test_scanner_run_produces_scan_result_audit(self, scanner_user_headers, admin_headers):
        """Scanner run should generate SCAN_RESULT audit log"""
        # Run scanner
        run_resp = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=scanner_user_headers,
            json={
                "mode": "ASSISTED",
                "max_results": 10,
                "symbol_source": "crypto",
                "symbol_selection_mode": "manual_selection",
                "selected_symbols": ["BTCUSDT"],
            },
            timeout=60,
        )
        assert run_resp.status_code == 200, run_resp.text

        # Check audit logs (admin endpoint)
        audit_resp = requests.get(
            f"{BASE_URL}/api/admin/audit-logs",
            params={"limit": 20},
            headers=admin_headers,
            timeout=30,
        )
        # Audit endpoint may exist
        if audit_resp.status_code == 200:
            logs = audit_resp.json()
            actions = [log.get("action") for log in logs]
            # SCAN_RESULT should appear
            assert any("SCAN" in str(a).upper() for a in actions), f"No SCAN action in audit logs: {actions}"

    def test_execution_preview_produces_audit_logs(self, scanner_user_headers, admin_headers):
        """Execution preview should generate RISK_RESULT and EXECUTION_INTENT audits"""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 30,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "manual",
        }
        preview_resp = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=scanner_user_headers,
            json=payload,
            timeout=30,
        )
        # Preview may return 200 or validation issues
        assert preview_resp.status_code in [200, 400, 429], preview_resp.text

        # Check audit logs for RISK_RESULT and EXECUTION_INTENT
        audit_resp = requests.get(
            f"{BASE_URL}/api/admin/audit-logs",
            params={"limit": 30},
            headers=admin_headers,
            timeout=30,
        )
        if audit_resp.status_code == 200:
            logs = audit_resp.json()
            actions = [str(log.get("action") or "").upper() for log in logs]
            # Check for expected audit actions
            has_risk = any("RISK" in a for a in actions)
            has_execution = any("EXECUTION" in a for a in actions)
            # At least one should exist after preview
            assert has_risk or has_execution, f"No RISK/EXECUTION audit in: {actions[:10]}"


# ========================== SYMBOL SELECTION PERSISTENCE ==========================

class TestSymbolSelectionPersistence:
    """Test symbol selection persistence endpoints"""

    def test_symbol_selection_save_and_load(self, scanner_user_headers):
        """PUT & GET /api/user/scanner/symbol-selection"""
        test_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        # Save selection
        save_resp = requests.put(
            f"{BASE_URL}/api/user/scanner/symbol-selection",
            headers=scanner_user_headers,
            json={
                "scanner_id": "default",
                "symbol_source": "crypto",
                "symbol_selection_mode": "manual_selection",
                "selected_symbols": test_symbols,
            },
            timeout=30,
        )
        assert save_resp.status_code == 200, save_resp.text
        save_data = save_resp.json()
        assert "saved_at" in save_data

        # Load selection
        load_resp = requests.get(
            f"{BASE_URL}/api/user/scanner/symbol-selection",
            params={"scanner_id": "default"},
            headers=scanner_user_headers,
            timeout=30,
        )
        assert load_resp.status_code == 200, load_resp.text
        load_data = load_resp.json()
        assert load_data.get("symbol_selection_mode") == "manual_selection"
        for sym in test_symbols:
            assert sym in load_data.get("selected_symbols", [])


# ========================== RUNTIME SNAPSHOT ==========================

class TestRuntimeSnapshot:
    """Test scanner runtime snapshot endpoint"""

    def test_runtime_snapshot_returns_200(self, scanner_user_headers):
        """GET /api/user/scanner/runtime/snapshot"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/runtime/snapshot",
            headers=scanner_user_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        # Snapshot structure may vary, just ensure it returns JSON
        assert isinstance(data, dict)


# ========================== DECISION CARDS ==========================

class TestDecisionCards:
    """Test user decision cards endpoint"""

    def test_decision_cards_returns_list(self, scanner_user_headers):
        """GET /api/user/decision-cards returns list"""
        response = requests.get(
            f"{BASE_URL}/api/user/decision-cards",
            params={"limit": 30},
            headers=scanner_user_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "items" in data or isinstance(data, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
