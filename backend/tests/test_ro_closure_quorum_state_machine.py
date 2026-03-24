import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://identity-control-1.preview.emergentagent.com").rstrip("/")
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


def _create_admin_user(super_token: str, label: str) -> tuple[str, str, str, str]:
    email = f"closure.{label}.{int(time.time() * 1000)}@platform.local"
    password = "ClosureAdmin123!"
    create_response = requests.post(
        f"{BASE_URL}/api/admin/users/admin-create",
        headers={"Authorization": f"Bearer {super_token}"},
        json={
            "email": email,
            "password": password,
            "full_name": f"Closure {label}",
            "role": "admin",
        },
        timeout=30,
    )
    assert create_response.status_code in [200, 201], f"Admin create failed: {create_response.text}"
    user_id = create_response.json().get("id")
    token = _login(email, password)
    return email, password, token, user_id


def _create_approval(requester_token: str, request_key: str) -> str:
    """Creates a CRITICAL policy change that LOOSENS constraints to trigger 4-eyes approval"""
    headers = {"Authorization": f"Bearer {requester_token}"}
    simulate = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
        headers=headers,
        json={
            "candidate_policy": {
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
        },
        timeout=30,
    )
    assert simulate.status_code == 200
    simulation_id = simulate.json()["simulation_id"]
    apply_response = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
        headers=headers,
        json={
            "simulation_id": simulation_id,
            "reason_note": "quorum-state-machine",
            "double_confirmed": True,
            "apply_with_override": True,
            "request_key": request_key,
        },
        timeout=30,
    )
    assert apply_response.status_code == 200
    approval_id = apply_response.json().get("approval_request_id")
    assert approval_id
    return approval_id


def test_quorum_threshold_and_finalize_once() -> None:
    super_token = _login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    _reset_policy_to_baseline(super_token)  # Reset policy before test
    _, _, requester_token, _ = _create_admin_user(super_token, "requester")
    _, _, approver_token, approver_id = _create_admin_user(super_token, "approver")

    approval_id = _create_approval(requester_token, f"closure-quorum-{int(time.time())}")

    assign = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"assignee_id": approver_id},
        timeout=30,
    )
    assert assign.status_code == 200, assign.text

    first_vote = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {approver_token}"},
        json={"decision_note": "vote-1"},
        timeout=30,
    )
    assert first_vote.status_code == 200, first_vote.text
    assert first_vote.json()["status"] == "assigned"

    finalize_vote = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"decision_note": "vote-2-finalize"},
        timeout=30,
    )
    assert finalize_vote.status_code == 200, finalize_vote.text
    assert finalize_vote.json()["status"] == "applied"

    duplicate_finalize = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"decision_note": "vote-3-duplicate"},
        timeout=30,
    )
    assert duplicate_finalize.status_code == 409


def test_simultaneous_votes_single_outcome() -> None:
    super_token = _login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    _reset_policy_to_baseline(super_token)  # Reset policy before test
    _, _, requester_token, _ = _create_admin_user(super_token, "requester-race")
    _, _, approver_token, approver_id = _create_admin_user(super_token, "approver-race")

    approval_id = _create_approval(requester_token, f"closure-race-{int(time.time())}")
    assign = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"assignee_id": approver_id},
        timeout=30,
    )
    assert assign.status_code == 200

    def _approve(token: str, note: str) -> int:
        response = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
            json={"decision_note": note},
            timeout=30,
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda payload: _approve(*payload), [(approver_token, "race-approver"), (super_token, "race-super")]))

    assert statuses.count(200) >= 1, f"Unexpected statuses: {statuses}"
    assert statuses.count(409) <= 1, f"Unexpected statuses: {statuses}"


def test_conflicting_vote_reject_vs_approve_race() -> None:
    super_token = _login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    _reset_policy_to_baseline(super_token)  # Reset policy before test
    _, _, requester_token, _ = _create_admin_user(super_token, "requester-conflict")
    _, _, approver_token, approver_id = _create_admin_user(super_token, "approver-conflict")

    approval_id = _create_approval(requester_token, f"closure-conflict-{int(time.time())}")
    assign = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"assignee_id": approver_id},
        timeout=30,
    )
    assert assign.status_code == 200

    def _approve() -> int:
        return requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
            headers={"Authorization": f"Bearer {super_token}"},
            json={"decision_note": "conflict-approve"},
            timeout=30,
        ).status_code

    def _reject() -> int:
        return requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/reject",
            headers={"Authorization": f"Bearer {approver_token}"},
            json={"decision_note": "conflict-reject"},
            timeout=30,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda fn: fn(), [_approve, _reject]))

    assert any(code in [200, 409] for code in statuses), f"Unexpected statuses: {statuses}"
    assert statuses.count(200) >= 1, f"No successful terminal decision: {statuses}"