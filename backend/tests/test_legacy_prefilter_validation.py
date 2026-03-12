import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
LEGACY_PREFILTERS = {
    "crypto_universe_prefilter_v1",
    "volatility_contraction_prefilter",
    "relative_strength_cluster_scanner_v2",
    "relative_strength_cluster_scanner_v2_alt",
}


@pytest.fixture(scope="module")
def admin_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL tanımlı değil")
    login = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if login.status_code != 200:
        pytest.skip(f"Admin login başarısız: {login.text}")
    token = login.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_legacy_prefilter_shadow_rows_available_in_strategy_status(admin_headers):
    run_response = requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
        headers=admin_headers,
        timeout=30,
    )
    assert run_response.status_code == 200, run_response.text

    response = requests.get(f"{BASE_URL}/api/admin/futures/strategy/status", headers=admin_headers, timeout=30)
    assert response.status_code == 200, response.text
    payload = response.json()

    rows = [row for row in (payload.get("legacy_formula_observability") or []) if row.get("strategy") in LEGACY_PREFILTERS]
    assert len(rows) >= 3
    for row in rows:
        assert row.get("source_type") == "legacy_formula"
        assert row.get("shadow_status") == "SHADOW_ONLY"
        assert isinstance(row.get("signal_frequency"), int)
        assert "diagnostic" in row
