#!/usr/bin/env python3
"""
Setup script to create test users for P2+Escalation testing
"""

import requests
import json

BASE_URL = "https://audit-closure-dash.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Super admin credentials (already exists)
SUPER_ADMIN_CREDS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}

# Test users to create
TEST_USERS = [
    {
        "email": "canary.requester@platform.local",
        "password": "CanaryRequester123!",
        "role": "admin"
    },
    {
        "email": "canary.ops@platform.local", 
        "password": "CanaryOps123!",
        "role": "ops"
    }
]

def setup_test_users():
    """Create test users for P2+Escalation testing"""
    session = requests.Session()
    
    # Login as super admin
    print("Logging in as super admin...")
    response = session.post(
        f"{API_BASE}/auth/login/admin",
        json=SUPER_ADMIN_CREDS,
        timeout=30
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to login as super admin: {response.status_code}")
        print(response.text)
        return False
        
    token = response.json().get("access_token")
    if not token:
        print("❌ No access token received")
        return False
        
    print("✅ Super admin login successful")
    
    # Create test users
    headers = {"Authorization": f"Bearer {token}"}
    
    for user in TEST_USERS:
        print(f"\nCreating user: {user['email']} (role: {user['role']})")
        
        response = session.post(
            f"{API_BASE}/admin/users/admin-create",
            json=user,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 201:
            print(f"✅ User {user['email']} created successfully")
        elif response.status_code == 400 and "email_already_exists" in response.text:
            print(f"ℹ️  User {user['email']} already exists")
        else:
            print(f"❌ Failed to create user {user['email']}: {response.status_code}")
            print(response.text)
            
    print("\n✅ Test user setup completed!")
    return True

if __name__ == "__main__":
    setup_test_users()