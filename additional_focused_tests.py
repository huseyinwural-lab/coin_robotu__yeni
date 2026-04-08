#!/usr/bin/env python3
"""
Additional focused tests for Turkish Review Request
"""

import requests
import json
import time

BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def authenticate_both():
    session = requests.Session()
    
    # User auth
    user_response = session.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=15
    )
    user_token = user_response.json().get("access_token") if user_response.status_code == 200 else None
    
    # Admin auth
    admin_response = session.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15
    )
    admin_token = admin_response.json().get("access_token") if admin_response.status_code == 200 else None
    
    return session, user_token, admin_token

def test_advisory_mode_rules():
    print("🔍 DETAILED ADVISORY MODE / BLOCKED RULES INVESTIGATION")
    session, user_token, admin_token = authenticate_both()
    
    if not user_token:
        print("❌ User authentication failed")
        return
    
    user_headers = {"Authorization": f"Bearer {user_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else user_headers
    
    # Test 1: Check trading validation rules
    print("\n📋 Testing trading validation...")
    try:
        validate_response = session.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "market",
                "quantity": 0.001
            },
            timeout=10
        )
        
        if validate_response.status_code == 200:
            validation_data = validate_response.json()
            print(f"Validation response: {validation_data}")
            
            # Check for blocking rules
            violations = validation_data.get("violations", [])
            blocked_reasons = validation_data.get("blocked_reasons", [])
            
            if violations or blocked_reasons:
                print(f"⚠️ BLOCKING RULES FOUND:")
                for violation in violations:
                    print(f"  - Violation: {violation}")
                for reason in blocked_reasons:
                    print(f"  - Blocked reason: {reason}")
            else:
                print("✅ No blocking rules detected in validation")
        else:
            print(f"Validation failed: {validate_response.status_code}")
    except Exception as e:
        print(f"Validation test error: {e}")
    
    # Test 2: Check symbol restrictions
    print("\n🚫 Testing symbol restrictions...")
    try:
        symbols_response = session.get(f"{BASE_URL}/api/market/symbols", headers=user_headers, timeout=10)
        if symbols_response.status_code == 200:
            symbols_data = symbols_response.json()
            symbols = symbols_data.get("symbols", [])
            
            blocked_count = 0
            non_tradeable_count = 0
            
            for symbol in symbols[:10]:  # Check first 10 symbols
                if symbol.get("status") == "blocked":
                    blocked_count += 1
                if not symbol.get("tradeable", True):
                    non_tradeable_count += 1
            
            print(f"Symbol analysis (first 10): {blocked_count} blocked, {non_tradeable_count} non-tradeable")
            
            if blocked_count > 0 or non_tradeable_count > 0:
                print(f"⚠️ HARD-CODED RESTRICTIONS FOUND")
            else:
                print("✅ No hard-coded symbol restrictions detected")
        else:
            print(f"Symbols request failed: {symbols_response.status_code}")
    except Exception as e:
        print(f"Symbols test error: {e}")

def test_auth_mechanisms():
    print("\n🔐 DETAILED AUTH PERSISTENCE INVESTIGATION")
    session, user_token, admin_token = authenticate_both()
    
    if not user_token:
        print("❌ Authentication failed")
        return
    
    # Test 1: JWT token refresh mechanism
    print("\n🔄 Testing refresh token mechanism...")
    try:
        # Try refresh with proper payload
        refresh_response = session.post(
            f"{BASE_URL}/api/auth/refresh",
            json={"refresh_token": "dummy_token"},  # This will likely fail but shows the mechanism
            timeout=10
        )
        
        print(f"Refresh endpoint status: {refresh_response.status_code}")
        if refresh_response.status_code == 422:
            error_data = refresh_response.json()
            print(f"Refresh validation error: {error_data}")
            print("✅ Refresh endpoint exists with proper validation")
        elif refresh_response.status_code == 200:
            print("✅ Refresh mechanism working")
        else:
            print(f"⚠️ Unexpected refresh response: {refresh_response.status_code}")
    except Exception as e:
        print(f"Refresh test error: {e}")
    
    # Test 2: Session persistence
    print("\n👤 Testing session persistence...")
    try:
        # Test /me endpoint
        me_response = session.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
        print(f"Auth /me status: {me_response.status_code}")
        
        if me_response.status_code == 200:
            user_data = me_response.json()
            print(f"User data: {user_data.get('email', 'N/A')}, Role: {user_data.get('role', 'N/A')}")
            print("✅ Session persistence working")
        else:
            print("❌ Session persistence issue")
    except Exception as e:
        print(f"Session test error: {e}")
    
    # Test 3: Cookie mechanism
    print("\n🍪 Testing cookie mechanism...")
    try:
        # Fresh session for cookie test
        cookie_session = requests.Session()
        login_response = cookie_session.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        
        if login_response.status_code == 200:
            cookies = dict(cookie_session.cookies)
            print(f"Cookies set: {list(cookies.keys())}")
            
            # Test if cookies work for auth
            me_with_cookies = cookie_session.get(f"{BASE_URL}/api/auth/me")
            print(f"Cookie auth status: {me_with_cookies.status_code}")
            
            if me_with_cookies.status_code == 200:
                print("✅ Cookie-based authentication working")
            else:
                print("⚠️ Cookie-based authentication not working")
        
    except Exception as e:
        print(f"Cookie test error: {e}")

def test_resource_monitoring():
    print("\n📊 RESOURCE CONSUMPTION MONITORING")
    session, user_token, admin_token = authenticate_both()
    
    if not user_token:
        print("❌ Authentication failed")
        return
    
    headers = {"Authorization": f"Bearer {user_token}"}
    
    # Test API response times under load
    print("\n⏱️ API Performance Testing...")
    
    endpoints = [
        "/api/health",
        "/api/user/signals",
        "/api/market/ticker?symbol=BTCUSDT",
        "/api/user/scanner-engine/config"
    ]
    
    for endpoint in endpoints:
        times = []
        for i in range(3):  # 3 requests per endpoint
            start = time.time()
            try:
                response = session.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
                end = time.time()
                response_time = (end - start) * 1000
                times.append(response_time)
                print(f"  {endpoint}: {response_time:.1f}ms (HTTP {response.status_code})")
            except Exception as e:
                print(f"  {endpoint}: ERROR - {e}")
        
        if times:
            avg_time = sum(times) / len(times)
            print(f"  Average: {avg_time:.1f}ms")
            
            if avg_time > 2000:  # > 2 seconds
                print(f"    ⚠️ SLOW RESPONSE TIME")
            elif avg_time > 1000:  # > 1 second
                print(f"    ⚠️ MODERATE RESPONSE TIME")
            else:
                print(f"    ✅ GOOD RESPONSE TIME")

if __name__ == "__main__":
    test_advisory_mode_rules()
    test_auth_mechanisms()
    test_resource_monitoring()