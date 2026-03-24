#!/usr/bin/env python3
"""
MFA Optional Policy Quick Backend Validation Test
Base URL: https://identity-control-1.preview.emergentagent.com
Test Requirements:
1) POST /api/auth/login/admin with canary.admin@platform.local / CanaryAdmin123! should return 200 with access_token directly and mfa_required=false.
2) Using returned token, PUT /api/auth/mfa/settings with is_enabled=false should return 200 (admin için disable artık izinli).
3) Confirm /api/health remains 200.
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://identity-control-1.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def log_test(test_name, status, details=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {test_name}: {status}")
    if details:
        print(f"  Details: {details}")

def test_admin_login_no_mfa():
    """Test 1: Admin login should return access_token directly with mfa_required=false"""
    try:
        url = f"{BASE_URL}/api/auth/login/admin"
        payload = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code != 200:
            log_test("Test 1 - Admin Login No MFA", "FAIL", f"HTTP {response.status_code}: {response.text}")
            return None, False
            
        data = response.json()
        
        # Check for access_token directly (no MFA challenge)
        if "access_token" not in data:
            log_test("Test 1 - Admin Login No MFA", "FAIL", "No access_token in response")
            return None, False
            
        # Check mfa_required is false
        if data.get("mfa_required", True) != False:
            log_test("Test 1 - Admin Login No MFA", "FAIL", f"mfa_required={data.get('mfa_required')}, expected False")
            return None, False
            
        log_test("Test 1 - Admin Login No MFA", "PASS", f"access_token received, mfa_required={data.get('mfa_required')}")
        return data["access_token"], True
        
    except Exception as e:
        log_test("Test 1 - Admin Login No MFA", "FAIL", f"Exception: {str(e)}")
        return None, False

def test_mfa_settings_disable(access_token):
    """Test 2: PUT /api/auth/mfa/settings with is_enabled=false should return 200"""
    try:
        url = f"{BASE_URL}/api/auth/mfa/settings"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "is_enabled": False
        }
        
        response = requests.put(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            log_test("Test 2 - MFA Settings Disable", "FAIL", f"HTTP {response.status_code}: {response.text}")
            return False
            
        data = response.json()
        log_test("Test 2 - MFA Settings Disable", "PASS", f"MFA disabled successfully: {data}")
        return True
        
    except Exception as e:
        log_test("Test 2 - MFA Settings Disable", "FAIL", f"Exception: {str(e)}")
        return False

def test_health_endpoint():
    """Test 3: Confirm /api/health remains 200"""
    try:
        url = f"{BASE_URL}/api/health"
        
        response = requests.get(url, timeout=30)
        
        if response.status_code != 200:
            log_test("Test 3 - Health Endpoint", "FAIL", f"HTTP {response.status_code}: {response.text}")
            return False
            
        data = response.json()
        log_test("Test 3 - Health Endpoint", "PASS", f"Health check successful: {data}")
        return True
        
    except Exception as e:
        log_test("Test 3 - Health Endpoint", "FAIL", f"Exception: {str(e)}")
        return False

def main():
    print("=" * 80)
    print("MFA OPTIONAL POLICY QUICK BACKEND VALIDATION")
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    print("=" * 80)
    
    results = []
    
    # Test 1: Admin login without MFA
    access_token, test1_pass = test_admin_login_no_mfa()
    results.append(("Admin Login No MFA", test1_pass))
    
    # Test 2: MFA settings disable (only if login succeeded)
    test2_pass = False
    if access_token:
        test2_pass = test_mfa_settings_disable(access_token)
    else:
        log_test("Test 2 - MFA Settings Disable", "SKIP", "No access token from Test 1")
    results.append(("MFA Settings Disable", test2_pass))
    
    # Test 3: Health endpoint
    test3_pass = test_health_endpoint()
    results.append(("Health Endpoint", test3_pass))
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY RESULTS:")
    print("=" * 80)
    
    passed = 0
    total = len(results)
    
    for test_name, passed_status in results:
        status = "PASS" if passed_status else "FAIL"
        print(f"{test_name}: {status}")
        if passed_status:
            passed += 1
    
    print(f"\nOVERALL: {passed}/{total} tests PASSED ({(passed/total)*100:.1f}%)")
    
    if passed == total:
        print("✅ ALL TESTS PASSED - MFA Optional Policy working correctly")
        return 0
    else:
        print("❌ SOME TESTS FAILED - MFA Optional Policy needs attention")
        return 1

if __name__ == "__main__":
    sys.exit(main())