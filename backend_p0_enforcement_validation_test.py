#!/usr/bin/env python3
"""
P0 Enforcement Backend Validation Test
=====================================

Turkish Review Request:
P0 doğrulama testi yap.
Hedef ortam: https://enforcement-backend.preview.emergentagent.com

Zorunlu kontrol listesi:
1) GET /api/health -> 200 ve JSON status=ok/degraded yerine erişilebilir cevap.
2) POST /api/auth/login (email: canary.admin@platform.local, password: CanaryAdmin123!) -> 200 ve access_token dönmeli.
3) Frontend route /admin/commercial-ops açılmalı (502/timeout olmamalı; HTML/login veya uygulama ekranı render kabul).

Ek notlar:
- Önceki ana sorun: startup deadlock/timeout ve 502.
- Son değişiklikler: startup'ta canary modda pipeline runtime otomatik skip, exchange health cycle ve export scheduler cycle thread'e taşındı.
- Özellikle timeout/502 regresyonu var mı raporla.
- Her madde için PASS/FAIL ve kısa kanıt (status code/response snippet) ver.
"""

import requests
import json
import time
from datetime import datetime
import sys

# Test Configuration
BASE_URL = "https://enforcement-backend.preview.emergentagent.com"
FRONTEND_URL = "https://enforcement-backend.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

# Test timeout settings
REQUEST_TIMEOUT = 30  # 30 seconds timeout for requests
FRONTEND_TIMEOUT = 15  # 15 seconds timeout for frontend checks

def log_test_result(test_name, status, evidence, details=""):
    """Log test result with timestamp and evidence"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] TEST: {test_name}")
    print(f"STATUS: {status}")
    print(f"EVIDENCE: {evidence}")
    if details:
        print(f"DETAILS: {details}")
    print("-" * 80)

def test_health_endpoint():
    """
    Test 1: GET /api/health -> 200 ve JSON status=ok/degraded yerine erişilebilir cevap
    """
    test_name = "GET /api/health - Health Check Endpoint"
    
    try:
        url = f"{BASE_URL}/api/health"
        print(f"Testing health endpoint: {url}")
        
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        # Check status code
        if response.status_code != 200:
            log_test_result(
                test_name, 
                "FAIL", 
                f"HTTP {response.status_code} instead of 200",
                f"Response: {response.text[:200]}"
            )
            return False
        
        # Check if response is JSON
        try:
            json_response = response.json()
        except json.JSONDecodeError:
            log_test_result(
                test_name, 
                "FAIL", 
                f"Non-JSON response received",
                f"Response: {response.text[:200]}"
            )
            return False
        
        # Check if status field exists and has acceptable value
        status_field = json_response.get('status', 'missing')
        if status_field not in ['ok', 'degraded']:
            log_test_result(
                test_name, 
                "FAIL", 
                f"Status field is '{status_field}', expected 'ok' or 'degraded'",
                f"Full response: {json.dumps(json_response, indent=2)}"
            )
            return False
        
        log_test_result(
            test_name, 
            "PASS", 
            f"HTTP 200, JSON response, status='{status_field}'",
            f"Response: {json.dumps(json_response, indent=2)}"
        )
        return True
        
    except requests.exceptions.Timeout:
        log_test_result(
            test_name, 
            "FAIL", 
            f"Request timeout after {REQUEST_TIMEOUT} seconds",
            "Possible startup deadlock/timeout issue"
        )
        return False
    except requests.exceptions.ConnectionError as e:
        log_test_result(
            test_name, 
            "FAIL", 
            f"Connection error: {str(e)}",
            "Backend service may be down or unreachable"
        )
        return False
    except Exception as e:
        log_test_result(
            test_name, 
            "FAIL", 
            f"Unexpected error: {str(e)}",
            f"Exception type: {type(e).__name__}"
        )
        return False

def test_admin_login():
    """
    Test 2: POST /api/auth/login (email: canary.admin@platform.local, password: CanaryAdmin123!) -> 200 ve access_token dönmeli
    """
    test_name = "POST /api/auth/login - Admin Authentication"
    
    try:
        url = f"{BASE_URL}/api/auth/login"
        print(f"Testing admin login endpoint: {url}")
        
        # Try different possible login endpoints
        possible_endpoints = [
            "/api/auth/login",
            "/api/auth/login/admin",
            "/api/admin/auth/login"
        ]
        
        login_data = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }
        
        success = False
        for endpoint in possible_endpoints:
            try:
                url = f"{BASE_URL}{endpoint}"
                print(f"Trying endpoint: {url}")
                
                response = requests.post(
                    url, 
                    json=login_data,
                    headers={"Content-Type": "application/json"},
                    timeout=REQUEST_TIMEOUT
                )
                
                if response.status_code == 200:
                    try:
                        json_response = response.json()
                        access_token = json_response.get('access_token')
                        
                        if access_token:
                            log_test_result(
                                test_name, 
                                "PASS", 
                                f"HTTP 200, access_token received (endpoint: {endpoint})",
                                f"Token preview: {access_token[:50]}... (length: {len(access_token)})"
                            )
                            return True, access_token
                        else:
                            print(f"No access_token in response from {endpoint}: {json_response}")
                    except json.JSONDecodeError:
                        print(f"Non-JSON response from {endpoint}: {response.text[:200]}")
                else:
                    print(f"HTTP {response.status_code} from {endpoint}: {response.text[:200]}")
                    
            except requests.exceptions.Timeout:
                print(f"Timeout for endpoint {endpoint}")
                continue
            except requests.exceptions.ConnectionError:
                print(f"Connection error for endpoint {endpoint}")
                continue
        
        # If we reach here, all endpoints failed
        log_test_result(
            test_name, 
            "FAIL", 
            f"No working login endpoint found. Tried: {', '.join(possible_endpoints)}",
            f"Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}"
        )
        return False, None
        
    except Exception as e:
        log_test_result(
            test_name, 
            "FAIL", 
            f"Unexpected error: {str(e)}",
            f"Exception type: {type(e).__name__}"
        )
        return False, None

def test_frontend_commercial_ops():
    """
    Test 3: Frontend route /admin/commercial-ops açılmalı (502/timeout olmamalı; HTML/login veya uygulama ekranı render kabul)
    """
    test_name = "Frontend /admin/commercial-ops - Route Accessibility"
    
    try:
        url = f"{FRONTEND_URL}/admin/commercial-ops"
        print(f"Testing frontend route: {url}")
        
        response = requests.get(url, timeout=FRONTEND_TIMEOUT)
        
        # Check for 502 error specifically
        if response.status_code == 502:
            log_test_result(
                test_name, 
                "FAIL", 
                f"HTTP 502 Bad Gateway - Service unavailable",
                "This indicates backend service issues or proxy problems"
            )
            return False
        
        # Check for timeout (this would be caught by exception, but check status codes that indicate timeout)
        if response.status_code == 504:
            log_test_result(
                test_name, 
                "FAIL", 
                f"HTTP 504 Gateway Timeout",
                "Backend service is taking too long to respond"
            )
            return False
        
        # Acceptable status codes: 200 (app), 401/403 (login required), 302/301 (redirect)
        acceptable_codes = [200, 301, 302, 401, 403]
        
        if response.status_code not in acceptable_codes:
            log_test_result(
                test_name, 
                "FAIL", 
                f"HTTP {response.status_code} - Unexpected status code",
                f"Response preview: {response.text[:300]}"
            )
            return False
        
        # Check if we got HTML content (not just error page)
        content_type = response.headers.get('content-type', '').lower()
        is_html = 'text/html' in content_type
        
        # Check content length (should not be empty)
        content_length = len(response.text)
        
        if content_length < 100:  # Very small response might be an error
            log_test_result(
                test_name, 
                "FAIL", 
                f"Response too small ({content_length} chars) - likely error page",
                f"Content: {response.text}"
            )
            return False
        
        # Look for common indicators of successful page load
        content_lower = response.text.lower()
        success_indicators = [
            'html',
            'commercial-ops',
            'admin',
            'login',
            'react',
            'app',
            'script',
            'div'
        ]
        
        found_indicators = [indicator for indicator in success_indicators if indicator in content_lower]
        
        if not found_indicators:
            log_test_result(
                test_name, 
                "FAIL", 
                f"No HTML/app indicators found in response",
                f"Content preview: {response.text[:300]}"
            )
            return False
        
        log_test_result(
            test_name, 
            "PASS", 
            f"HTTP {response.status_code}, {content_length} chars, HTML content detected",
            f"Content-Type: {content_type}, Indicators found: {', '.join(found_indicators)}"
        )
        return True
        
    except requests.exceptions.Timeout:
        log_test_result(
            test_name, 
            "FAIL", 
            f"Request timeout after {FRONTEND_TIMEOUT} seconds",
            "Frontend taking too long to respond - possible timeout/502 regression"
        )
        return False
    except requests.exceptions.ConnectionError as e:
        log_test_result(
            test_name, 
            "FAIL", 
            f"Connection error: {str(e)}",
            "Frontend service may be down or unreachable"
        )
        return False
    except Exception as e:
        log_test_result(
            test_name, 
            "FAIL", 
            f"Unexpected error: {str(e)}",
            f"Exception type: {type(e).__name__}"
        )
        return False

def main():
    """Run all P0 validation tests"""
    print("=" * 80)
    print("P0 ENFORCEMENT BACKEND VALIDATION TEST")
    print("=" * 80)
    print(f"Target Environment: {BASE_URL}")
    print(f"Frontend URL: {FRONTEND_URL}")
    print(f"Test Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Track test results
    test_results = []
    
    # Test 1: Health endpoint
    print("\n🔍 RUNNING TEST 1: Health Endpoint")
    health_result = test_health_endpoint()
    test_results.append(("Health Endpoint", health_result))
    
    # Test 2: Admin login
    print("\n🔍 RUNNING TEST 2: Admin Login")
    login_result, access_token = test_admin_login()
    test_results.append(("Admin Login", login_result))
    
    # Test 3: Frontend route
    print("\n🔍 RUNNING TEST 3: Frontend Commercial Ops Route")
    frontend_result = test_frontend_commercial_ops()
    test_results.append(("Frontend Route", frontend_result))
    
    # Summary
    print("\n" + "=" * 80)
    print("P0 VALIDATION TEST SUMMARY")
    print("=" * 80)
    
    passed_tests = 0
    total_tests = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed_tests += 1
    
    print("-" * 80)
    print(f"OVERALL RESULT: {passed_tests}/{total_tests} tests passed ({(passed_tests/total_tests)*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("🎉 ALL P0 VALIDATION TESTS PASSED")
        print("✅ No timeout/502 regression detected")
        print("✅ Backend startup and authentication working")
        print("✅ Frontend route accessible")
    else:
        print("⚠️  SOME P0 VALIDATION TESTS FAILED")
        print("❌ Manual investigation required")
        
        # Check for specific regression patterns
        if not test_results[0][1]:  # Health failed
            print("🚨 CRITICAL: Health endpoint failure - possible startup deadlock/timeout")
        if not test_results[1][1]:  # Login failed
            print("🚨 CRITICAL: Admin authentication failure")
        if not test_results[2][1]:  # Frontend failed
            print("🚨 CRITICAL: Frontend route failure - possible 502/timeout regression")
    
    print("=" * 80)
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Return exit code based on results
    return 0 if passed_tests == total_tests else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)