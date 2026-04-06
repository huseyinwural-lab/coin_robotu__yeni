import os
import time
from datetime import datetime, timezone

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture()
def admin_session():
    session = requests.Session()
    login_response = None
    for attempt in range(1, 4):
        try:
            login_response = session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=30,
            )
            if login_response.status_code == 200:
                break
        except requests.RequestException:
            login_response = None
        if attempt < 3:
            time.sleep(1.5)

    if login_response is None:
        pytest.skip("admin_login_failed_timeout")
    if login_response.status_code != 200:
        pytest.skip(f"admin_login_failed: {login_response.status_code}")

    token = login_response.json().get("access_token") or login_response.json().get("token")
    if not token:
        pytest.skip("admin_token_missing")
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


def _builder_payload(policy_code: str) -> dict:
    return {
        "policy_code": policy_code,
        "version_label": "mapping_regression_v1",
        "description": "policy mapping regression",
        "change_summary": "mapping regression coverage",
        "scope": {
            "environment": "dev",
            "strategy": "breakout_live",
            "symbol": "btcusdt",
        },
        "rules": [
            {
                "rule_id": "rule_1",
                "action": "BLOCK",
                "severity": "HIGH",
                "logical_operator": "AND",
                "conditions": [
                    {"field": "exposure", "operator": ">", "value": "100000"},
                ],
            }
        ],
    }


def test_policy_builder_validate_maps_scope_strategy_symbol(admin_session):
    policy_code = f"TEST_MAPPING_VALIDATE_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    payload = _builder_payload(policy_code)

    response = admin_session.post(f"{BASE_URL}/api/admin/execution-policies/validate", json=payload, timeout=30)
    assert response.status_code == 200

    data = response.json()
    schema = data.get("schema") or {}
    scope = schema.get("scope") or {}

    assert schema.get("policy_code") == policy_code
    assert scope.get("strategy") == payload["scope"]["strategy"]
    assert scope.get("symbol") == payload["scope"]["symbol"].upper()


def test_policy_builder_create_version_persists_scope_mapping(admin_session):
    policy_code = f"TEST_MAPPING_CREATE_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    payload = _builder_payload(policy_code)

    create_response = admin_session.post(
        f"{BASE_URL}/api/admin/execution-policies/builder/versions",
        json=payload,
        timeout=30,
    )
    assert create_response.status_code in {200, 201}
    create_data = create_response.json()

    version_id = create_data.get("version_id")
    assert version_id
    assert create_data.get("policy_code") == policy_code

    validate_response = admin_session.post(
        f"{BASE_URL}/api/admin/execution-policies/versions/{version_id}/validate",
        timeout=30,
    )
    assert validate_response.status_code == 200
    validate_data = validate_response.json()
    validate_scope = (validate_data.get("schema") or {}).get("scope") or {}

    assert validate_data.get("policy_code") == policy_code
    assert validate_scope.get("strategy") == payload["scope"]["strategy"]
    assert validate_scope.get("symbol") == payload["scope"]["symbol"].upper()