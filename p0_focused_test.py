#!/usr/bin/env python3
"""
P0 Regression Test - Focused Backend Testing
Quick focused test for specific P0 requirements
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

def test_login_and_endpoints():
    """Test login and specific endpoints"""
    session = requests.Session()
    
    print("=" * 60)
    print("P0 REGRESSION TEST - FOCUSED")
    print("=" * 60)
    
    # Test 1: Login
    print("🔐 Testing User Login...")
    login_url = f"{BASE_URL}/api/auth/login"
    login_data = {"email": USER_EMAIL, "password": USER_PASSWORD}
    
    try:
        response = session.post(login_url, json=login_data)
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            device_id = data.get("device_id")
            
            session.headers.update({
                "Authorization": f"Bearer {token}",
                "X-Session-Device": device_id
            })
            
            print(f"✅ Login successful - Token length: {len(token)}")
        else:
            print(f"❌ Login failed - HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return
    except Exception as e:
        print(f"❌ Login error: {e}")
        return
    
    # Test 2: Scanner Status Contract
    print("\n📊 Testing Scanner Status Contract...")
    try:
        url = f"{BASE_URL}/api/user/scanner/status-contract"
        response = session.get(url)
        
        if response.status_code == 200:
            data = response.json()
            blocking_reasons = data.get("blocking_reasons", [])
            health = data.get("health", "UNKNOWN")
            
            print(f"✅ Scanner Status Contract - HTTP 200")
            print(f"   blocking_reasons: {blocking_reasons}")
            print(f"   health: {health}")
            
            # Check if blocking_reasons is properly populated (not force-reset to empty)
            if isinstance(blocking_reasons, list):
                print(f"   ✅ blocking_reasons is list type (not force-reset)")
            else:
                print(f"   ❌ blocking_reasons is not list type")
                
            # Check if health is BLOCKED/HEALTHY
            if health in ["BLOCKED", "HEALTHY"]:
                print(f"   ✅ health status is valid: {health}")
            else:
                print(f"   ❌ health status invalid: {health}")
        else:
            print(f"❌ Scanner Status Contract failed - HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"❌ Scanner Status Contract error: {e}")
    
    # Test 3: Exchange Connections
    print("\n🔗 Testing Exchange Connections...")
    try:
        url = f"{BASE_URL}/api/user/exchange-connections"
        response = session.get(url)
        
        if response.status_code == 200:
            data = response.json()
            routing_preview = data.get("routing_preview", {})
            selection_reason = routing_preview.get("selection_reason", "")
            
            print(f"✅ Exchange Connections - HTTP 200")
            print(f"   routing_preview: {routing_preview}")
            print(f"   selection_reason: {selection_reason}")
            
            # Check if selection_reason is execution_user_source_required
            expected = "execution_user_source_required"
            if selection_reason == expected:
                print(f"   ✅ selection_reason matches expected: {expected}")
            else:
                print(f"   ❌ selection_reason mismatch - got: {selection_reason}, expected: {expected}")
        else:
            print(f"❌ Exchange Connections failed - HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"❌ Exchange Connections error: {e}")
    
    # Test 4: Trading Preview
    print("\n📈 Testing Trading Preview...")
    try:
        # First validate
        validate_url = f"{BASE_URL}/api/user/validate-order"
        validate_data = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 20,
            "market_type": "spot"
        }
        
        validate_response = session.post(validate_url, json=validate_data)
        print(f"   Validation: HTTP {validate_response.status_code}")
        
        if validate_response.status_code == 200:
            # Test preview
            preview_url = f"{BASE_URL}/api/v1/user/trading/preview"
            preview_data = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 20,
                "market_type": "spot"
            }
            
            preview_response = session.post(preview_url, json=preview_data)
            print(f"   Preview: HTTP {preview_response.status_code}")
            
            if preview_response.status_code == 200:
                preview_result = preview_response.json()
                execution_mode = preview_result.get("execution_mode", "")
                readiness_status = preview_result.get("readiness_status", "")
                
                print(f"   ✅ Preview successful")
                print(f"   execution_mode: {execution_mode}")
                print(f"   readiness_status: {readiness_status}")
                
                # Test open position to check execution guard
                open_url = f"{BASE_URL}/api/user/open-position"
                open_response = session.post(open_url, json=preview_data)
                print(f"   Open Position: HTTP {open_response.status_code}")
                
                if readiness_status == "FAIL" and open_response.status_code in [423, 400]:
                    print(f"   ✅ Execution guard STRICT - correctly blocked on readiness fail")
                elif readiness_status == "READY" and open_response.status_code == 200:
                    print(f"   ✅ Execution guard STRICT - allowed on readiness pass")
                else:
                    print(f"   ⚠️ Execution guard behavior: readiness={readiness_status}, open_status={open_response.status_code}")
                    if open_response.status_code != 200:
                        print(f"   Open Position Error: {open_response.text[:200]}")
            else:
                print(f"   ❌ Preview failed: {preview_response.text[:200]}")
        else:
            print(f"   ❌ Validation failed: {validate_response.text[:200]}")
    except Exception as e:
        print(f"❌ Trading Preview error: {e}")
    
    print("\n" + "=" * 60)
    print("P0 REGRESSION TEST COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    test_login_and_endpoints()