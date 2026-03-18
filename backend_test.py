#!/usr/bin/env python3

"""
Focused Regression Testing for FastAPI + React App

Priority context:
- Fixed P0 blocker where /api/auth/login was returning 500 due to storage pressure symptoms
- Added storage guard logic in daily ops automation
- Testing critical endpoints and daily ops automation script

Tests:
1) Auth smoke - admin login 
2) Release smoke CLI parity through API outcomes
3) Daily ops automation script behavior (critical)
4) No regression on login after automation dry-run
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# Base URL from frontend/.env 
BASE_URL = "https://peaceful-visvesvaraya-2.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Admin credentials
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"

# Test results tracking
test_results = {
    "passed": [],
    "failed": [],
    "total_tests": 0,
    "start_time": time.time()
}

def log_result(test_name: str, success: bool, details: str = ""):
    """Log test result"""
    test_results["total_tests"] += 1
    result = {
        "test": test_name,
        "success": success,
        "details": details,
        "timestamp": time.time()
    }
    
    if success:
        test_results["passed"].append(result)
        print(f"✅ PASS: {test_name} - {details}")
    else:
        test_results["failed"].append(result)
        print(f"❌ FAIL: {test_name} - {details}")

def get_admin_token() -> str:
    """Get admin authentication token"""
    try:
        response = requests.post(
            f"{API_BASE}/auth/login/admin",
            json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            if token:
                log_result("Admin Login", True, f"Status: {response.status_code}, Token received")
                return token
            else:
                log_result("Admin Login", False, f"Status: {response.status_code}, No token in response")
                return ""
        else:
            log_result("Admin Login", False, f"Status: {response.status_code}, Response: {response.text[:200]}")
            return ""
            
    except Exception as e:
        log_result("Admin Login", False, f"Exception: {str(e)[:200]}")
        return ""

def test_auth_smoke():
    """Test 1: Auth smoke - POST /api/auth/login with admin credentials"""
    print("\n=== TEST 1: AUTH SMOKE ===")
    
    try:
        response = requests.post(
            f"{API_BASE}/auth/login/admin",
            json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            
            if token and user.get("email") == ADMIN_EMAIL:
                log_result("Auth Smoke Test", True, f"Login successful, token: {token[:20]}..., user: {user.get('email')}")
                return token
            else:
                log_result("Auth Smoke Test", False, f"Missing token or user data. Response: {data}")
        else:
            log_result("Auth Smoke Test", False, f"Status: {response.status_code}, Response: {response.text}")
            
    except Exception as e:
        log_result("Auth Smoke Test", False, f"Exception: {str(e)}")
    
    return None

def test_release_smoke_endpoints(admin_token: str):
    """Test 2: Release smoke CLI parity through API outcomes"""
    print("\n=== TEST 2: RELEASE SMOKE CLI PARITY ENDPOINTS ===")
    
    if not admin_token:
        log_result("Release Smoke - Prerequisites", False, "No admin token available")
        return
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    endpoints_to_test = [
        {
            "name": "Health Check",
            "url": f"{API_BASE}/health",
            "method": "GET",
            "auth_required": False,
            "expected_status": 200,
            "expected_keys": ["status"]
        },
        {
            "name": "Futures Live Path Check", 
            "url": f"{API_BASE}/admin/users/futures-live-path-check",
            "method": "GET", 
            "auth_required": True,
            "expected_status": 200,
            "expected_keys": ["generated_at", "total_users", "pass_count", "fail_count"]
        },
        {
            "name": "System Alerts Burn-in (7 days)",
            "url": f"{API_BASE}/admin/system-alerts/burn-in?days=7", 
            "method": "GET",
            "auth_required": True,
            "expected_status": 200,
            "expected_keys": ["window_days", "total_alerts"]
        },
        {
            "name": "Audit Logs Timeline", 
            "url": f"{API_BASE}/audit-logs/timeline?limit=100",
            "method": "GET",
            "auth_required": True, 
            "expected_status": 200,
            "expected_keys": ["total", "items"]
        },
        {
            "name": "Audit Logs Incident Export (7 days)",
            "url": f"{API_BASE}/audit-logs/admin/incident-export?window_days=7",
            "method": "GET",
            "auth_required": True,
            "expected_status": 200,
            "expected_content_type": "application/zip"
        }
    ]
    
    for endpoint in endpoints_to_test:
        try:
            test_headers = headers if endpoint["auth_required"] else {}
            
            response = requests.get(
                endpoint["url"],
                headers=test_headers,
                timeout=15
            )
            
            # Check status code
            if response.status_code != endpoint["expected_status"]:
                log_result(
                    f"Release Smoke - {endpoint['name']}", 
                    False, 
                    f"Status {response.status_code}, expected {endpoint['expected_status']}"
                )
                continue
            
            # Check content type for zip exports
            if endpoint.get("expected_content_type") == "application/zip":
                content_type = response.headers.get("content-type", "")
                if "zip" in content_type or "application/zip" in content_type:
                    log_result(
                        f"Release Smoke - {endpoint['name']}", 
                        True, 
                        f"Status {response.status_code}, ZIP content received ({len(response.content)} bytes)"
                    )
                else:
                    log_result(
                        f"Release Smoke - {endpoint['name']}", 
                        False, 
                        f"Expected ZIP content, got content-type: {content_type}"
                    )
                continue
            
            # Check JSON response structure  
            try:
                data = response.json()
                missing_keys = [key for key in endpoint.get("expected_keys", []) if key not in data]
                
                if missing_keys:
                    log_result(
                        f"Release Smoke - {endpoint['name']}", 
                        False, 
                        f"Missing keys: {missing_keys}, Response keys: {list(data.keys())}"
                    )
                else:
                    log_result(
                        f"Release Smoke - {endpoint['name']}", 
                        True, 
                        f"Status {response.status_code}, All expected keys present: {endpoint.get('expected_keys', [])}"
                    )
                    
            except json.JSONDecodeError:
                log_result(
                    f"Release Smoke - {endpoint['name']}", 
                    False, 
                    f"Status {response.status_code}, Invalid JSON response"
                )
                
        except Exception as e:
            log_result(
                f"Release Smoke - {endpoint['name']}", 
                False, 
                f"Exception: {str(e)[:200]}"
            )

def test_daily_ops_automation():
    """Test 3: Daily ops automation script behavior (critical)"""
    print("\n=== TEST 3: DAILY OPS AUTOMATION SCRIPT ===")
    
    # Create test gate file directory if it doesn't exist
    test_reports_dir = Path("/app/test_reports")
    test_reports_dir.mkdir(exist_ok=True)
    
    gate_file_path = test_reports_dir / "release_gate_latest.json"
    
    # Create a basic gate file for testing
    gate_data = {
        "overall": "PASS",
        "fail_count": 0,
        "warn_count": 1,
        "generated_at": "2026-03-15T12:00:00Z",
        "tests": []
    }
    
    with open(gate_file_path, "w") as f:
        json.dump(gate_data, f)
    
    try:
        # Run the daily ops automation script with dry-run
        cmd = [
            "python",
            "/app/backend/cli/daily_ops_automation.py", 
            "--gate-file", str(gate_file_path),
            "--dry-run"
        ]
        
        # Change to backend directory for proper imports
        result = subprocess.run(
            cmd,
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            # Parse output JSON
            try:
                output = json.loads(result.stdout)
                
                # Required fields in output
                required_fields = [
                    "generated_at", 
                    "gate_overall", 
                    "storage",
                    "dry_run",
                    "actions"
                ]
                
                # Check storage structure
                storage = output.get("storage", {})
                storage_required_fields = ["before", "after"]
                
                # Check actions structure for required types
                actions = output.get("actions", [])
                expected_action_types = {
                    "strategy_observability_prune",
                    "audit_logs_prune", 
                    "decision_trace_prune"
                }
                
                found_action_types = {action.get("type") for action in actions if action.get("type")}
                
                # Validation checks
                missing_fields = [field for field in required_fields if field not in output]
                missing_storage_fields = [field for field in storage_required_fields if field not in storage]
                missing_actions = expected_action_types - found_action_types
                
                success = True
                details_parts = []
                
                if missing_fields:
                    success = False
                    details_parts.append(f"Missing required fields: {missing_fields}")
                
                if missing_storage_fields:
                    success = False  
                    details_parts.append(f"Missing storage fields: {missing_storage_fields}")
                
                if missing_actions:
                    success = False
                    details_parts.append(f"Missing action types: {missing_actions}")
                
                if output.get("dry_run") != True:
                    success = False
                    details_parts.append("dry_run flag not set to True")
                
                if success:
                    details = (f"Exit code: 0, JSON structure valid, "
                             f"Actions: {found_action_types}, "
                             f"Storage fields: {list(storage.keys())}, "
                             f"Dry run: {output.get('dry_run')}")
                else:
                    details = "; ".join(details_parts)
                
                log_result("Daily Ops Automation Script", success, details)
                
            except json.JSONDecodeError as e:
                log_result("Daily Ops Automation Script", False, f"Exit code: 0, Invalid JSON output: {str(e)}")
                
        else:
            log_result(
                "Daily Ops Automation Script", 
                False, 
                f"Exit code: {result.returncode}, Error: {result.stderr[:200]}"
            )
            
    except subprocess.TimeoutExpired:
        log_result("Daily Ops Automation Script", False, "Script timeout after 60 seconds")
    except Exception as e:
        log_result("Daily Ops Automation Script", False, f"Exception: {str(e)[:200]}")

def test_login_regression_after_automation():
    """Test 4: No regression on login after automation dry-run"""
    print("\n=== TEST 4: LOGIN REGRESSION AFTER AUTOMATION ===")
    
    try:
        response = requests.post(
            f"{API_BASE}/auth/login/admin",
            json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            
            if token:
                log_result(
                    "Login Regression Test", 
                    True, 
                    f"Status: {response.status_code}, Login still works after automation dry-run"
                )
            else:
                log_result(
                    "Login Regression Test", 
                    False, 
                    f"Status: {response.status_code}, No token received"
                )
        else:
            log_result(
                "Login Regression Test", 
                False, 
                f"Status: {response.status_code}, Response: {response.text[:200]}"
            )
            
    except Exception as e:
        log_result("Login Regression Test", False, f"Exception: {str(e)[:200]}")

def print_final_summary():
    """Print final test summary"""
    elapsed_time = time.time() - test_results["start_time"]
    
    print("\n" + "="*60)
    print("REGRESSION TEST SUMMARY")
    print("="*60)
    print(f"Total Tests: {test_results['total_tests']}")
    print(f"Passed: {len(test_results['passed'])}")
    print(f"Failed: {len(test_results['failed'])}")
    print(f"Success Rate: {(len(test_results['passed'])/test_results['total_tests']*100):.1f}%" if test_results['total_tests'] > 0 else "No tests")
    print(f"Elapsed Time: {elapsed_time:.2f}s")
    
    if test_results["failed"]:
        print("\nFAILED TESTS:")
        for result in test_results["failed"]:
            print(f"  ❌ {result['test']}: {result['details']}")
    
    print("\nPASSED TESTS:")
    for result in test_results["passed"]:
        print(f"  ✅ {result['test']}: {result['details']}")
    
    print("\n" + "="*60)

def main():
    """Main test execution"""
    print("FastAPI + React App - Focused Regression Testing")
    print(f"Base URL: {BASE_URL}")
    print(f"Admin Credentials: {ADMIN_EMAIL}")
    print("="*60)
    
    # Test 1: Auth Smoke
    admin_token = test_auth_smoke()
    
    # Test 2: Release Smoke Endpoints 
    if admin_token:
        test_release_smoke_endpoints(admin_token)
    else:
        log_result("Release Smoke - Prerequisites", False, "Cannot run without admin token")
    
    # Test 3: Daily Ops Automation
    test_daily_ops_automation()
    
    # Test 4: Login Regression
    test_login_regression_after_automation()
    
    # Print final summary
    print_final_summary()
    
    # Exit with non-zero code if any tests failed
    if test_results["failed"]:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()