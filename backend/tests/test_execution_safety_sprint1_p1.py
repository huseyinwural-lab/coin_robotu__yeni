"""
Execution Safety Sprint-1 P1 Tests
Tests for:
- GET /api/execution-safety/gate/explain contract
- POST bulk recovery endpoints (bulk-retry, bulk-cancel, bulk-reconcile, bulk-force-reconcile, bulk-move-to-quarantine, bulk-release-from-quarantine)
- GET /api/execution-safety/quarantine/{quarantine_id} detail fields
- POST /api/execution-safety/quarantine/{quarantine_id}/{action} actions
- GET /api/execution-safety/quarantine list summary and per-item fields
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def auth_session():
    """Authenticate and return session with token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if login_resp.status_code != 200:
        pytest.skip(f"Login failed: {login_resp.status_code} - {login_resp.text}")
    
    # Extract token and set Authorization header
    data = login_resp.json()
    token = data.get("access_token") or data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestGateExplainContract:
    """GET /api/execution-safety/gate/explain contract tests"""

    def test_gate_explain_returns_required_fields(self, auth_session):
        """Verify gate/explain returns score, state, confidence_band, components, blockers, override_reason"""
        resp = auth_session.get(f"{BASE_URL}/api/execution-safety/gate/explain")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Required fields per contract
        assert "score" in data, "Missing 'score' field"
        assert "state" in data, "Missing 'state' field"
        assert "confidence_band" in data, "Missing 'confidence_band' field"
        assert "components" in data, "Missing 'components' field"
        assert "blockers" in data, "Missing 'blockers' field"
        assert "override_reason" in data, "Missing 'override_reason' field"
        
        # Validate types
        assert isinstance(data["score"], (int, float)), "score should be numeric"
        assert isinstance(data["state"], str), "state should be string"
        assert data["confidence_band"] in ["HIGH", "MEDIUM", "LOW"], f"confidence_band should be HIGH/MEDIUM/LOW, got {data['confidence_band']}"
        assert isinstance(data["components"], list), "components should be list"
        assert isinstance(data["blockers"], list), "blockers should be list"
        assert isinstance(data["override_reason"], str), "override_reason should be string"
        
        print(f"Gate explain: score={data['score']}, state={data['state']}, confidence_band={data['confidence_band']}")
        print(f"Components count: {len(data['components'])}, Blockers: {data['blockers']}")

    def test_gate_explain_components_structure(self, auth_session):
        """Verify components have name, weight, score fields"""
        resp = auth_session.get(f"{BASE_URL}/api/execution-safety/gate/explain")
        assert resp.status_code == 200
        data = resp.json()
        
        components = data.get("components", [])
        for comp in components:
            assert "name" in comp, f"Component missing 'name': {comp}"
            assert "weight" in comp, f"Component missing 'weight': {comp}"
            assert "score" in comp, f"Component missing 'score': {comp}"
            assert isinstance(comp["weight"], (int, float)), f"weight should be numeric: {comp}"
            assert isinstance(comp["score"], (int, float)), f"score should be numeric: {comp}"
        
        print(f"Components validated: {[c['name'] for c in components]}")


class TestQuarantineListContract:
    """GET /api/execution-safety/quarantine list tests"""

    def test_quarantine_list_returns_summary(self, auth_session):
        """Verify quarantine list includes summary with by_status and by_failure_stage"""
        resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=50")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "total" in data, "Missing 'total' field"
        assert "summary" in data, "Missing 'summary' field"
        assert "items" in data, "Missing 'items' field"
        
        summary = data.get("summary", {})
        assert "by_status" in summary, "summary missing 'by_status'"
        assert "by_failure_stage" in summary, "summary missing 'by_failure_stage'"
        
        print(f"Quarantine list: total={data['total']}, by_status={summary.get('by_status')}")

    def test_quarantine_list_item_fields(self, auth_session):
        """Verify each quarantine item has required fields"""
        resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=50")
        assert resp.status_code == 200
        data = resp.json()
        
        items = data.get("items", [])
        required_fields = [
            "quarantine_id", "correlation_id", "reason", "failure_stage",
            "retry_count", "max_retry", "first_seen_at", "last_seen_at",
            "payload_snapshot", "error_snapshot", "status", "entity_type", "event_type"
        ]
        
        for item in items[:5]:  # Check first 5 items
            for field in required_fields:
                assert field in item, f"Item missing '{field}': {item.get('quarantine_id', 'unknown')}"
            
            # Validate error_snapshot structure
            error_snapshot = item.get("error_snapshot", {})
            assert "error_message" in error_snapshot or error_snapshot == {}, f"error_snapshot should have error_message"
        
        print(f"Validated {len(items)} quarantine items with required fields")


class TestQuarantineDetailContract:
    """GET /api/execution-safety/quarantine/{quarantine_id} detail tests"""

    def test_quarantine_detail_returns_404_for_missing(self, auth_session):
        """Verify 404 for non-existent quarantine_id"""
        resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine/nonexistent-id-12345")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"

    def test_quarantine_detail_includes_resolution_history(self, auth_session):
        """Verify detail includes resolution_history field"""
        # First get list to find a quarantine_id
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        assert list_resp.status_code == 200
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items to test detail")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "resolution_history" in data, "Missing 'resolution_history' field"
        assert isinstance(data["resolution_history"], list), "resolution_history should be list"
        print(f"Quarantine {quarantine_id} has {len(data['resolution_history'])} resolution history entries")

    def test_quarantine_detail_includes_correlation_chain_link(self, auth_session):
        """Verify detail includes correlation_chain_link field"""
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        assert list_resp.status_code == 200
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items to test detail")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "correlation_chain_link" in data, "Missing 'correlation_chain_link' field"
        chain = data.get("correlation_chain_link", {})
        # Should have links to related resources
        assert "quarantine_detail" in chain, "correlation_chain_link missing 'quarantine_detail'"
        print(f"Correlation chain link: {chain}")

    def test_quarantine_detail_includes_failure_timeline(self, auth_session):
        """Verify detail includes failure_timeline field"""
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        assert list_resp.status_code == 200
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items to test detail")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "failure_timeline" in data, "Missing 'failure_timeline' field"
        assert isinstance(data["failure_timeline"], list), "failure_timeline should be list"
        
        # Each timeline entry should have type, at, status
        for entry in data.get("failure_timeline", [])[:3]:
            assert "type" in entry, f"Timeline entry missing 'type': {entry}"
            assert "at" in entry, f"Timeline entry missing 'at': {entry}"
        
        print(f"Failure timeline has {len(data['failure_timeline'])} entries")


class TestQuarantineActions:
    """POST /api/execution-safety/quarantine/{quarantine_id}/{action} tests"""

    def test_quarantine_action_replay(self, auth_session):
        """Test replay action on quarantine item"""
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        assert list_resp.status_code == 200
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items to test action")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.post(
            f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}/replay",
            json={"note": "test replay action"}
        )
        # Should succeed or return appropriate error
        assert resp.status_code in [200, 400], f"Unexpected status: {resp.status_code}: {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert "requested_action" in data, "Missing 'requested_action' in response"
            print(f"Replay action result: {data.get('requested_action')}, status: {data.get('status')}")

    def test_quarantine_action_reprocess(self, auth_session):
        """Test reprocess action (alias for replay)"""
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.post(
            f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}/reprocess",
            json={}
        )
        assert resp.status_code in [200, 400], f"Unexpected: {resp.status_code}"
        print(f"Reprocess action status: {resp.status_code}")

    def test_quarantine_action_mark_resolved(self, auth_session):
        """Test mark_resolved action"""
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.post(
            f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}/mark_resolved",
            json={"note": "resolved via test"}
        )
        assert resp.status_code in [200, 400], f"Unexpected: {resp.status_code}"
        print(f"Mark resolved action status: {resp.status_code}")

    def test_quarantine_action_escalate(self, auth_session):
        """Test escalate action"""
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.post(
            f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}/escalate",
            json={"note": "escalated for review"}
        )
        assert resp.status_code in [200, 400], f"Unexpected: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("status") == "escalated" or "status" in data
        print(f"Escalate action status: {resp.status_code}")

    def test_quarantine_action_attach_note(self, auth_session):
        """Test attach_note action"""
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.post(
            f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}/attach_note",
            json={"note": "test note attachment"}
        )
        assert resp.status_code in [200, 400], f"Unexpected: {resp.status_code}"
        print(f"Attach note action status: {resp.status_code}")

    def test_quarantine_action_invalid_returns_400(self, auth_session):
        """Test invalid action returns 400"""
        list_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/quarantine?limit=10")
        items = list_resp.json().get("items", [])
        
        if not items:
            pytest.skip("No quarantine items")
        
        quarantine_id = items[0].get("quarantine_id")
        resp = auth_session.post(
            f"{BASE_URL}/api/execution-safety/quarantine/{quarantine_id}/invalid_action_xyz",
            json={}
        )
        assert resp.status_code == 400, f"Expected 400 for invalid action, got {resp.status_code}"


class TestBulkRecoveryEndpoints:
    """POST bulk recovery endpoint tests"""

    def test_bulk_retry_returns_item_level_output(self, auth_session):
        """POST /api/execution-safety/recovery/bulk-retry returns item-level results"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "limit": 10,
            "reason": "test bulk retry"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-retry", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Required fields
        assert "action" in data, "Missing 'action' field"
        assert data["action"] == "bulk_retry", f"Expected action=bulk_retry, got {data['action']}"
        assert "total" in data, "Missing 'total' field"
        assert "success_count" in data, "Missing 'success_count' field"
        assert "failed_count" in data, "Missing 'failed_count' field"
        assert "items" in data or "results" in data, "Missing 'items' or 'results' field"
        
        items = data.get("items") or data.get("results", [])
        for item in items[:3]:
            assert "target_type" in item, f"Item missing 'target_type'"
            assert "target_id" in item, f"Item missing 'target_id'"
            assert "result" in item, f"Item missing 'result'"
        
        print(f"Bulk retry: total={data['total']}, success={data['success_count']}, failed={data['failed_count']}")

    def test_bulk_cancel_returns_item_level_output(self, auth_session):
        """POST /api/execution-safety/recovery/bulk-cancel returns item-level results"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "limit": 10,
            "reason": "test bulk cancel"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-cancel", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data["action"] == "bulk_cancel"
        assert "total" in data
        assert "success_count" in data
        assert "failed_count" in data
        print(f"Bulk cancel: total={data['total']}, success={data['success_count']}")

    def test_bulk_reconcile_returns_item_level_output(self, auth_session):
        """POST /api/execution-safety/recovery/bulk-reconcile returns item-level results"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "limit": 10,
            "reason": "test bulk reconcile"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-reconcile", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data["action"] == "bulk_reconcile"
        assert "total" in data
        assert "success_count" in data
        assert "failed_count" in data
        print(f"Bulk reconcile: total={data['total']}, success={data['success_count']}")

    def test_bulk_force_reconcile_endpoint(self, auth_session):
        """POST /api/execution-safety/recovery/bulk-force-reconcile"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "limit": 10,
            "reason": "test bulk force reconcile"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-force-reconcile", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data["action"] == "bulk_force_reconcile"
        assert "total" in data
        print(f"Bulk force reconcile: total={data['total']}")

    def test_bulk_move_to_quarantine_endpoint(self, auth_session):
        """POST /api/execution-safety/recovery/bulk-move-to-quarantine"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "limit": 10,
            "reason": "test bulk move to quarantine"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-move-to-quarantine", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data["action"] == "bulk_move_to_quarantine"
        assert "total" in data
        print(f"Bulk move to quarantine: total={data['total']}")

    def test_bulk_release_from_quarantine_endpoint(self, auth_session):
        """POST /api/execution-safety/recovery/bulk-release-from-quarantine"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "limit": 10,
            "reason": "test bulk release from quarantine"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-release-from-quarantine", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data["action"] == "bulk_release_from_quarantine"
        assert "total" in data
        print(f"Bulk release from quarantine: total={data['total']}")

    def test_bulk_retry_with_filter_selection_mode(self, auth_session):
        """Test bulk-retry with by_filter selection mode"""
        payload = {
            "selection_mode": "by_filter",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {
                "states": ["FAILED"],
                "age_minutes": 60
            },
            "limit": 5,
            "reason": "test filter mode"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-retry", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        
        assert "selection_mode" in data
        print(f"Filter mode bulk retry: selection_mode={data.get('selection_mode')}, total={data['total']}")

    def test_bulk_item_level_fields(self, auth_session):
        """Verify item-level output has before_state, after_state, attempted_action"""
        # First create some test data by getting intents
        intents_resp = auth_session.get(f"{BASE_URL}/api/execution-safety/intents?limit=5")
        if intents_resp.status_code != 200:
            pytest.skip("Cannot get intents")
        
        intents = intents_resp.json().get("items", [])
        intent_ids = [i.get("intent_id") for i in intents if i.get("intent_id")][:2]
        
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": intent_ids,
            "quarantine_ids": [],
            "filters": {},
            "limit": 10,
            "reason": "test item fields"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-reconcile", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        
        items = data.get("items") or data.get("results", [])
        for item in items:
            # Check item-level fields exist
            assert "before_state" in item or item.get("result") == "skipped", f"Missing before_state: {item}"
            assert "attempted_action" in item, f"Missing attempted_action: {item}"
            assert "result" in item, f"Missing result: {item}"
        
        print(f"Item-level fields validated for {len(items)} items")


class TestSkippedCountField:
    """Verify skipped_count is returned in bulk operations"""

    def test_bulk_retry_has_skipped_count(self, auth_session):
        """Verify bulk-retry returns skipped_count"""
        payload = {
            "selection_mode": "explicit_ids",
            "intent_ids": [],
            "quarantine_ids": [],
            "filters": {},
            "limit": 10,
            "reason": "test skipped count"
        }
        resp = auth_session.post(f"{BASE_URL}/api/execution-safety/recovery/bulk-retry", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        
        assert "skipped_count" in data, "Missing 'skipped_count' field"
        print(f"Skipped count: {data['skipped_count']}")
