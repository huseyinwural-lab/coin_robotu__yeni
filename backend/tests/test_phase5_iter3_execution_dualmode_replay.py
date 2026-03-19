"""
Phase 5 Iterasyon 3 (Execution+DualMode+Replay) backend testleri
Features tested:
- A1/A2/A3/A4 infrastructure readiness: test-order failure contract includes normalized failure_code + venue context
- GET /api/exchange/readiness-checklist supports venue params and returns venue context fields
- Spot/Futures dual-mode backend: /api/user-risk/preview with market_type=spot vs futures
- B3 test-order routing: frontend sends venue + leverage context, backend accepts and routes
- C1/C2/C3 replay backend: POST /api/backtest/replay/run with 1m/5m/15m/1h timeframes, SIM_NEW/SIM_FILLED/SIM_CANCELED
- No regressions on admin exchanges and user exchange settings page load
"""

import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trading-hardening.preview.emergentagent.com")


@pytest.fixture(scope="module")
def admin_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        timeout=20,
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def user_context() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": "TEST_phase4iter2_pipeline@example.com", "password": "TestPassword123!"},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    return {"token": payload["access_token"], "user_id": payload["user"]["id"]}


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _ensure_assignment(admin_token: str, user_id: str):
    response = requests.put(
        f"{BASE_URL}/api/venues/admin/user-assignments",
        headers=_headers(admin_token),
        json={
            "user_id": user_id,
            "exchange_code": "binance",
            "spot_allowed": True,
            "futures_allowed": True,
            "testnet_allowed": True,
            "live_allowed": False,
        },
        timeout=20,
    )
    assert response.status_code == 200


# ==================== A: Infrastructure Readiness Tests ====================

class TestInfrastructureReadiness:
    """A1/A2/A3/A4: Test-order failure contract with venue context"""

    def test_readiness_checklist_returns_venue_context(self, user_context):
        """GET /api/exchange/readiness-checklist supports venue params and returns venue context fields"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=_headers(user_context["token"]),
            params={"exchange": "binance", "market_type": "futures", "environment": "testnet"},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        # Venue context fields
        assert data["exchange"] == "binance"
        assert data["market_type"] == "futures"
        assert data["environment"] == "testnet"
        # Standard readiness fields
        assert "readiness_status" in data
        assert "has_api_key" in data
        assert "has_api_secret" in data
        assert "capability_match" in data

    def test_readiness_checklist_spot_venue(self, user_context):
        """Readiness checklist with spot market_type"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=_headers(user_context["token"]),
            params={"exchange": "binance", "market_type": "spot", "environment": "testnet"},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exchange"] == "binance"
        assert data["market_type"] == "spot"
        assert data["environment"] == "testnet"

    def test_test_order_error_contract_includes_venue_context(self, user_context):
        """Test-order failure response MUST include normalized failure_code + venue context"""
        response = requests.post(
            f"{BASE_URL}/api/exchange/test-order",
            headers=_headers(user_context["token"]),
            params={"exchange": "binance", "market_type": "futures", "environment": "testnet", "leverage": 3},
            timeout=30,
        )
        assert response.status_code in (200, 400)
        if response.status_code == 400:
            detail = response.json()["detail"]
            # Venue context fields MUST be present
            assert detail["exchange"] == "binance"
            assert detail["market_type"] == "futures"
            assert detail["environment"] == "testnet"
            # Normalized failure_code MUST be present and valid
            assert detail["failure_code"] in {
                "invalid_key",
                "permission_denied",
                "ip_restricted",
                "insufficient_balance",
                "exchange_rejected",
                "testnet_unreachable",
                "stale_validation",
                "unknown_exchange_error",
            }

    def test_lifecycle_evidence_endpoint_still_works(self, user_context):
        """GET /api/exchange/lifecycle-evidence/latest still works (may be 404 if no execution yet)"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/lifecycle-evidence/latest",
            headers=_headers(user_context["token"]),
            timeout=20,
        )
        # 404 is acceptable if no execution exists, 200 if exists
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.json()
            assert "order_id" in data
            assert "timeline" in data


# ==================== B: Spot/Futures Dual-Mode Backend ====================

class TestDualModeBackend:
    """B: Spot/Futures dual-mode backend behavior"""

    def test_user_risk_preview_spot_returns_null_futures_fields(self, user_context):
        """Spot preview MUST NOT return leverage/margin/liquidation fields"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers=_headers(user_context["token"]),
            params={"market_type": "spot"},
            timeout=20,
        )
        assert response.status_code == 200
        spot = response.json()
        assert spot["market_type"] == "spot"
        # Futures-only fields MUST be null for spot
        assert spot["leverage"] is None
        assert spot["margin_mode"] is None
        assert spot["position_side"] is None
        assert spot["estimated_liquidation_buffer_pct"] is None
        assert spot["margin_usage_pct"] is None
        # Core risk fields MUST be present
        assert spot["current_capital"] is not None
        assert spot["position_size"] is not None
        assert spot["risk_amount"] is not None

    def test_user_risk_preview_futures_returns_all_fields(self, user_context):
        """Futures preview MUST return leverage/margin/liquidation fields"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers=_headers(user_context["token"]),
            params={"market_type": "futures", "leverage": 5, "margin_mode": "isolated", "position_side": "LONG"},
            timeout=20,
        )
        assert response.status_code == 200
        futures = response.json()
        assert futures["market_type"] == "futures"
        # Futures-only fields MUST be present with correct values
        assert futures["leverage"] == 5
        assert futures["margin_mode"] == "isolated"
        assert futures["position_side"] == "LONG"
        assert futures["estimated_liquidation_buffer_pct"] is not None
        assert futures["margin_usage_pct"] is not None
        # Core risk fields MUST be present
        assert futures["current_capital"] is not None
        assert futures["position_size"] is not None

    def test_user_risk_preview_futures_default_values(self, user_context):
        """Futures preview with defaults (leverage=1, margin_mode=cross, position_side=BOTH)"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers=_headers(user_context["token"]),
            params={"market_type": "futures"},
            timeout=20,
        )
        assert response.status_code == 200
        futures = response.json()
        assert futures["market_type"] == "futures"
        assert futures["leverage"] == 1  # Default leverage
        assert futures["margin_mode"] == "cross"  # Default margin mode
        assert futures["position_side"] == "BOTH"  # Default position side

    def test_test_order_accepts_venue_and_leverage_context(self, user_context):
        """B3: Frontend sends venue + leverage context, backend accepts and routes"""
        response = requests.post(
            f"{BASE_URL}/api/exchange/test-order",
            headers=_headers(user_context["token"]),
            params={
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "leverage": 5,
                "margin_mode": "isolated",
                "position_side": "LONG",
            },
            timeout=30,
        )
        # Either succeeds (200) or fails with proper error contract (400)
        assert response.status_code in (200, 400)
        if response.status_code == 200:
            data = response.json()
            assert data["exchange"] == "binance"
            assert data["market_type"] == "futures"
            assert data["environment"] == "testnet"


# ==================== C: Replay Backend Tests ====================

class TestReplayBackend:
    """C1/C2/C3: Replay backend with Binance futures klines"""

    def test_replay_run_15m_timeframe(self, admin_token, user_context):
        """POST /api/backtest/replay/run with 15m timeframe"""
        _ensure_assignment(admin_token, user_context["user_id"])

        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_context["token"]),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "strategy_type": "trend_following",
                "limit": 180,
            },
            timeout=60,
        )
        assert run_response.status_code == 201
        run = run_response.json()
        assert run["status"] == "completed"
        assert run["candles_processed"] >= 120
        assert run["exchange"] == "binance"
        assert run["market_type"] == "futures"
        assert run["environment"] == "testnet"
        assert run["timeframe"] == "15m"

    def test_replay_run_1m_timeframe(self, admin_token, user_context):
        """POST /api/backtest/replay/run with 1m timeframe"""
        _ensure_assignment(admin_token, user_context["user_id"])

        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_context["token"]),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "strategy_type": "trend_following",
                "limit": 180,
            },
            timeout=60,
        )
        assert run_response.status_code == 201
        run = run_response.json()
        assert run["status"] == "completed"
        assert run["timeframe"] == "1m"

    def test_replay_run_5m_timeframe(self, admin_token, user_context):
        """POST /api/backtest/replay/run with 5m timeframe"""
        _ensure_assignment(admin_token, user_context["user_id"])

        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_context["token"]),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "strategy_type": "trend_following",
                "limit": 180,
            },
            timeout=60,
        )
        assert run_response.status_code == 201
        run = run_response.json()
        assert run["status"] == "completed"
        assert run["timeframe"] == "5m"

    def test_replay_run_1h_timeframe(self, admin_token, user_context):
        """POST /api/backtest/replay/run with 1h timeframe"""
        _ensure_assignment(admin_token, user_context["user_id"])

        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_context["token"]),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "strategy_type": "trend_following",
                "limit": 180,
            },
            timeout=60,
        )
        assert run_response.status_code == 201
        run = run_response.json()
        assert run["status"] == "completed"
        assert run["timeframe"] == "1h"

    def test_replay_run_unsupported_timeframe_rejected(self, admin_token, user_context):
        """Unsupported timeframe should be rejected"""
        _ensure_assignment(admin_token, user_context["user_id"])

        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_context["token"]),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "4h",  # Not in supported: 1m, 5m, 15m, 1h
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "strategy_type": "trend_following",
                "limit": 180,
            },
            timeout=60,
        )
        assert run_response.status_code == 400
        assert "unsupported_timeframe" in run_response.json().get("detail", "")

    def test_replay_run_detail_returns_lifecycle(self, admin_token, user_context):
        """GET /api/backtest/replay/run/{run_id} returns simulated lifecycle SIM_NEW/SIM_FILLED/SIM_CANCELED"""
        _ensure_assignment(admin_token, user_context["user_id"])

        # Create a run first
        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_context["token"]),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "strategy_type": "trend_following",
                "limit": 180,
            },
            timeout=60,
        )
        assert run_response.status_code == 201
        run = run_response.json()

        # Get detail
        detail_response = requests.get(
            f"{BASE_URL}/api/backtest/replay/run/{run['run_id']}",
            headers=_headers(user_context["token"]),
            timeout=30,
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert "metrics" in detail
        assert isinstance(detail["executions"], list)
        # Check lifecycle states
        if detail["executions"]:
            for execution in detail["executions"]:
                lifecycle = execution["lifecycle"]
                assert lifecycle[0] == "SIM_NEW"
                assert lifecycle[1] in ("SIM_FILLED", "SIM_CANCELED")
                assert execution["status"] in ("SIM_FILLED", "SIM_CANCELED")

    def test_replay_run_returns_metrics(self, admin_token, user_context):
        """Replay run returns metrics persistence (gross_pnl, win_rate_proxy_pct, pipeline)"""
        _ensure_assignment(admin_token, user_context["user_id"])

        run_response = requests.post(
            f"{BASE_URL}/api/backtest/replay/run",
            headers=_headers(user_context["token"]),
            json={
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
                "strategy_type": "trend_following",
                "limit": 180,
            },
            timeout=60,
        )
        assert run_response.status_code == 201
        run = run_response.json()

        detail_response = requests.get(
            f"{BASE_URL}/api/backtest/replay/run/{run['run_id']}",
            headers=_headers(user_context["token"]),
            timeout=30,
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        # Check metrics structure
        assert "metrics" in detail
        metrics = detail["metrics"]
        assert "gross_pnl" in metrics
        assert "win_rate_proxy_pct" in metrics
        assert "pipeline" in metrics
        assert isinstance(metrics["pipeline"], list)


# ==================== No Regression Tests ====================

class TestNoRegression:
    """No regressions on admin exchanges and user exchange settings pages"""

    def test_admin_exchanges_endpoint(self, admin_token):
        """GET /api/venues/admin/exchanges should still work"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/exchanges",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least binance seeded
        exchange_codes = [item["exchange_code"] for item in data]
        assert "binance" in exchange_codes

    def test_admin_capabilities_endpoint(self, admin_token):
        """GET /api/venues/admin/capabilities should still work"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/capabilities",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_admin_allowed_markets_endpoint(self, admin_token):
        """GET /api/venues/admin/allowed-markets should still work"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/allowed-markets",
            headers=_headers(admin_token),
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_user_exchange_settings_endpoint(self, user_context):
        """GET /api/phase4/exchange-settings should still work"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers=_headers(user_context["token"]),
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "exchange" in data
        assert "mode" in data

    def test_user_risk_settings_endpoint(self, user_context):
        """GET /api/user-risk/settings should still work"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/settings",
            headers=_headers(user_context["token"]),
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "allocation_pct" in data
        assert "trade_risk_pct" in data

    def test_user_risk_overview_endpoint(self, user_context):
        """GET /api/user-risk/overview should still work"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/overview",
            headers=_headers(user_context["token"]),
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_capital" in data
        assert "available_balance" in data

    def test_user_venue_options_endpoint(self, user_context):
        """GET /api/venues/options should still work"""
        response = requests.get(
            f"{BASE_URL}/api/venues/options",
            headers=_headers(user_context["token"]),
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
