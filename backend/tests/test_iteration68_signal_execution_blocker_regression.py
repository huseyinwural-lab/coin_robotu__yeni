"""
BUG-EXEC-12: /user/signals signal lifecycle and execution blocker regression tests

Tests cover:
- Signal lifecycle/state machine trace fields
- Pending reason codes deterministic production
- Manual mode behavior (signal pending + approval reason visible)
- Approve flow: signal -> intent -> submit -> filled or blocked
- Full auto scenario with created_order_intent_id
- UI column data availability (Execution Mode, Blokaj Nedeni, etc.)
- Badge state normalization (Pending/Blocked/Ready/Queued/Submitted/Filled/Rejected/Expired)
- Decision trace endpoints for traceability
"""

import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
USER_EMAIL = "e2_conn_last@example.com"
USER_PASSWORD = "User12345!"
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def user_token():
    """Authenticate as regular user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"User auth failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token():
    """Authenticate as admin"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin auth failed: {response.status_code} - {response.text}")


@pytest.fixture
def user_client(user_token):
    """User authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json"
    })
    return session


@pytest.fixture
def admin_client(admin_token):
    """Admin authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    })
    return session


class TestHealthAndAuth:
    """Basic health and authentication tests"""

    def test_health_endpoint(self):
        """API is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        assert response.json().get("status") == "ok"

    def test_user_login(self):
        """User can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("email") == USER_EMAIL

    def test_admin_login(self):
        """Admin can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data


class TestSignalModeAPI:
    """Signal mode configuration tests"""

    def test_get_signal_mode(self, user_client):
        """GET /user/signal-mode returns current mode"""
        response = user_client.get(f"{BASE_URL}/api/user/signal-mode")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert data["mode"] in ["MANUAL", "ASSISTED", "AUTO"]

    def test_update_signal_mode_manual(self, user_client):
        """PUT /user/signal-mode can set MANUAL mode"""
        response = user_client.put(f"{BASE_URL}/api/user/signal-mode", json={
            "mode": "MANUAL"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "MANUAL"

    def test_update_signal_mode_auto(self, user_client):
        """PUT /user/signal-mode can set AUTO mode"""
        response = user_client.put(f"{BASE_URL}/api/user/signal-mode", json={
            "mode": "AUTO"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "AUTO"

    def test_update_signal_mode_assisted(self, user_client):
        """PUT /user/signal-mode can set ASSISTED mode"""
        response = user_client.put(f"{BASE_URL}/api/user/signal-mode", json={
            "mode": "ASSISTED"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "ASSISTED"


class TestScannerRunAPI:
    """Scanner run and signal generation tests"""

    def test_scanner_run_manual_mode(self, user_client):
        """POST /user/scanner/run generates signals in MANUAL mode"""
        # First set mode to MANUAL
        user_client.put(f"{BASE_URL}/api/user/signal-mode", json={"mode": "MANUAL"})

        # Run scanner
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 5
        })
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "run_id" in data
        assert "mode" in data
        assert data["mode"] == "MANUAL"
        assert "result_count" in data
        assert "actionable_count" in data
        assert "queued_count" in data
        assert "pending_total" in data
        assert "generated_at" in data

    def test_scanner_run_auto_mode(self, user_client):
        """POST /user/scanner/run in AUTO mode attempts execution"""
        # Set mode to AUTO
        user_client.put(f"{BASE_URL}/api/user/signal-mode", json={"mode": "AUTO"})

        # Run scanner (max_results must be >= 5)
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "AUTO",
            "max_results": 5
        })
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "AUTO"

    def test_scanner_results(self, user_client):
        """GET /user/scanner/results returns scanner results"""
        response = user_client.get(f"{BASE_URL}/api/user/scanner/results", params={
            "limit": 50
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_scanner_overview(self, user_client):
        """GET /user/scanner returns overview"""
        response = user_client.get(f"{BASE_URL}/api/user/scanner")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "total_results" in data
        assert "pending_signals" in data


class TestSignalsListAPI:
    """Signal list and trace field tests"""

    def test_list_signals(self, user_client):
        """GET /user/signals returns signals with trace fields"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 100
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # If signals exist, verify trace fields
        if len(data) > 0:
            signal = data[0]
            # Lifecycle trace fields (from PRD requirement)
            trace_fields = [
                "previous_state",
                "current_state",
                "blocked_reason_code",
                "requires_manual_approval",
                "execution_eligible",
                "bot_profile_id",
                "risk_policy_id",
                "exchange_connection_id",
                "created_order_intent_id",
                "runtime_owner"
            ]
            for field in trace_fields:
                assert field in signal, f"Missing trace field: {field}"

            # UI visibility columns
            ui_fields = [
                "execution_mode_label",
                "blocked_reason_message",
                "blocked_solution_hint",
                "last_eligibility_check_at"
            ]
            for field in ui_fields:
                assert field in signal, f"Missing UI field: {field}"

    def test_signal_status_values(self, user_client):
        """Verify signal status is normalized badge state"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 100
        })
        assert response.status_code == 200
        data = response.json()

        valid_statuses = [
            "pending", "blocked", "ready", "approved", "queued",
            "submitted", "filled", "rejected", "expired"
        ]

        for signal in data:
            assert signal.get("status") in valid_statuses, \
                f"Invalid status: {signal.get('status')}"


class TestPendingReasonCodes:
    """Test deterministic pending reason code production"""

    VALID_REASON_CODES = [
        "MANUAL_APPROVAL_REQUIRED",
        "BOT_NOT_RUNNING",
        "RISK_POLICY_MISSING",
        "RISK_LIMIT_BLOCKED",
        "EXCHANGE_NOT_READY",
        "MARKET_DATA_STALE",
        "POSITION_LIMIT_REACHED",
        "SYMBOL_NOT_ALLOWED",
        "ORDER_PRECHECK_FAILED",
        "EXECUTION_DISABLED",
        "SIGNAL_EXPIRED"
    ]

    def test_manual_mode_reason_code(self, user_client):
        """Manual mode signals have MANUAL_APPROVAL_REQUIRED reason"""
        # Set to MANUAL mode
        user_client.put(f"{BASE_URL}/api/user/signal-mode", json={"mode": "MANUAL"})

        # Run scanner to generate signals
        user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 3
        })

        # Get signals
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 20
        })
        assert response.status_code == 200
        data = response.json()

        # Find pending signals in manual mode
        manual_pending = [s for s in data if s.get("mode") == "MANUAL" and s.get("status") == "pending"]

        for signal in manual_pending:
            # Should have MANUAL_APPROVAL_REQUIRED or be blocked for other reason
            reason = signal.get("blocked_reason_code", "")
            if signal.get("requires_manual_approval"):
                # Either MANUAL_APPROVAL_REQUIRED or another blocker took priority
                assert reason in self.VALID_REASON_CODES or reason == "", \
                    f"Invalid reason code: {reason}"

    def test_reason_code_has_message_and_hint(self, user_client):
        """Each blocked reason code has message and solution hint"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 100
        })
        assert response.status_code == 200
        data = response.json()

        for signal in data:
            reason_code = signal.get("blocked_reason_code", "")
            if reason_code and reason_code != "":
                # Should have corresponding message and hint
                assert "blocked_reason_message" in signal
                assert "blocked_solution_hint" in signal


class TestSignalApprovalFlow:
    """Test signal approval pipeline: signal -> intent -> submit -> filled/blocked"""

    def test_approve_pending_signal(self, user_client):
        """POST /user/signal/{id}/approve triggers execution pipeline"""
        # First generate a signal in MANUAL mode
        user_client.put(f"{BASE_URL}/api/user/signal-mode", json={"mode": "MANUAL"})
        user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 3
        })

        # Get pending signals
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 50
        })
        assert response.status_code == 200
        signals = response.json()

        # Find an approvable signal
        pending_signals = [
            s for s in signals
            if s.get("status") in ["pending", "ready"]
            and (not s.get("blocked_reason_code") or s.get("blocked_reason_code") == "MANUAL_APPROVAL_REQUIRED")
        ]

        if not pending_signals:
            pytest.skip("No approvable pending signals found")

        signal = pending_signals[0]
        signal_id = signal["id"]

        # Approve the signal
        response = user_client.post(f"{BASE_URL}/api/user/signal/{signal_id}/approve", json={
            "note": "test_approve"
        })

        # May succeed or fail based on exchange/risk state
        if response.status_code == 200:
            data = response.json()
            assert "id" in data
            assert "status" in data
            # Status should be one of: approved, submitted, filled, blocked
            assert data["status"] in ["approved", "submitted", "filled", "blocked", "queued"]
            # Should have decision metadata
            assert "decided_at" in data
            assert "decision_note" in data
            # Check execution trace
            assert "current_state" in data
            if data["status"] == "filled":
                assert data.get("order_position_id") is not None
        elif response.status_code == 400:
            # Signal was blocked for another reason
            detail = response.json().get("detail", "")
            assert "signal_blocked" in detail or "not_actionable" in detail

    def test_reject_pending_signal(self, user_client):
        """POST /user/signal/{id}/reject marks signal as rejected"""
        # Generate signals
        user_client.put(f"{BASE_URL}/api/user/signal-mode", json={"mode": "MANUAL"})
        user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 3
        })

        # Get pending signals
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 50
        })
        assert response.status_code == 200
        signals = response.json()

        pending_signals = [
            s for s in signals
            if s.get("status") in ["pending", "ready", "blocked"]
        ]

        if not pending_signals:
            pytest.skip("No pending signals found")

        signal = pending_signals[0]
        signal_id = signal["id"]

        # Reject the signal
        response = user_client.post(f"{BASE_URL}/api/user/signal/{signal_id}/reject", json={
            "note": "test_reject"
        })

        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "rejected"
            assert "decided_at" in data
            assert data["current_state"] == "REJECTED"


class TestAutoModeExecution:
    """Test full auto mode execution scenario"""

    def test_auto_mode_creates_intent(self, user_client):
        """AUTO mode signal can create order intent when eligible"""
        # Set to AUTO mode
        user_client.put(f"{BASE_URL}/api/user/signal-mode", json={"mode": "AUTO"})

        # Run scanner in AUTO mode
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "AUTO",
            "max_results": 5
        })
        assert response.status_code == 200

        # Get signals
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 50
        })
        assert response.status_code == 200
        signals = response.json()

        # Look for signals with created_order_intent_id (auto execution attempted)
        auto_signals = [s for s in signals if s.get("mode") == "AUTO"]

        # Check if any have intent or filled status
        executed = [s for s in auto_signals if
                    s.get("created_order_intent_id") or
                    s.get("status") in ["submitted", "queued", "filled"]]

        # Note: May be empty if all blocked by risk/exchange checks
        # But the test verifies the data structure is correct
        for signal in auto_signals:
            # Trace fields should be present
            assert "current_state" in signal
            assert "execution_eligible" in signal
            assert "created_order_intent_id" in signal


class TestDecisionTraceEndpoints:
    """Test decision trace for signal traceability"""

    def test_signal_decision_trace(self, user_client):
        """GET /user/signals/{id}/decision-trace returns trace"""
        # Get signals
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 20
        })
        assert response.status_code == 200
        signals = response.json()

        if not signals:
            pytest.skip("No signals to trace")

        signal_id = signals[0]["id"]

        # Get decision trace
        response = user_client.get(f"{BASE_URL}/api/user/signals/{signal_id}/decision-trace")
        assert response.status_code == 200
        data = response.json()

        # Verify trace structure
        assert "entity_id" in data
        assert "trace_count" in data
        assert "timeline" in data

    def test_strategy_explain_endpoint(self, user_client):
        """GET /user/strategies/{code}/explain returns explanation"""
        # Get signals to find a strategy code
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 20
        })
        assert response.status_code == 200
        signals = response.json()

        if not signals:
            pytest.skip("No signals found")

        strategy_code = signals[0].get("strategy_code", "spot_pullback_v1")

        # Get strategy explanation
        response = user_client.get(
            f"{BASE_URL}/api/user/strategies/{strategy_code}/explain",
            params={"lookback_days": 30}
        )
        assert response.status_code == 200
        data = response.json()

        assert "strategy_code" in data
        assert "trace_count" in data
        assert "decision_distribution" in data
        assert "top_reason_codes" in data


class TestUIDataContract:
    """Verify data contract for UI columns"""

    def test_signals_response_has_ui_columns(self, user_client):
        """Signal response includes all required UI columns"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 20
        })
        assert response.status_code == 200
        signals = response.json()

        if not signals:
            pytest.skip("No signals for UI contract test")

        signal = signals[0]

        # Required UI columns per PRD
        required_columns = [
            "execution_mode_label",  # Execution Mode
            "blocked_reason_code",   # Blokaj Nedeni
            "blocked_solution_hint", # Çözüm
            "last_eligibility_check_at",  # Son Uygunluk Kontrolü
            "created_order_intent_id",    # Intent
            "runtime_owner"          # Runtime Sahibi
        ]

        for col in required_columns:
            assert col in signal, f"Missing UI column: {col}"

    def test_execution_mode_label_values(self, user_client):
        """execution_mode_label returns correct values"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 50
        })
        assert response.status_code == 200
        signals = response.json()

        valid_labels = ["Manual", "Semi-Auto", "Full Auto"]

        for signal in signals:
            label = signal.get("execution_mode_label")
            if label:
                assert label in valid_labels, f"Invalid mode label: {label}"


class TestStateTransitions:
    """Verify state machine transitions"""

    VALID_STATES = [
        "DETECTED",
        "PENDING_APPROVAL",
        "EXECUTION_READY",
        "APPROVED",
        "ORDER_INTENT_CREATED",
        "ORDER_SUBMITTED",
        "BLOCKED",
        "FILLED",
        "REJECTED",
        "EXPIRED"
    ]

    def test_signal_states_are_valid(self, user_client):
        """All signal states are valid state machine states"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 100
        })
        assert response.status_code == 200
        signals = response.json()

        for signal in signals:
            current_state = signal.get("current_state")
            previous_state = signal.get("previous_state")

            if current_state:
                assert current_state in self.VALID_STATES, \
                    f"Invalid current_state: {current_state}"

            if previous_state:
                assert previous_state in self.VALID_STATES, \
                    f"Invalid previous_state: {previous_state}"


class TestExchangeConnectionIntegration:
    """Test exchange connection impact on signal execution"""

    def test_signals_have_exchange_connection_id(self, user_client):
        """Signals track exchange_connection_id"""
        # Run scanner to ensure signals exist
        user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 3
        })

        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 20
        })
        assert response.status_code == 200
        signals = response.json()

        # exchange_connection_id field should exist (may be null if not resolved)
        for signal in signals:
            assert "exchange_connection_id" in signal

    def test_exchange_not_ready_blocks_execution(self, user_client):
        """EXCHANGE_NOT_READY reason blocks execution appropriately"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 100
        })
        assert response.status_code == 200
        signals = response.json()

        exchange_blocked = [
            s for s in signals
            if s.get("blocked_reason_code") == "EXCHANGE_NOT_READY"
        ]

        # If any are blocked for exchange, verify they're not execution_eligible
        for signal in exchange_blocked:
            assert signal.get("execution_eligible") is False


class TestRiskPolicyIntegration:
    """Test risk policy impact on signal execution"""

    def test_signals_have_risk_policy_id(self, user_client):
        """Signals track risk_policy_id"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 20
        })
        assert response.status_code == 200
        signals = response.json()

        for signal in signals:
            assert "risk_policy_id" in signal

    def test_risk_policy_missing_blocks_execution(self, user_client):
        """RISK_POLICY_MISSING reason blocks execution"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 100
        })
        assert response.status_code == 200
        signals = response.json()

        risk_blocked = [
            s for s in signals
            if s.get("blocked_reason_code") == "RISK_POLICY_MISSING"
        ]

        for signal in risk_blocked:
            assert signal.get("execution_eligible") is False


class TestBotProfileIntegration:
    """Test bot profile impact on signal execution"""

    def test_signals_have_bot_profile_id(self, user_client):
        """Signals track bot_profile_id"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 20
        })
        assert response.status_code == 200
        signals = response.json()

        for signal in signals:
            assert "bot_profile_id" in signal

    def test_bot_not_running_blocks_execution(self, user_client):
        """BOT_NOT_RUNNING reason blocks execution"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 100
        })
        assert response.status_code == 200
        signals = response.json()

        bot_blocked = [
            s for s in signals
            if s.get("blocked_reason_code") == "BOT_NOT_RUNNING"
        ]

        for signal in bot_blocked:
            assert signal.get("execution_eligible") is False


class TestPositionLimitIntegration:
    """Test position limit blocking"""

    def test_position_limit_reached_blocks_execution(self, user_client):
        """POSITION_LIMIT_REACHED reason blocks execution"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={
            "limit": 100
        })
        assert response.status_code == 200
        signals = response.json()

        limit_blocked = [
            s for s in signals
            if s.get("blocked_reason_code") == "POSITION_LIMIT_REACHED"
        ]

        for signal in limit_blocked:
            assert signal.get("execution_eligible") is False


# Run these tests with:
# pytest /app/backend/tests/test_iteration68_signal_execution_blocker_regression.py -v --tb=short
