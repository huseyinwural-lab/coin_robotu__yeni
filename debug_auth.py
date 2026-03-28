#!/usr/bin/env python3
"""
Debug script for Trading Lifecycle Debugger authentication issue
"""

import requests
import json

BASE_URL = "https://failure-explainer.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def debug_auth():
    """Debug authentication and endpoint access"""
    
    # Step 1: Test admin login
    print("=== STEP 1: Admin Login ===")
    login_url = f"{BASE_URL}/api/auth/login/admin"
    login_payload = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    login_response = requests.post(login_url, json=login_payload, timeout=10)
    print(f"Login Status: {login_response.status_code}")
    print(f"Login Headers: {dict(login_response.headers)}")
    
    if login_response.status_code == 200:
        login_data = login_response.json()
        print(f"Login Response Keys: {list(login_data.keys())}")
        token = login_data.get('access_token')
        print(f"Token Length: {len(token) if token else 'None'}")
        
        # Step 2: Test with Bearer token
        print("\n=== STEP 2: Test Lifecycle Endpoint with Bearer Token ===")
        headers = {"Authorization": f"Bearer {token}"}
        lifecycle_url = f"{BASE_URL}/api/audit-logs/trading-lifecycle?limit=20"
        
        lifecycle_response = requests.get(lifecycle_url, headers=headers, timeout=10)
        print(f"Lifecycle Status: {lifecycle_response.status_code}")
        print(f"Lifecycle Headers: {dict(lifecycle_response.headers)}")
        
        if lifecycle_response.status_code != 200:
            print(f"Lifecycle Error Response: {lifecycle_response.text[:500]}")
        
        # Step 3: Test with cookies (if any)
        print("\n=== STEP 3: Test with Session Cookies ===")
        session = requests.Session()
        session.post(login_url, json=login_payload, timeout=10)
        
        lifecycle_response_cookies = session.get(lifecycle_url, timeout=10)
        print(f"Lifecycle with Cookies Status: {lifecycle_response_cookies.status_code}")
        
        # Step 4: Test alternative auth endpoint
        print("\n=== STEP 4: Test Alternative Auth Endpoint ===")
        alt_login_url = f"{BASE_URL}/api/auth/login"
        alt_response = requests.post(alt_login_url, json=login_payload, timeout=10)
        print(f"Alternative Login Status: {alt_response.status_code}")
        
        if alt_response.status_code == 200:
            alt_data = alt_response.json()
            alt_token = alt_data.get('access_token')
            if alt_token:
                alt_headers = {"Authorization": f"Bearer {alt_token}"}
                alt_lifecycle_response = requests.get(lifecycle_url, headers=alt_headers, timeout=10)
                print(f"Lifecycle with Alt Token Status: {alt_lifecycle_response.status_code}")
    
    else:
        print(f"Login failed: {login_response.text}")

if __name__ == "__main__":
    debug_auth()