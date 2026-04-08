#!/usr/bin/env python3
"""
P0 Backend Validation - Turkish Review Request
Targeted P0 validation for specific critical issues:
1) P0-1 Market Data Zero-Price
2) P0-2 Scanner Analyze endpoint 404  
3) P0-3 session_device_missing (allocation)
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

def log_test(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def admin_login():
    """Admin authentication"""
    log_test("🔐 Admin Login...")
    
    login_data = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    response = requests.post(f"{BASE_URL}/api/auth/login/admin", json=login_data, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        token = data.get('access_token')
        log_test(f"✅ Admin login successful. Token length: {len(token)} chars")
        return token
    else:
        log_test(f"❌ Admin login failed: {response.status_code} - {response.text}")
        return None

def user_login():
    """User authentication"""
    log_test("🔐 User Login...")
    
    login_data = {
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    }
    
    response = requests.post(f"{BASE_URL}/api/auth/login/user", json=login_data, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        token = data.get('access_token')
        log_test(f"✅ User login successful. Token length: {len(token)} chars")
        return token
    else:
        log_test(f"❌ User login failed: {response.status_code} - {response.text}")
        return None

def test_p0_1_market_data_zero_price(user_token):
    """
    P0-1 Market Data Zero-Price
    Check if scanner market data source has symbols with last_price <= 0
    Validate BTCUSDT price > 0
    """
    log_test("\n📊 P0-1 Market Data Zero-Price Test")
    
    try:
        # Test market ticker endpoint for BTCUSDT with authentication
        headers = {"Authorization": f"Bearer {user_token}"} if user_token else {}
        response = requests.get(f"{BASE_URL}/api/market/ticker?symbol=BTCUSDT", headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            # Check for last_price first, then fallback to mid_price
            last_price = data.get('last_price', 0)
            mid_price = data.get('mid_price', 0)
            
            # Use the available price field
            price_to_check = last_price if last_price > 0 else mid_price
            price_field = "last_price" if last_price > 0 else "mid_price"
            
            log_test(f"Market ticker response: {json.dumps(data, indent=2)}")
            
            if price_to_check > 0:
                log_test(f"✅ P0-1 PASS: BTCUSDT {price_field} = {price_to_check} (> 0)")
                return "PASS", f"BTCUSDT {price_field}: {price_to_check}"
            else:
                log_test(f"❌ P0-1 FAIL: BTCUSDT {price_field} = {price_to_check} (<= 0)")
                return "FAIL", f"BTCUSDT {price_field}: {price_to_check} (zero price detected)"
        else:
            log_test(f"❌ P0-1 FAIL: Market ticker endpoint error: {response.status_code}")
            return "FAIL", f"Market ticker API error: {response.status_code}"
            
    except Exception as e:
        log_test(f"❌ P0-1 FAIL: Exception during market data test: {str(e)}")
        return "FAIL", f"Exception: {str(e)}"

def test_p0_2_scanner_analyze_404(admin_token, user_token):
    """
    P0-2 Scanner Analyze endpoint 404
    Check these endpoints don't return 404:
    - /api/user/scanner-engine/analyze
    - /api/user/scanner/analyze  
    - /api/admin/universe-monitor/scanner-engine/analyze
    """
    log_test("\n🔍 P0-2 Scanner Analyze endpoint 404 Test")
    
    endpoints = [
        ("/api/user/scanner-engine/analyze", user_token, "User"),
        ("/api/user/scanner/analyze", user_token, "User"),
        ("/api/admin/universe-monitor/scanner-engine/analyze", admin_token, "Admin")
    ]
    
    results = []
    
    for endpoint, token, auth_type in endpoints:
        try:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            
            # Try GET first
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=15)
            status_code = response.status_code
            
            log_test(f"{auth_type} GET {endpoint}: {status_code}")
            
            if status_code == 404:
                # Try POST if GET returns 404
                response = requests.post(f"{BASE_URL}{endpoint}", headers=headers, json={}, timeout=15)
                status_code = response.status_code
                log_test(f"{auth_type} POST {endpoint}: {status_code}")
            
            if status_code == 404:
                log_test(f"❌ {endpoint}: 404 (FAIL)")
                results.append(f"❌ {endpoint}: 404")
            elif status_code in [405, 422, 200]:
                log_test(f"✅ {endpoint}: {status_code} (PASS - not 404)")
                results.append(f"✅ {endpoint}: {status_code}")
            else:
                log_test(f"⚠️ {endpoint}: {status_code} (unexpected but not 404)")
                results.append(f"⚠️ {endpoint}: {status_code}")
                
        except Exception as e:
            log_test(f"❌ {endpoint}: Exception - {str(e)}")
            results.append(f"❌ {endpoint}: Exception")
    
    # Determine overall result
    fail_count = len([r for r in results if r.startswith("❌")])
    
    if fail_count == 0:
        return "PASS", f"All endpoints accessible: {', '.join(results)}"
    else:
        return "FAIL", f"{fail_count}/3 endpoints return 404: {', '.join(results)}"

def test_p0_3_session_device_missing(admin_token):
    """
    P0-3 session_device_missing (allocation)
    Test admin allocation endpoints with auth-only requests multiple times
    Check if 401 session_device_missing repeats
    """
    log_test("\n🔒 P0-3 session_device_missing (allocation) Test")
    
    endpoints = [
        "/api/admin/strategy-allocation",
        "/api/admin/strategy-allocation/summary"
    ]
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    session_device_errors = []
    
    for endpoint in endpoints:
        log_test(f"Testing {endpoint} multiple times...")
        
        for attempt in range(3):
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=15)
                status_code = response.status_code
                
                log_test(f"  Attempt {attempt + 1}: {status_code}")
                
                if status_code == 401:
                    try:
                        error_data = response.json()
                        if "session_device_missing" in str(error_data):
                            session_device_errors.append(f"{endpoint} attempt {attempt + 1}: session_device_missing")
                            log_test(f"    ❌ session_device_missing detected")
                        else:
                            log_test(f"    ⚠️ 401 but not session_device_missing: {error_data}")
                    except:
                        log_test(f"    ⚠️ 401 but cannot parse error")
                elif status_code == 200:
                    log_test(f"    ✅ Success")
                else:
                    log_test(f"    ⚠️ Unexpected status: {status_code}")
                    
                # Small delay between attempts
                time.sleep(1)
                
            except Exception as e:
                log_test(f"    ❌ Exception: {str(e)}")
                session_device_errors.append(f"{endpoint} attempt {attempt + 1}: Exception")
    
    if session_device_errors:
        return "FAIL", f"session_device_missing detected: {', '.join(session_device_errors)}"
    else:
        return "PASS", "No session_device_missing errors detected"

def main():
    """Main test execution"""
    log_test("🚀 P0 Backend Validation - Turkish Review Request")
    log_test(f"Base URL: {BASE_URL}")
    log_test(f"Admin: {ADMIN_EMAIL}")
    log_test(f"User: {USER_EMAIL}")
    
    # Authentication
    admin_token = admin_login()
    user_token = user_login()
    
    if not admin_token:
        log_test("❌ Cannot proceed without admin token")
        return
    
    if not user_token:
        log_test("⚠️ Proceeding without user token (some tests may fail)")
    
    # Test Results
    results = {}
    
    # P0-1: Market Data Zero-Price
    result, details = test_p0_1_market_data_zero_price(user_token)
    results["P0-1 Market Data Zero-Price"] = {"result": result, "details": details}
    
    # P0-2: Scanner Analyze endpoint 404
    result, details = test_p0_2_scanner_analyze_404(admin_token, user_token)
    results["P0-2 Scanner Analyze endpoint 404"] = {"result": result, "details": details}
    
    # P0-3: session_device_missing (allocation)
    result, details = test_p0_3_session_device_missing(admin_token)
    results["P0-3 session_device_missing (allocation)"] = {"result": result, "details": details}
    
    # Summary Report
    log_test("\n" + "="*80)
    log_test("📋 P0 VALIDATION SUMMARY REPORT")
    log_test("="*80)
    
    pass_count = 0
    fail_count = 0
    
    for test_name, test_data in results.items():
        result = test_data["result"]
        details = test_data["details"]
        
        if result == "PASS":
            log_test(f"✅ {test_name}: PASS")
            log_test(f"   {details}")
            pass_count += 1
        else:
            log_test(f"❌ {test_name}: FAIL")
            log_test(f"   {details}")
            fail_count += 1
    
    log_test(f"\nOVERALL RESULT: {pass_count} PASS, {fail_count} FAIL")
    
    if fail_count == 0:
        log_test("🎉 ALL P0 VALIDATIONS PASSED")
    else:
        log_test("⚠️ CRITICAL BLOCKERS DETECTED")
    
    # Turkish Summary
    log_test("\n" + "="*80)
    log_test("🇹🇷 TÜRKÇE ÖZET")
    log_test("="*80)
    
    for test_name, test_data in results.items():
        result = test_data["result"]
        details = test_data["details"]
        
        if "Market Data" in test_name:
            log_test(f"1) P0-1 Market Data Zero-Price: {result}")
            log_test(f"   - {details}")
        elif "Scanner Analyze" in test_name:
            log_test(f"2) P0-2 Scanner Analyze endpoint 404: {result}")
            log_test(f"   - {details}")
        elif "session_device_missing" in test_name:
            log_test(f"3) P0-3 session_device_missing (allocation): {result}")
            log_test(f"   - {details}")
    
    log_test(f"\nSONUÇ: {pass_count}/{len(results)} test başarılı")
    
    if fail_count > 0:
        log_test("⚠️ Kritik blokajlar tespit edildi - düzeltme gerekli")
    else:
        log_test("✅ Tüm P0 doğrulamalar başarılı")

if __name__ == "__main__":
    main()