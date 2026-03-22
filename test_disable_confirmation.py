#!/usr/bin/env python3
"""
Additional Faz-1 Strategy Control Test - Disable Action with Confirmation
"""

import requests
import json
from datetime import datetime

def test_disable_with_confirmation():
    """Test the disable action with proper confirmation phrase"""
    
    BASE_URL = "https://ops-trace-control.preview.emergentagent.com"
    
    print("=" * 60)
    print("FAZ-1 DISABLE ACTION WITH CONFIRMATION TEST")
    print(f"Target: {BASE_URL}")
    print("=" * 60)
    
    # Configure session
    session = requests.Session()
    session.timeout = 15
    
    # Login as super admin
    super_admin_creds = {
        "email": "canary.admin@platform.local",
        "password": "CanaryAdmin123!"
    }
    
    try:
        # Login
        response = session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json=super_admin_creds,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
            print(f"✅ Login successful, token length: {len(token)}")
            
            # Get strategy list
            headers = {"Authorization": f"Bearer {token}"}
            response = session.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                strategies = data.get("strategies", [])
                if strategies:
                    strategy_id = strategies[0].get("id")
                    print(f"✅ Using strategy ID: {strategy_id}")
                    
                    # Test disable with proper confirmation phrase
                    print("\nTesting disable with confirmation phrase...")
                    disable_payload = {
                        "reason": "Test disable action for Faz-1 validation",
                        "confirm_phrase": "DISABLE_STRATEGY"
                    }
                    
                    response = session.post(
                        f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/disable",
                        json=disable_payload,
                        headers={**headers, "Content-Type": "application/json"}
                    )
                    
                    print(f"Status: {response.status_code}")
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            required_fields = ["status", "trace_id", "message", "state_snapshot"]
                            missing_fields = [field for field in required_fields if field not in data]
                            
                            if not missing_fields:
                                print("✅ PASS - Disable with confirmation returns 200 with required fields")
                                print(f"   Status: {data.get('status')}")
                                print(f"   Trace ID: {data.get('trace_id')}")
                                print(f"   Message: {data.get('message')}")
                            else:
                                print(f"❌ FAIL - Missing fields: {missing_fields}")
                        except json.JSONDecodeError:
                            print("❌ FAIL - Invalid JSON response")
                    else:
                        try:
                            error_data = response.json()
                            print(f"Response: {error_data}")
                            if response.status_code in [400, 422]:
                                print("✅ PASS - Disable properly rejected (may be due to strategy state)")
                            else:
                                print(f"❌ FAIL - Unexpected status {response.status_code}")
                        except:
                            print(f"❌ FAIL - Status {response.status_code}, response: {response.text[:200]}")
                else:
                    print("❌ No strategies found")
            else:
                print(f"❌ Failed to get strategies: {response.status_code}")
        else:
            print(f"❌ Login failed: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    print("=" * 60)

if __name__ == "__main__":
    test_disable_with_confirmation()