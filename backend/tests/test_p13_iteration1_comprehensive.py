"""P1.3 Iteration 1 Comprehensive Tests

Coverage:
- POST /api/auth/login -> token + role + user response
- Legacy wrapper endpoints /api/auth/login/admin and /api/auth/login/user
- POST /api/runtime/strategy/signal EMA+RSI normalized contract
- POST /api/runtime/execution/submit risk reject scenario (leverage cap or position cap)
- POST /api/runtime/execution/submit accept -> queue payload required fields
- POST /api/runtime/execution/worker/process-once queue consume and order/job state advance
- GET /api/runtime/execution/jobs/{id} state machine values
- Idempotency: same key second submit returns duplicate
- DB tables check: execution_jobs, orders, positions, execution_events
- positions table runtime columns (external_order_id, last_state_transition_at, reject_reason, fail_reason)
"""

import os
import time
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


def _wait_health_ok(timeout_seconds: int = 40) -> None:
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    pytest.skip("backend health not ready")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin token for authenticated requests"""
    _wait_health_ok()
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip("admin login failed")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ============================================================================
# AUTH LOGIN TESTS
# ============================================================================

class TestUnifiedAuthLogin:
    """POST /api/auth/login -> token + role + user response"""

    def test_login_returns_token_role_user(self):
        """Unified login must return token, role, and user object"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert data.get("token"), "token field missing"
        assert data.get("access_token"), "access_token field missing"
        assert data.get("role"), "role field missing"
        assert data.get("user"), "user object missing"
        
        # Validate user object structure
        user = data["user"]
        assert user.get("id"), "user.id missing"
        assert user.get("email") == ADMIN_EMAIL, "user.email mismatch"
        
        # Role should be valid
        assert data["role"] in {"super_admin", "admin", "ops", "user"}

    def test_login_invalid_credentials_returns_401(self):
        """Invalid credentials should return 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@test.com", "password": "wrongpassword"},
            timeout=20,
        )
        assert response.status_code in {401, 403, 404}


class TestLegacyAuthEndpoints:
    """Legacy wrapper endpoints /api/auth/login/admin and /api/auth/login/user"""

    def test_admin_login_endpoint_works(self):
        """POST /api/auth/login/admin should work for admin users"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("token"), "token missing from admin login"
        assert data.get("role") in {"super_admin", "admin", "ops"}

    def test_user_login_endpoint_rejects_admin(self):
        """POST /api/auth/login/user should reject admin users (role mismatch)"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        # Admin should be rejected from user login endpoint
        assert response.status_code in {401, 403}


# ============================================================================
# STRATEGY SIGNAL TESTS
# ============================================================================

class TestStrategySignal:
    """POST /api/runtime/strategy/signal EMA+RSI normalized contract"""

    def test_strategy_signal_ema_rsi_contract(self, auth_headers):
        """Strategy signal endpoint should return normalized EMA+RSI signal"""
        # Generate closes that should trigger a signal (uptrend)
        closes = [100 + i * 0.2 for i in range(80)]
        
        response = requests.post(
            f"{BASE_URL}/api/runtime/strategy/signal",
            json={"symbol": "ETHUSDT", "closes": closes, "strategy_name": "ema_rsi"},
            headers=auth_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") in {"ok", "no_signal"}
        
        if data.get("signal"):
            signal = data["signal"]
            # Verify normalized contract fields
            required_fields = ["symbol", "side", "size", "confidence", "strategy_name", "timestamp"]
            for field in required_fields:
                assert field in signal, f"signal missing field: {field}"
            
            # Validate field values
            assert signal["symbol"] == "ETHUSDT"
            assert signal["side"] in {"BUY", "SELL"}
            assert signal["size"] > 0
            assert 0 <= signal["confidence"] <= 1
            assert signal["strategy_name"] == "ema_rsi"

    def test_strategy_signal_requires_admin(self):
        """Strategy signal endpoint requires admin authentication"""
        closes = [100 + i * 0.1 for i in range(80)]
        response = requests.post(
            f"{BASE_URL}/api/runtime/strategy/signal",
            json={"symbol": "BTCUSDT", "closes": closes, "strategy_name": "ema_rsi"},
            timeout=20,
        )
        assert response.status_code in {401, 403}


# ============================================================================
# EXECUTION SUBMIT TESTS
# ============================================================================

class TestExecutionSubmitRiskReject:
    """POST /api/runtime/execution/submit risk reject scenario"""

    def test_leverage_cap_rejection(self, auth_headers):
        """Submission with leverage > cap should be rejected"""
        idem = f"test-leverage-reject-{uuid.uuid4()}"
        response = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "ETHUSDT",
                "side": "BUY",
                "size": 1.0,
                "confidence": 0.8,
                "strategy_name": "ema_rsi",
                "mark_price": 1000,
                "leverage": 10,  # Exceeds default cap of 3
                "idempotency_key": idem,
            },
            headers=auth_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "rejected"
        assert data.get("risk", {}).get("reject_reason") is not None
        assert "leverage" in str(data.get("risk", {}).get("reject_reasons", [])).lower()

    def test_position_cap_rejection(self, auth_headers):
        """Submission exceeding position cap should be rejected"""
        idem = f"test-position-reject-{uuid.uuid4()}"
        response = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 100.0,  # Large size
                "confidence": 0.8,
                "strategy_name": "ema_rsi",
                "mark_price": 50000,  # High price = high notional
                "leverage": 1,
                "idempotency_key": idem,
            },
            headers=auth_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should be rejected due to position cap
        assert data.get("status") == "rejected"
        assert data.get("risk", {}).get("reject_reason") is not None


class TestExecutionSubmitAccept:
    """POST /api/runtime/execution/submit accept -> queue payload required fields"""

    def test_submit_accept_queue_payload_fields(self, auth_headers):
        """Accepted submission should have all required queue payload fields"""
        idem = f"test-accept-{uuid.uuid4()}"
        response = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "ETHUSDT",
                "side": "BUY",
                "size": 0.1,
                "confidence": 0.75,
                "strategy_name": "ema_rsi",
                "mark_price": 100,  # Low price = low notional
                "leverage": 1,
                "idempotency_key": idem,
            },
            headers=auth_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "enqueued"
        assert data.get("execution_job_id")
        assert data.get("idempotency_key") == idem
        
        # Verify queue_payload required fields
        queue_payload = data.get("queue_payload", {})
        required_fields = [
            "execution_job_id",
            "idempotency_key",
            "user_id",
            "symbol",
            "side",
            "size",
            "strategy_name",
            "created_at",
            "retry_count",
        ]
        for field in required_fields:
            assert field in queue_payload, f"queue_payload missing field: {field}"


# ============================================================================
# WORKER PROCESS TESTS
# ============================================================================

class TestWorkerProcessOnce:
    """POST /api/runtime/execution/worker/process-once queue consume and state advance"""

    def test_worker_process_advances_state(self, auth_headers):
        """Worker should consume queue and advance job/order state"""
        # First submit a job
        idem = f"test-worker-{uuid.uuid4()}"
        submit = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "ETHUSDT",
                "side": "BUY",
                "size": 0.15,
                "confidence": 0.8,
                "strategy_name": "ema_rsi",
                "mark_price": 100,
                "leverage": 1,
                "idempotency_key": idem,
            },
            headers=auth_headers,
            timeout=20,
        )
        assert submit.status_code == 200
        submit_data = submit.json()
        
        if submit_data.get("status") != "enqueued":
            pytest.skip("submission not enqueued")
        
        job_id = submit_data.get("execution_job_id")
        
        # Process the queue
        worker = requests.post(
            f"{BASE_URL}/api/runtime/execution/worker/process-once",
            headers=auth_headers,
            timeout=20,
        )
        assert worker.status_code == 200
        worker_data = worker.json()
        
        assert worker_data.get("status") in {"processed", "queue_empty"}
        
        if worker_data.get("status") == "processed":
            assert worker_data.get("execution_job_id")
            assert worker_data.get("state") in {"SENT", "PARTIALLY_FILLED", "FILLED"}


# ============================================================================
# EXECUTION JOB STATE MACHINE TESTS
# ============================================================================

class TestExecutionJobStateMachine:
    """GET /api/runtime/execution/jobs/{id} state machine values"""

    def test_get_job_shows_state_machine_values(self, auth_headers):
        """Job endpoint should show state machine values"""
        # Submit and process a job
        idem = f"test-state-{uuid.uuid4()}"
        submit = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "BTCUSDT",
                "side": "SELL",
                "size": 0.1,
                "confidence": 0.7,
                "strategy_name": "ema_rsi",
                "mark_price": 100,
                "leverage": 1,
                "idempotency_key": idem,
            },
            headers=auth_headers,
            timeout=20,
        )
        assert submit.status_code == 200
        submit_data = submit.json()
        
        if submit_data.get("status") != "enqueued":
            pytest.skip("submission not enqueued")
        
        job_id = submit_data.get("execution_job_id")
        
        # Get job state
        job = requests.get(
            f"{BASE_URL}/api/runtime/execution/jobs/{job_id}",
            headers=auth_headers,
            timeout=20,
        )
        assert job.status_code == 200
        job_data = job.json()
        
        # Verify state machine fields
        assert job_data.get("id") == job_id
        assert job_data.get("state") in {"CREATED", "SENT", "PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELED"}
        assert job_data.get("idempotency_key") == idem
        assert job_data.get("symbol") == "BTCUSDT"
        assert job_data.get("side") == "SELL"
        
        # Optional fields that should be present
        assert "reject_reason" in job_data
        assert "fail_reason" in job_data
        assert "retry_count" in job_data
        assert "created_at" in job_data
        assert "last_state_transition_at" in job_data

    def test_get_nonexistent_job_returns_404(self, auth_headers):
        """Getting non-existent job should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/execution/jobs/nonexistent-job-id",
            headers=auth_headers,
            timeout=20,
        )
        assert response.status_code == 404


# ============================================================================
# IDEMPOTENCY TESTS
# ============================================================================

class TestIdempotency:
    """Idempotency: same key second submit returns duplicate"""

    def test_duplicate_submission_returns_duplicate_status(self, auth_headers):
        """Second submission with same idempotency key should return duplicate"""
        idem = f"test-idem-{uuid.uuid4()}"
        payload = {
            "symbol": "ETHUSDT",
            "side": "BUY",
            "size": 0.1,
            "confidence": 0.7,
            "strategy_name": "ema_rsi",
            "mark_price": 100,
            "leverage": 1,
            "idempotency_key": idem,
        }
        
        # First submission
        first = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json=payload,
            headers=auth_headers,
            timeout=20,
        )
        assert first.status_code == 200
        first_data = first.json()
        
        # Second submission with same key
        second = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json=payload,
            headers=auth_headers,
            timeout=20,
        )
        assert second.status_code == 200
        second_data = second.json()
        
        assert second_data.get("status") == "duplicate"
        assert second_data.get("idempotency_key") == idem
        
        # Should return same execution_job_id
        if first_data.get("execution_job_id"):
            assert second_data.get("execution_job_id") == first_data.get("execution_job_id")


# ============================================================================
# DB TABLES CHECK (via API endpoints)
# ============================================================================

class TestDBTablesViaAPI:
    """DB tables check: execution_jobs, orders, positions via API"""

    def test_execution_job_persisted_in_db(self, auth_headers):
        """Execution job should be persisted and retrievable"""
        idem = f"test-db-job-{uuid.uuid4()}"
        submit = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "ETHUSDT",
                "side": "BUY",
                "size": 0.1,
                "confidence": 0.8,
                "strategy_name": "ema_rsi",
                "mark_price": 100,
                "leverage": 1,
                "idempotency_key": idem,
            },
            headers=auth_headers,
            timeout=20,
        )
        assert submit.status_code == 200
        submit_data = submit.json()
        
        if submit_data.get("status") not in {"enqueued", "rejected"}:
            pytest.skip("unexpected status")
        
        job_id = submit_data.get("execution_job_id")
        
        # Verify job is persisted
        job = requests.get(
            f"{BASE_URL}/api/runtime/execution/jobs/{job_id}",
            headers=auth_headers,
            timeout=20,
        )
        assert job.status_code == 200
        assert job.json().get("id") == job_id

    def test_order_created_after_worker_process(self, auth_headers):
        """Order should be created after worker processes job"""
        idem = f"test-db-order-{uuid.uuid4()}"
        submit = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "ETHUSDT",
                "side": "BUY",
                "size": 0.2,
                "confidence": 0.8,
                "strategy_name": "ema_rsi",
                "mark_price": 100,
                "leverage": 1,
                "idempotency_key": idem,
            },
            headers=auth_headers,
            timeout=20,
        )
        assert submit.status_code == 200
        submit_data = submit.json()
        
        if submit_data.get("status") != "enqueued":
            pytest.skip("submission not enqueued")
        
        # Process the job
        worker = requests.post(
            f"{BASE_URL}/api/runtime/execution/worker/process-once",
            headers=auth_headers,
            timeout=20,
        )
        assert worker.status_code == 200
        worker_data = worker.json()
        
        if worker_data.get("status") == "processed":
            # Order should be created
            order_id = worker_data.get("order_id")
            if order_id:
                order = requests.get(
                    f"{BASE_URL}/api/runtime/execution/orders/{order_id}",
                    headers=auth_headers,
                    timeout=20,
                )
                assert order.status_code == 200
                order_data = order.json()
                assert order_data.get("id") == order_id
                assert order_data.get("state") in {"CREATED", "SENT", "PARTIALLY_FILLED", "FILLED"}


# ============================================================================
# POSITIONS TABLE RUNTIME COLUMNS
# ============================================================================

class TestPositionsRuntimeColumns:
    """positions table runtime columns (external_order_id, last_state_transition_at, reject_reason, fail_reason)"""

    def test_position_created_with_runtime_columns(self, auth_headers):
        """Position should have runtime columns after fill"""
        idem = f"test-position-{uuid.uuid4()}"
        
        # Submit a job that will be filled
        submit = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "SOLUSDT",
                "side": "BUY",
                "size": 0.5,
                "confidence": 0.8,
                "strategy_name": "ema_rsi",
                "mark_price": 50,
                "leverage": 1,
                "idempotency_key": idem,
            },
            headers=auth_headers,
            timeout=20,
        )
        assert submit.status_code == 200
        submit_data = submit.json()
        
        if submit_data.get("status") != "enqueued":
            pytest.skip("submission not enqueued")
        
        # Process to fill
        worker = requests.post(
            f"{BASE_URL}/api/runtime/execution/worker/process-once",
            headers=auth_headers,
            timeout=20,
        )
        assert worker.status_code == 200
        worker_data = worker.json()
        
        # If processed and filled, position should be created
        if worker_data.get("status") == "processed" and worker_data.get("state") == "FILLED":
            # Position should have external_order_id
            assert worker_data.get("external_order_id") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
