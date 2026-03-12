import json
import os
import random
import string
from datetime import datetime
from pathlib import Path

import pytest
import requests

SNAPSHOT_PATH = Path("/app/contracts/api_contract_snapshot.json")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct

    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _resolve_base_url()


def _random_email(prefix: str = "contract") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{prefix}_{suffix}@example.com"


def _matches_type(value, schema_type: str) -> bool:
    options = [option.strip() for option in schema_type.split("|")]
    for option in options:
        if option == "null" and value is None:
            return True
        if option == "string" and isinstance(value, str):
            return True
        if option == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if option == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if option == "boolean" and isinstance(value, bool):
            return True
        if option == "object" and isinstance(value, dict):
            return True
        if option == "array" and isinstance(value, list):
            return True
        if option == "datetime" and isinstance(value, str):
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                return True
            except ValueError:
                continue
        if option.startswith("array") and isinstance(value, list):
            return True
    return False


@pytest.fixture(scope="module")
def contract_snapshot():
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def user_token():
    email = _random_email()
    password = "Contract123!"

    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
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


def _contract_lookup(snapshot: dict, endpoint: str, method: str = "GET") -> dict:
    for item in snapshot.get("contracts", []):
        if item.get("endpoint") == endpoint and item.get("method") == method:
            return item
    raise AssertionError(f"contract not found: {method} {endpoint}")


def _assert_schema(payload, schema):
    if isinstance(schema, dict) and schema.get("type") == "array":
        assert isinstance(payload, list)
        if payload:
            _assert_schema(payload[0], schema["item"])
        return

    assert isinstance(payload, dict)
    for field_name, field_type in schema.items():
        assert field_name in payload, f"missing field: {field_name}"
        assert _matches_type(payload[field_name], field_type), f"invalid type for {field_name}: expected {field_type} got {type(payload[field_name]).__name__}"


def test_contract_endpoints_match_snapshot_schema(user_token, contract_snapshot):
    headers = {"Authorization": f"Bearer {user_token}"}

    for endpoint in [
        "/api/user/dashboard",
        "/api/user/portfolio",
        "/api/user/trades",
        "/api/user/scanner",
        "/api/user/signals",
    ]:
        contract = _contract_lookup(contract_snapshot, endpoint)
        response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=20)
        assert response.status_code in contract["status_codes"], f"status mismatch for {endpoint}"
        assert response.status_code == 200
        _assert_schema(response.json(), contract["response_schema"])


def test_reports_weekly_live_contract(user_token, contract_snapshot):
    headers = {"Authorization": f"Bearer {user_token}"}
    contract = _contract_lookup(contract_snapshot, "/api/user/reports/weekly")

    response = requests.get(f"{BASE_URL}/api/user/reports/weekly", headers=headers, timeout=20)
    assert response.status_code == 200
    assert response.status_code in contract["status_codes"]
    _assert_schema(response.json(), contract["response_schema"])
