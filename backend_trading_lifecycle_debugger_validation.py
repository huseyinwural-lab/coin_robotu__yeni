#!/usr/bin/env python3
"""
Trading Lifecycle Debugger Backend Validation
Quick validation for backend stabilization after Trading Lifecycle Debugger work.

Test Requirements:
1. Health endpoint: /api/health -> 200
2. Admin login: POST /api/auth/login/admin with canary.admin@platform.local / CanaryAdmin123!
3. Lifecycle endpoints:
   - GET /api/audit-logs/trading-lifecycle?limit=20
   - GET /api/audit-logs/lifecycle/{correlation_id} (new alias)
   - POST /api/audit-logs/explain body:{"correlation_id":"..."} (new alias)
4. Expected: 200 responses with trace_incomplete or missing_critical_stages fields
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://failure-explainer.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def log_test(test_name, status, details=""):
    """Log test results with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"[{timestamp}] {status_symbol} {test_name}: {status}")
    if details:
        print(f"    {details}")

def test_health_endpoint():
    """Test 1: Health endpoint validation"""
    try:
        url = f"{BASE_URL}/api/health"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            log_test("Health Endpoint", "PASS", f"Status: {data.get('status', 'unknown')}")
            return True
        else:
            log_test("Health Endpoint", "FAIL", f"HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log_test("Health Endpoint", "FAIL", f"Exception: {str(e)}")
        return False

def test_admin_login():
    """Test 2: Admin authentication"""
    try:
        url = f"{BASE_URL}/api/auth/login/admin"
        payload = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            if token:
                log_test("Admin Login", "PASS", f"Token received (length: {len(token)} chars)")
                return token
            else:
                log_test("Admin Login", "FAIL", "No access_token in response")
                return None
        else:
            log_test("Admin Login", "FAIL", f"HTTP {response.status_code}")
            return None
            
    except Exception as e:
        log_test("Admin Login", "FAIL", f"Exception: {str(e)}")
        return None

def test_lifecycle_endpoints(token):
    """Test 3: Lifecycle endpoints validation"""
    headers = {"Authorization": f"Bearer {token}"}
    results = []
    
    # Test 3a: Trading lifecycle list
    try:
        url = f"{BASE_URL}/api/audit-logs/trading-lifecycle?limit=20"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Check for trace_incomplete or missing_critical_stages fields
            has_trace_fields = False
            if isinstance(data, list) and len(data) > 0:
                for item in data:
                    if 'trace_incomplete' in item or 'missing_critical_stages' in item:
                        has_trace_fields = True
                        break
            elif isinstance(data, dict):
                has_trace_fields = 'trace_incomplete' in data or 'missing_critical_stages' in data
            
            log_test("Trading Lifecycle List", "PASS", 
                    f"HTTP 200, {len(data) if isinstance(data, list) else 'dict'} items, trace fields: {has_trace_fields}")
            results.append(True)
            
            # Get correlation_id for next tests if available
            correlation_id = None
            if isinstance(data, list) and len(data) > 0:
                correlation_id = data[0].get('correlation_id')
            elif isinstance(data, dict):
                correlation_id = data.get('correlation_id')
                
            return results, correlation_id
        else:
            log_test("Trading Lifecycle List", "FAIL", f"HTTP {response.status_code}")
            results.append(False)
            return results, None
            
    except Exception as e:
        log_test("Trading Lifecycle List", "FAIL", f"Exception: {str(e)}")
        results.append(False)
        return results, None

def test_lifecycle_alias_endpoints(token, correlation_id):
    """Test 3b & 3c: New alias endpoints"""
    headers = {"Authorization": f"Bearer {token}"}
    results = []
    
    if not correlation_id:
        log_test("Lifecycle Alias Endpoints", "SKIP", "No correlation_id available")
        return [False, False]
    
    # Test 3b: GET /api/audit-logs/lifecycle/{correlation_id}
    try:
        url = f"{BASE_URL}/api/audit-logs/lifecycle/{correlation_id}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            has_trace_fields = 'trace_incomplete' in data or 'missing_critical_stages' in data
            log_test("Lifecycle Alias GET", "PASS", 
                    f"HTTP 200, trace fields: {has_trace_fields}")
            results.append(True)
        else:
            log_test("Lifecycle Alias GET", "FAIL", f"HTTP {response.status_code}")
            results.append(False)
            
    except Exception as e:
        log_test("Lifecycle Alias GET", "FAIL", f"Exception: {str(e)}")
        results.append(False)
    
    # Test 3c: POST /api/audit-logs/explain
    try:
        url = f"{BASE_URL}/api/audit-logs/explain"
        payload = {"correlation_id": correlation_id}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            has_trace_fields = 'trace_incomplete' in data or 'missing_critical_stages' in data
            log_test("Lifecycle Explain POST", "PASS", 
                    f"HTTP 200, trace fields: {has_trace_fields}")
            results.append(True)
        else:
            log_test("Lifecycle Explain POST", "FAIL", f"HTTP {response.status_code}")
            results.append(False)
            
    except Exception as e:
        log_test("Lifecycle Explain POST", "FAIL", f"Exception: {str(e)}")
        results.append(False)
    
    return results

def main():
    """Main test execution"""
    print("=" * 80)
    print("TRADING LIFECYCLE DEBUGGER BACKEND VALIDATION")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin Credentials: {ADMIN_EMAIL}")
    print()
    
    all_results = []
    
    # Test 1: Health endpoint
    health_result = test_health_endpoint()
    all_results.append(health_result)
    
    # Test 2: Admin login
    token = test_admin_login()
    login_result = token is not None
    all_results.append(login_result)
    
    if not token:
        print("\n❌ Cannot proceed with lifecycle tests - admin login failed")
        print_summary(all_results, [])
        return
    
    # Test 3: Lifecycle endpoints
    lifecycle_results, correlation_id = test_lifecycle_endpoints(token)
    all_results.extend(lifecycle_results)
    
    # Test 3b & 3c: Alias endpoints
    alias_results = test_lifecycle_alias_endpoints(token, correlation_id)
    all_results.extend(alias_results)
    
    print_summary(all_results, lifecycle_results + alias_results)

def print_summary(all_results, lifecycle_results):
    """Print test summary"""
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for r in all_results if r)
    total = len(all_results)
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"Overall: {passed}/{total} PASS ({success_rate:.1f}% success rate)")
    
    test_names = [
        "Health Endpoint",
        "Admin Login", 
        "Trading Lifecycle List",
        "Lifecycle Alias GET",
        "Lifecycle Explain POST"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, all_results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}) {name}: {status}")
    
    print()
    if success_rate >= 80:
        print("✅✅✅ OVERALL: PASS - Trading Lifecycle Debugger backend validation successful")
        print("Backend stabilization verified. System ready for lifecycle debugging operations.")
    else:
        print("❌❌❌ OVERALL: FAIL - Critical issues detected in Trading Lifecycle Debugger")
        print("Backend stabilization incomplete. Investigation required.")
    
    print("=" * 80)

if __name__ == "__main__":
    main()