#!/usr/bin/env python3
"""
FAZ-4+ / FAZ-5 Backend Diagnostic Test
Focused diagnostic test for failing endpoints
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://hard-guard-layer.preview.emergentagent.com"
CREDENTIALS = {
    "super_admin": {"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"}
}

def login_and_get_token():
    """Login and get access token"""
    try:
        creds = CREDENTIALS["super_admin"]
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": creds["email"], "password": creds["password"]},
            timeout=30
        )
        
        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"✅ Login successful, token length: {len(token) if token else 0}")
            return token
        else:
            print(f"❌ Login failed: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Login exception: {str(e)}")
        return None

def test_endpoint_detailed(endpoint, method="GET", payload=None):
    """Test endpoint with detailed error reporting"""
    token = login_and_get_token()
    if not token:
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\n🔍 Testing {method} {endpoint}")
    
    try:
        if method == "GET":
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(f"{BASE_URL}{endpoint}", headers=headers, json=payload, timeout=30)
        else:
            print(f"❌ Unsupported method: {method}")
            return
            
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"✅ Response JSON keys: {list(data.keys()) if isinstance(data, dict) else f'List with {len(data)} items'}")
                
                # Pretty print first few lines of response
                response_text = json.dumps(data, indent=2)[:500]
                print(f"Response preview:\n{response_text}...")
                
            except Exception as e:
                print(f"⚠️ JSON parse error: {str(e)}")
                print(f"Raw response: {response.text[:200]}...")
        else:
            print(f"❌ Error response: {response.text[:200]}...")
            
    except requests.exceptions.Timeout:
        print("❌ Request timeout (30s)")
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error: {str(e)}")
    except Exception as e:
        print(f"❌ Request exception: {str(e)}")

def main():
    print("=" * 80)
    print("FAZ-4+ / FAZ-5 BACKEND DIAGNOSTIC TEST")
    print("=" * 80)
    
    # Test the failing endpoints
    endpoints_to_test = [
        # Rollback request endpoint
        ("/api/admin/futures/strategy/trend_follow_v1/rollback-request", "POST", {}),
        ("/api/admin/futures/strategy/trend_follow_v1/rollback-request", "POST", {
            "reason": "Test rollback request for diagnostic",
            "preview": True
        }),
        
        # Policy suggestions endpoint
        ("/api/admin/futures/strategy-control/policy-suggestions", "GET", None),
        
        # Working endpoints for comparison
        ("/api/admin/futures/strategy/trend_follow_v1/rollback-snapshots", "GET", None),
        ("/api/admin/futures/strategy-control/drift-alerts", "GET", None),
    ]
    
    for endpoint, method, payload in endpoints_to_test:
        test_endpoint_detailed(endpoint, method, payload)
        print("-" * 40)

if __name__ == "__main__":
    main()