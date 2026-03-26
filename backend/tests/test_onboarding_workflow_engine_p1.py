from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from db import SessionLocal
from models import UserActivationEvent, UserOnboardingWorkflowCase, UserStrategyScope
from server import fastapi_app


def _admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!", "panel": "admin"},
    )
    assert response.status_code == 200
    payload = response.json()
    return payload.get("access_token") or payload.get("token")


def _register_user(client: TestClient) -> str:
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"p1-{uuid.uuid4().hex[:8]}@example.com",
            "password": "VeryStrong123!",
            "first_name": "P1",
            "last_name": "Case",
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def _prepare_user_foundation(client: TestClient, token: str, user_id: str, risk_score: float):
    headers = {"Authorization": f"Bearer {token}"}
    upload = client.post(
        f"/api/admin/onboarding/{user_id}/kyc-documents",
        headers=headers,
        files={"file": ("kyc.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert upload.status_code == 200
    doc_id = upload.json()["document_id"]
    review = client.post(
        f"/api/admin/onboarding/{user_id}/kyc-documents/{doc_id}/review",
        headers=headers,
        json={"review_status": "approved", "review_note": "KYC approved for workflow"},
    )
    assert review.status_code == 200
    risk = client.post(
        f"/api/admin/onboarding/{user_id}/risk-foundation",
        headers=headers,
        json={
            "risk_score": risk_score,
            "aml_flag": "clear",
            "api_key_validity": "valid",
            "balance_usd": 600,
            "country_code": "TR",
            "leverage_permission": True,
            "futures_capability": True,
            "spot_capability": True,
        },
    )
    assert risk.status_code == 200


def test_workflow_sequence_enforced_ops_risk_final_and_priority_queue():
    client = TestClient(fastapi_app)
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    high_user = _register_user(client)
    low_user = _register_user(client)
    _prepare_user_foundation(client, token, high_user, risk_score=80)
    _prepare_user_foundation(client, token, low_user, risk_score=20)

    start_high = client.post(f"/api/admin/onboarding/{high_user}/workflow/start", headers=headers, json={})
    start_low = client.post(f"/api/admin/onboarding/{low_user}/workflow/start", headers=headers, json={})
    assert start_high.status_code == 200
    assert start_low.status_code == 200

    invalid_final = client.post(
        f"/api/admin/onboarding/{high_user}/workflow/steps/final/complete",
        headers=headers,
        json={"note": "risk adimi atlandi"},
    )
    assert invalid_final.status_code == 409

    complete_ops = client.post(
        f"/api/admin/onboarding/{high_user}/workflow/steps/ops/complete",
        headers=headers,
        json={"note": "ops review done"},
    )
    assert complete_ops.status_code == 200
    assert complete_ops.json()["current_step"] == "risk"

    queue = client.get("/api/admin/onboarding/workflow/queue", headers=headers)
    assert queue.status_code == 200
    items = queue.json()["items"]
    assert len(items) >= 2
    assert items[0]["priority_score"] >= items[1]["priority_score"]


def test_sla_timeout_escalation_to_supervisor_queue():
    client = TestClient(fastapi_app)
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    user_id = _register_user(client)
    _prepare_user_foundation(client, token, user_id, risk_score=55)
    start = client.post(f"/api/admin/onboarding/{user_id}/workflow/start", headers=headers, json={})
    assert start.status_code == 200

    db = SessionLocal()
    try:
        row = db.query(UserOnboardingWorkflowCase).filter(UserOnboardingWorkflowCase.user_id == user_id).first()
        assert row is not None
        row.sla_due_at = row.created_at
        db.commit()
    finally:
        db.close()

    escalation = client.post("/api/admin/onboarding/workflow/escalate-timeouts", headers=headers, json={})
    assert escalation.status_code == 200
    assert escalation.json()["escalated"] >= 1

    check = client.get(f"/api/admin/onboarding/{user_id}/workflow", headers=headers)
    assert check.status_code == 200
    payload = check.json()["workflow_case"]
    assert payload["supervisor_queue"] is True


def test_decision_support_shape_and_activation_chain_events():
    client = TestClient(fastapi_app)
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    user_id = _register_user(client)
    _prepare_user_foundation(client, token, user_id, risk_score=20)

    support = client.get(f"/api/admin/onboarding/{user_id}/decision-support", headers=headers)
    assert support.status_code == 200
    decision_support = support.json()["decision_support"]
    assert "recommended_action" in decision_support
    assert "confidence" in decision_support
    assert "reason_codes" in decision_support
    assert "human_readable_summary" in decision_support

    auto = client.post(
        f"/api/admin/onboarding/{user_id}/decision/auto-approve",
        headers=headers,
        json={"decision": "approve", "reason": "workflow activation test", "confirm_token": "CONFIRM"},
    )
    assert auto.status_code == 200

    db = SessionLocal()
    try:
        event_types = [
            row.event_type
            for row in db.query(UserActivationEvent).filter(UserActivationEvent.user_id == user_id).all()
        ]
        assert "user.approval.completed" in event_types
        assert "user.risk.defaults_assigned" in event_types
        assert "user.strategy.default_bound" in event_types
        assert "user.activation.started" in event_types

        strategy_scope = db.query(UserStrategyScope).filter(UserStrategyScope.user_id == user_id).first()
        assert strategy_scope is not None
        assert strategy_scope.strategy_code == "core-default"
    finally:
        db.close()
