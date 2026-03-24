from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests


BASE_URL = os.environ.get("STRATEGY_TEST_BASE_URL") or os.environ.get("REACT_APP_BACKEND_URL")
ADMIN_EMAIL = os.environ.get("STRATEGY_TEST_ADMIN_EMAIL", "canary.admin@platform.local")
ADMIN_PASSWORD = os.environ.get("STRATEGY_TEST_ADMIN_PASSWORD", "CanaryAdmin123!")


def _require_base_url() -> str:
    if not BASE_URL:
        pytest.skip("BASE_URL yok; integration concurrency test atlandı")
    return str(BASE_URL).rstrip("/")


def _login_token(base: str) -> str:
    session = requests.Session()
    endpoints = [
        "/api/auth/login",
        "/api/auth/login/admin",
    ]
    for endpoint in endpoints:
        resp = session.post(
            f"{base}{endpoint}",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        if resp.status_code == 200 and resp.json().get("access_token"):
            return str(resp.json()["access_token"])
    pytest.skip("admin login başarısız; integration concurrency test atlandı")


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _admin_session() -> requests.Session:
    base = _require_base_url()
    token = _login_token(base)
    session = requests.Session()
    session.headers.update(_auth_headers(token))
    return session


def _build_context(version_id: str, version_hash: str) -> dict:
    return {
        "context_id": f"ctx-{uuid.uuid4().hex[:8]}",
        "account_id": "acct-demo",
        "timestamp_utc": "2026-03-24T09:00:00Z",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "market_snapshot": {"last_price": 100000, "bid": 99990, "ask": 100010},
        "market_snapshot_hash": "snapshot-hash",
        "position_state": {"side": "flat", "qty": 0},
        "risk_state": {"blocked": False},
        "account_state_projection": {"equity": 1000, "free_margin": 900, "daily_loss_pct": 1, "daily_loss_usd": 10},
        "strategy_version_id": version_id,
        "strategy_version_hash": version_hash,
        "input_features": {"momentum": 0.2, "volatility": 0.1, "base_size": 0.001},
        "correlation_id": f"corr-{uuid.uuid4().hex[:8]}",
    }


def _prepare_strategy(session: requests.Session, base: str) -> tuple[str, dict, dict]:
    code = f"race-{uuid.uuid4().hex[:8]}"
    create = session.post(
        f"{base}/api/strategy-domain/admin/strategies",
        json={"name": "Race Strategy", "code": code, "description": "concurrency"},
        timeout=30,
    )
    assert create.status_code == 201
    strategy_id = create.json()["strategy_id"]

    version_payloads = [
        {"momentum_threshold": 0.1, "base_size": 0.001, "volatility_guard": 0.5},
        {"momentum_threshold": 0.2, "base_size": 0.002, "volatility_guard": 0.45},
    ]
    created = []
    for cfg in version_payloads:
        resp = session.post(
            f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/versions",
            json={"config_json": cfg, "config_schema_version": "1.0"},
            timeout=30,
        )
        assert resp.status_code == 201
        created.append(resp.json())

    for item in created:
        version_id = item["version_id"]
        validate = session.post(
            f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/validate",
            json={"force": False},
            timeout=30,
        )
        assert validate.status_code == 200
        dry = session.post(
            f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/versions/{version_id}/dry-run",
            json={"context_snapshot": _build_context(version_id, item["version_hash"])} ,
            timeout=30,
        )
        assert dry.status_code == 200

    return strategy_id, created[0], created[1]


def _create_promote_request(session: requests.Session, base: str, strategy_id: str, version_id: str, note: str = "test promote") -> str:
    promote = session.post(
        f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/promote-request",
        json={
            "strategy_version_id": version_id,
            "request_note": note,
            "require_validation": True,
            "require_dry_run": True,
            "requested_stage": None,
        },
        timeout=30,
    )
    assert promote.status_code == 200, promote.text
    return str(promote.json()["request_id"])


def _fetch_lifecycle(session: requests.Session, base: str, strategy_id: str) -> list[dict]:
    lifecycle = session.get(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/lifecycle", timeout=30)
    assert lifecycle.status_code == 200, lifecycle.text
    return lifecycle.json().get("items", [])


def _assert_single_active_and_production(items: list[dict]) -> None:
    active_count = len([item for item in items if bool(item.get("is_active"))])
    production_count = len([item for item in items if bool(item.get("is_production"))])
    assert active_count == 1
    assert production_count <= 1


def test_concurrent_activate_keeps_single_active_version():
    base = _require_base_url()
    session = _admin_session()
    token = _login_token(base)
    strategy_id, v1, v2 = _prepare_strategy(session, base)

    def activate(version_id: str) -> int:
        resp = requests.post(
            f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version_id}",
            headers=_auth_headers(token),
            timeout=30,
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(activate, [v1["version_id"], v2["version_id"]]))

    assert any(code == 200 for code in statuses)
    assert all(code in {200, 409} for code in statuses)

    items = _fetch_lifecycle(session, base, strategy_id)
    _assert_single_active_and_production(items)


def test_concurrent_rollback_and_promote_keeps_consistent_state():
    base = _require_base_url()
    session = _admin_session()
    token = _login_token(base)
    strategy_id, v1, v2 = _prepare_strategy(session, base)

    activate_v2 = session.post(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{v2['version_id']}", timeout=30)
    assert activate_v2.status_code == 200

    request_id = _create_promote_request(session, base, strategy_id, v2["version_id"], note="race promote")

    def approve() -> int:
        resp = requests.post(
            f"{base}/api/strategy-domain/admin/promotion-requests/{request_id}/approve",
            json={"note": "approve race"},
            headers=_auth_headers(token),
            timeout=30,
        )
        return resp.status_code

    def rollback() -> int:
        resp = requests.post(
            f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/rollback",
            json={"target_version_id": v1["version_id"], "reason": "race rollback"},
            headers=_auth_headers(token),
            timeout=30,
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda fn: fn(), [approve, rollback]))

    assert all(code in {200, 400, 409} for code in statuses)

    items = _fetch_lifecycle(session, base, strategy_id)
    _assert_single_active_and_production(items)


def test_approve_after_approve_attempt_is_blocked():
    base = _require_base_url()
    session = _admin_session()
    strategy_id, _v1, v2 = _prepare_strategy(session, base)
    request_id = _create_promote_request(session, base, strategy_id, v2["version_id"], note="approve twice")

    first = session.post(
        f"{base}/api/strategy-domain/admin/promotion-requests/{request_id}/approve",
        json={"note": "first approve"},
        timeout=30,
    )
    assert first.status_code == 200, first.text

    second = session.post(
        f"{base}/api/strategy-domain/admin/promotion-requests/{request_id}/approve",
        json={"note": "second approve"},
        timeout=30,
    )
    assert second.status_code == 400
    assert "promotion_request_not_pending" in second.text


def test_reject_then_promote_bypass_attempt_fails():
    base = _require_base_url()
    session = _admin_session()
    strategy_id, _v1, v2 = _prepare_strategy(session, base)
    request_id = _create_promote_request(session, base, strategy_id, v2["version_id"], note="reject then bypass")

    reject = session.post(
        f"{base}/api/strategy-domain/admin/promotion-requests/{request_id}/reject",
        json={"note": "reject path"},
        timeout=30,
    )
    assert reject.status_code == 200, reject.text

    bypass_approve = session.post(
        f"{base}/api/strategy-domain/admin/promotion-requests/{request_id}/approve",
        json={"note": "bypass attempt"},
        timeout=30,
    )
    assert bypass_approve.status_code == 400
    assert "promotion_request_not_pending" in bypass_approve.text


def test_stale_version_activate_attempt_blocked_when_strategy_archived():
    base = _require_base_url()
    session = _admin_session()
    strategy_id, v1, _v2 = _prepare_strategy(session, base)

    archive = session.post(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/archive", timeout=30)
    assert archive.status_code == 200, archive.text

    activate = session.post(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{v1['version_id']}", timeout=30)
    assert activate.status_code == 400
    assert "strategy_archived_cannot_activate" in activate.text


def test_archived_strategy_promote_attempt_blocked():
    base = _require_base_url()
    session = _admin_session()
    strategy_id, _v1, v2 = _prepare_strategy(session, base)

    archive = session.post(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/archive", timeout=30)
    assert archive.status_code == 200, archive.text

    promote = session.post(
        f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/promote-request",
        json={
            "strategy_version_id": v2["version_id"],
            "request_note": "archived promote deny",
            "require_validation": True,
            "require_dry_run": True,
            "requested_stage": None,
        },
        timeout=30,
    )
    assert promote.status_code == 400
    assert "strategy_archived_cannot_promote" in promote.text


def test_active_and_production_pointer_sync_after_approve():
    base = _require_base_url()
    session = _admin_session()
    strategy_id, _v1, v2 = _prepare_strategy(session, base)
    request_id = _create_promote_request(session, base, strategy_id, v2["version_id"], note="pointer sync")

    approve = session.post(
        f"{base}/api/strategy-domain/admin/promotion-requests/{request_id}/approve",
        json={"note": "sync approve"},
        timeout=30,
    )
    assert approve.status_code == 200, approve.text

    detail = session.get(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}", timeout=30)
    assert detail.status_code == 200, detail.text
    assert detail.json().get("strategy", {}).get("active_version_id") == v2["version_id"]

    items = _fetch_lifecycle(session, base, strategy_id)
    prod_rows = [item for item in items if bool(item.get("is_production"))]
    active_rows = [item for item in items if bool(item.get("is_active"))]
    assert len(prod_rows) == 1
    assert len(active_rows) == 1
    assert prod_rows[0]["strategy_version_id"] == v2["version_id"]
    assert active_rows[0]["strategy_version_id"] == v2["version_id"]


def test_lifecycle_pointer_consistency_and_audit_presence_under_race():
    base = _require_base_url()
    session = _admin_session()
    token = _login_token(base)
    strategy_id, v1, v2 = _prepare_strategy(session, base)
    request_id = _create_promote_request(session, base, strategy_id, v2["version_id"], note="audit race")

    def approve() -> int:
        resp = requests.post(
            f"{base}/api/strategy-domain/admin/promotion-requests/{request_id}/approve",
            json={"note": "race approve"},
            headers=_auth_headers(token),
            timeout=30,
        )
        return resp.status_code

    def activate_old() -> int:
        resp = requests.post(
            f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{v1['version_id']}",
            headers=_auth_headers(token),
            timeout=30,
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda fn: fn(), [approve, activate_old]))

    assert all(code in {200, 400, 409} for code in statuses)

    items = _fetch_lifecycle(session, base, strategy_id)
    _assert_single_active_and_production(items)

    detail = session.get(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}", timeout=30)
    assert detail.status_code == 200, detail.text
    active_version_id = detail.json().get("strategy", {}).get("active_version_id")
    active_rows = [item for item in items if bool(item.get("is_active"))]
    assert len(active_rows) == 1
    assert active_rows[0].get("strategy_version_id") == active_version_id

    audit = session.get(
        f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/audit-history",
        params={"limit": 200},
        timeout=30,
    )
    assert audit.status_code == 200, audit.text
    logs = audit.json().get("items", [])
    assert len(logs) > 0
    actions = [str(item.get("action") or "").lower() for item in logs]
    assert any("promot" in action or "activate" in action or "rollback" in action for action in actions)
