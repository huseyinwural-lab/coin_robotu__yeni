"""Production Gate P2 Analytics & Timeline Test Suite."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from sqlalchemy import create_engine, text

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://strategy-version-gov.preview.emergentagent.com"
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("PG_DSN")

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture()
def authed_session() -> requests.Session:
    session = requests.Session()
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, login.text
    token = login.json().get("access_token")
    assert token
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


def _db_url() -> str:
    if DATABASE_URL:
        return DATABASE_URL
    with open("/app/backend/.env", "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("DATABASE_URL not found")


def test_p2_history_compare_and_flapping(authed_session: requests.Session):
    rerun = authed_session.post(f"{BASE_URL}/api/phase4/admin/production-gate/checks/rerun", timeout=60)
    assert rerun.status_code == 200, rerun.text

    history_resp = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/checks/history?limit=200", timeout=30)
    assert history_resp.status_code == 200, history_resp.text
    history = history_resp.json()
    assert isinstance(history.get("items"), list)
    assert len(history.get("items", [])) >= 1

    compare_resp = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/checks/compare?limit=200", timeout=30)
    assert compare_resp.status_code == 200, compare_resp.text
    compare = compare_resp.json()
    assert len(compare.get("items", [])) >= 1

    # deterministic flapping injection (PASS/FAIL alternation)
    engine = create_engine(_db_url())
    with engine.begin() as conn:
        meta_raw = conn.execute(text("SELECT metadata_json FROM brand_settings WHERE id='default'"))
        metadata = meta_raw.scalar() or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        pg = metadata.get("production_gate_control") or {}
        rows = list(pg.get("check_history") or [])
        now = datetime.now(timezone.utc)
        alternating = ["PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL"]
        for idx, state in enumerate(alternating):
            rows.append(
                {
                    "check_key": "release_gate_contract",
                    "status": state,
                    "timestamp": (now - timedelta(seconds=idx * 40)).isoformat(),
                    "latency_ms": 10 + idx,
                    "error_code": None if state == "PASS" else "release_gate_blocked",
                    "run_id": f"p2-flap-{idx}",
                    "flapping": False,
                }
            )
        pg["check_history"] = rows
        metadata["production_gate_control"] = pg
        conn.execute(
            text("UPDATE brand_settings SET metadata_json=:metadata WHERE id='default'"),
            {"metadata": json.dumps(metadata)},
        )

    history_after = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/checks/history?limit=300", timeout=30)
    assert history_after.status_code == 200
    payload = history_after.json()
    assert "release_gate_contract" in payload.get("flapping_checks", []), payload


def test_p2_override_analytics_timeline_and_risk(authed_session: requests.Session):
    analytics_resp = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/override-analytics", timeout=30)
    assert analytics_resp.status_code == 200, analytics_resp.text
    analytics = analytics_resp.json()

    for key in [
        "override_count",
        "override_rate",
        "reason_distribution",
        "top_override_checks",
        "expiry_count",
        "revoke_count",
        "expiry_vs_revoke_ratio",
        "timeline",
    ]:
        assert key in analytics, f"missing analytics key: {key}"

    timeline_resp = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/timeline?limit=200", timeout=30)
    assert timeline_resp.status_code == 200, timeline_resp.text
    timeline = timeline_resp.json()
    assert isinstance(timeline.get("items"), list)
    assert len(timeline.get("items", [])) >= 1

    timeline_filtered = authed_session.get(
        f"{BASE_URL}/api/phase4/admin/production-gate/timeline?categories=checks,overrides&limit=200",
        timeout=30,
    )
    assert timeline_filtered.status_code == 200
    items = timeline_filtered.json().get("items", [])
    assert all(item.get("category") in {"checks", "overrides"} for item in items)

    gate_resp = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate", timeout=30)
    assert gate_resp.status_code == 200
    gate = gate_resp.json()
    assert "risk_score" in gate and "risk_level" in gate
    assert 0 <= int(gate["risk_score"]) <= 100
    assert gate["risk_level"] in {"LOW", "MEDIUM", "HIGH"}


def test_p2_export_v2_contains_history_analytics_timeline_and_risk(authed_session: requests.Session):
    date_from = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    date_to = datetime.now(timezone.utc).isoformat()
    export_resp = authed_session.get(
        f"{BASE_URL}/api/phase4/admin/production-gate/export/raw",
        params={"scope": "full", "date_from": date_from, "date_to": date_to},
        timeout=30,
    )
    assert export_resp.status_code == 200, export_resp.text
    payload = export_resp.json()

    export_payload = payload.get("export_payload") or {}
    state_summary = export_payload.get("active_state_summary") or {}
    assert "risk_score" in state_summary
    assert "risk_level" in state_summary
    assert "check_history_snapshot" in export_payload
    assert "override_analytics_summary" in export_payload
    assert "timeline_snapshot" in export_payload
