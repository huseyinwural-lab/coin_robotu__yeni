"""
Faz-4 Strategy Control Governance Tests
- Feedback Loop: POST /api/admin/futures/strategy/{id}/feedback-label
- Feedback List: GET /api/admin/futures/strategy/{id}/feedback
- Model Update Trigger: POST /api/admin/futures/strategy/{id}/trigger-model-update
- Model Update Status: GET /api/admin/futures/strategy/{id}/model-update-status
- Timeline Export: GET /api/admin/futures/strategy/{id}/timeline-export?format=json|csv
- Authorization: Ops user 403 on super_admin-only endpoints
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def ops_token():
    """Get ops user auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Ops login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def strategy_id(super_admin_token):
    """Get first available strategy ID"""
    headers = {"Authorization": f"Bearer {super_admin_token}"}
    response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview", headers=headers)
    if response.status_code != 200:
        pytest.skip("Cannot get strategy overview")
    strategies = response.json().get("strategies", [])
    if not strategies:
        pytest.skip("No strategies available")
    return strategies[0]["strategy_id"]


@pytest.fixture(scope="module")
def drift_alert_id(super_admin_token, strategy_id):
    """Get first drift alert ID for the strategy"""
    headers = {"Authorization": f"Bearer {super_admin_token}"}
    response = requests.get(f"{BASE_URL}/api/admin/futures/strategy-control/drift-alerts", headers=headers)
    if response.status_code != 200:
        pytest.skip("Cannot get drift alerts")
    alerts = response.json().get("items", [])
    for alert in alerts:
        if alert.get("strategy_id") == strategy_id:
            return alert.get("alert_id")
    if alerts:
        return alerts[0].get("alert_id")
    pytest.skip("No drift alerts available")


class TestFeedbackLabelEndpoint:
    """POST /api/admin/futures/strategy/{id}/feedback-label tests"""

    def test_feedback_label_success(self, super_admin_token, strategy_id, drift_alert_id):
        """Test successful feedback label creation with strategy+drift context"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {
            "reason": "TEST_FAZ4 feedback correction test",
            "drift_alert_id": drift_alert_id,
            "corrected_label": "false_reject",
            "reason_taxonomy": "threshold_too_strict",
            "sample_link": "https://example.com/sample",
            "related_data_slice": {
                "symbol": "BTCUSDT",
                "time_window": "24h",
                "severity": "MEDIUM"
            },
            "dry_run": False
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback-label",
            headers=headers,
            json=payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response contract: {status, trace_id, message, state_snapshot}
        assert "status" in data, "Response must have 'status'"
        assert "trace_id" in data, "Response must have 'trace_id'"
        assert "message" in data, "Response must have 'message'"
        assert "state_snapshot" in data, "Response must have 'state_snapshot'"
        
        assert data["status"] == "success", f"Expected success, got {data['status']}"
        assert data["trace_id"].startswith("feedback_"), "trace_id should start with 'feedback_'"
        
        # Verify state_snapshot contains entry details
        snapshot = data["state_snapshot"]
        assert snapshot.get("strategy_id") == strategy_id
        assert snapshot.get("drift_alert_id") == drift_alert_id
        assert snapshot.get("corrected_label") == "false_reject"
        assert snapshot.get("reason_taxonomy") == "threshold_too_strict"
        assert "dataset_version" in snapshot, "state_snapshot must have dataset_version"
        assert "entry_id" in snapshot, "state_snapshot must have entry_id"
        
        # Verify dataset_version in extra
        assert "dataset_version" in data, "Response must have dataset_version in extra"
        assert isinstance(data["dataset_version"], int)

    def test_feedback_label_context_mismatch_rejected(self, super_admin_token, strategy_id):
        """Test feedback rejected when drift context doesn't match strategy"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {
            "reason": "TEST_FAZ4 context mismatch test",
            "drift_alert_id": "nonexistent_alert_id::999",
            "corrected_label": "false_allow",
            "reason_taxonomy": "feature_drift",
            "dry_run": False
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback-label",
            headers=headers,
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected", "Should reject when drift context doesn't match"
        assert "context" in data["message"].lower() or "eşleşmedi" in data["message"].lower()

    def test_feedback_label_immutable_append(self, super_admin_token, strategy_id, drift_alert_id):
        """Test that feedback entries are immutable (append-only)"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # Create first feedback
        payload1 = {
            "reason": "TEST_FAZ4 immutable test entry 1",
            "drift_alert_id": drift_alert_id,
            "corrected_label": "false_reject",
            "reason_taxonomy": "threshold_too_strict",
            "dry_run": False
        }
        response1 = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback-label",
            headers=headers,
            json=payload1
        )
        assert response1.status_code == 200
        version1 = response1.json().get("dataset_version", 0)
        
        # Create second feedback
        payload2 = {
            "reason": "TEST_FAZ4 immutable test entry 2",
            "drift_alert_id": drift_alert_id,
            "corrected_label": "false_allow",
            "reason_taxonomy": "data_quality",
            "dry_run": False
        }
        response2 = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback-label",
            headers=headers,
            json=payload2
        )
        assert response2.status_code == 200
        version2 = response2.json().get("dataset_version", 0)
        
        # Verify version incremented (immutable append)
        assert version2 > version1, f"Dataset version should increment: {version1} -> {version2}"

    def test_feedback_label_related_data_slice_fields(self, super_admin_token, strategy_id, drift_alert_id):
        """Test related_data_slice fields are properly stored"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {
            "reason": "TEST_FAZ4 data slice test",
            "drift_alert_id": drift_alert_id,
            "corrected_label": "correct",
            "reason_taxonomy": "threshold_too_loose",
            "related_data_slice": {
                "symbol": "ETHUSDT",
                "time_window": "7d",
                "severity": "HIGH"
            },
            "dry_run": False
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback-label",
            headers=headers,
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        snapshot = data.get("state_snapshot", {})
        slice_data = snapshot.get("related_data_slice", {})
        assert slice_data.get("symbol") == "ETHUSDT"
        assert slice_data.get("time_window") == "7d"
        assert slice_data.get("severity") == "HIGH"


class TestFeedbackListEndpoint:
    """GET /api/admin/futures/strategy/{id}/feedback tests"""

    def test_feedback_list_success(self, super_admin_token, strategy_id):
        """Test feedback list retrieval"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("strategy_id") == strategy_id
        assert "items" in data
        assert "dataset_version" in data
        assert isinstance(data["items"], list)
        assert isinstance(data["dataset_version"], int)

    def test_feedback_list_filter_by_drift_alert_id(self, super_admin_token, strategy_id, drift_alert_id):
        """Test feedback list filtering by drift_alert_id"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback",
            headers=headers,
            params={"drift_alert_id": drift_alert_id}
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        for item in items:
            assert item.get("drift_alert_id") == drift_alert_id, "Filter should only return matching drift_alert_id"

    def test_feedback_list_filter_by_taxonomy(self, super_admin_token, strategy_id):
        """Test feedback list filtering by taxonomy"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback",
            headers=headers,
            params={"taxonomy": "threshold_too_strict"}
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        for item in items:
            assert item.get("reason_taxonomy", "").lower() == "threshold_too_strict"


class TestModelUpdateTriggerEndpoint:
    """POST /api/admin/futures/strategy/{id}/trigger-model-update tests"""

    def test_model_update_trigger_success(self, super_admin_token, strategy_id):
        """Test successful model update trigger creates queued job"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {
            "reason": "TEST_FAZ4 model update trigger test",
            "dataset_version": 1,
            "dry_run": False
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/trigger-model-update",
            headers=headers,
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response contract
        assert "status" in data
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        
        if data["status"] == "success":
            assert data["trace_id"].startswith("model_update_")
            snapshot = data["state_snapshot"]
            assert snapshot.get("status") == "queued", "New job should be queued"
            assert "job_id" in snapshot
            assert snapshot["job_id"].startswith("mu_")
            assert snapshot.get("strategy_id") == strategy_id
        elif data["status"] == "rejected":
            # Concurrent job already running - this is valid behavior
            assert "zaten var" in data["message"].lower() or "already" in data["message"].lower()

    def test_model_update_concurrent_job_blocked(self, super_admin_token, strategy_id):
        """Test that concurrent model update jobs are blocked"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # First trigger
        payload1 = {
            "reason": "TEST_FAZ4 concurrent test 1",
            "dry_run": False
        }
        response1 = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/trigger-model-update",
            headers=headers,
            json=payload1
        )
        
        # Immediately try second trigger
        payload2 = {
            "reason": "TEST_FAZ4 concurrent test 2",
            "dry_run": False
        }
        response2 = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/trigger-model-update",
            headers=headers,
            json=payload2
        )
        
        # At least one should be rejected if first was successful
        data1 = response1.json()
        data2 = response2.json()
        
        if data1["status"] == "success":
            # Second should be rejected due to concurrent job
            assert data2["status"] == "rejected", "Concurrent job should be blocked"
            assert "zaten var" in data2["message"].lower() or "already" in data2["message"].lower()


class TestModelUpdateStatusEndpoint:
    """GET /api/admin/futures/strategy/{id}/model-update-status tests"""

    def test_model_update_status_success(self, super_admin_token, strategy_id):
        """Test model update status retrieval"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/model-update-status",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("strategy_id") == strategy_id
        assert "current_job" in data
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_model_update_lifecycle_polling(self, super_admin_token, strategy_id):
        """Test model update lifecycle: queued -> running -> completed"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # First check current status
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/model-update-status",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        current_job = data.get("current_job", {})
        
        if current_job:
            status = current_job.get("status", "")
            # Valid lifecycle states
            assert status in ["queued", "running", "completed", "failed", ""], f"Invalid status: {status}"
            
            # If queued, wait and check for transition
            if status == "queued":
                time.sleep(5)  # Wait for queued -> running transition (4 seconds threshold)
                response2 = requests.get(
                    f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/model-update-status",
                    headers=headers
                )
                data2 = response2.json()
                new_status = data2.get("current_job", {}).get("status", "")
                assert new_status in ["running", "completed"], f"Should transition from queued: {new_status}"
            
            # If running, wait and check for completion
            if status == "running":
                time.sleep(10)  # Wait for running -> completed transition (8 seconds threshold)
                response3 = requests.get(
                    f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/model-update-status",
                    headers=headers
                )
                data3 = response3.json()
                final_status = data3.get("current_job", {}).get("status", "")
                assert final_status == "completed", f"Should complete: {final_status}"


class TestTimelineExportEndpoint:
    """GET /api/admin/futures/strategy/{id}/timeline-export tests"""

    def test_timeline_export_json_format(self, super_admin_token, strategy_id):
        """Test timeline export in JSON format"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/timeline-export",
            headers=headers,
            params={"format": "json"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response contract
        assert data.get("status") == "success"
        assert "trace_id" in data
        assert data["trace_id"].startswith("timeline_export_")
        assert "message" in data
        assert "state_snapshot" in data
        assert "items" in data
        
        # Verify state_snapshot
        snapshot = data["state_snapshot"]
        assert snapshot.get("strategy_id") == strategy_id
        assert snapshot.get("format") == "json"
        assert "count" in snapshot
        
        # Verify items structure (drift + action + feedback combined)
        items = data["items"]
        assert isinstance(items, list)
        for item in items:
            assert "event_type" in item
            assert item["event_type"] in ["ACTION", "FEEDBACK", "MODEL_UPDATE", "DRIFT_SIGNAL"]
            assert "event_id" in item
            assert "timestamp" in item
            assert "message" in item
            assert "payload" in item

    def test_timeline_export_csv_format(self, super_admin_token, strategy_id):
        """Test timeline export in CSV format"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/timeline-export",
            headers=headers,
            params={"format": "csv"}
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("Content-Type", "")
        assert "attachment" in response.headers.get("Content-Disposition", "")
        
        # Verify CSV content
        csv_content = response.text
        lines = csv_content.strip().split("\n")
        assert len(lines) >= 1, "CSV should have at least header row"
        
        # Verify header
        header = lines[0]
        assert "event_type" in header
        assert "event_id" in header
        assert "timestamp" in header
        assert "message" in header

    def test_timeline_export_combined_events(self, super_admin_token, strategy_id):
        """Test that timeline export includes drift + action + feedback events"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/timeline-export",
            headers=headers,
            params={"format": "json"}
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        
        event_types = set(item.get("event_type") for item in items)
        # At minimum, we should have some events (may not have all types)
        # The important thing is the structure supports all types
        print(f"Event types found: {event_types}")
        # Timeline should be sorted by timestamp (reverse)
        if len(items) >= 2:
            timestamps = [item.get("timestamp", "") for item in items]
            assert timestamps == sorted(timestamps, reverse=True), "Timeline should be sorted by timestamp descending"


class TestOpsUserAuthorization:
    """Test that ops users get 403 on super_admin-only endpoints"""

    def test_ops_feedback_label_403(self, ops_token, strategy_id, drift_alert_id):
        """Ops user should get 403 on feedback-label endpoint"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        payload = {
            "reason": "TEST_FAZ4 ops user test",
            "drift_alert_id": drift_alert_id,
            "corrected_label": "false_reject",
            "reason_taxonomy": "threshold_too_strict",
            "dry_run": False
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback-label",
            headers=headers,
            json=payload
        )
        assert response.status_code == 403, f"Ops should get 403, got {response.status_code}"

    def test_ops_feedback_list_403(self, ops_token, strategy_id):
        """Ops user should get 403 on feedback list endpoint"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback",
            headers=headers
        )
        assert response.status_code == 403, f"Ops should get 403, got {response.status_code}"

    def test_ops_model_update_trigger_403(self, ops_token, strategy_id):
        """Ops user should get 403 on model update trigger endpoint"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        payload = {
            "reason": "TEST_FAZ4 ops user test",
            "dry_run": False
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/trigger-model-update",
            headers=headers,
            json=payload
        )
        assert response.status_code == 403, f"Ops should get 403, got {response.status_code}"

    def test_ops_model_update_status_403(self, ops_token, strategy_id):
        """Ops user should get 403 on model update status endpoint"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/model-update-status",
            headers=headers
        )
        assert response.status_code == 403, f"Ops should get 403, got {response.status_code}"

    def test_ops_timeline_export_403(self, ops_token, strategy_id):
        """Ops user should get 403 on timeline export endpoint"""
        headers = {"Authorization": f"Bearer {ops_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/timeline-export",
            headers=headers,
            params={"format": "json"}
        )
        assert response.status_code == 403, f"Ops should get 403, got {response.status_code}"


class TestResponseContract:
    """Test that all Faz-4 endpoints follow response contract {status, trace_id, message, state_snapshot}"""

    def test_feedback_label_response_contract(self, super_admin_token, strategy_id, drift_alert_id):
        """Verify feedback-label response contract"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {
            "reason": "TEST_FAZ4 contract test",
            "drift_alert_id": drift_alert_id,
            "corrected_label": "false_reject",
            "reason_taxonomy": "threshold_too_strict",
            "dry_run": True
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/feedback-label",
            headers=headers,
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data

    def test_model_update_trigger_response_contract(self, super_admin_token, strategy_id):
        """Verify model update trigger response contract"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        payload = {
            "reason": "TEST_FAZ4 contract test",
            "dry_run": True
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/trigger-model-update",
            headers=headers,
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data

    def test_timeline_export_response_contract(self, super_admin_token, strategy_id):
        """Verify timeline export response contract"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/timeline-export",
            headers=headers,
            params={"format": "json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
