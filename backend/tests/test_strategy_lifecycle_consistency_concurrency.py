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


def _admin_session() -> requests.Session:
    base = _require_base_url()
    session = requests.Session()
    resp = session.post(
        f"{base}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if resp.status_code != 200:
        pytest.skip("admin login başarısız; integration concurrency test atlandı")
    token = resp.json().get("access_token")
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
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


def test_concurrent_activate_keeps_single_active_version():
    base = _require_base_url()
    session = _admin_session()
    strategy_id, v1, v2 = _prepare_strategy(session, base)

    def activate(version_id: str) -> int:
        resp = session.post(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{version_id}", timeout=30)
        return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(activate, [v1["version_id"], v2["version_id"]]))

    assert any(code == 200 for code in statuses)
    assert all(code in {200, 409} for code in statuses)

    lifecycle = session.get(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/lifecycle", timeout=30)
    assert lifecycle.status_code == 200
    items = lifecycle.json().get("items", [])
    active_count = len([item for item in items if bool(item.get("is_active"))])
    assert active_count == 1


def test_concurrent_rollback_and_promote_keeps_consistent_state():
    base = _require_base_url()
    session = _admin_session()
    strategy_id, v1, v2 = _prepare_strategy(session, base)

    activate_v2 = session.post(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/activate/{v2['version_id']}", timeout=30)
    assert activate_v2.status_code == 200

    promote = session.post(
        f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/promote-request",
        json={
            "strategy_version_id": v2["version_id"],
            "request_note": "race promote",
            "require_validation": True,
            "require_dry_run": True,
            "requested_stage": None,
        },
        timeout=30,
    )
    assert promote.status_code == 200
    request_id = promote.json()["request_id"]

    def approve() -> int:
        resp = session.post(
            f"{base}/api/strategy-domain/admin/promotion-requests/{request_id}/approve",
            json={"note": "approve race"},
            timeout=30,
        )
        return resp.status_code

    def rollback() -> int:
        resp = session.post(
            f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/rollback",
            json={"target_version_id": v1["version_id"], "reason": "race rollback"},
            timeout=30,
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda fn: fn(), [approve, rollback]))

    assert all(code in {200, 400, 409} for code in statuses)

    lifecycle = session.get(f"{base}/api/strategy-domain/admin/strategies/{strategy_id}/lifecycle", timeout=30)
    assert lifecycle.status_code == 200
    items = lifecycle.json().get("items", [])
    active_count = len([item for item in items if bool(item.get("is_active"))])
    production_count = len([item for item in items if bool(item.get("is_production"))])
    assert active_count == 1
    assert production_count <= 1
