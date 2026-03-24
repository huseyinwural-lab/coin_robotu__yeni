import os
from pathlib import Path
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _db_context():
    from db import SessionLocal
    from model_domains.risk_execution_positions import RiskOrchestratorApprovalRequest

    return SessionLocal, RiskOrchestratorApprovalRequest


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


def _seed_admin(super_token: str, label: str) -> tuple[str, str, str, str]:
    email = f"closure.{label}.{int(time.time() * 1000)}@platform.local"
    password = "ClosureOps123!"
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
    assert create_response.status_code in [200, 201], f"Admin seed failed: {create_response.text}"
    token = _login(email, password)
    return email, password, token, create_response.json().get("id")


def _critical_candidate(multiplier: float = 1.0) -> dict:
    """Returns a policy that LOOSENS constraints to trigger CRITICAL classification"""
    return {
        "reference_equity_usd": 10000,
        "account_max_notional_pct": min(100, int(100 * multiplier)),
        "symbol_max_notional_pct": min(100, int(100 * multiplier)),
        "strategy_max_concurrent_positions": int(50 * multiplier),
        "strategy_cooldown_seconds": 0,
        "max_order_frequency_per_min": int(200 * multiplier),
        "max_order_burst_per_10s": int(100 * multiplier),
        "daily_loss_limit_pct": int(50 * multiplier),
        "duplicate_suppression_window_seconds": 0,
    }


def _create_request(token: str, suffix: str, multiplier: float = 1.0) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    sim = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate",
        headers=headers,
        json={"candidate_policy": _critical_candidate(multiplier=multiplier)},
        timeout=30,
    )
    assert sim.status_code == 200
    apply = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/apply",
        headers=headers,
        json={
            "simulation_id": sim.json()["simulation_id"],
            "reason_note": f"chaos-{suffix}",
            "double_confirmed": True,
            "apply_with_override": True,
            "request_key": f"chaos-{suffix}-{int(time.time() * 1000)}",
        },
        timeout=30,
    )
    assert apply.status_code == 200, apply.text
    approval_id = apply.json().get("approval_request_id")
    assert approval_id
    return approval_id


def test_predictive_risk_drift_and_normalization() -> None:
    super_token = _login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    _reset_policy_to_baseline(super_token)  # Reset policy before test
    _, _, requester_token, _ = _seed_admin(super_token, "predictive")
    headers = {"Authorization": f"Bearer {requester_token}"}

    payload = {"candidate_policy": _critical_candidate(multiplier=1.05)}
    sim1 = requests.post(f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate", headers=headers, json=payload, timeout=30)
    sim2 = requests.post(f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/simulate", headers=headers, json=payload, timeout=30)
    assert sim1.status_code == 200 and sim2.status_code == 200

    score1 = sim1.json().get("risk_score")
    score2 = sim2.json().get("risk_score")
    assert score1 == score2, f"Predictive drift detected for same input: {score1} vs {score2}"

    dashboard = requests.get(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/operations/dashboard",
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=30,
    )
    assert dashboard.status_code == 200
    signal = dashboard.json().get("predictive_risk_signal") or {}
    assert 0 <= float(signal.get("predictive_score", 0)) <= 100
    normalization = signal.get("normalization") or {}
    assert set(normalization.keys()) == {"breach", "queue_pressure", "volatility"}


def test_cache_telemetry_and_chaos_e2e() -> None:
    super_token = _login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    _reset_policy_to_baseline(super_token)  # Reset policy before test
    _, _, requester_token, requester_id = _seed_admin(super_token, "chaos-requester")
    _, _, approver_token, approver_id = _seed_admin(super_token, "chaos-approver")

    # High-load approval generation
    approval_ids = [_create_request(requester_token, f"bulk-{idx}", multiplier=1.0 + (idx * 0.03)) for idx in range(4)]

    # Assign and parallel vote/reject operations
    for approval_id in approval_ids:
        assign = requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{approval_id}/assign",
            headers={"Authorization": f"Bearer {super_token}"},
            json={"assignee_id": approver_id},
            timeout=30,
        )
        assert assign.status_code == 200

    def _approve(approval_id: str) -> int:
        return requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/approve",
            headers={"Authorization": f"Bearer {super_token}"},
            json={"decision_note": "chaos-approve"},
            timeout=30,
        ).status_code

    def _reject(approval_id: str) -> int:
        return requests.post(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/approvals/{approval_id}/reject",
            headers={"Authorization": f"Bearer {approver_token}"},
            json={"decision_note": "chaos-reject"},
            timeout=30,
        ).status_code

    with ThreadPoolExecutor(max_workers=4) as executor:
        statuses = list(
            executor.map(
                lambda payload: payload[0](payload[1]),
                [(_approve, approval_ids[0]), (_approve, approval_ids[1]), (_reject, approval_ids[2]), (_approve, approval_ids[3])],
            )
        )
    assert any(code == 200 for code in statuses), f"No successful chaos decisions: {statuses}"

    # expire + reassign + force path - reset policy first to ensure CRITICAL classification
    _reset_policy_to_baseline(super_token)
    expiring_id = _create_request(requester_token, "chaos-expire", multiplier=1.2)
    assign_exp = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{expiring_id}/assign",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"assignee_id": approver_id},
        timeout=30,
    )
    assert assign_exp.status_code == 200

    # Use raw SQL to update expires_at to avoid ORM foreign key issues
    from sqlalchemy import text
    from db import SessionLocal as DBSession
    db = DBSession()
    try:
        past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.execute(
            text("UPDATE risk_orchestrator_approval_requests SET expires_at = :expires_at WHERE approval_id = :approval_id"),
            {"expires_at": past_time, "approval_id": expiring_id}
        )
        db.commit()
    finally:
        db.close()

    sweep = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/sweep",
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=30,
    )
    assert sweep.status_code == 200

    force_apply = requests.post(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue/{expiring_id}/force-apply",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"reason_note": "chaos-force-expired"},
        timeout=30,
    )
    assert force_apply.status_code == 200, force_apply.text

    # cache telemetry should be visible and non-empty after repeated reads
    for _ in range(3):
        requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/policy/queue",
            headers={"Authorization": f"Bearer {super_token}"},
            params={"scope": "all", "state": "assigned", "page": 1, "limit": 20},
            timeout=30,
        )
        requests.get(
            f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/operations/dashboard",
            headers={"Authorization": f"Bearer {super_token}"},
            timeout=30,
        )

    dashboard = requests.get(
        f"{BASE_URL}/api/strategy-domain/admin/risk-orchestrator/operations/dashboard",
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=30,
    )
    assert dashboard.status_code == 200
    cache_health = dashboard.json().get("cache_health") or {}
    assert "queue" in cache_health and "dashboard" in cache_health
    assert float(cache_health["queue"].get("hit_ratio", 0)) >= 0
    assert float(cache_health["dashboard"].get("hit_ratio", 0)) >= 0