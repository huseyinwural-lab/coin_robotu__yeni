import os
import random
import string
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text().splitlines():
            if raw_line.strip().startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def _unique_email(prefix: str = "phase6close") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{prefix}_{suffix}@example.com"


def _register_and_login_user() -> str:
    email = _unique_email("close")
    password = "CloseFlow123!"
    register = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200
    user_id = register.json()["id"]

    admin_login = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert approve.status_code == 200

    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200
    return login.json()["access_token"]


class TestPhase6ClosureBackend:
    def test_scanner_signal_assisted_flow(self):
        user_token = _register_and_login_user()
        user_headers = {"Authorization": f"Bearer {user_token}"}

        mode_put = requests.put(
            f"{BASE_URL}/api/user/signal-mode",
            headers=user_headers,
            json={"mode": "ASSISTED"},
            timeout=20,
        )
        assert mode_put.status_code == 200
        assert mode_put.json()["mode"] == "ASSISTED"

        run_response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json={"max_results": 25},
            timeout=20,
        )
        assert run_response.status_code == 200, run_response.text
        run_data = run_response.json()
        assert run_data["mode"] == "ASSISTED"

        scanner_results = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers=user_headers,
            timeout=20,
        )
        assert scanner_results.status_code == 200
        assert isinstance(scanner_results.json(), list)

        signals_response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=user_headers,
            timeout=20,
        )
        assert signals_response.status_code == 200
        signals = signals_response.json()
        assert isinstance(signals, list)

        pending = [item for item in signals if item["status"] == "pending"]
        if pending:
            signal_id = pending[0]["id"]

            pre_portfolio = requests.get(f"{BASE_URL}/api/user/portfolio", headers=user_headers, timeout=20)
            pre_trades = requests.get(f"{BASE_URL}/api/user/trades", headers=user_headers, timeout=20)
            assert pre_portfolio.status_code == 200
            assert pre_trades.status_code == 200
            pre_open = pre_portfolio.json()["open_positions_count"]
            pre_trade_count = len(pre_trades.json())

            approve = requests.post(
                f"{BASE_URL}/api/user/signal/{signal_id}/approve",
                headers=user_headers,
                json={"note": "approve_for_phase6_closure"},
                timeout=20,
            )
            assert approve.status_code == 200, approve.text
            assert approve.json()["status"] == "approved"

            post_portfolio = requests.get(f"{BASE_URL}/api/user/portfolio", headers=user_headers, timeout=20)
            post_trades = requests.get(f"{BASE_URL}/api/user/trades", headers=user_headers, timeout=20)
            assert post_portfolio.status_code == 200
            assert post_trades.status_code == 200
            assert post_portfolio.json()["open_positions_count"] >= pre_open
            assert len(post_trades.json()) >= pre_trade_count

    def test_reject_flow_and_admin_forbidden(self):
        user_token = _register_and_login_user()
        user_headers = {"Authorization": f"Bearer {user_token}"}

        run_response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json={"max_results": 20},
            timeout=20,
        )
        assert run_response.status_code == 200

        signals_response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=user_headers,
            timeout=20,
        )
        assert signals_response.status_code == 200
        pending = [item for item in signals_response.json() if item["status"] == "pending"]
        if pending:
            reject = requests.post(
                f"{BASE_URL}/api/user/signal/{pending[0]['id']}/reject",
                headers=user_headers,
                json={"note": "reject_for_phase6_closure"},
                timeout=20,
            )
            assert reject.status_code == 200
            assert reject.json()["status"] == "rejected"

        admin_login = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        assert admin_login.status_code == 200
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        for method, endpoint, payload in [
            (requests.post, "/api/user/scanner/run", {"max_results": 10}),
            (requests.get, "/api/user/scanner/results", None),
            (requests.get, "/api/user/signals", None),
            (requests.get, "/api/user/portfolio", None),
            (requests.get, "/api/user/performance", None),
            (requests.get, "/api/user/trades", None),
        ]:
            if payload is None:
                response = method(f"{BASE_URL}{endpoint}", headers=admin_headers, timeout=20)
            else:
                response = method(f"{BASE_URL}{endpoint}", headers=admin_headers, json=payload, timeout=20)
            assert response.status_code == 403, f"{endpoint} expected 403 got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])