#!/usr/bin/env python3
"""
P0 Enforcement Backend Validation Test
=====================================

Test Requirements (Turkish):
1) GET /api/health -> 200
2) POST /api/auth/login (canary.admin@platform.local / CanaryAdmin123!) -> 200 + access_token
3) GET /api/health/ready ve /api/ready -> preview_smoke_gate check'i status=ready/gate_status=pass olmalı
4) /api/health içindeki startup.preview_smoke_gate.checks anahtarları: api_health, auth_login, commercial_route, overview_fetch

Base URL: https://trade-trace-engine.preview.emergentagent.com
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def log_test_result(test_name, status, details, evidence=None):
    """Log test result with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] TEST: {test_name}")
    print(f"STATUS: {status}")
    print(f"DETAILS: {details}")
    if evidence:
        print(f"EVIDENCE: {evidence}")
    print("-" * 80)

def test_health_endpoint():
    """Test 1: GET /api/health -> 200"""
    try:
        url = f"{BASE_URL}/api/health"
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            log_test_result(
                "GET /api/health", 
                "✅ PASS", 
                f"HTTP {response.status_code} response received with JSON status",
                f"Response: {json.dumps(response_data, indent=2)[:500]}..."
            )
            return True, response_data
        else:
            log_test_result(
                "GET /api/health", 
                "❌ FAIL", 
                f"Expected HTTP 200, got {response.status_code}",
                f"Response: {response.text[:200]}..."
            )
            return False, None
            
    except Exception as e:
        log_test_result(
            "GET /api/health", 
            "❌ FAIL", 
            f"Request failed with exception: {str(e)}",
            None
        )
        return False, None

def test_admin_login():
    """Test 2: POST /api/auth/login -> 200 + access_token"""
    try:
        url = f"{BASE_URL}/api/auth/login"
        payload = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            if "access_token" in response_data:
                token_preview = response_data["access_token"][:50] + "..." if len(response_data["access_token"]) > 50 else response_data["access_token"]
                log_test_result(
                    "POST /api/auth/login", 
                    "✅ PASS", 
                    f"HTTP {response.status_code} response with access_token received",
                    f"Token preview: {token_preview} (length: {len(response_data['access_token'])} chars)"
                )
                return True, response_data["access_token"]
            else:
                log_test_result(
                    "POST /api/auth/login", 
                    "❌ FAIL", 
                    "HTTP 200 received but no access_token in response",
                    f"Response: {json.dumps(response_data, indent=2)}"
                )
                return False, None
        else:
            log_test_result(
                "POST /api/auth/login", 
                "❌ FAIL", 
                f"Expected HTTP 200, got {response.status_code}",
                f"Response: {response.text[:200]}..."
            )
            return False, None
            
    except Exception as e:
        log_test_result(
            "POST /api/auth/login", 
            "❌ FAIL", 
            f"Request failed with exception: {str(e)}",
            None
        )
        return False, None

def test_ready_endpoints():
    """Test 3: GET /api/health/ready and /api/ready -> preview_smoke_gate status check"""
    results = []
    
    # Test /api/health/ready
    try:
        url = f"{BASE_URL}/api/health/ready"
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            
            # Check for preview_smoke_gate in checks
            smoke_gate_status = None
            gate_status = None
            
            checks = response_data.get("checks", {})
            if "preview_smoke_gate" in checks:
                smoke_gate_data = checks["preview_smoke_gate"]
                smoke_gate_status = smoke_gate_data.get("status")
                gate_status = smoke_gate_data.get("gate_status")
            
            if smoke_gate_status == "ready" and gate_status == "pass":
                log_test_result(
                    "GET /api/health/ready", 
                    "✅ PASS", 
                    f"preview_smoke_gate status=ready, gate_status=pass",
                    f"smoke_gate: {json.dumps(checks.get('preview_smoke_gate', {}), indent=2)}"
                )
                results.append(True)
            else:
                log_test_result(
                    "GET /api/health/ready", 
                    "❌ FAIL", 
                    f"preview_smoke_gate status={smoke_gate_status}, gate_status={gate_status} (expected: status=ready, gate_status=pass)",
                    f"Response: {json.dumps(response_data, indent=2)[:500]}..."
                )
                results.append(False)
        else:
            log_test_result(
                "GET /api/health/ready", 
                "❌ FAIL", 
                f"Expected HTTP 200, got {response.status_code}",
                f"Response: {response.text[:200]}..."
            )
            results.append(False)
            
    except Exception as e:
        log_test_result(
            "GET /api/health/ready", 
            "❌ FAIL", 
            f"Request failed with exception: {str(e)}",
            None
        )
        results.append(False)
    
    # Test /api/ready
    try:
        url = f"{BASE_URL}/api/ready"
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            
            # Check for preview_smoke_gate in checks
            smoke_gate_status = None
            gate_status = None
            
            checks = response_data.get("checks", {})
            if "preview_smoke_gate" in checks:
                smoke_gate_data = checks["preview_smoke_gate"]
                smoke_gate_status = smoke_gate_data.get("status")
                gate_status = smoke_gate_data.get("gate_status")
            
            if smoke_gate_status == "ready" and gate_status == "pass":
                log_test_result(
                    "GET /api/ready", 
                    "✅ PASS", 
                    f"preview_smoke_gate status=ready, gate_status=pass",
                    f"smoke_gate: {json.dumps(checks.get('preview_smoke_gate', {}), indent=2)}"
                )
                results.append(True)
            else:
                log_test_result(
                    "GET /api/ready", 
                    "❌ FAIL", 
                    f"preview_smoke_gate status={smoke_gate_status}, gate_status={gate_status} (expected: status=ready, gate_status=pass)",
                    f"Response: {json.dumps(response_data, indent=2)[:500]}..."
                )
                results.append(False)
        else:
            log_test_result(
                "GET /api/ready", 
                "❌ FAIL", 
                f"Expected HTTP 200, got {response.status_code}",
                f"Response: {response.text[:200]}..."
            )
            results.append(False)
            
    except Exception as e:
        log_test_result(
            "GET /api/ready", 
            "❌ FAIL", 
            f"Request failed with exception: {str(e)}",
            None
        )
        results.append(False)
    
    return all(results)

def test_health_smoke_gate_checks(health_data):
    """Test 4: /api/health startup.preview_smoke_gate.checks keys validation"""
    try:
        required_checks = ["api_health", "auth_login", "commercial_route", "overview_fetch"]
        
        if not health_data:
            log_test_result(
                "Health smoke gate checks", 
                "❌ FAIL", 
                "No health data available from previous test",
                None
            )
            return False
        
        # Navigate to checks.startup.preview_smoke_gate.checks
        checks_data_root = health_data.get("checks", {})
        startup_data = checks_data_root.get("startup", {})
        smoke_gate_data = startup_data.get("preview_smoke_gate", {})
        checks_data = smoke_gate_data.get("checks", {})
        
        if not checks_data:
            log_test_result(
                "Health smoke gate checks", 
                "❌ FAIL", 
                "checks.startup.preview_smoke_gate.checks not found in health response",
                f"Available keys in health: {list(health_data.keys())}"
            )
            return False
        
        # Check for required keys
        missing_checks = []
        present_checks = []
        
        for check in required_checks:
            if check in checks_data:
                present_checks.append(check)
            else:
                missing_checks.append(check)
        
        if not missing_checks:
            log_test_result(
                "Health smoke gate checks", 
                "✅ PASS", 
                f"All required checks present: {', '.join(present_checks)}",
                f"checks: {json.dumps(checks_data, indent=2)}"
            )
            return True
        else:
            log_test_result(
                "Health smoke gate checks", 
                "❌ FAIL", 
                f"Missing checks: {', '.join(missing_checks)}. Present: {', '.join(present_checks)}",
                f"Available checks: {list(checks_data.keys())}"
            )
            return False
            
    except Exception as e:
        log_test_result(
            "Health smoke gate checks", 
            "❌ FAIL", 
            f"Exception during checks validation: {str(e)}",
            None
        )
        return False

def main():
    """Main test execution"""
    print("=" * 80)
    print("P0 ENFORCEMENT BACKEND VALIDATION TEST")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"Test Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    test_results = []
    
    # Test 1: Health endpoint
    health_success, health_data = test_health_endpoint()
    test_results.append(("GET /api/health", health_success))
    
    # Test 2: Admin login
    login_success, access_token = test_admin_login()
    test_results.append(("POST /api/auth/login", login_success))
    
    # Test 3: Ready endpoints
    ready_success = test_ready_endpoints()
    test_results.append(("Ready endpoints", ready_success))
    
    # Test 4: Health smoke gate checks
    checks_success = test_health_smoke_gate_checks(health_data)
    test_results.append(("Health smoke gate checks", checks_success))
    
    # Summary
    print("\n" + "=" * 80)
    print("P0 VALIDATION TEST SUMMARY")
    print("=" * 80)
    
    passed_tests = 0
    total_tests = len(test_results)
    
    for test_name, success in test_results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
        if success:
            passed_tests += 1
    
    print("-" * 80)
    print(f"OVERALL RESULT: {passed_tests}/{total_tests} tests passed ({(passed_tests/total_tests)*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("🎉 ALL P0 REQUIREMENTS PASSED - System ready for enforcement operations")
        return 0
    else:
        print("⚠️  SOME P0 REQUIREMENTS FAILED - Investigation required")
        return 1

if __name__ == "__main__":
    sys.exit(main())