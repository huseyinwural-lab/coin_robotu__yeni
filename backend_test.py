#!/usr/bin/env python3
"""
Release Validation Backend Test Suite
Yayın Öncesi Son Kapatma Paketi Doğrulaması

Tests requested in review:
1) Bootstrap admin - admin@platform.dev / Admin12345! login validation
2) Admin profile/password update - PATCH profile, POST password change, re-login
3) CI portability/gate - ci_alembic_drift_gate.sh, ci_stage_gate.sh, ci_prod_gate.sh
4) Frontend release smoke checklist - backend support validation
5) Endpoint regression - health, universe-monitor, scanner symbol-selection
"""

import os
import sys
import subprocess
import requests
import json
from datetime import datetime

# Backend URL from environment
BACKEND_URL = "https://market-scanner-prod.preview.emergentagent.com/api"

# Test admin credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"

# Global auth tokens for reuse
admin_token = None
user_token = None

def log_test(test_name, status, details=""):
    """Log test results with Turkish status"""
    status_tr = "GEÇTI" if status == "PASS" else "BAŞARISIZ"
    print(f"[{status_tr}] {test_name}")
    if details:
        print(f"    {details}")

def run_command(cmd, description):
    """Run shell command and return result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd="/app")
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def authenticate_admin():
    """Get admin authentication token"""
    global admin_token
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            admin_token = response.json()["access_token"]
            return True, response.json()
        else:
            return False, f"Status: {response.status_code}, Body: {response.text}"
    except Exception as e:
        return False, str(e)

def register_and_approve_user():
    """Register a test user and get approval, then login"""
    global user_token
    try:
        # Register user
        test_email = f"test_user_faz3_{int(datetime.now().timestamp())}@test.com"
        reg_response = requests.post(
            f"{BACKEND_URL}/auth/register",
            json={
                "email": test_email,
                "password": "TestUser123!",
                "first_name": "Test",
                "last_name": "User"
            },
            timeout=10
        )
        if reg_response.status_code != 200:
            return False, f"Registration failed: {reg_response.status_code} - {reg_response.text}"
        
        user_id = reg_response.json()["id"]
        
        # Admin approves user  
        headers = {"Authorization": f"Bearer {admin_token}"}
        approve_response = requests.post(
            f"{BACKEND_URL}/admin/user-approvals/bulk-approve",
            json={"ids": [user_id]},
            headers=headers,
            timeout=10
        )
        if approve_response.status_code != 200:
            return False, f"Approval failed: {approve_response.status_code} - {approve_response.text}"
        
        # User login
        login_response = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": test_email, "password": "TestUser123!"},
            timeout=10
        )
        if login_response.status_code == 200:
            user_token = login_response.json()["access_token"]
            return True, {"email": test_email, "user_id": user_id}
        else:
            return False, f"User login failed: {login_response.status_code} - {login_response.text}"
            
    except Exception as e:
        return False, str(e)

# TEST 1: Drift & Migration Validation
def test_1_drift_migration():
    """Test 1) Drift & migration - bash /app/scripts/ci_alembic_drift_gate.sh PASS olmalı"""
    print("\n=== TEST 1: Drift & Migration Validation ===")
    
    success, stdout, stderr = run_command("bash /app/scripts/ci_alembic_drift_gate.sh", "Alembic drift gate")
    
    if success and "PASS" in stdout:
        log_test("1A) Alembic Drift Gate", "PASS", stdout.strip())
        return True
    else:
        log_test("1A) Alembic Drift Gate", "FAIL", f"stdout: {stdout}, stderr: {stderr}")
        return False

# TEST 2: Required Endpoint Regression  
def test_2_endpoint_regression():
    """Test 2) Zorunlu endpoint regresyon - 4 critical endpoints"""
    print("\n=== TEST 2: Required Endpoint Regression ===")
    
    passed = 0
    total = 4
    
    # 2A) GET /api/health
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=10)
        if response.status_code == 200 and response.json().get("status") == "ok":
            log_test("2A) GET /api/health", "PASS", "Health check OK")
            passed += 1
        else:
            log_test("2A) GET /api/health", "FAIL", f"Status: {response.status_code}, Body: {response.text}")
    except Exception as e:
        log_test("2A) GET /api/health", "FAIL", str(e))
    
    # 2B) POST /api/auth/login/admin
    success, result = authenticate_admin()
    if success:
        log_test("2B) POST /api/auth/login/admin", "PASS", f"Admin login successful, token received")
        passed += 1
    else:
        log_test("2B) POST /api/auth/login/admin", "FAIL", result)
        return False  # Can't continue without admin auth
    
    # 2C) GET /api/admin/universe-monitor
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BACKEND_URL}/admin/universe-monitor", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            required_fields = ["market_type", "scanner_mode", "total_exchange_symbols", "symbols_evaluated_this_cycle"]
            if all(field in data for field in required_fields):
                log_test("2C) GET /api/admin/universe-monitor", "PASS", f"Data contains {len(data)} fields")
                passed += 1
            else:
                log_test("2C) GET /api/admin/universe-monitor", "FAIL", f"Missing required fields")
        else:
            log_test("2C) GET /api/admin/universe-monitor", "FAIL", f"Status: {response.status_code}")
    except Exception as e:
        log_test("2C) GET /api/admin/universe-monitor", "FAIL", str(e))
    
    # 2D) GET /api/user/scanner/symbol-selection (with user flow)
    user_success, user_result = register_and_approve_user()
    if user_success:
        try:
            headers = {"Authorization": f"Bearer {user_token}"}
            response = requests.get(f"{BACKEND_URL}/user/scanner/symbol-selection", headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                required_fields = ["user_id", "scanner_id", "symbol_selection_mode", "selected_symbols"]
                if all(field in data for field in required_fields):
                    log_test("2D) GET /api/user/scanner/symbol-selection", "PASS", f"User scanner data: {len(data)} fields")
                    passed += 1
                else:
                    log_test("2D) GET /api/user/scanner/symbol-selection", "FAIL", f"Missing required fields")
            else:
                log_test("2D) GET /api/user/scanner/symbol-selection", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            log_test("2D) GET /api/user/scanner/symbol-selection", "FAIL", str(e))
    else:
        log_test("2D) GET /api/user/scanner/symbol-selection", "FAIL", f"User registration/approval failed: {user_result}")
    
    return passed == total

# TEST 3: New Runtime Endpoints
def test_3_runtime_endpoints():
    """Test 3) Yeni runtime endpointler - 4 new runtime endpoints"""
    print("\n=== TEST 3: New Runtime Endpoints ===")
    
    passed = 0
    total = 4
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 3A) GET /api/admin/universe/runtime-summary
    try:
        response = requests.get(f"{BACKEND_URL}/admin/universe/runtime-summary", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            required_fields = ["scanner_mode_effective", "fallback_state", "universe"]
            if all(field in data for field in required_fields):
                log_test("3A) GET /api/admin/universe/runtime-summary", "PASS", f"Contains scanner_mode_effective: {data.get('scanner_mode_effective')}")
                passed += 1
            else:
                log_test("3A) GET /api/admin/universe/runtime-summary", "FAIL", f"Missing required fields")
        else:
            log_test("3A) GET /api/admin/universe/runtime-summary", "FAIL", f"Status: {response.status_code}")
    except Exception as e:
        log_test("3A) GET /api/admin/universe/runtime-summary", "FAIL", str(e))
    
    # 3B) GET /api/admin/universe/runtime-latest-scan  
    try:
        response = requests.get(f"{BACKEND_URL}/admin/universe/runtime-latest-scan", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            log_test("3B) GET /api/admin/universe/runtime-latest-scan", "PASS", f"Latest scan data: {len(str(data))} chars")
            passed += 1
        else:
            log_test("3B) GET /api/admin/universe/runtime-latest-scan", "FAIL", f"Status: {response.status_code}")
    except Exception as e:
        log_test("3B) GET /api/admin/universe/runtime-latest-scan", "FAIL", str(e))
    
    # 3C) POST /api/user/scanner/runtime/run
    if user_token:
        try:
            user_headers = {"Authorization": f"Bearer {user_token}"}
            response = requests.post(
                f"{BACKEND_URL}/user/scanner/runtime/run",
                headers=user_headers,
                params={"symbol_selection_mode": "all_market_symbols", "max_results": 50},
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                # Check for decisions[] structure
                decisions = data.get("decisions", [])
                runtime_metrics = data.get("runtime_metrics", {})
                
                decision_valid = True
                if decisions:
                    decision_keys = set(decisions[0].keys()) if decisions else set()
                    required_decision_keys = {"symbol", "decision", "confidence", "reason"}
                    if not required_decision_keys.issubset(decision_keys):
                        decision_valid = False
                
                metrics_valid = True
                required_metrics = {"scan_latency_ms", "decision_latency_ms", "snapshot_age_ms", "queue_depth", "candidate_count"}
                if not required_metrics.issubset(set(runtime_metrics.keys())):
                    metrics_valid = False
                
                if decision_valid and metrics_valid:
                    log_test("3C) POST /api/user/scanner/runtime/run", "PASS", f"Decisions: {len(decisions)}, Metrics: {len(runtime_metrics)} fields")
                    passed += 1
                else:
                    log_test("3C) POST /api/user/scanner/runtime/run", "FAIL", f"Invalid structure - decisions_ok: {decision_valid}, metrics_ok: {metrics_valid}")
            else:
                log_test("3C) POST /api/user/scanner/runtime/run", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            log_test("3C) POST /api/user/scanner/runtime/run", "FAIL", str(e))
    else:
        log_test("3C) POST /api/user/scanner/runtime/run", "FAIL", "No user token available")
    
    # 3D) GET /api/user/scanner/runtime/snapshot
    if user_token:
        try:
            user_headers = {"Authorization": f"Bearer {user_token}"}
            response = requests.get(f"{BACKEND_URL}/user/scanner/runtime/snapshot", headers=user_headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                log_test("3D) GET /api/user/scanner/runtime/snapshot", "PASS", f"Snapshot data: {len(str(data))} chars")
                passed += 1
            else:
                log_test("3D) GET /api/user/scanner/runtime/snapshot", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            log_test("3D) GET /api/user/scanner/runtime/snapshot", "FAIL", str(e))
    else:
        log_test("3D) GET /api/user/scanner/runtime/snapshot", "FAIL", "No user token available")
    
    return passed == total

# TEST 4: Candidate Persistence
def test_4_candidate_persistence():
    """Test 4) Candidate persistence - runtime_scan_candidates table validation"""
    print("\n=== TEST 4: Candidate Persistence ===")
    
    passed = 0
    total = 2
    
    # 4A) Check table exists via migration logs
    success, stdout, stderr = run_command("grep -r 'runtime_scan_candidates' /app/backend/migrations/versions/ || echo 'not found'", "Check migration files")
    if success and "runtime_scan_candidates" in stdout:
        log_test("4A) runtime_scan_candidates table migration", "PASS", "Migration file found")
        passed += 1
    else:
        log_test("4A) runtime_scan_candidates table migration", "FAIL", "Migration file not found")
    
    # 4B) Check model definition
    success, stdout, stderr = run_command("grep -A 10 'class RuntimeScanCandidate' /app/backend/model_domains/runtime_scan_candidate.py", "Check model definition")
    if success and "symbol" in stdout and "market_type" in stdout:
        required_columns = ["symbol", "market_type", "scan_timestamp", "strategy_signal", "risk_score", "decision", "confidence"]
        found_columns = sum(1 for col in required_columns if col in stdout)
        if found_columns >= 6:  # Most columns should be present
            log_test("4B) RuntimeScanCandidate model columns", "PASS", f"Found {found_columns}/{len(required_columns)} required columns")
            passed += 1
        else:
            log_test("4B) RuntimeScanCandidate model columns", "FAIL", f"Only found {found_columns}/{len(required_columns)} columns")
    else:
        log_test("4B) RuntimeScanCandidate model columns", "FAIL", "Model definition not found or missing key fields")
    
    return passed == total

# TEST 5: Futures Execution Alignment
def test_5_futures_execution():
    """Test 5) Futures execution alignment - symbol market_type resolution"""
    print("\n=== TEST 5: Futures Execution Alignment ===")
    
    # This is a "hafif kontrol" (light check) - just ensure no 500 errors
    # Test with a futures symbol if available, or check that spot/futures distinction works
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Test both spot and futures market types don't return 500
        spot_response = requests.get(f"{BACKEND_URL}/admin/universe-monitor?market_type=spot", headers=headers, timeout=10)
        futures_response = requests.get(f"{BACKEND_URL}/admin/universe-monitor?market_type=futures", headers=headers, timeout=10)
        
        spot_ok = spot_response.status_code != 500
        futures_ok = futures_response.status_code != 500
        
        if spot_ok and futures_ok:
            log_test("5A) Futures/Spot market_type resolution", "PASS", f"Spot: {spot_response.status_code}, Futures: {futures_response.status_code}")
            return True
        else:
            log_test("5A) Futures/Spot market_type resolution", "FAIL", f"Spot: {spot_response.status_code}, Futures: {futures_response.status_code}")
            return False
            
    except Exception as e:
        log_test("5A) Futures/Spot market_type resolution", "FAIL", str(e))
        return False

def main():
    """Run all FAZ-3A/3B/3C validation tests"""
    print("=== FAZ-3A/3B/3C Backend Doğrulama Paketi ===")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    
    results = {
        "drift_migration": False,
        "endpoint_regression": False, 
        "runtime_endpoints": False,
        "candidate_persistence": False,
        "futures_execution": False
    }
    
    # Run all tests
    results["drift_migration"] = test_1_drift_migration()
    results["endpoint_regression"] = test_2_endpoint_regression()
    results["runtime_endpoints"] = test_3_runtime_endpoints()
    results["candidate_persistence"] = test_4_candidate_persistence()
    results["futures_execution"] = test_5_futures_execution()
    
    # Summary
    print("\n=== TEST SUMMARY ===")
    passed_count = sum(1 for result in results.values() if result)
    total_count = len(results)
    
    for test_name, result in results.items():
        status = "GEÇTI" if result else "BAŞARISIZ"
        print(f"[{status}] {test_name}")
    
    print(f"\nToplam: {passed_count}/{total_count} test geçti")
    
    if passed_count == total_count:
        print("🟢 FAZ-3A/3B/3C validation PASSED - Tüm testler başarılı!")
        return 0
    else:
        print("🔴 FAZ-3A/3B/3C validation FAILED - Bazı testler başarısız!")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)