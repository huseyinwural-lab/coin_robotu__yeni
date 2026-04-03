#!/usr/bin/env python3
"""
Debug authentication and session management
"""

import requests
import json

BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def debug_auth():
    session = requests.Session()
    
    # Login
    login_url = f"{BASE_URL}/api/auth/login"
    payload = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "panel": "admin"
    }
    
    print("=== LOGIN REQUEST ===")
    response = session.post(login_url, json=payload)
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print(f"Cookies: {dict(response.cookies)}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        token = data.get("access_token")
        if token:
            print(f"\nToken length: {len(token)}")
            
            # Try to call the execution timeline endpoint
            print("\n=== EXECUTION TIMELINE TEST ===")
            url = f"{BASE_URL}/api/runtime/ws/execution-timeline"
            
            # Try different authentication approaches
            approaches = [
                {
                    "name": "Bearer token only",
                    "headers": {"Authorization": f"Bearer {token}"}
                },
                {
                    "name": "Bearer + Session headers",
                    "headers": {
                        "Authorization": f"Bearer {token}",
                        "X-Session-ID": "test-session-123",
                        "X-Session-Device": "test-device-456"
                    }
                },
                {
                    "name": "Bearer + Session headers + Cookies",
                    "headers": {
                        "Authorization": f"Bearer {token}",
                        "X-Session-ID": "test-session-123", 
                        "X-Session-Device": "test-device-456"
                    },
                    "cookies": {"session_id": "test-session-123", "device_id": "test-device-456"}
                }
            ]
            
            for approach in approaches:
                print(f"\n--- {approach['name']} ---")
                headers = approach["headers"]
                cookies = approach.get("cookies", {})
                
                if cookies:
                    for k, v in cookies.items():
                        session.cookies.set(k, v)
                
                resp = session.get(url, headers=headers)
                print(f"Status: {resp.status_code}")
                print(f"Response: {resp.text}")
                
            # Try WS health endpoint
            print("\n=== WS HEALTH TEST ===")
            health_url = f"{BASE_URL}/api/runtime/ws/health"
            resp = session.get(health_url, headers={"Authorization": f"Bearer {token}"})
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")
    else:
        print(f"Login failed: {response.text}")

if __name__ == "__main__":
    debug_auth()