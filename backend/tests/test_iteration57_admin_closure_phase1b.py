import os
from pathlib import Path

import requests


def _resolve_base_url() -> str:
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _resolve_base_url()


def _admin_headers() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def test_admin_closure_panels_inventory_contract():
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/admin/closure/panels", headers=headers, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "generated_at" in data
    assert "panels" in data and isinstance(data["panels"], list)
    assert "contracts" in data and isinstance(data["contracts"], dict)
    assert len(data["panels"]) >= 10

    first_panel = data["panels"][0]
    assert "panel_key" in first_panel
    assert "route" in first_panel
    assert "state_coverage" in first_panel
    assert "state_contract_pass" in first_panel


def test_admin_closure_canonical_metrics_contract():
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/admin/closure/canonical-metrics", headers=headers, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()

    required_fields = [
        "generated_at",
        "active_positions",
        "queued_executions",
        "pending_executions",
        "total_exposure_7d",
        "risk_alerts_24h",
        "avg_risk_score_24h",
        "queued_in_recent_200",
    ]
    for field in required_fields:
        assert field in data


def test_admin_closure_consistency_contract():
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/admin/closure/consistency", headers=headers, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()

    assert "status" in data
    assert "mismatch_count" in data
    assert "canonical_metrics" in data and isinstance(data["canonical_metrics"], dict)
    assert "panel_proxy_metrics" in data and isinstance(data["panel_proxy_metrics"], dict)
    assert "checks" in data and isinstance(data["checks"], list)
    assert len(data["checks"]) >= 4

    first_check = data["checks"][0]
    for key in ["metric_name", "canonical_value", "panel_value", "delta", "tolerance", "in_tolerance"]:
        assert key in first_check


def test_admin_closure_requires_auth():
    response = requests.get(f"{BASE_URL}/api/admin/closure/panels", timeout=20)
    assert response.status_code in [401, 403]


# ------------------ Admin Dashboard State Tests ------------------
def test_admin_dashboard_summary_contract():
    """Test /dashboard/summary returns proper metrics/alerts/heartbeat structure"""
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "metrics" in data and isinstance(data["metrics"], dict)
    assert "alerts" in data and isinstance(data["alerts"], list)
    assert "heartbeat" in data


def test_admin_dashboard_summary_metrics_fields():
    """Test /dashboard/summary metrics contains expected fields"""
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    metrics = data.get("metrics", {})
    # At minimum these keys should exist
    for key in ["users", "running_bots", "risk_policies", "strategy_templates"]:
        assert key in metrics, f"Missing key: {key}"


# ------------------ Strategy Allocation Page State Tests ------------------
def test_admin_strategy_allocation_contract():
    """Test /admin/strategy-allocation returns list with required fields"""
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", headers=headers, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)
    # Can be empty but structure should be consistent
    if len(data) > 0:
        first = data[0]
        for key in ["strategy_id", "capital_weight", "max_capital", "current_capital", "state"]:
            assert key in first, f"Missing key: {key}"


def test_admin_strategy_allocation_requires_auth():
    """Test /admin/strategy-allocation requires admin auth"""
    response = requests.get(f"{BASE_URL}/api/admin/strategy-allocation", timeout=20)
    assert response.status_code in [401, 403]


# ------------------ Strategy Intelligence Page State Tests ------------------
def test_admin_strategy_intelligence_contract():
    """Test /admin/strategy-intelligence returns proper structure"""
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/admin/strategy-intelligence", headers=headers, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    required_fields = ["generated_at", "strategy_conflicts", "capital_rebalance_events", "hedge_suggestions"]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"
    assert isinstance(data["strategy_conflicts"], list)
    assert isinstance(data["capital_rebalance_events"], list)
    assert isinstance(data["hedge_suggestions"], list)


def test_admin_manual_overrides_contract():
    """Test /admin/manual-overrides returns list"""
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/admin/manual-overrides", headers=headers, timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)


def test_admin_strategy_intelligence_requires_auth():
    """Test /admin/strategy-intelligence requires admin auth"""
    response = requests.get(f"{BASE_URL}/api/admin/strategy-intelligence", timeout=20)
    assert response.status_code in [401, 403]


def test_admin_manual_overrides_requires_auth():
    """Test /admin/manual-overrides requires admin auth"""
    response = requests.get(f"{BASE_URL}/api/admin/manual-overrides", timeout=20)
    assert response.status_code in [401, 403]


# ------------------ Closure Endpoints Auth Tests ------------------
def test_admin_closure_canonical_metrics_requires_auth():
    """Test /admin/closure/canonical-metrics requires admin auth"""
    response = requests.get(f"{BASE_URL}/api/admin/closure/canonical-metrics", timeout=20)
    assert response.status_code in [401, 403]


def test_admin_closure_consistency_requires_auth():
    """Test /admin/closure/consistency requires admin auth"""
    response = requests.get(f"{BASE_URL}/api/admin/closure/consistency", timeout=20)
    assert response.status_code in [401, 403]
