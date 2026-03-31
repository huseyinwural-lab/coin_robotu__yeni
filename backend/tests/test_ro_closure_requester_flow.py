import os
from pathlib import Path
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _db_context():
    from db import SessionLocal
    from model_domains.risk_execution_positions import RiskOrchestratorApprovalRequest

    return SessionLocal, RiskOrchestratorApprovalRequest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


def _login(email: str, password: str, max_retries: int = 3) -> str:
    """Login with retry logic for rate limiting"""
    for attempt in range(max_retries):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 15))
            if attempt < max_retries - 1:
                time.sleep(retry_after + 1)
                continue
        assert response.status_code == 200, f"Login failed ({email}): {response.text}"
    raise AssertionError(f"Login failed after {max_retries} retries ({email})")


def _reset_policy_to_baseline(token: str) -> None:
    """Reset policy to a tight baseline so that loosening triggers CRITICAL classification"""
    headers = {"Authorization": f"Bearer {token}"}
    baseline_policy = {
        "reference_equity_usd": 10000,
        "account_max_notional_pct": 70,
        "symbol_max_notional_pct": 60,
        "strategy_max_concurrent_positions": 8,
        "strategy_cooldown_seconds": 3,
        "max_order_frequency_per_min": 30,
        "max_order_burst_per_10s": 10,
        "daily_loss_limit_pct": 10,
        "duplicate_suppression_window_seconds": 3,
    }
    sim = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
        headers=headers,
        json={"candidate_policy": baseline_policy},
        timeout=30,
    )
    if sim.status_code == 200:
        sim_id = sim.json()["simulation_id"]
        requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
            headers=headers,
            json={
                "simulation_id": sim_id,
                "reason_note": "reset-to-baseline",
                "double_confirmed": True,
                "apply_with_override": False,
                "request_key": f"baseline-reset-{int(time.time() * 1000)}",
            },
            timeout=30,
        )


def _seed_requester_admin(super_token: str) -> tuple[str, str, str]:
    email = f"closure.requester.{int(time.time() * 1000)}@platform.local"
    password = "ClosureRequester123!"
    create_response = requests.post(
        f"{BASE_URL}/api/admin/users/admin-create",
        headers={"Authorization": f"Bearer {super_token}"},
        json={
            "email": email,
            "password": password,
            "full_name": "Closure Deterministic Requester",
            "role": "admin",
        },
        timeout=30,
    )
    assert create_response.status_code in [200, 201], f"Requester seed failed: {create_response.text}"
    token = _login(email, password)
    return email, password, token


def _critical_policy_payload() -> dict:
    """Returns a policy that LOOSENS constraints to trigger CRITICAL classification"""
    return {
        "reference_equity_usd": 10000,
        "account_max_notional_pct": 100,
        "symbol_max_notional_pct": 100,
        "strategy_max_concurrent_positions": 50,
        "strategy_cooldown_seconds": 0,
        "max_order_frequency_per_min": 200,
        "max_order_burst_per_10s": 100,
        "daily_loss_limit_pct": 50,
        "duplicate_suppression_window_seconds": 0,
    }


def _create_approval_request(requester_token: str, request_key: str) -> str:
    headers = {"Authorization": f"Bearer {requester_token}"}
    simulate = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
        headers=headers,
        json={"candidate_policy": _critical_policy_payload()},
        timeout=30,
    )
    assert simulate.status_code == 200, f"Simulation failed: {simulate.text}"
    simulation_id = simulate.json()["simulation_id"]

    apply_response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
        headers=headers,
        json={
            "simulation_id": simulation_id,
            "reason_note": f"requester-flow-{request_key}",
            "double_confirmed": True,
            "apply_with_override": True,
            "request_key": request_key,
        },
        timeout=30,
    )
    assert apply_response.status_code == 200, f"Apply failed: {apply_response.text}"
    approval_id = apply_response.json().get("approval_request_id")
    assert approval_id, "approval_request_id missing"
    return approval_id


def _assign_super(super_token: str, approval_id: str) -> None:
    assign_response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"auto_assign": True},
        timeout=30,
    )
    assert assign_response.status_code in [200, 400], f"Assign failed: {assign_response.text}"


def test_requester_to_quorum_to_apply_flow() -> None:
    super_token = _login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    _reset_policy_to_baseline(super_token)  # Reset policy before test
    _, _, requester_token = _seed_requester_admin(super_token)

    approval_id = _create_approval_request(requester_token, request_key=f"closure-flow-apply-{int(time.time())}")
    _assign_super(super_token, approval_id)

    approve_response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"decision_note": "quorum finalize"},
        timeout=30,
    )
    assert approve_response.status_code == 200, f"Approve failed: {approve_response.text}"
    body = approve_response.json()
    assert body["status"] == "applied", f"Unexpected approve status: {body}"


def test_requester_reject_then_retry_flow() -> None:
    super_token = _login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    _reset_policy_to_baseline(super_token)  # Reset policy before test
    _, _, requester_token = _seed_requester_admin(super_token)

    approval_id = _create_approval_request(requester_token, request_key=f"closure-flow-reject-{int(time.time())}")
    _assign_super(super_token, approval_id)

    reject_response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/reject",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"decision_note": "reject for retry"},
        timeout=30,
    )
    assert reject_response.status_code == 200, f"Reject failed: {reject_response.text}"
    assert reject_response.json().get("state") == "rejected"

    retry_approval_id = _create_approval_request(requester_token, request_key=f"closure-flow-retry-{int(time.time())}")
    _assign_super(super_token, retry_approval_id)
    queue_item = requests.get(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
        headers={"Authorization": f"Bearer {super_token}"},
        params={"scope": "all", "state": "assigned", "limit": 50, "page": 1},
        timeout=30,
    )
    assert queue_item.status_code == 200
    ids = {row["approval_id"] for row in queue_item.json()}
    assert retry_approval_id in ids, "Retry approval queue item not found"


def test_requester_expired_to_force_path_flow() -> None:
    super_token = _login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    _reset_policy_to_baseline(super_token)  # Reset policy before test
    _, _, requester_token = _seed_requester_admin(super_token)

    approval_id = _create_approval_request(requester_token, request_key=f"closure-flow-expire-{int(time.time())}")
    _assign_super(super_token, approval_id)

    # Use raw SQL to update expires_at to avoid ORM foreign key issues
    from sqlalchemy import text
    from db import SessionLocal
    db = SessionLocal()
    try:
        past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.execute(
            text("UPDATE risk_orchestrator_approval_requests SET expires_at = :expires_at WHERE approval_id = :approval_id"),
            {"expires_at": past_time, "approval_id": approval_id}
        )
        db.commit()
    finally:
        db.close()

    sweep_response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/sweep",
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=30,
    )
    assert sweep_response.status_code == 200

    force_response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/force-apply",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"reason_note": "expired-force-path"},
        timeout=30,
    )
    assert force_response.status_code == 200, f"Force path failed: {force_response.text}"
    assert force_response.json().get("status") == "applied"