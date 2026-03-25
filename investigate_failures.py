#!/usr/bin/env python3
"""
Detailed investigation of the failing tests
"""

import requests
import json
import time

# Get backend URL from frontend env
BACKEND_URL = "https://finops-dashboard-10.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def login_and_get_token():
    """Login and get admin token"""
    session = requests.Session()
    response = session.post(
        f"{API_BASE}/auth/login/admin",
        json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
            return session
    return None

def investigate_determinism():
    """Investigate the determinism issue"""
    print("🔍 Investigating Determinism Issue")
    print("=" * 50)
    
    session = login_and_get_token()
    if not session:
        print("❌ Failed to login")
        return
    
    # Make first call
    print("Making first call...")
    response1 = session.get(f"{API_BASE}/admin/users/economics")
    if response1.status_code != 200:
        print(f"❌ First call failed: {response1.status_code}")
        return
    
    data1 = response1.json()
    print(f"First call data keys: {list(data1.keys()) if isinstance(data1, dict) else 'Not a dict'}")
    
    # Wait a moment
    time.sleep(2)
    
    # Make second call
    print("Making second call...")
    response2 = session.get(f"{API_BASE}/admin/users/economics")
    if response2.status_code != 200:
        print(f"❌ Second call failed: {response2.status_code}")
        return
    
    data2 = response2.json()
    print(f"Second call data keys: {list(data2.keys()) if isinstance(data2, dict) else 'Not a dict'}")
    
    # Compare
    if data1 == data2:
        print("✅ Data is identical")
    else:
        print("❌ Data differs")
        print("Analyzing differences...")
        
        if isinstance(data1, dict) and isinstance(data2, dict):
            for key in data1.keys():
                if key not in data2:
                    print(f"  Key '{key}' missing in second call")
                elif data1[key] != data2[key]:
                    print(f"  Key '{key}' differs:")
                    print(f"    Call 1: {data1[key]}")
                    print(f"    Call 2: {data2[key]}")
        
        # Check if only timestamps differ
        if isinstance(data1, dict) and isinstance(data2, dict):
            data1_clean = {k: v for k, v in data1.items() if 'timestamp' not in k.lower() and 'time' not in k.lower() and 'generated_at' not in k.lower()}
            data2_clean = {k: v for k, v in data2.items() if 'timestamp' not in k.lower() and 'time' not in k.lower() and 'generated_at' not in k.lower()}
            
            if data1_clean == data2_clean:
                print("✅ Only timestamp fields differ (acceptable)")
            else:
                print("❌ Non-timestamp fields also differ")

def investigate_live_gate():
    """Investigate the live gate issue"""
    print("\n🔍 Investigating Live Gate Issue")
    print("=" * 50)
    
    session = login_and_get_token()
    if not session:
        print("❌ Failed to login")
        return
    
    # Try with different parameters
    test_cases = [
        {},  # No parameters
        {"target_user_email": ADMIN_EMAIL},  # With admin email
        {"target_user_email": "test@example.com"},  # With test email
        {"target_user_email": ADMIN_EMAIL, "environment": "testnet"},  # With environment
        {"target_user_email": ADMIN_EMAIL, "environment": "testnet", "required_market_types": ["futures"]},  # Full params
    ]
    
    for i, params in enumerate(test_cases):
        print(f"\nTest case {i+1}: {params}")
        response = session.get(f"{API_BASE}/admin/commercial/p0/live-gate", params=params)
        print(f"Status: {response.status_code}")
        if response.content:
            try:
                data = response.json()
                print(f"Response: {data}")
            except:
                print(f"Response (text): {response.text[:200]}...")

if __name__ == "__main__":
    investigate_determinism()
    investigate_live_gate()