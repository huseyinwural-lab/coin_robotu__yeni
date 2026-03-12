import os
import random
import string
from pathlib import Path

import requests

ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


def _rand_email(prefix: str = "sim") -> str:
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"


def test_risk_simulation_mode_endpoint_and_manual_override_log():
    base = _resolve_base_url()

    admin_login = requests.post(
        f"{base}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    email = _rand_email()
    password = "RiskSim123!"
    register = requests.post(f"{base}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200
    user_id = register.json()["id"]

    approve = requests.post(
        f"{base}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200

    simulation = requests.post(
        f"{base}/api/admin/risk-simulation",
        headers=admin_headers,
        json={
            "user_id": user_id,
            "intent_payload": {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 120,
                "strategy_binding": "spot_pullback_v1",
                "volatility_pct": 3.5,
                "position_size_value": 120,
            },
            "apply_override": True,
            "override_action_type": "risk_simulation_override",
            "override_reason": "test_override",
        },
        timeout=20,
    )
    assert simulation.status_code == 200
    payload = simulation.json()
    assert "strategy_conflict" in payload
    assert "allocation_adjustment" in payload
    assert "hedge_suggestion" in payload
    assert payload["projected_risk_score"] >= 0

    overrides = requests.get(f"{base}/api/admin/manual-overrides", headers=admin_headers, timeout=20)
    assert overrides.status_code == 200
    rows = overrides.json()
    assert isinstance(rows, list)
    assert any(row.get("action_type") == "risk_simulation_override" for row in rows)
