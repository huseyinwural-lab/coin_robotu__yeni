#!/usr/bin/env python3
"""
Quick validation of the acceptance latest endpoint to understand the actual response structure
"""

import json
import requests
import sys

def test_acceptance_latest():
    """Test the acceptance latest endpoint specifically"""
    base_url = "https://trade-trace-engine.preview.emergentagent.com"
    
    # Authenticate
    auth_data = {"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"}
    
    session = requests.Session()
    session.headers.update({'Content-Type': 'application/json'})
    
    try:
        # Login
        auth_response = session.post(f"{base_url}/api/auth/login/admin", json=auth_data, timeout=30)
        if auth_response.status_code != 200:
            print(f"❌ Auth failed: {auth_response.status_code} - {auth_response.text}")
            return False
            
        token = auth_response.json().get('access_token')
        if not token:
            print("❌ No token in auth response")
            return False
            
        session.headers['Authorization'] = f'Bearer {token}'
        
        # Test latest endpoint
        response = session.get(f"{base_url}/api/execution-safety/acceptance/live/latest", timeout=30)
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📋 Response Body: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"📄 Response Keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            
            # Check for contract fields
            required_fields = ['acceptance_run_id', 'correlation_id', 'final_verdict']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                print(f"⚠️ Missing contract fields: {missing_fields}")
                print(f"✅ Available fields: {[k for k in data.keys() if k in required_fields]}")
                return False
            else:
                print(f"✅ All contract fields present: {required_fields}")
                return True
        else:
            print(f"❌ HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_acceptance_latest()
    sys.exit(0 if success else 1)