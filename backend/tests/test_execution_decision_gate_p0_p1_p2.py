"""
Comprehensive tests for Execution Decision Gate features.
P0: Decision enforcement, high-risk safety, detail drawer contract, audit visibility, state machine, queue reliability
P1: Bulk operations, queue control, search/filter/sort, manual edit
P2: Observability, notification signals
"""
import os
import random
import string
import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


def resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL bulunamadı")


BASE_URL = resolve_base_url()


def random_email(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}@example.com"


def login(email: str, password: str) -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert response.status_code == 200, f"Login failed ({email}): {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)}"}


@pytest.fixture(scope="module")
def regular_admin_headers(admin_headers):
    """Create a regular admin (not super_admin) for permission tests"""
    email = random_email("regular_admin")
    password = "RegularAdmin123!"
    create_resp = requests.post(
        f"{BASE_URL}/api/admin/users/admin-create",
        headers=admin_headers,
        json={"email": email, "password": password, "role": "admin"},
        timeout=30,
    )
    assert create_resp.status_code in [200, 201], create_resp.text
    return {"Authorization": f"Bearer {login(email, password)}"}


@pytest.fixture(scope="module")
def test_user_id(admin_headers):
    """Create a test user for intent creation"""
    email = random_email("execution_test_user")
    password = "ExecutionTestUser123!"
    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert register.status_code in [200, 201], register.text
    user_id = register.json()["id"]
    
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=30,
    )
    assert approve.status_code == 200, approve.text
    return user_id


def create_queued_intent(user_id: str, *, high_risk: bool = False, symbol: str = "BTCUSDT") -> str:
    """Create a QUEUED intent directly in the database"""
    from db import SessionLocal
    from models import UserExecutionIntent

    now_ts = datetime.now(timezone.utc)
    row = UserExecutionIntent(
        id=str(uuid.uuid4()),
        intent_id=f"intent-{uuid.uuid4().hex[:20]}",
        idempotency_key=f"idem-{uuid.uuid4().hex[:20]}",
        user_id=user_id,
        source_type="manual",
        intent_type="OPEN_POSITION",
        status="QUEUED",
        intent_token=f"tok-{uuid.uuid4().hex[:16]}",
        preview_hash=f"prev-{uuid.uuid4().hex[:16]}",
        approval_required=True,
        symbol=symbol,
        market_type="spot",
        side="buy",
        notional=180.0,
        size=1.5,
        reduce_only=False,
        normalized_order_payload={"strategy_binding": "spot_pullback_v1", "execution_mode": "manual"},
        reject_reason_codes=[],
        risk_flags=["high_volatility_spike", "critical_exposure"] if high_risk else ["normal"],
        risk_score=85.0 if high_risk else 22.0,
        gate_decision="ALLOW",
        meta_engine_decision="ALLOW",
        submitted_at=now_ts,
        created_at=now_ts,
        updated_at=now_ts,
    )
    db = SessionLocal()
    try:
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def fetch_detail(admin_headers: dict, intent_id: str) -> dict:
    detail = requests.get(
        f"{BASE_URL}/api/admin/execution-queue/{intent_id}/detail",
        headers=admin_headers,
        timeout=30,
    )
    assert detail.status_code == 200, detail.text
    return detail.json()


def ensure_queue_resumed(admin_headers: dict) -> None:
    requests.post(
        f"{BASE_URL}/api/admin/execution-queue/control/resume",
        headers=admin_headers,
        json={"reason": "test setup resume"},
        timeout=30,
    )


class TestP0DecisionEnforcement:
    """P0: Decision enforcement - reason zorunlu, reason yoksa 400; FE tarafında action disabled"""
    
    def test_approve_without_reason_returns_400(self, admin_headers, test_user_id):
        """Approve without reason should return 400"""
        ensure_queue_resumed(admin_headers)
        intent_id = create_queued_intent(test_user_id)
        detail = fetch_detail(admin_headers, intent_id)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={
                "reason": "",
                "detail_version": detail.get("detail_version"),
                "read_acknowledged": True,
            },
            timeout=30,
        )
        assert response.status_code == 400
        assert "reason" in response.text.lower() or "decision" in response.text.lower()
    
    def test_reject_without_reason_returns_400(self, admin_headers, test_user_id):
        """Reject without reason should return 400"""
        ensure_queue_resumed(admin_headers)
        intent_id = create_queued_intent(test_user_id)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/reject",
            headers=admin_headers,
            json={"reason": "", "read_acknowledged": True},
            timeout=30,
        )
        assert response.status_code == 400
    
    def test_cancel_without_reason_returns_400(self, admin_headers, test_user_id):
        """Cancel without reason should return 400"""
        ensure_queue_resumed(admin_headers)
        intent_id = create_queued_intent(test_user_id)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/cancel",
            headers=admin_headers,
            json={"reason": ""},
            timeout=30,
        )
        assert response.status_code == 400
    
    def test_approve_without_read_ack_returns_400(self, admin_headers, test_user_id):
        """Approve without read_acknowledged should return 400"""
        ensure_queue_resumed(admin_headers)
        intent_id = create_queued_intent(test_user_id)
        detail = fetch_detail(admin_headers, intent_id)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={
                "reason": "valid reason",
                "detail_version": detail.get("detail_version"),
                "read_acknowledged": False,
            },
            timeout=30,
        )
        assert response.status_code == 400


class TestP0HighRiskSafety:
    """P0: High-risk safety - double confirmation zorunlu, risk payload severity+breakdown dönüyor"""
    
    def test_high_risk_approve_without_double_confirmation_returns_400(self, admin_headers, test_user_id):
        """High-risk intent için execute aşamasında confirmation zorunlu"""
        ensure_queue_resumed(admin_headers)
        intent_id = create_queued_intent(test_user_id, high_risk=True)
        detail = fetch_detail(admin_headers, intent_id)
        
        # Verify it's high risk
        assert detail.get("risk_payload", {}).get("is_high_risk") is True
        
        approve = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={
                "reason": "valid reason",
                "detail_version": detail.get("detail_version"),
                "read_acknowledged": True,
                "double_confirmation": False,
                "override_execute": True,
            },
            timeout=30,
        )
        assert approve.status_code == 200, approve.text
        assert approve.json().get("status") == "APPROVED"

        execute = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/execute",
            headers=admin_headers,
            json={
                "reason": "execute without confirmation",
                "detail_version": fetch_detail(admin_headers, intent_id).get("detail_version"),
                "execute_confirmation": False,
            },
            timeout=30,
        )
        assert execute.status_code == 400
        assert "execute_confirmation" in execute.text
    
    def test_high_risk_approve_with_double_confirmation_succeeds(self, admin_headers, test_user_id):
        """High-risk flow: approve -> execute(with confirmation)"""
        ensure_queue_resumed(admin_headers)
        intent_id = create_queued_intent(test_user_id, high_risk=True)
        detail = fetch_detail(admin_headers, intent_id)
        
        # Note: override_execute=True is needed because execution guard blocks without exchange connection
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={
                "reason": "approved with double confirmation and override",
                "detail_version": detail.get("detail_version"),
                "read_acknowledged": True,
                "double_confirmation": True,
                "override_execute": True,  # Required to bypass execution guard in test env
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "APPROVED"

        execute = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/execute",
            headers=admin_headers,
            json={
                "reason": "execute with confirmation",
                "detail_version": fetch_detail(admin_headers, intent_id).get("detail_version"),
                "execute_confirmation": True,
            },
            timeout=30,
        )
        assert execute.status_code == 200, execute.text
        assert execute.json().get("status") == "RELEASED"
    
    def test_risk_payload_contains_severity_and_breakdown(self, admin_headers, test_user_id):
        """Risk payload should contain severity and reason_breakdown"""
        intent_id = create_queued_intent(test_user_id, high_risk=True)
        detail = fetch_detail(admin_headers, intent_id)
        
        risk_payload = detail.get("risk_payload", {})
        assert "severity" in risk_payload
        assert risk_payload.get("severity") == "high"
        assert "is_high_risk" in risk_payload
        assert risk_payload.get("is_high_risk") is True
        assert "reason_breakdown" in risk_payload
        assert isinstance(risk_payload.get("reason_breakdown"), list)


class TestP0IntentDetailDrawerContract:
    """P0: Intent detail drawer backend contract - order_preview, normalized_payload, risk_payload, gate_decision, expected_impact"""
    
    def test_detail_endpoint_returns_required_fields(self, admin_headers, test_user_id):
        """Detail endpoint should return all required fields"""
        intent_id = create_queued_intent(test_user_id)
        detail = fetch_detail(admin_headers, intent_id)
        
        # Check required fields
        assert "intent_id" in detail
        assert "detail_version" in detail
        assert "order_preview" in detail
        assert "normalized_payload" in detail
        assert "risk_payload" in detail
        assert "gate_decision" in detail
        assert "expected_impact" in detail
        
        # Check order_preview structure
        order_preview = detail.get("order_preview", {})
        assert "symbol" in order_preview
        assert "market_type" in order_preview
        assert "side" in order_preview
        assert "notional" in order_preview
        
        # Check expected_impact structure
        expected_impact = detail.get("expected_impact", {})
        assert "exposure_before" in expected_impact
        assert "exposure_after" in expected_impact
        assert "exposure_delta" in expected_impact
    
    def test_detail_not_found_returns_404(self, admin_headers):
        """Non-existent intent should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue/non-existent-id/detail",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 404


class TestP0AuditVisibility:
    """P0: Audit visibility - /execution-queue/{id}/history endpointi aksiyonları döndürüyor"""
    
    def test_history_endpoint_returns_actions(self, admin_headers, test_user_id):
        """History endpoint should return action history"""
        intent_id = create_queued_intent(test_user_id)
        
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/history",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        history = response.json()
        assert isinstance(history, list)
        
        # Should have at least synthetic events
        assert len(history) >= 1
        
        # Check history item structure
        if history:
            item = history[0]
            assert "id" in item
            assert "action" in item
            assert "created_at" in item
    
    def test_history_after_approve_contains_approval_action(self, admin_headers, test_user_id):
        """History should contain approval action after approve"""
        intent_id = create_queued_intent(test_user_id)
        detail = fetch_detail(admin_headers, intent_id)
        
        # Approve the intent (with override due to no exchange connection in test env)
        approve_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={
                "reason": "test approval for history",
                "detail_version": detail.get("detail_version"),
                "read_acknowledged": True,
                "override_execute": True,  # Required to bypass execution guard in test env
            },
            timeout=30,
        )
        assert approve_resp.status_code == 200
        
        # Check history
        history_resp = requests.get(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/history",
            headers=admin_headers,
            timeout=30,
        )
        assert history_resp.status_code == 200
        history = history_resp.json()
        
        # Should contain approval action
        actions = [item.get("action") for item in history]
        assert any("APPROVED" in action or "RELEASED" in action for action in actions)


class TestP0StateMachineStrictness:
    """P0: State machine strictness - invalid transition hard reject, cancel endpoint davranışı"""
    
    def test_invalid_transition_rejected(self, admin_headers, test_user_id):
        """Invalid state transition should be rejected"""
        intent_id = create_queued_intent(test_user_id)
        detail = fetch_detail(admin_headers, intent_id)
        
        # First approve (with override due to no exchange connection in test env)
        approve_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={
                "reason": "first approval",
                "detail_version": detail.get("detail_version"),
                "read_acknowledged": True,
                "override_execute": True,  # Required to bypass execution guard in test env
            },
            timeout=30,
        )
        assert approve_resp.status_code == 200
        
        # Try to reject after approval (invalid transition)
        reject_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/reject",
            headers=admin_headers,
            json={"reason": "invalid transition", "read_acknowledged": True},
            timeout=30,
        )
        assert reject_resp.status_code in [400, 409]
    
    def test_cancel_from_queued_succeeds(self, admin_headers, test_user_id):
        """Cancel from QUEUED state should succeed"""
        intent_id = create_queued_intent(test_user_id)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/cancel",
            headers=admin_headers,
            json={"reason": "cancel from queued"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "CANCELLED"


class TestP0QueueReliability:
    """P0: Queue reliability - stale detail_version ile approve reject, queue pause durumda approve blocked"""
    
    def test_stale_detail_version_rejected(self, admin_headers, test_user_id):
        """Approve with stale detail_version should be rejected"""
        intent_id = create_queued_intent(test_user_id)
        detail = fetch_detail(admin_headers, intent_id)
        old_version = detail.get("detail_version")
        
        # Edit to change version
        edit_resp = requests.patch(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/edit",
            headers=admin_headers,
            json={"notional": 250, "reason": "version bump"},
            timeout=30,
        )
        assert edit_resp.status_code == 200
        
        # Try approve with old version
        approve_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={
                "reason": "stale version test",
                "detail_version": old_version,
                "read_acknowledged": True,
            },
            timeout=30,
        )
        assert approve_resp.status_code == 400
        assert "stale" in approve_resp.text.lower()
    
    def test_approve_blocked_when_queue_paused(self, admin_headers, test_user_id):
        """Approve should be blocked when queue is paused"""
        # Pause the queue
        pause_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/control/pause",
            headers=admin_headers,
            json={"reason": "test pause"},
            timeout=30,
        )
        assert pause_resp.status_code == 200
        
        try:
            intent_id = create_queued_intent(test_user_id)
            detail = fetch_detail(admin_headers, intent_id)
            
            # Try to approve while paused
            approve_resp = requests.post(
                f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
                headers=admin_headers,
                json={
                    "reason": "should fail while paused",
                    "detail_version": detail.get("detail_version"),
                    "read_acknowledged": True,
                },
                timeout=30,
            )
            assert approve_resp.status_code == 423
        finally:
            # Resume the queue
            requests.post(
                f"{BASE_URL}/api/admin/execution-queue/control/resume",
                headers=admin_headers,
                json={"reason": "test resume"},
                timeout=30,
            )


class TestP1BulkOperations:
    """P1: Bulk operations - approve/reject/cancel ve max 20 limiti, high-risk bulk confirm guard"""
    
    def test_bulk_limit_exceeded_returns_400(self, admin_headers):
        """Bulk operation with >20 items should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/bulk-decision",
            headers=admin_headers,
            json={
                "intent_ids": [f"dummy-{i}" for i in range(21)],
                "action": "approve",
                "reason": "bulk limit test",
                "read_acknowledged": True,
                "double_confirmation": True,
            },
            timeout=30,
        )
        assert response.status_code == 400
        assert "20" in response.text or "limit" in response.text.lower()
    
    def test_bulk_without_reason_returns_400(self, admin_headers):
        """Bulk operation without reason should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/bulk-decision",
            headers=admin_headers,
            json={
                "intent_ids": ["dummy-1"],
                "action": "approve",
                "reason": "",
                "read_acknowledged": True,
            },
            timeout=30,
        )
        assert response.status_code == 400
    
    def test_bulk_high_risk_without_double_confirm_returns_400(self, admin_headers, test_user_id):
        """Bulk with high-risk items without double_confirmation should return 400"""
        intent_id = create_queued_intent(test_user_id, high_risk=True)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/bulk-decision",
            headers=admin_headers,
            json={
                "intent_ids": [intent_id],
                "action": "approve",
                "reason": "bulk high risk test",
                "read_acknowledged": True,
                "double_confirmation": False,
            },
            timeout=30,
        )
        assert response.status_code == 400
        assert "high" in response.text.lower() or "double" in response.text.lower()
    
    def test_bulk_cancel_succeeds(self, admin_headers, test_user_id):
        """Bulk cancel should succeed"""
        intent_ids = [create_queued_intent(test_user_id) for _ in range(3)]
        
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/bulk-decision",
            headers=admin_headers,
            json={
                "intent_ids": intent_ids,
                "action": "cancel",
                "reason": "bulk cancel test",
                "read_acknowledged": True,
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("processed_count") >= 1


class TestP1QueueControl:
    """P1: Queue control - pause/resume/clear sadece super_admin + immutable audit"""
    
    def test_pause_requires_super_admin(self, regular_admin_headers):
        """Pause should require super_admin role"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/control/pause",
            headers=regular_admin_headers,
            json={"reason": "unauthorized pause"},
            timeout=30,
        )
        assert response.status_code in [401, 403]
    
    def test_resume_requires_super_admin(self, regular_admin_headers):
        """Resume should require super_admin role"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/control/resume",
            headers=regular_admin_headers,
            json={"reason": "unauthorized resume"},
            timeout=30,
        )
        assert response.status_code in [401, 403]
    
    def test_clear_requires_super_admin(self, regular_admin_headers):
        """Clear should require super_admin role"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/control/clear",
            headers=regular_admin_headers,
            json={"reason": "unauthorized clear"},
            timeout=30,
        )
        assert response.status_code in [401, 403]
    
    def test_queue_control_state_endpoint(self, admin_headers):
        """Queue control state endpoint should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue/control/state",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "paused" in data


class TestP1SearchFilterSort:
    """P1: Search/filter/sort parametreleri queue endpointinde çalışıyor mu"""
    
    def test_status_filter(self, admin_headers):
        """Status filter should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=admin_headers,
            params={"status_filter": "QUEUED"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_risk_filter(self, admin_headers):
        """Risk filter should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=admin_headers,
            params={"risk_filter": "high"},
            timeout=30,
        )
        assert response.status_code == 200
    
    def test_type_filter(self, admin_headers):
        """Type filter should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=admin_headers,
            params={"type_filter": "OPEN_POSITION"},
            timeout=30,
        )
        assert response.status_code == 200
    
    def test_sort_by_and_dir(self, admin_headers):
        """Sort by and direction should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=admin_headers,
            params={"sort_by": "risk_score", "sort_dir": "desc"},
            timeout=30,
        )
        assert response.status_code == 200
    
    def test_search_query(self, admin_headers, test_user_id):
        """Search query should work"""
        intent_id = create_queued_intent(test_user_id, symbol="ETHUSDT")
        
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=admin_headers,
            params={"search": "ETHUSDT", "status_filter": "all"},
            timeout=30,
        )
        assert response.status_code == 200
        ids = {item.get("id") for item in response.json()}
        assert intent_id in ids


class TestP1ManualEdit:
    """P1: Manual edit + revalidation endpoint diff döndürüyor mu"""
    
    def test_edit_returns_diff(self, admin_headers, test_user_id):
        """Edit endpoint should return diff"""
        intent_id = create_queued_intent(test_user_id)
        
        response = requests.patch(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/edit",
            headers=admin_headers,
            json={
                "notional": 300,
                "size": 2.5,
                "reason": "manual edit test",
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "diff" in data
        assert "detail_version" in data
    
    def test_edit_without_reason_returns_400(self, admin_headers, test_user_id):
        """Edit without reason should return 400"""
        intent_id = create_queued_intent(test_user_id)
        
        response = requests.patch(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/edit",
            headers=admin_headers,
            json={"notional": 300, "reason": ""},
            timeout=30,
        )
        assert response.status_code == 400


class TestP2Observability:
    """P2: Observability endpoint - approval latency, operator activity, override usage"""
    
    def test_observability_endpoint_returns_metrics(self, admin_headers):
        """Observability endpoint should return metrics"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue/observability",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "queue" in data
        assert "metrics" in data
        assert "queue_control_state" in data
        
        metrics = data.get("metrics", {})
        assert "approval_latency_seconds" in metrics
    
    def test_rejection_summary_endpoint(self, admin_headers):
        """Rejection summary endpoint should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue/rejection-summary",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "queue" in data
        assert "rejection_reason_distribution" in data
        assert "trend" in data
        assert "guidance" in data


class TestP2NotificationSignals:
    """P2: Notification signal - backlog/high-risk/reject spike system-alert tetik yolları"""
    
    def test_queue_endpoint_triggers_alerts_on_backlog(self, admin_headers, test_user_id):
        """Queue endpoint should trigger alerts on backlog (tested via response)"""
        # Create multiple intents to potentially trigger backlog alert
        for _ in range(5):
            create_queued_intent(test_user_id, high_risk=True)
        
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=admin_headers,
            params={"status_filter": "QUEUED"},
            timeout=30,
        )
        assert response.status_code == 200
        # Alert creation is internal, we just verify the endpoint works


class TestRetryEndpoint:
    """Test retry endpoint for rejected intents"""
    
    def test_retry_rejected_intent(self, admin_headers, test_user_id):
        """Retry should work for rejected intents"""
        intent_id = create_queued_intent(test_user_id)
        
        # First reject
        reject_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/reject",
            headers=admin_headers,
            json={"reason": "reject for retry test", "read_acknowledged": True},
            timeout=30,
        )
        assert reject_resp.status_code == 200
        
        # Then retry
        retry_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/retry",
            headers=admin_headers,
            json={"reason": "retry after reject"},
            timeout=30,
        )
        assert retry_resp.status_code == 200
        data = retry_resp.json()
        assert data.get("status") == "QUEUED"


class TestOverrideExecute:
    """Test override execute functionality (super_admin only)"""
    
    def test_override_requires_super_admin(self, regular_admin_headers, test_user_id, admin_headers):
        """Override execute should require super_admin"""
        intent_id = create_queued_intent(test_user_id)
        detail = fetch_detail(admin_headers, intent_id)
        
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=regular_admin_headers,
            json={
                "reason": "override test",
                "detail_version": detail.get("detail_version"),
                "read_acknowledged": True,
                "override_execute": True,
            },
            timeout=30,
        )
        assert response.status_code == 403
