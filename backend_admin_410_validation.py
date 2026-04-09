#!/usr/bin/env python3
"""
Admin Action Migration 410 Status Validation
Turkish Review Request - Admin->User aksiyon taşıma sonrası tekrar doğrula

Test specific admin endpoints to verify they return 410 (PURE_LIVE_410) status.
"""

import requests
import json
import sys
from typing import Dict, Any, List, Tuple

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

# Target endpoints that should return 410
TARGET_ENDPOINTS = [
    "POST /api/admin/execution-queue/bulk-decision",
    "POST /api/admin/strategy/signals/approve", 
    "POST /api/admin/strategy/signals/reject",
    "POST /api/admin/strategy/top-signals/execute",
    "POST /api/admin/universe-monitor/scanner/start",
    "POST /api/admin/universe-monitor/scanner/stop",
    "POST /api/admin/universe-monitor/scanner/trigger",
    "POST /api/admin/universe-monitor/scanner/rescan-stale"
]

def authenticate_admin() -> str:
    """Authenticate admin and return access token."""
    print("🔐 Authenticating admin...")
    
    auth_url = f"{BASE_URL}/api/auth/login/admin"
    auth_payload = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    try:
        response = requests.post(auth_url, json=auth_payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token", "")
            print(f"✅ Admin authentication successful (token length: {len(token)} chars)")
            return token
        else:
            print(f"❌ Admin authentication failed: {response.status_code} - {response.text}")
            return ""
    except Exception as e:
        print(f"❌ Admin authentication error: {str(e)}")
        return ""

def test_endpoint_410_status(token: str, method: str, endpoint: str) -> Tuple[int, str]:
    """Test a specific endpoint and return status code and response text."""
    url = f"{BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Prepare minimal payload for POST requests
    payload = {}
    if "bulk-decision" in endpoint:
        payload = {"intent_ids": ["test-intent-id"], "decision": "approve", "reason": "test"}
    elif "signals/approve" in endpoint or "signals/reject" in endpoint:
        payload = {"signal_ids": ["test-signal-id"], "reason": "test"}
    elif "top-signals/execute" in endpoint:
        payload = {"signal_ids": ["test-signal-id"]}
    elif "scanner" in endpoint:
        payload = {"reason": "test"}
    
    try:
        if method == "POST":
            response = requests.post(url, json=payload, headers=headers, timeout=30)
        else:
            response = requests.get(url, headers=headers, timeout=30)
        
        return response.status_code, response.text[:200]  # Limit response text
    except Exception as e:
        return 0, f"Request error: {str(e)}"

def main():
    """Main test execution."""
    print("=" * 80)
    print("ADMIN ACTION MIGRATION 410 STATUS VALIDATION")
    print("Turkish Review Request - Admin->User aksiyon taşıma sonrası tekrar doğrula")
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    print("=" * 80)
    
    # Step 1: Authenticate admin
    token = authenticate_admin()
    if not token:
        print("❌ Cannot proceed without admin authentication")
        sys.exit(1)
    
    # Step 2: Test each target endpoint
    print(f"\n📋 Testing {len(TARGET_ENDPOINTS)} admin endpoints for 410 status...")
    
    results = []
    pass_count = 0
    fail_count = 0
    
    for endpoint_spec in TARGET_ENDPOINTS:
        method, endpoint = endpoint_spec.split(" ", 1)
        print(f"\n🔍 Testing: {endpoint_spec}")
        
        status_code, response_text = test_endpoint_410_status(token, method, endpoint)
        
        if status_code == 410:
            print(f"✅ PASS - Returns 410 (PURE_LIVE_410) as expected")
            results.append(f"✅ {endpoint_spec} -> 410")
            pass_count += 1
        elif status_code == 0:
            print(f"❌ FAIL - Request error: {response_text}")
            results.append(f"❌ {endpoint_spec} -> ERROR: {response_text}")
            fail_count += 1
        else:
            print(f"❌ FAIL - Returns {status_code} (expected 410)")
            print(f"   Response: {response_text}")
            results.append(f"❌ {endpoint_spec} -> {status_code}")
            fail_count += 1
    
    # Step 3: Summary
    print("\n" + "=" * 80)
    print("SUMMARY RESULTS")
    print("=" * 80)
    
    for result in results:
        print(result)
    
    success_rate = (pass_count / len(TARGET_ENDPOINTS)) * 100
    print(f"\n📊 OVERALL RESULT: {pass_count}/{len(TARGET_ENDPOINTS)} PASS ({success_rate:.1f}% success rate)")
    
    if pass_count == len(TARGET_ENDPOINTS):
        print("✅✅✅ ALL ENDPOINTS RETURN 410 - Admin action migration completed successfully")
        print("🎯 EXPECTATION MET: tamamı 410 (PURE_LIVE_410)")
    else:
        print(f"❌ PARTIAL FAIL - {fail_count} endpoints not returning 410")
        print("⚠️ Admin action migration incomplete")
    
    # Turkish summary
    print("\n🇹🇷 TURKISH SUMMARY:")
    print("Çıktı:")
    for endpoint_spec in TARGET_ENDPOINTS:
        method, endpoint = endpoint_spec.split(" ", 1)
        endpoint_name = endpoint.split("/")[-1]
        result = next((r for r in results if endpoint_spec in r), "")
        if "410" in result:
            print(f"- {endpoint_name} -> 410")
        else:
            status = result.split("->")[-1].strip() if "->" in result else "ERROR"
            print(f"- {endpoint_name} -> {status}")
    
    if pass_count == len(TARGET_ENDPOINTS):
        print("PASS/FAIL özet: ✅ PASS - Tüm endpoint'ler 410 döndürüyor")
    else:
        print(f"PASS/FAIL özet: ❌ FAIL - {fail_count} endpoint 410 döndürmüyor")

if __name__ == "__main__":
    main()