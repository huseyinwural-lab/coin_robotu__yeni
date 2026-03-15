import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")
LEGACY_STRATEGIES = {
    "momentum_volume_breakout_v3",
    "volatility_breakout_v2",
    "adaptive_level_breakout_v2",
    "oscillator_composite_reversion_v2",
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


def test_legacy_strategy_shadow_validation_contract(admin_headers):
    run_response = requests.post(
        f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
        headers=admin_headers,
        timeout=30,
    )
    assert run_response.status_code == 200, run_response.text
    status_payload = run_response.json()

    legacy_rows = [
        row
        for row in (status_payload.get("legacy_formula_observability") or [])
        if row.get("strategy") in LEGACY_STRATEGIES
    ]
    assert len(legacy_rows) == 4

    required_fields = {
        "strategy",
        "family_code",
        "source_type",
        "shadow_status",
        "signal_frequency",
        "shadow_pnl",
        "false_breakout_rate",
        "confidence_drift",
    }
    for row in legacy_rows:
        assert required_fields.issubset(set(row.keys()))
        assert row["source_type"] == "legacy_formula"
        assert row["shadow_status"] == "SHADOW_ONLY"

    signal_distribution = status_payload.get("strategy_signal_distribution") or []
    signal_map = {row.get("strategy"): row for row in signal_distribution}
    for strategy in LEGACY_STRATEGIES:
        assert strategy in signal_map
        assert int(signal_map[strategy].get("allowed_total") or 0) == 0


def test_legacy_strategy_lifecycle_locked_disabled(admin_headers):
    governance_response = requests.get(
        f"{BASE_URL}/api/admin/futures/strategy-governance",
        headers=admin_headers,
        timeout=30,
    )
    assert governance_response.status_code == 200, governance_response.text
    payload = governance_response.json()

    lifecycle_rows = payload.get("lifecycle_state") or []
    lifecycle_map = {row.get("strategy"): row.get("lifecycle_state") for row in lifecycle_rows}
    for strategy in LEGACY_STRATEGIES:
        assert lifecycle_map.get(strategy) == "DISABLED"
