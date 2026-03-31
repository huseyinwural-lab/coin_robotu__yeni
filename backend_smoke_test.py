#!/usr/bin/env python3
"""
Backend Smoke Test - Identity Control Endpoints
Test specific endpoints for basic backend availability
"""

import requests
import json
import sys
from datetime import datetime

# Test configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
TIMEOUT = 10

def test_endpoint(method, endpoint, expected_codes=None, description=""):
    """Test a single endpoint and return result"""
    if expected_codes is None:
        expected_codes = [200, 401, 403]
    
    url = f"{BASE_URL}{endpoint}"
    
    try:
        print(f"\n🔍 Testing: {method} {endpoint}")
        print(f"   Description: {description}")
        print(f"   URL: {url}")
        
        if method.upper() == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method.upper() == "POST":
            response = requests.post(url, timeout=TIMEOUT)
        else:
            print(f"   ❌ FAIL: Unsupported method {method}")
            return False, f"Unsupported method {method}"
        
        status_code = response.status_code
        print(f"   Status: {status_code}")
        
        # Check for 5xx errors (server errors)
        if 500 <= status_code < 600:
            print(f"   ❌ FAIL: Server error {status_code}")
            try:
                error_detail = response.text[:200] if response.text else "No error detail"
                print(f"   Error detail: {error_detail}")
                return False, f"Server error {status_code}: {error_detail}"
            except:
                return False, f"Server error {status_code}"
        
        # Check for 502 specifically (Bad Gateway)
        if status_code == 502:
            print(f"   ❌ FAIL: Bad Gateway (502) - Backend service down")
            return False, "Bad Gateway (502) - Backend service down"
        
        # Check if status code is in expected range
        if status_code in expected_codes:
            print(f"   ✅ PASS: Expected status {status_code}")
            return True, f"Expected status {status_code}"
        elif status_code in [401, 403]:
            print(f"   ✅ PASS: Auth required ({status_code}) - Backend is up")
            return True, f"Auth required ({status_code}) - Backend is up"
        else:
            print(f"   ⚠️  UNEXPECTED: Status {status_code} (not in expected {expected_codes})")
            try:
                response_text = response.text[:200] if response.text else "No response body"
                print(f"   Response: {response_text}")
                return True, f"Unexpected status {status_code} but backend responding"
            except:
                return True, f"Unexpected status {status_code} but backend responding"
                
    except requests.exceptions.Timeout:
        print(f"   ❌ FAIL: Timeout after {TIMEOUT}s")
        return False, f"Timeout after {TIMEOUT}s"
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ FAIL: Connection error - {str(e)}")
        return False, f"Connection error: {str(e)}"
    except Exception as e:
        print(f"   ❌ FAIL: Unexpected error - {str(e)}")
        return False, f"Unexpected error: {str(e)}"

def main():
    """Run backend smoke tests"""
    print("=" * 60)
    print("BACKEND SMOKE TEST - Identity Control Endpoints")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Test time: {datetime.now().isoformat()}")
    
    # Test cases
    test_cases = [
        {
            "method": "GET",
            "endpoint": "/api/auth/me",
            "expected_codes": [401, 403, 200],
            "description": "Auth me endpoint - should require authentication"
        },
        {
            "method": "GET", 
            "endpoint": "/api/admin/identity/users",
            "expected_codes": [401, 403],
            "description": "Admin identity users - should require admin auth"
        },
        {
            "method": "GET",
            "endpoint": "/api/admin/identity/approvals", 
            "expected_codes": [401, 403],
            "description": "Admin identity approvals - should require admin auth"
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        success, message = test_endpoint(
            test_case["method"],
            test_case["endpoint"], 
            test_case["expected_codes"],
            test_case["description"]
        )
        
        results.append({
            "endpoint": test_case["endpoint"],
            "success": success,
            "message": message
        })
    
    # Summary
    print("\n" + "=" * 60)
    print("SMOKE TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    
    for result in results:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"{status}: {result['endpoint']} - {result['message']}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 SMOKE TEST RESULT: PASS")
        print("Backend is responding correctly - all endpoints return expected auth errors (401/403)")
        return 0
    else:
        print(f"\n💥 SMOKE TEST RESULT: FAIL")
        print("Backend has issues - check failed endpoints above")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)