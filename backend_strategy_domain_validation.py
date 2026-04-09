#!/usr/bin/env python3
"""
Backend Strategy Domain Runtime Validation
Turkish Review Request - Strategy Domain Runtime Dispatch/Run-Once 410 Block Validation

Test Requirements:
1) POST /api/strategy-domain/admin/runtime/dispatch => 410 PURE_LIVE_410
2) POST /api/strategy-domain/admin/runtime/worker/run-once => 410 PURE_LIVE_410
3) Code verification: strategy_domain.py contains 410 block mechanism

Base URL: https://trade-trace-engine.preview.emergentagent.com
Admin: canary.admin@platform.local / CanaryAdmin123!
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def authenticate_admin():
    """Authenticate as admin and return access token"""
    print("🔐 Authenticating as admin...")
    
    auth_url = f"{BASE_URL}/api/auth/login/admin"
    auth_payload = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    try:
        response = requests.post(auth_url, json=auth_payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            access_token = data.get("access_token")
            if access_token:
                print(f"✅ Admin authentication successful. Token length: {len(access_token)} chars")
                return access_token
            else:
                print("❌ No access token in response")
                return None
        else:
            print(f"❌ Admin authentication failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Admin authentication error: {e}")
        return None

def test_strategy_domain_endpoints(token):
    """Test strategy domain runtime endpoints for 410 PURE_LIVE_410 responses"""
    print("\n📋 Testing Strategy Domain Runtime Endpoints...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    test_results = []
    
    # Test 1: POST /api/strategy-domain/admin/runtime/dispatch
    print("\n1️⃣ Testing POST /api/strategy-domain/admin/runtime/dispatch")
    try:
        dispatch_url = f"{BASE_URL}/api/strategy-domain/admin/runtime/dispatch"
        dispatch_payload = {
            "action": "test_dispatch",
            "parameters": {}
        }
        
        response = requests.post(dispatch_url, json=dispatch_payload, headers=headers, timeout=10)
        status_code = response.status_code
        
        if status_code == 410:
            try:
                response_data = response.json()
                detail = response_data.get("detail", "")
                if detail == "PURE_LIVE_410":
                    print(f"✅ PASS - POST /api/strategy-domain/admin/runtime/dispatch => 410 PURE_LIVE_410")
                    test_results.append(("dispatch", "PASS", f"410 + PURE_LIVE_410"))
                else:
                    print(f"⚠️ PARTIAL - POST /api/strategy-domain/admin/runtime/dispatch => 410 but detail='{detail}' (expected PURE_LIVE_410)")
                    test_results.append(("dispatch", "PARTIAL", f"410 + {detail}"))
            except:
                print(f"⚠️ PARTIAL - POST /api/strategy-domain/admin/runtime/dispatch => 410 but no JSON detail")
                test_results.append(("dispatch", "PARTIAL", f"410 + no_json"))
        else:
            print(f"❌ FAIL - POST /api/strategy-domain/admin/runtime/dispatch => {status_code} (expected 410)")
            test_results.append(("dispatch", "FAIL", f"{status_code}"))
            
    except Exception as e:
        print(f"❌ ERROR - POST /api/strategy-domain/admin/runtime/dispatch: {e}")
        test_results.append(("dispatch", "ERROR", str(e)))
    
    # Test 2: POST /api/strategy-domain/admin/runtime/worker/run-once
    print("\n2️⃣ Testing POST /api/strategy-domain/admin/runtime/worker/run-once")
    try:
        run_once_url = f"{BASE_URL}/api/strategy-domain/admin/runtime/worker/run-once"
        run_once_payload = {
            "worker_type": "test_worker",
            "parameters": {}
        }
        
        response = requests.post(run_once_url, json=run_once_payload, headers=headers, timeout=10)
        status_code = response.status_code
        
        if status_code == 410:
            try:
                response_data = response.json()
                detail = response_data.get("detail", "")
                if detail == "PURE_LIVE_410":
                    print(f"✅ PASS - POST /api/strategy-domain/admin/runtime/worker/run-once => 410 PURE_LIVE_410")
                    test_results.append(("run-once", "PASS", f"410 + PURE_LIVE_410"))
                else:
                    print(f"⚠️ PARTIAL - POST /api/strategy-domain/admin/runtime/worker/run-once => 410 but detail='{detail}' (expected PURE_LIVE_410)")
                    test_results.append(("run-once", "PARTIAL", f"410 + {detail}"))
            except:
                print(f"⚠️ PARTIAL - POST /api/strategy-domain/admin/runtime/worker/run-once => 410 but no JSON detail")
                test_results.append(("run-once", "PARTIAL", f"410 + no_json"))
        else:
            print(f"❌ FAIL - POST /api/strategy-domain/admin/runtime/worker/run-once => {status_code} (expected 410)")
            test_results.append(("run-once", "FAIL", f"{status_code}"))
            
    except Exception as e:
        print(f"❌ ERROR - POST /api/strategy-domain/admin/runtime/worker/run-once: {e}")
        test_results.append(("run-once", "ERROR", str(e)))
    
    return test_results

def main():
    """Main test execution"""
    print("🚀 BACKEND STRATEGY DOMAIN RUNTIME VALIDATION")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Step 1: Authenticate
    token = authenticate_admin()
    if not token:
        print("\n❌ CRITICAL: Admin authentication failed. Cannot proceed with testing.")
        sys.exit(1)
    
    # Step 2: Test strategy domain endpoints
    test_results = test_strategy_domain_endpoints(token)
    
    # Step 3: Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    total_tests = len(test_results)
    passed_tests = len([r for r in test_results if r[1] == "PASS"])
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    print("\nDetailed Results:")
    for endpoint, status, evidence in test_results:
        status_emoji = "✅" if status == "PASS" else "⚠️" if status == "PARTIAL" else "❌"
        print(f"{status_emoji} {endpoint}: {status} - {evidence}")
    
    # Turkish Summary
    print("\n🇹🇷 TURKISH SUMMARY:")
    print("PASS/FAIL + kısa kanıt:")
    
    for endpoint, status, evidence in test_results:
        if endpoint == "dispatch":
            endpoint_tr = "runtime dispatch"
        elif endpoint == "run-once":
            endpoint_tr = "runtime worker run-once"
        else:
            endpoint_tr = endpoint
            
        if status == "PASS":
            print(f"✅ PASS - {endpoint_tr}: {evidence}")
        elif status == "PARTIAL":
            print(f"⚠️ PARTIAL - {endpoint_tr}: {evidence}")
        else:
            print(f"❌ FAIL - {endpoint_tr}: {evidence}")
    
    overall_status = "PASS" if passed_tests == total_tests else "PARTIAL" if passed_tests > 0 else "FAIL"
    print(f"\nSONUÇ: {overall_status} - {passed_tests}/{total_tests} endpoint 410 PURE_LIVE_410 döndürüyor.")
    
    print("\n" + "=" * 60)
    print("✅ BACKEND STRATEGY DOMAIN RUNTIME VALIDATION COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    main()