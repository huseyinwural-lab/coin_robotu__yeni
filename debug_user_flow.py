#!/usr/bin/env python3
"""
Debug user registration and scanner flow
"""

import requests
import json
import time

BASE_URL = "https://trading-infra.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

def test_user_registration_debug():
    print("🔍 Debugging User Registration Flow...")
    
    # Get admin token first
    admin_response = requests.post(
        f"{API_BASE}/auth/login/admin",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=10
    )
    
    if admin_response.status_code != 200:
        print(f"❌ Admin login failed: {admin_response.status_code}")
        return False
        
    admin_token = admin_response.json().get("access_token")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Generate unique test user
    timestamp = int(time.time())
    test_email = f"debug_test_{timestamp}@test.com"
    test_password = "TestPass123!"
    
    # 1. Test user registration
    print(f"📝 Registering user: {test_email}")
    register_response = requests.post(
        f"{API_BASE}/auth/register",
        json={
            "email": test_email,
            "password": test_password,
            "first_name": "Debug",
            "last_name": "Test"
        },
        timeout=10
    )
    
    print(f"Registration response: {register_response.status_code}")
    print(f"Registration body: {register_response.text}")
    
    if register_response.status_code in [200, 201]:
        print("✅ User registration successful")
        
        # Small delay for database consistency
        time.sleep(2)
        
        # 2. Get pending users
        print("📋 Fetching pending users...")
        pending_response = requests.get(
            f"{API_BASE}/admin/user-approvals?status_filter=pending",
            headers=admin_headers,
            timeout=10
        )
        
        print(f"Pending users response: {pending_response.status_code}")
        
        if pending_response.status_code == 200:
            pending_users = pending_response.json()
            print(f"Found {len(pending_users)} pending users")
            
            # Find our test user
            test_user = None
            for user in pending_users:
                if user["email"] == test_email:
                    test_user = user
                    break
            
            if test_user:
                print(f"✅ Found test user: {test_user['id']}")
                
                # 3. Approve the user
                print("👍 Approving user...")
                approve_response = requests.post(
                    f"{API_BASE}/admin/user-approvals/bulk-approve",
                    json={"user_ids": [test_user["id"]]},
                    headers=admin_headers,
                    timeout=10
                )
                
                print(f"Approval response: {approve_response.status_code}")
                print(f"Approval body: {approve_response.text}")
                
                if approve_response.status_code in [200, 201]:
                    print("✅ User approved successfully")
                    
                    # Small delay for database consistency
                    time.sleep(2)
                    
                    # 4. Login as approved user
                    print("🔑 Logging in as approved user...")
                    login_response = requests.post(
                        f"{API_BASE}/auth/login",
                        json={"email": test_email, "password": test_password},
                        timeout=10
                    )
                    
                    print(f"User login response: {login_response.status_code}")
                    print(f"User login body: {login_response.text}")
                    
                    if login_response.status_code == 200:
                        user_token = login_response.json().get("access_token")
                        if user_token:
                            print("✅ User login successful")
                            
                            # 5. Test scanner endpoint
                            print("🔍 Testing scanner endpoint...")
                            user_headers = {"Authorization": f"Bearer {user_token}"}
                            scanner_response = requests.get(
                                f"{API_BASE}/user/scanner/symbol-selection",
                                headers=user_headers,
                                timeout=10
                            )
                            
                            print(f"Scanner response: {scanner_response.status_code}")
                            print(f"Scanner body: {scanner_response.text}")
                            
                            if scanner_response.status_code == 200:
                                print("✅ Scanner endpoint working!")
                                return True
                            else:
                                print("❌ Scanner endpoint failed")
                                return False
                        else:
                            print("❌ No user token received")
                            return False
                    else:
                        print("❌ User login failed")
                        return False
                else:
                    print("❌ User approval failed")
                    return False
            else:
                print("❌ Test user not found in pending list")
                return False
        else:
            print("❌ Could not fetch pending users")
            return False
    else:
        print("❌ User registration failed")
        return False

if __name__ == "__main__":
    success = test_user_registration_debug()
    print(f"\n🎯 Debug result: {'SUCCESS' if success else 'FAILED'}")