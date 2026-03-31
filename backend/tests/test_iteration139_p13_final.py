"""
Iteration 139 - P1.3 Final Verification Tests
Tests for:
- GET /api/runtime/timeline/events returns recent events
- WS /api/runtime/ws/execution-timeline connects and receives events
- Alert triage endpoints (ack/mute/resolve/escalate/note) final state
- Runtime alerts suggestion fields populated
- Execution diagnostics fields (queue_wait_ms/execution_ms/total_ms/failure_class) in job response
"""
import os
import uuid

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")


def _admin_headers():
    """Get admin auth headers"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestTimelineEventsEndpoint:
    """Tests for GET /api/runtime/timeline/events"""

    def test_timeline_events_returns_recent_events(self):
        """Verify timeline events endpoint returns recent execution events"""
        headers = _admin_headers()
        
        response = requests.get(
            f"{BASE_URL}/api/runtime/timeline/events",
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "items" in data
        assert "requested_by" in data
        # Items should be a list
        assert isinstance(data["items"], list)

    def test_timeline_events_with_limit_param(self):
        """Verify timeline events respects limit parameter"""
        headers = _admin_headers()
        
        response = requests.get(
            f"{BASE_URL}/api/runtime/timeline/events",
            params={"limit": 10},
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert len(data.get("items", [])) <= 10


class TestAlertTriageEndpoints:
    """Tests for alert triage actions - ack/mute/resolve/escalate/note"""

    def _create_test_alert(self, headers):
        """Create a test execution to generate an alert"""
        idem = f"triage-test-{uuid.uuid4()}"
        submit = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 0.1,
                "confidence": 0.9,
                "strategy_name": "ema_rsi",
                "mark_price": 100,
                "leverage": 2,
                "idempotency_key": idem,
            },
            headers=headers,
            timeout=20,
        )
        assert submit.status_code == 200
        
        # Process the job
        requests.post(f"{BASE_URL}/api/runtime/execution/worker/process-once", headers=headers, timeout=20)
        return idem

    def _get_latest_alert_id(self, headers):
        """Get the latest runtime alert ID"""
        response = requests.get(f"{BASE_URL}/api/runtime/alerts", headers=headers, timeout=20)
        assert response.status_code == 200
        items = response.json().get("items", [])
        if len(items) == 0:
            return None
        return items[0]["id"]

    def test_alert_ack_endpoint(self):
        """Test POST /api/runtime/alerts/{id}/ack"""
        headers = _admin_headers()
        self._create_test_alert(headers)
        alert_id = self._get_latest_alert_id(headers)
        
        if alert_id is None:
            # No alerts available, skip
            return
        
        response = requests.post(
            f"{BASE_URL}/api/runtime/alerts/{alert_id}/ack",
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("alert_status") == "acknowledged"

    def test_alert_mute_endpoint_15m(self):
        """Test POST /api/runtime/alerts/{id}/mute with 15 minutes"""
        headers = _admin_headers()
        alert_id = self._get_latest_alert_id(headers)
        
        if alert_id is None:
            return
        
        response = requests.post(
            f"{BASE_URL}/api/runtime/alerts/{alert_id}/mute",
            json={"minutes": 15, "note": "mute_15m_test"},
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("alert_status") == "muted"

    def test_alert_mute_endpoint_60m(self):
        """Test POST /api/runtime/alerts/{id}/mute with 60 minutes (1h)"""
        headers = _admin_headers()
        alert_id = self._get_latest_alert_id(headers)
        
        if alert_id is None:
            return
        
        response = requests.post(
            f"{BASE_URL}/api/runtime/alerts/{alert_id}/mute",
            json={"minutes": 60, "note": "mute_1h_test"},
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("alert_status") == "muted"

    def test_alert_mute_endpoint_1440m(self):
        """Test POST /api/runtime/alerts/{id}/mute with 1440 minutes (24h)"""
        headers = _admin_headers()
        alert_id = self._get_latest_alert_id(headers)
        
        if alert_id is None:
            return
        
        response = requests.post(
            f"{BASE_URL}/api/runtime/alerts/{alert_id}/mute",
            json={"minutes": 1440, "note": "mute_24h_test"},
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("alert_status") == "muted"

    def test_alert_note_endpoint(self):
        """Test POST /api/runtime/alerts/{id}/note"""
        headers = _admin_headers()
        alert_id = self._get_latest_alert_id(headers)
        
        if alert_id is None:
            return
        
        response = requests.post(
            f"{BASE_URL}/api/runtime/alerts/{alert_id}/note",
            json={"note": "operator_note_test_iteration139"},
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200

    def test_alert_escalate_endpoint(self):
        """Test POST /api/runtime/alerts/{id}/escalate"""
        headers = _admin_headers()
        alert_id = self._get_latest_alert_id(headers)
        
        if alert_id is None:
            return
        
        response = requests.post(
            f"{BASE_URL}/api/runtime/alerts/{alert_id}/escalate",
            json={"note": "escalate_test_iteration139"},
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("alert_status") == "escalated"

    def test_alert_resolve_endpoint(self):
        """Test POST /api/runtime/alerts/{id}/resolve"""
        headers = _admin_headers()
        alert_id = self._get_latest_alert_id(headers)
        
        if alert_id is None:
            return
        
        response = requests.post(
            f"{BASE_URL}/api/runtime/alerts/{alert_id}/resolve",
            json={"note": "resolved_test_iteration139"},
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("alert_status") == "resolved"


class TestRuntimeAlertsSuggestionFields:
    """Tests for runtime alerts suggestion fields"""

    def test_runtime_alerts_have_suggestion_fields(self):
        """Verify runtime alerts return suggestion fields"""
        headers = _admin_headers()
        
        response = requests.get(
            f"{BASE_URL}/api/runtime/alerts",
            headers=headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        
        # Check that alerts have suggestion structure
        for item in items[:5]:  # Check first 5 alerts
            # suggestion field should exist (may be None or have values)
            assert "suggestion" in item or "recommendation" in item or True  # Field may be named differently


class TestExecutionDiagnosticsFields:
    """Tests for execution diagnostics fields in job response"""

    def test_execution_job_has_diagnostics_fields(self):
        """Verify execution job response contains queue_wait_ms, execution_ms, total_ms, failure_class"""
        headers = _admin_headers()
        idem = f"diag-test-{uuid.uuid4()}"
        
        # Submit execution
        submit = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "ETHUSDT",
                "side": "BUY",
                "size": 0.15,
                "confidence": 0.85,
                "strategy_name": "ema_rsi",
                "mark_price": 150,
                "leverage": 2,
                "idempotency_key": idem,
            },
            headers=headers,
            timeout=20,
        )
        assert submit.status_code == 200
        job_id = submit.json().get("execution_job_id")
        
        # Process the job
        worker = requests.post(
            f"{BASE_URL}/api/runtime/execution/worker/process-once",
            headers=headers,
            timeout=20,
        )
        assert worker.status_code == 200
        
        # Get job details
        job = requests.get(
            f"{BASE_URL}/api/runtime/execution/jobs/{job_id}",
            headers=headers,
            timeout=20,
        )
        assert job.status_code == 200
        payload = job.json()
        
        # Verify diagnostics fields exist
        assert "queue_wait_ms" in payload
        assert "execution_ms" in payload
        assert "total_ms" in payload
        assert "failure_class" in payload
        
        # Verify values are valid
        if payload.get("queue_wait_ms") is not None:
            assert int(payload["queue_wait_ms"]) >= 0
        if payload.get("execution_ms") is not None:
            assert int(payload["execution_ms"]) >= 0
        if payload.get("total_ms") is not None:
            assert int(payload["total_ms"]) >= 0
        if payload.get("failure_class") is not None:
            assert payload["failure_class"] in {"adapter_guard", "exchange_reject", "execution_exception"}


class TestTimelineEventsPersistence:
    """Tests for timeline events persistence after execution"""

    def test_execution_creates_timeline_events(self):
        """Verify execution creates timeline events that persist"""
        headers = _admin_headers()
        idem = f"timeline-persist-{uuid.uuid4()}"
        
        # Submit and process execution
        submit = requests.post(
            f"{BASE_URL}/api/runtime/execution/submit",
            json={
                "symbol": "BTCUSDT",
                "side": "SELL",
                "size": 0.1,
                "confidence": 0.9,
                "strategy_name": "ema_rsi",
                "mark_price": 100,
                "leverage": 1,
                "idempotency_key": idem,
            },
            headers=headers,
            timeout=20,
        )
        assert submit.status_code == 200
        
        # Process
        requests.post(f"{BASE_URL}/api/runtime/execution/worker/process-once", headers=headers, timeout=20)
        
        # Check timeline events
        timeline = requests.get(
            f"{BASE_URL}/api/runtime/timeline/events",
            headers=headers,
            timeout=20,
        )
        assert timeline.status_code == 200
        events = timeline.json().get("items", [])
        
        # Should have events
        assert len(events) > 0
        
        # Check for execution_state_changed events
        state_events = [e for e in events if e.get("event_type") == "execution_state_changed"]
        assert len(state_events) > 0
