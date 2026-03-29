#!/usr/bin/env python3
"""
P2 Execution Microstructure API Contract Tests
Tests: impact_model, hidden_liquidity, depth_decay, portfolio_capacity, execution_budget, slicing_plan
Endpoints: /guard-preview, /budget-status, /slicing-preview, /execution-replay/latest
"""

import json
import os
import sys
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
TIMEOUT = 60

results = {"passed": 0, "failed": 0, "tests": []}


def log_result(test_name: str, passed: bool, details: str = ""):
    status = "PASS" if passed else "FAIL"
    results["tests"].append({"name": test_name, "status": status, "details": details})
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1
    print(f"[{status}] {test_name}: {details}")


def get_token():
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} - {resp.text[:200]}")
        sys.exit(1)
    return resp.json().get("access_token")


def main():
    print(f"Testing P2 Execution Microstructure API at {BASE_URL}")
    print("=" * 60)
    
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test 1: Guard preview returns impact_model with P2 fields
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            impact = data.get("impact_model", {})
            required = ["square_root_impact", "performance_degradation_pct", "impact_ratio", "impact_score", "liquidity_tier"]
            missing = [f for f in required if f not in impact]
            if not missing:
                log_result("guard_preview_impact_model", True, f"All P2 impact_model fields present: {required}")
            else:
                log_result("guard_preview_impact_model", False, f"Missing fields: {missing}")
        else:
            log_result("guard_preview_impact_model", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("guard_preview_impact_model", False, str(e))

    # Test 2: Guard preview returns hidden_liquidity
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            hidden = data.get("hidden_liquidity", {})
            if "hidden_liquidity_ratio" in hidden and "state" in hidden and hidden["state"] in {"LOW", "MEDIUM", "HIGH"}:
                log_result("guard_preview_hidden_liquidity", True, f"state={hidden['state']}, ratio={hidden.get('hidden_liquidity_ratio')}")
            else:
                log_result("guard_preview_hidden_liquidity", False, f"Invalid hidden_liquidity: {hidden}")
        else:
            log_result("guard_preview_hidden_liquidity", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("guard_preview_hidden_liquidity", False, str(e))

    # Test 3: Guard preview returns depth_decay
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            decay = data.get("depth_decay", {})
            if "decay_ratio" in decay and "state" in decay and decay["state"] in {"STABLE", "ELEVATED", "RAPID"}:
                log_result("guard_preview_depth_decay", True, f"state={decay['state']}, ratio={decay.get('decay_ratio')}")
            else:
                log_result("guard_preview_depth_decay", False, f"Invalid depth_decay: {decay}")
        else:
            log_result("guard_preview_depth_decay", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("guard_preview_depth_decay", False, str(e))

    # Test 4: Guard preview returns portfolio_capacity
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            capacity = data.get("portfolio_capacity", {})
            required = ["same_symbol_open_notional", "same_strategy_open_notional", "combined_load_notional", "combined_load_ratio", "performance_degradation_pct"]
            missing = [f for f in required if f not in capacity]
            if not missing:
                log_result("guard_preview_portfolio_capacity", True, f"All P2 portfolio_capacity fields present")
            else:
                log_result("guard_preview_portfolio_capacity", False, f"Missing fields: {missing}")
        else:
            log_result("guard_preview_portfolio_capacity", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("guard_preview_portfolio_capacity", False, str(e))

    # Test 5: Guard preview returns execution_budget
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            budget = data.get("execution_budget", {})
            required = ["state", "symbol_budget_notional", "strategy_budget_notional", "impact_budget_bps", "symbol_budget_used", "strategy_budget_used", "allowed_notional", "reasons"]
            missing = [f for f in required if f not in budget]
            if not missing and budget.get("state") in {"ALLOW", "REDUCE_SIZE", "BLOCK"}:
                log_result("guard_preview_execution_budget", True, f"state={budget['state']}, all fields present")
            else:
                log_result("guard_preview_execution_budget", False, f"Missing fields: {missing} or invalid state: {budget.get('state')}")
        else:
            log_result("guard_preview_execution_budget", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("guard_preview_execution_budget", False, str(e))

    # Test 6: Guard preview returns slicing_plan
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            plan = data.get("slicing_plan", {})
            required = ["slice_count", "slice_notional", "interval_ms", "preferred_order_type", "execution_style", "should_slice"]
            missing = [f for f in required if f not in plan]
            if not missing and isinstance(plan.get("should_slice"), bool):
                log_result("guard_preview_slicing_plan", True, f"slice_count={plan['slice_count']}, should_slice={plan['should_slice']}")
            else:
                log_result("guard_preview_slicing_plan", False, f"Missing fields: {missing}")
        else:
            log_result("guard_preview_slicing_plan", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("guard_preview_slicing_plan", False, str(e))

    # Test 7: Budget status endpoint
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/budget-status",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            required = ["state", "execution_budget", "portfolio_capacity", "impact_model"]
            missing = [f for f in required if f not in data]
            if not missing:
                log_result("budget_status_endpoint", True, f"All required fields present: {required}")
            else:
                log_result("budget_status_endpoint", False, f"Missing fields: {missing}")
        else:
            log_result("budget_status_endpoint", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("budget_status_endpoint", False, str(e))

    # Test 8: Slicing preview endpoint
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/slicing-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            required = ["state", "execution_recommendation", "slicing_plan", "impact_model", "hidden_liquidity", "depth_decay"]
            missing = [f for f in required if f not in data]
            if not missing:
                log_result("slicing_preview_endpoint", True, f"All required fields present: {required}")
            else:
                log_result("slicing_preview_endpoint", False, f"Missing fields: {missing}")
        else:
            log_result("slicing_preview_endpoint", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("slicing_preview_endpoint", False, str(e))

    # Test 9: Execution replay latest returns P2 fields
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/execution-replay/latest",
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                if "should_have_been_sliced" in data and "slicing_plan" in data:
                    log_result("execution_replay_latest_p2_fields", True, f"should_have_been_sliced={data['should_have_been_sliced']}")
                else:
                    log_result("execution_replay_latest_p2_fields", False, f"Missing P2 fields in execution replay")
            else:
                log_result("execution_replay_latest_p2_fields", True, f"status={data.get('status')} (no execution data)")
        else:
            log_result("execution_replay_latest_p2_fields", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("execution_replay_latest_p2_fields", False, str(e))

    # Test 10: P0/P1 regression - status endpoint
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/status",
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if "portfolio_microstructure_state" in data:
                log_result("p0_regression_status", True, f"portfolio_microstructure_state present")
            else:
                log_result("p0_regression_status", False, "Missing portfolio_microstructure_state")
        else:
            log_result("p0_regression_status", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("p0_regression_status", False, str(e))

    # Test 11: P0/P1 regression - venues endpoint
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/venues",
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if "tracked_symbols" in data and "venues" in data:
                binance = data.get("venues", {}).get("binance", {})
                if "venue_health_score" in binance and "liquidity_stress_score" in binance:
                    log_result("p1_regression_venues", True, f"P1 venue health fields present")
                else:
                    log_result("p1_regression_venues", False, "Missing P1 venue health fields")
            else:
                log_result("p1_regression_venues", False, "Missing tracked_symbols or venues")
        else:
            log_result("p1_regression_venues", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("p1_regression_venues", False, str(e))

    # Test 12: P1 regression - guard preview P1 fields
    try:
        resp = requests.get(
            f"{BASE_URL}/api/admin/futures/microstructure/guard-preview",
            params={"symbol": "BTCUSDT", "side": "buy", "size": 0.1, "price": 65000},
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            p1_fields = ["slippage_decomposition", "market_regime", "execution_recommendation", "venue_health"]
            p0_fields = ["state", "selected_venue", "market_snapshot", "capacity"]
            missing_p1 = [f for f in p1_fields if f not in data]
            missing_p0 = [f for f in p0_fields if f not in data]
            if not missing_p1 and not missing_p0:
                log_result("p0p1_regression_guard_preview", True, "All P0/P1 fields present")
            else:
                log_result("p0p1_regression_guard_preview", False, f"Missing P1: {missing_p1}, P0: {missing_p0}")
        else:
            log_result("p0p1_regression_guard_preview", False, f"Status {resp.status_code}")
    except Exception as e:
        log_result("p0p1_regression_guard_preview", False, str(e))

    # Summary
    print("=" * 60)
    print(f"SUMMARY: {results['passed']} passed, {results['failed']} failed")
    
    # Save results
    with open("/app/test_reports/execution_microstructure_p2_api_probe.json", "w") as f:
        json.dump(results, f, indent=2)
    
    return results["failed"] == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
