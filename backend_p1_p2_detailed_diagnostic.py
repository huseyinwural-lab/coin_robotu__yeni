#!/usr/bin/env python3
"""
P1+P2 Readiness Hardening Detailed Diagnostic Test
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def get_admin_token():
    """Get admin authentication token"""
    session = requests.Session()
    login_data = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json=login_data,
        timeout=30
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    else:
        print(f"❌ Login failed: {response.status_code}")
        return None

def test_detailed_api_responses():
    """Test and display detailed API responses"""
    session = get_admin_token()
    if not session:
        return
    
    print("=" * 80)
    print("P1+P2 READINESS HARDENING - DETAILED API RESPONSE ANALYSIS")
    print("=" * 80)
    
    # Test 1: /api/admin/futures/live-readiness
    print("\n1. GET /api/admin/futures/live-readiness")
    print("-" * 50)
    try:
        response = session.get(f"{BASE_URL}/api/admin/futures/live-readiness", timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response Keys: {list(data.keys())}")
            print(f"Full Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error Response: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")
    
    # Test 2: /api/admin/futures/readiness/history
    print("\n\n2. GET /api/admin/futures/readiness/history?limit=20&days=14")
    print("-" * 50)
    try:
        response = session.get(f"{BASE_URL}/api/admin/futures/readiness/history?limit=20&days=14", timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response Keys: {list(data.keys())}")
            print(f"Full Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error Response: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")
    
    # Test 3: /api/admin/execution-readiness
    print("\n\n3. GET /api/admin/execution-readiness")
    print("-" * 50)
    try:
        response = session.get(f"{BASE_URL}/api/admin/execution-readiness", timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response Keys: {list(data.keys())}")
            print(f"Full Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error Response: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_detailed_api_responses()