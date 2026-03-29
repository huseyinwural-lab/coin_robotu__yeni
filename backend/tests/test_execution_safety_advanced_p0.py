"""
Execution Safety Advanced P0 Tests - Iteration 175
Tests for:
- POST /api/execution-safety/acceptance/testnet/run (ack->fill sequence, acceptance_run_id/correlation_id generation)
- GET /api/execution-safety/acceptance/testnet/latest
- GET /api/execution-safety/acceptance/testnet/history
- GET /api/execution-safety/intents/{intent_id}/timeline
- GET /api/execution-safety/intents/{intent_id}/reconcile
- GET /api/execution-safety/artifacts/{intent_id}
- GET /api/execution-safety/quarantine/{quarantine_id}
- POST /api/execution-safety/recovery/bulk-retry
- POST /api/execution-safety/recovery/bulk-cancel
- POST /api/execution-safety/recovery/bulk-reconcile
- Correlation enforcement behavior: missing spine critical stages -> quarantine, non-critical -> blocked
- Canonical CANCELED output (not CANCELLED)
"""
import pytest
from fastapi.testclient import TestClient

from server import fastapi_app


ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def client():
    return TestClient(fastapi_app)


@pytest.fixture(scope="module")
def auth_headers(client):
    response = client.post(
        "/api/auth/login/admin",
        headers={"X-Session-Device": "devtestclientsessionid0123456789"},
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"admin login failed: {response.status_code}")
    token = response.json().get("access_token") or response.json().get("token")
    return {
        "Authorization": f"Bearer {token}",
        "X-Session-Device": "devtestclientsessionid0123456789",
    }


# ============================================================================
# ACCEPTANCE TESTNET ENDPOINTS
# ============================================================================

class TestAcceptanceTestnetRun:
    """POST /api/execution-safety/acceptance/testnet/run"""

    def test_acceptance_run_returns_required_fields(self, client, auth_headers):
        """Acceptance run should return acceptance_run_id, correlation_id, final_verdict"""
        response = client.post(
            "/api/execution-safety/acceptance/testnet/run?symbol=BTCUSDT&qty=0.001",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "acceptance_run_id" in data
        assert "correlation_id" in data
        assert "final_verdict" in data
        
        # Verdict must be one of expected values
        assert data["final_verdict"] in {"PASS", "FAILED", "BLOCKED"}
        
        # IDs must be non-empty strings
        assert isinstance(data["acceptance_run_id"], str)
        assert len(data["acceptance_run_id"]) > 0
        assert isinstance(data["correlation_id"], str)
        assert len(data["correlation_id"]) > 0

    def test_acceptance_run_ack_fill_sequence(self, client, auth_headers):
        """Acceptance run should follow ack->fill sequence, skip fill if ack fails"""
        response = client.post(
            "/api/execution-safety/acceptance/testnet/run?symbol=BTCUSDT&qty=0.001",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # If BLOCKED, check for gate blockers
        if data["final_verdict"] == "BLOCKED":
            assert "gate" in data or "reason_code" in data
            # Blocked should still produce artifact
            assert "artefact_manifest" in data
            return
        
        # If not blocked, check acceptance_summary
        if "acceptance_summary" in data:
            summary = data["acceptance_summary"]
            ack_status = summary.get("ack_mode")
            fill_status = summary.get("fill_mode")
            
            # If ack failed, fill should be SKIPPED
            if ack_status != "PASS":
                assert fill_status == "SKIPPED", "fill_mode should be SKIPPED when ack_mode fails"

    def test_acceptance_run_produces_artifact(self, client, auth_headers):
        """Acceptance run should always produce artifact manifest"""
        response = client.post(
            "/api/execution-safety/acceptance/testnet/run?symbol=BTCUSDT&qty=0.001",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Artifact manifest should exist regardless of verdict
        assert "artefact_manifest" in data
        manifest = data["artefact_manifest"]
        assert isinstance(manifest, dict)
        
        # Run artifact should always be present
        assert "run" in manifest

    def test_acceptance_run_audit_record(self, client, auth_headers):
        """Acceptance run should produce audit record"""
        response = client.post(
            "/api/execution-safety/acceptance/testnet/run?symbol=BTCUSDT&qty=0.001",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Audit record should exist
        assert "audit_record" in data
        audit = data["audit_record"]
        assert "action" in audit
        assert "entity_id" in audit


class TestAcceptanceTestnetLatest:
    """GET /api/execution-safety/acceptance/testnet/latest"""

    def test_latest_returns_200(self, client, auth_headers):
        response = client.get(
            "/api/execution-safety/acceptance/testnet/latest",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "latest" in data

    def test_latest_structure(self, client, auth_headers):
        """Latest should return latest acceptance run or null"""
        response = client.get(
            "/api/execution-safety/acceptance/testnet/latest",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        latest = data.get("latest")
        # Can be None if no runs yet
        if latest is not None:
            assert isinstance(latest, dict)


class TestAcceptanceTestnetHistory:
    """GET /api/execution-safety/acceptance/testnet/history"""

    def test_history_returns_200(self, client, auth_headers):
        response = client.get(
            "/api/execution-safety/acceptance/testnet/history?limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_history_respects_limit(self, client, auth_headers):
        response = client.get(
            "/api/execution-safety/acceptance/testnet/history?limit=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("items", [])) <= 5


# ============================================================================
# INTENT TIMELINE AND RECONCILE ENDPOINTS
# ============================================================================

class TestIntentTimeline:
    """GET /api/execution-safety/intents/{intent_id}/timeline"""

    def test_timeline_missing_intent_returns_404(self, client, auth_headers):
        response = client.get(
            "/api/execution-safety/intents/nonexistent-intent-id/timeline",
            headers=auth_headers,
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_timeline_structure_with_existing_intent(self, client, auth_headers):
        """If intents exist, timeline should have required fields"""
        # First get list of intents
        intents_resp = client.get(
            "/api/execution-safety/intents?limit=5",
            headers=auth_headers,
        )
        assert intents_resp.status_code == 200
        intents = intents_resp.json().get("items", [])
        
        if not intents:
            pytest.skip("No intents available for timeline test")
        
        intent_id = intents[0].get("intent_id")
        response = client.get(
            f"/api/execution-safety/intents/{intent_id}/timeline",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "intent_id" in data
        assert "correlation_id" in data
        assert "current_status" in data
        assert "timeline" in data
        assert isinstance(data["timeline"], list)


class TestIntentReconcile:
    """GET /api/execution-safety/intents/{intent_id}/reconcile"""

    def test_reconcile_missing_intent_returns_404(self, client, auth_headers):
        response = client.get(
            "/api/execution-safety/intents/nonexistent-intent-id/reconcile",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_reconcile_structure_with_existing_intent(self, client, auth_headers):
        """If intents exist, reconcile should have required fields"""
        intents_resp = client.get(
            "/api/execution-safety/intents?limit=5",
            headers=auth_headers,
        )
        assert intents_resp.status_code == 200
        intents = intents_resp.json().get("items", [])
        
        if not intents:
            pytest.skip("No intents available for reconcile test")
        
        intent_id = intents[0].get("intent_id")
        response = client.get(
            f"/api/execution-safety/intents/{intent_id}/reconcile",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "intent_id" in data
        assert "correlation_id" in data
        assert "current_status" in data
        assert "latest_reconcile" in data


# ============================================================================
# ARTIFACTS ENDPOINT
# ============================================================================

class TestArtifactsByIntent:
    """GET /api/execution-safety/artifacts/{intent_id}"""

    def test_artifacts_missing_intent_returns_404(self, client, auth_headers):
        response = client.get(
            "/api/execution-safety/artifacts/nonexistent-intent-id",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_artifacts_structure_with_existing_intent(self, client, auth_headers):
        """If intents exist, artifacts should have required fields"""
        intents_resp = client.get(
            "/api/execution-safety/intents?limit=5",
            headers=auth_headers,
        )
        assert intents_resp.status_code == 200
        intents = intents_resp.json().get("items", [])
        
        if not intents:
            pytest.skip("No intents available for artifacts test")
        
        intent_id = intents[0].get("intent_id")
        response = client.get(
            f"/api/execution-safety/artifacts/{intent_id}",
            headers=auth_headers,
        )
        # May return 400 if correlation spine missing
        assert response.status_code in {200, 400}
        
        if response.status_code == 200:
            data = response.json()
            assert "intent_id" in data


# ============================================================================
# QUARANTINE DETAIL ENDPOINT
# ============================================================================

class TestQuarantineDetail:
    """GET /api/execution-safety/quarantine/{quarantine_id}"""

    def test_quarantine_missing_returns_404(self, client, auth_headers):
        response = client.get(
            "/api/execution-safety/quarantine/nonexistent-quarantine-id",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_quarantine_detail_structure(self, client, auth_headers):
        """If quarantine items exist, detail should have required fields"""
        quarantine_resp = client.get(
            "/api/execution-safety/quarantine?limit=5",
            headers=auth_headers,
        )
        assert quarantine_resp.status_code == 200
        items = quarantine_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items available for detail test")
        
        quarantine_id = items[0].get("quarantine_id")
        response = client.get(
            f"/api/execution-safety/quarantine/{quarantine_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields per contract
        required_fields = [
            "quarantine_id",
            "correlation_id",
            "intent_id",
            "reason",
            "failure_stage",
            "retry_count",
            "first_seen_at",
            "last_seen_at",
            "payload_snapshot",
            "error_snapshot",
            "status",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


# ============================================================================
# BULK RECOVERY ENDPOINTS
# ============================================================================

class TestBulkRetry:
    """POST /api/execution-safety/recovery/bulk-retry"""

    def test_bulk_retry_empty_selection(self, client, auth_headers):
        """Bulk retry with empty selection should return 200 with 0 items"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "reason": "test_bulk_retry",
            "requested_by": "tester",
        }
        response = client.post(
            "/api/execution-safety/recovery/bulk-retry",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "action" in data
        assert data["action"] == "bulk_retry"
        assert "total" in data
        assert "success_count" in data
        assert "failed_count" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_bulk_retry_item_level_results(self, client, auth_headers):
        """Bulk retry should return item-level results with before/after states"""
        # Get existing intents
        intents_resp = client.get(
            "/api/execution-safety/intents?limit=5",
            headers=auth_headers,
        )
        intents = intents_resp.json().get("items", [])
        
        # Filter for retryable states
        retryable_intents = [
            i["intent_id"] for i in intents
            if i.get("state") in {"CREATED", "SUBMITTED", "ACKED", "PARTIALLY_FILLED", "RECONCILING"}
        ]
        
        if not retryable_intents:
            pytest.skip("No retryable intents available")
        
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": retryable_intents[:1],
            "quarantine_ids": [],
            "filters": {},
            "reason": "test_bulk_retry",
            "requested_by": "tester",
        }
        response = client.post(
            "/api/execution-safety/recovery/bulk-retry",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["items"]:
            item = data["items"][0]
            assert "target_type" in item
            assert "target_id" in item
            assert "before_state" in item
            assert "after_state" in item
            assert "result" in item
            assert item["result"] in {"success", "failed"}


class TestBulkCancel:
    """POST /api/execution-safety/recovery/bulk-cancel"""

    def test_bulk_cancel_empty_selection(self, client, auth_headers):
        """Bulk cancel with empty selection should return 200 with 0 items"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "reason": "test_bulk_cancel",
            "requested_by": "tester",
        }
        response = client.post(
            "/api/execution-safety/recovery/bulk-cancel",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["action"] == "bulk_cancel"
        assert "total" in data
        assert "items" in data


class TestBulkReconcile:
    """POST /api/execution-safety/recovery/bulk-reconcile"""

    def test_bulk_reconcile_empty_selection(self, client, auth_headers):
        """Bulk reconcile with empty selection should return 200 with 0 items"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "reason": "test_bulk_reconcile",
            "requested_by": "tester",
        }
        response = client.post(
            "/api/execution-safety/recovery/bulk-reconcile",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["action"] == "bulk_reconcile"
        assert "total" in data
        assert "items" in data


# ============================================================================
# CORRELATION ENFORCEMENT BEHAVIOR
# ============================================================================

class TestCorrelationEnforcement:
    """Test correlation enforcement: critical stages -> quarantine, non-critical -> blocked"""

    def test_canonical_canceled_not_cancelled(self, client, auth_headers):
        """State output should use CANCELED not CANCELLED"""
        response = client.get(
            "/api/execution-safety/intents?limit=50",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check state_counts keys
        state_counts = data.get("state_counts", {})
        assert "CANCELED" in state_counts, "CANCELED should be in state_counts"
        assert "CANCELLED" not in state_counts, "CANCELLED should NOT be in state_counts (use CANCELED)"
        
        # Check individual items
        for item in data.get("items", []):
            state = item.get("state", "")
            assert state != "CANCELLED", "Found CANCELLED state, should be CANCELED"

    def test_gate_blocked_produces_artifact(self, client, auth_headers):
        """When gate is BLOCKED, acceptance should still produce artifact"""
        # Check gate state first
        gate_resp = client.get(
            "/api/execution-safety/gate",
            headers=auth_headers,
        )
        assert gate_resp.status_code == 200
        _ = gate_resp.json()
        
        # Run acceptance
        response = client.post(
            "/api/execution-safety/acceptance/testnet/run?symbol=BTCUSDT&qty=0.001",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # If blocked, should still have artifact
        if data.get("final_verdict") == "BLOCKED":
            assert "artefact_manifest" in data, "BLOCKED verdict should still produce artifact"
            assert data["artefact_manifest"].get("run") is not None


class TestSelectionModes:
    """Test bulk recovery selection modes"""

    def test_by_state_selection(self, client, auth_headers):
        """Selection mode by_state should filter by intent states"""
        payload = {
            "selection_mode": "by_state",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {"states": ["FAILED"]},
            "reason": "test_by_state",
            "requested_by": "tester",
        }
        response = client.post(
            "/api/execution-safety/recovery/bulk-reconcile",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_by_failure_stage_selection(self, client, auth_headers):
        """Selection mode by_failure_stage should filter quarantine by stage"""
        payload = {
            "selection_mode": "by_failure_stage",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {"failure_stages": ["order_submit"]},
            "reason": "test_by_failure_stage",
            "requested_by": "tester",
        }
        response = client.post(
            "/api/execution-safety/recovery/bulk-retry",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200

    def test_by_reason_code_selection(self, client, auth_headers):
        """Selection mode by_reason_code should filter by reason codes"""
        payload = {
            "selection_mode": "by_reason_code",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {"reason_codes": ["correlation_spine_missing"]},
            "reason": "test_by_reason_code",
            "requested_by": "tester",
        }
        response = client.post(
            "/api/execution-safety/recovery/bulk-retry",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200


# ============================================================================
# AUTHORITATIVE PATHS
# ============================================================================

class TestAuthoritativePaths:
    """Test authoritative paths without CANCELLED regression"""

    def test_intents_list_no_cancelled(self, client, auth_headers):
        """Intents list should not contain CANCELLED state"""
        response = client.get(
            "/api/execution-safety/intents?limit=100",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        for item in data.get("items", []):
            assert item.get("state") != "CANCELLED"
            for path_state in item.get("state_path", []):
                assert path_state != "CANCELLED"

    def test_quarantine_list_no_cancelled(self, client, auth_headers):
        """Quarantine list should not contain CANCELLED in failure_stage"""
        response = client.get(
            "/api/execution-safety/quarantine?limit=100",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        for item in data.get("items", []):
            # Check status field
            status = item.get("status", "")
            assert "CANCELLED" not in status.upper() if status else True
