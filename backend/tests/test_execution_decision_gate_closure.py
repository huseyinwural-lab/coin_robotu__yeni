import os
import random
import string
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import uuid
from datetime import datetime, timezone

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


def random_email(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}@example.com"


def login(base: str, email: str, password: str) -> str:
    response = requests.post(
        f"{base}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert response.status_code == 200, f"Login failed ({email}): {response.text}"
    return response.json()["access_token"]


def admin_headers(base: str) -> dict:
    return {"Authorization": f"Bearer {login(base, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)}"}


def provision_user(base: str, admin_headers_payload: dict) -> tuple[dict, str]:
    email = random_email("execution_gate_user")
    password = "ExecutionGateUser123!"
    register = requests.post(
        f"{base}/api/auth/register",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert register.status_code in [200, 201], register.text
    user_id = register.json()["id"]

    approve = requests.post(
        f"{base}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers_payload,
        timeout=30,
    )
    assert approve.status_code == 200, approve.text

    return {"Authorization": f"Bearer {login(base, email, password)}"}, user_id


def create_queued_intent(user_id: str, *, high_risk: bool = True) -> str:
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
        symbol="BTCUSDT",
        market_type="spot",
        side="buy",
        notional=180.0,
        size=1.5,
        reduce_only=False,
        normalized_order_payload={"strategy_binding": "spot_pullback_v1", "execution_mode": "manual"},
        reject_reason_codes=[],
        risk_flags=["high_volatility_spike"] if high_risk else ["normal"],
        risk_score=78.0 if high_risk else 22.0,
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


def fetch_detail(base: str, admin_headers_payload: dict, intent_id: str) -> dict:
    detail = requests.get(
        f"{base}/api/admin/execution-queue/{intent_id}/detail",
        headers=admin_headers_payload,
        timeout=30,
    )
    assert detail.status_code == 200, detail.text
    return detail.json()


def build_approve_payload(detail: dict, reason: str) -> dict:
    return {
        "reason": reason,
        "detail_version": detail.get("detail_version"),
        "read_acknowledged": True,
        "double_confirmation": True if (detail.get("risk_payload") or {}).get("is_high_risk") else False,
    }


def ensure_queue_resumed(base: str, admin: dict) -> None:
    requests.post(
        f"{base}/api/admin/execution-queue/control/resume",
        headers=admin,
        json={"reason": "test setup resume"},
        timeout=30,
    )


def test_p0_reason_read_ack_and_stale_version_enforced() -> None:
    base = resolve_base_url()
    admin = admin_headers(base)
    ensure_queue_resumed(base, admin)
    _, user_id = provision_user(base, admin)
    intent_id = create_queued_intent(user_id)
    detail = fetch_detail(base, admin, intent_id)

    no_reason = requests.post(
        f"{base}/api/admin/execution-queue/{intent_id}/approve",
        headers=admin,
        json={"reason": "", "detail_version": detail.get("detail_version"), "read_acknowledged": True},
        timeout=30,
    )
    assert no_reason.status_code == 400

    no_read_ack = requests.post(
        f"{base}/api/admin/execution-queue/{intent_id}/approve",
        headers=admin,
        json={"reason": "valid reason", "detail_version": detail.get("detail_version"), "read_acknowledged": False},
        timeout=30,
    )
    assert no_read_ack.status_code == 400

    edit = requests.patch(
        f"{base}/api/admin/execution-queue/{intent_id}/edit",
        headers=admin,
        json={"notional": 220, "reason": "version bump for stale test"},
        timeout=30,
    )
    assert edit.status_code == 200, edit.text

    stale_try = requests.post(
        f"{base}/api/admin/execution-queue/{intent_id}/approve",
        headers=admin,
        json=build_approve_payload(detail, "stale version should fail"),
        timeout=30,
    )
    assert stale_try.status_code == 400
    assert "stale" in str(stale_try.text).lower()


def test_p0_invalid_transition_and_race_determinism() -> None:
    base = resolve_base_url()
    admin = admin_headers(base)
    ensure_queue_resumed(base, admin)
    _, user_id = provision_user(base, admin)
    intent_id = create_queued_intent(user_id)
    detail = fetch_detail(base, admin, intent_id)

    def approve_call() -> int:
        return requests.post(
            f"{base}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin,
            json=build_approve_payload(detail, "race approve"),
            timeout=30,
        ).status_code

    def reject_call() -> int:
        return requests.post(
            f"{base}/api/admin/execution-queue/{intent_id}/reject",
            headers=admin,
            json={
                "reason": "race reject",
                "detail_version": detail.get("detail_version"),
                "read_acknowledged": True,
            },
            timeout=30,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda fn: fn(), [approve_call, reject_call]))

    assert any(code == 200 for code in statuses), f"Race: success yok {statuses}"
    assert all(code in [200, 400, 409, 423] for code in statuses), f"Beklenmeyen status: {statuses}"

    queue_all = requests.get(
        f"{base}/api/admin/execution-queue",
        headers=admin,
        params={"status_filter": "all", "limit": 300},
        timeout=30,
    )
    assert queue_all.status_code == 200
    item = next((row for row in queue_all.json() if row.get("id") == intent_id), None)
    assert item is not None
    assert item.get("status") in {"RELEASED", "REJECTED"}

    invalid_reject = requests.post(
        f"{base}/api/admin/execution-queue/{intent_id}/reject",
        headers=admin,
        json={"reason": "invalid transition", "read_acknowledged": True},
        timeout=30,
    )
    assert invalid_reject.status_code in [400, 409]


def test_p0_queue_control_authorization_and_pause_behavior() -> None:
    base = resolve_base_url()
    admin = admin_headers(base)

    # create non-super admin
    child_email = random_email("execution_queue_admin")
    child_password = "ExecutionQueueAdmin123!"
    create_admin = requests.post(
        f"{base}/api/admin/users/admin-create",
        headers=admin,
        json={"email": child_email, "password": child_password, "role": "admin", "full_name": "Queue Admin"},
        timeout=30,
    )
    assert create_admin.status_code in [200, 201], create_admin.text
    admin_token = login(base, child_email, child_password)
    child_admin_headers = {"Authorization": f"Bearer {admin_token}"}

    unauthorized_pause = requests.post(
        f"{base}/api/admin/execution-queue/control/pause",
        headers=child_admin_headers,
        json={"reason": "not allowed"},
        timeout=30,
    )
    assert unauthorized_pause.status_code in [401, 403]

    pause = requests.post(
        f"{base}/api/admin/execution-queue/control/pause",
        headers=admin,
        json={"reason": "maintenance pause"},
        timeout=30,
    )
    assert pause.status_code == 200, pause.text

    _, user_id = provision_user(base, admin)
    intent_id = create_queued_intent(user_id)
    detail = fetch_detail(base, admin, intent_id)

    blocked_approve = requests.post(
        f"{base}/api/admin/execution-queue/{intent_id}/approve",
        headers=admin,
        json=build_approve_payload(detail, "should fail while paused"),
        timeout=30,
    )
    assert blocked_approve.status_code == 423

    resume = requests.post(
        f"{base}/api/admin/execution-queue/control/resume",
        headers=admin,
        json={"reason": "maintenance done"},
        timeout=30,
    )
    assert resume.status_code == 200, resume.text


def test_p1_p2_bulk_limit_and_observability_contract() -> None:
    base = resolve_base_url()
    admin = admin_headers(base)

    bulk_limit = requests.post(
        f"{base}/api/admin/execution-queue/bulk-decision",
        headers=admin,
        json={
            "intent_ids": [f"dummy-{idx}" for idx in range(21)],
            "action": "approve",
            "reason": "bulk limit test",
            "read_acknowledged": True,
            "double_confirmation": True,
        },
        timeout=30,
    )
    assert bulk_limit.status_code == 400

    observability = requests.get(
        f"{base}/api/admin/execution-queue/observability",
        headers=admin,
        timeout=30,
    )
    assert observability.status_code == 200, observability.text
    payload = observability.json()
    assert "queue" in payload and "metrics" in payload and "queue_control_state" in payload
    assert "approval_latency_seconds" in (payload.get("metrics") or {})