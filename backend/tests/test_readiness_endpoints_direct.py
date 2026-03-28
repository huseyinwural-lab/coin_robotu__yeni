# Readiness endpoint contract tests - direct execution
import requests

BASE_URL = "https://futures-health-check.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


def get_admin_token():
    """Get admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if response.status_code != 200:
        print(f"Admin login failed: {response.status_code} - {response.text}")
        return None
    return response.json().get("access_token")


def test_live_readiness_endpoint_contract():
    """Test /api/admin/futures/live-readiness endpoint contract"""
    token = get_admin_token()
    if not token:
        print("SKIP: Admin login failed")
        return False
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.get(f"{BASE_URL}/api/admin/futures/live-readiness", headers=headers, timeout=20)
    
    if response.status_code != 200:
        print(f"FAIL: live-readiness endpoint returned {response.status_code}")
        return False
    
    payload = response.json()
    required_fields = [
        "readiness_score",
        "readiness_state",
        "go_live_allowed",
        "execution_allowed",
        "summary",
        "steps",
        "scores",
        "by_layer",
        "blocking_failures",
        "warnings",
        "unknowns",
        "reason_codes",
        "data_freshness",
        "position_sync_state",
        "order_reconciliation_state",
        "balance_integrity_state",
        "exchange_latency_state",
        "alerts",
    ]
    
    missing = [f for f in required_fields if f not in payload]
    if missing:
        print(f"FAIL: Missing fields: {missing}")
        return False
    
    # Verify contract invariants
    assert isinstance(payload.get("scores"), dict), "scores must be dict"
    assert isinstance(payload.get("by_layer"), dict), "by_layer must be dict"
    assert isinstance(payload.get("blocking_failures"), list), "blocking_failures must be list"
    assert isinstance(payload.get("warnings"), list), "warnings must be list"
    assert isinstance(payload.get("unknowns"), list), "unknowns must be list"
    assert isinstance(payload.get("reason_codes"), list), "reason_codes must be list"
    
    # Verify layer keys
    expected_layers = ["core", "trading_state", "exchange", "execution", "risk", "infra", "latency", "safety"]
    for layer in expected_layers:
        assert layer in payload.get("scores", {}), f"scores missing layer: {layer}"
        assert layer in payload.get("by_layer", {}), f"by_layer missing layer: {layer}"
    
    print(f"PASS: live-readiness endpoint contract verified")
    print(f"  readiness_state: {payload.get('readiness_state')}")
    print(f"  go_live_allowed: {payload.get('go_live_allowed')}")
    print(f"  execution_allowed: {payload.get('execution_allowed')}")
    print(f"  blocking_failures count: {len(payload.get('blocking_failures', []))}")
    print(f"  unknowns count: {len(payload.get('unknowns', []))}")
    return True


def test_readiness_score_endpoint_contract():
    """Test /api/admin/futures/readiness-score endpoint contract"""
    token = get_admin_token()
    if not token:
        print("SKIP: Admin login failed")
        return False
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.get(f"{BASE_URL}/api/admin/futures/readiness-score", headers=headers, timeout=20)
    
    if response.status_code != 200:
        print(f"FAIL: readiness-score endpoint returned {response.status_code}")
        return False
    
    payload = response.json()
    required_fields = [
        "readiness_score",
        "readiness_state",
        "position_sync_state",
        "order_reconciliation_state",
        "balance_integrity_state",
        "exchange_latency_state",
        "alerts",
    ]
    
    missing = [f for f in required_fields if f not in payload]
    if missing:
        print(f"FAIL: Missing fields: {missing}")
        return False
    
    print(f"PASS: readiness-score endpoint contract verified")
    print(f"  readiness_score: {payload.get('readiness_score')}")
    print(f"  readiness_state: {payload.get('readiness_state')}")
    return True


def test_live_readiness_history_endpoint():
    """Test /api/admin/futures/live-readiness/history endpoint"""
    token = get_admin_token()
    if not token:
        print("SKIP: Admin login failed")
        return False
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.get(f"{BASE_URL}/api/admin/futures/live-readiness/history", headers=headers, timeout=20)
    
    if response.status_code != 200:
        print(f"FAIL: live-readiness/history endpoint returned {response.status_code}")
        return False
    
    payload = response.json()
    if "items" not in payload:
        print("FAIL: Missing 'items' field")
        return False
    
    print(f"PASS: live-readiness/history endpoint contract verified")
    print(f"  items count: {len(payload.get('items', []))}")
    return True


def test_execution_readiness_endpoint():
    """Test /api/admin/execution-readiness endpoint"""
    token = get_admin_token()
    if not token:
        print("SKIP: Admin login failed")
        return False
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.get(f"{BASE_URL}/api/admin/execution-readiness", headers=headers, timeout=20)
    
    if response.status_code != 200:
        print(f"FAIL: execution-readiness endpoint returned {response.status_code}")
        return False
    
    payload = response.json()
    required_fields = [
        "exchange_connection",
        "permissions",
        "latency_ms",
        "order_test",
        "mode",
        "final_status",
        "mocked_flag",
        "reason_codes",
        "readiness_state",
        "execution_allowed",
        "go_live_allowed",
    ]
    
    missing = [f for f in required_fields if f not in payload]
    if missing:
        print(f"FAIL: Missing fields: {missing}")
        return False
    
    # Verify execution_allowed is False when blocking failures exist
    if payload.get("final_status") == "BLOCKED":
        assert payload.get("execution_allowed") is False, "execution_allowed must be False when BLOCKED"
    
    print(f"PASS: execution-readiness endpoint contract verified")
    print(f"  final_status: {payload.get('final_status')}")
    print(f"  execution_allowed: {payload.get('execution_allowed')}")
    print(f"  reason_codes: {payload.get('reason_codes')}")
    return True


def test_strategy_engine_unknown_blocks_readiness():
    """Verify strategy_engine UNKNOWN status blocks go_live_allowed"""
    token = get_admin_token()
    if not token:
        print("SKIP: Admin login failed")
        return False
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.get(f"{BASE_URL}/api/admin/futures/live-readiness", headers=headers, timeout=20)
    
    if response.status_code != 200:
        print(f"FAIL: live-readiness endpoint returned {response.status_code}")
        return False
    
    payload = response.json()
    
    # Find strategy_engine step
    steps = payload.get("steps", [])
    strategy_step = next((s for s in steps if s.get("step_key") == "strategy_engine"), None)
    
    if strategy_step:
        status = strategy_step.get("status")
        reason_code = strategy_step.get("reason_code")
        print(f"  strategy_engine status: {status}")
        print(f"  strategy_engine reason_code: {reason_code}")
        
        # If strategy_engine is UNKNOWN, go_live_allowed must be False
        if status == "UNKNOWN":
            assert payload.get("go_live_allowed") is False, "go_live_allowed must be False when strategy_engine is UNKNOWN"
            assert "STRATEGY_ENGINE_UNKNOWN" in payload.get("reason_codes", []), "STRATEGY_ENGINE_UNKNOWN must be in reason_codes"
            print("PASS: strategy_engine UNKNOWN correctly blocks go_live_allowed")
        else:
            print(f"INFO: strategy_engine status is {status}, not UNKNOWN")
    else:
        print("WARN: strategy_engine step not found in steps")
    
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Running Readiness Endpoint Contract Tests")
    print("=" * 60)
    
    results = []
    
    print("\n1. Testing live-readiness endpoint contract...")
    results.append(("live-readiness", test_live_readiness_endpoint_contract()))
    
    print("\n2. Testing readiness-score endpoint contract...")
    results.append(("readiness-score", test_readiness_score_endpoint_contract()))
    
    print("\n3. Testing live-readiness/history endpoint...")
    results.append(("live-readiness/history", test_live_readiness_history_endpoint()))
    
    print("\n4. Testing execution-readiness endpoint...")
    results.append(("execution-readiness", test_execution_readiness_endpoint()))
    
    print("\n5. Testing strategy_engine UNKNOWN blocks readiness...")
    results.append(("strategy_engine_unknown", test_strategy_engine_unknown_blocks_readiness()))
    
    print("\n" + "=" * 60)
    print("Summary:")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
