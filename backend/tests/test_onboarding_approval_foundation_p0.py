from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient

from db import SessionLocal
from models import User, UserOnboardingDecisionLog
from server import fastapi_app


def _admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!", "panel": "admin"},
    )
    assert response.status_code == 200
    payload = response.json()
    return payload.get("access_token") or payload.get("token")


def _register_pending_user(client: TestClient) -> str:
    email = f"onboarding-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "VeryStrong123!",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def _upload_and_verify_single_kyc(client: TestClient, token: str, user_id: str):
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
        json={"review_status": "approved", "review_note": "KYC dokuman kontrol edildi"},
    )
    assert review.status_code == 200


def test_context_endpoint_and_hard_block_without_kyc_aml_risk():
    client = TestClient(fastapi_app)
    token = _admin_token(client)
    user_id = _register_pending_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    context_resp = client.get(f"/api/admin/onboarding/{user_id}/context", headers=headers)
    assert context_resp.status_code == 200
    context = context_resp.json()
    assert context["approval_disabled"] is True
    assert "kyc_not_verified" in context["approval_disable_reasons"]
    assert "risk_score_missing" in context["approval_disable_reasons"]

    approve_resp = client.post(
        f"/api/admin/onboarding/{user_id}/decision",
        headers=headers,
        json={"decision": "approve", "reason": "Onay veriyorum", "confirm_token": "CONFIRM"},
    )
    assert approve_resp.status_code == 409


def test_auto_approve_flow_and_same_actor_constraint():
    client = TestClient(fastapi_app)
    token = _admin_token(client)
    user_id = _register_pending_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    _upload_and_verify_single_kyc(client, token, user_id)
    risk_resp = client.post(
        f"/api/admin/onboarding/{user_id}/risk-foundation",
        headers=headers,
        json={
            "risk_score": 20,
            "aml_flag": "clear",
            "api_key_validity": "valid",
            "balance_usd": 250,
            "country_code": "TR",
            "leverage_permission": True,
            "futures_capability": True,
            "spot_capability": True,
        },
    )
    assert risk_resp.status_code == 200
    assert risk_resp.json()["decision_engine"]["recommended_action"] == "auto_approve"

    auto_resp = client.post(
        f"/api/admin/onboarding/{user_id}/decision/auto-approve",
        headers=headers,
        json={"decision": "approve", "reason": "Auto approve uygula", "confirm_token": "CONFIRM"},
    )
    assert auto_resp.status_code == 200
    assert auto_resp.json()["approval_status"] == "approved"

    reject_same_actor = client.post(
        f"/api/admin/onboarding/{user_id}/decision",
        headers=headers,
        json={"decision": "reject", "reason": "Ayni actor reject denemesi", "confirm_token": "CONFIRM"},
    )
    assert reject_same_actor.status_code == 409


def test_high_risk_forces_manual_review_and_bulk_approve_disabled():
    client = TestClient(fastapi_app)
    token = _admin_token(client)
    user_id = _register_pending_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    _upload_and_verify_single_kyc(client, token, user_id)
    risk_resp = client.post(
        f"/api/admin/onboarding/{user_id}/risk-foundation",
        headers=headers,
        json={
            "risk_score": 75,
            "aml_flag": "clear",
            "api_key_validity": "valid",
            "balance_usd": 600,
            "country_code": "TR",
            "leverage_permission": False,
            "futures_capability": True,
            "spot_capability": True,
        },
    )
    assert risk_resp.status_code == 200
    assert risk_resp.json()["decision_engine"]["recommended_action"] == "force_manual_review"

    bulk_approve = client.post("/api/admin/user-approvals/bulk-approve", headers=headers, json={"ids": [user_id]})
    assert bulk_approve.status_code == 403


def test_reject_reason_mandatory_and_audit_export_immutable_append_only():
    client = TestClient(fastapi_app)
    token = _admin_token(client)
    user_id = _register_pending_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    _upload_and_verify_single_kyc(client, token, user_id)
    risk_resp = client.post(
        f"/api/admin/onboarding/{user_id}/risk-foundation",
        headers=headers,
        json={
            "risk_score": 60,
            "aml_flag": "clear",
            "api_key_validity": "valid",
            "balance_usd": 100,
            "country_code": "TR",
            "leverage_permission": True,
            "futures_capability": True,
            "spot_capability": True,
        },
    )
    assert risk_resp.status_code == 200

    reject_without_reason = client.post(
        f"/api/admin/onboarding/{user_id}/decision",
        headers=headers,
        json={"decision": "reject", "reason": "bad", "confirm_token": "CONFIRM"},
    )
    assert reject_without_reason.status_code == 400

    reject_ok = client.post(
        f"/api/admin/onboarding/{user_id}/decision",
        headers=headers,
        json={"decision": "reject", "reason": "Manual reject compliance nedeni", "confirm_token": "CONFIRM"},
    )
    assert reject_ok.status_code == 200
    decision_log_id = reject_ok.json()["decision_log_id"]

    db = SessionLocal()
    try:
        row = db.query(UserOnboardingDecisionLog).filter(UserOnboardingDecisionLog.id == decision_log_id).first()
        assert row is not None
        assert row.reason == "Manual reject compliance nedeni"
        before_timestamp = row.created_at
    finally:
        db.close()

    export_resp = client.get("/api/admin/audit/export", headers=headers)
    assert export_resp.status_code == 200
    assert "onboarding_decision_audit.csv" in export_resp.headers.get("content-disposition", "")
    assert decision_log_id in export_resp.text

    db = SessionLocal()
    try:
        row = db.query(UserOnboardingDecisionLog).filter(UserOnboardingDecisionLog.id == decision_log_id).first()
        assert row.created_at == before_timestamp
    finally:
        db.close()
