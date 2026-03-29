#!/usr/bin/env python3
"""
Identity Control P1/P2 Backend Investigation
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class IdentityControlInvestigator:
    def __init__(self):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.admin_token = None
        
    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def login_admin(self):
        """Login as admin and get access token"""
        try:
            self.log("🔐 Logging in as admin...")
            
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{self.base_url}/api/auth/login/admin",
                json=login_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('access_token'):
                    self.admin_token = data['access_token']
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.admin_token}'
                    })
                    self.log(f"✅ Admin login successful")
                    return True
                else:
                    self.log(f"❌ Admin login failed: No access token in response")
                    return False
            else:
                self.log(f"❌ Admin login failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Admin login error: {str(e)}")
            return False
    
    def investigate_users(self):
        """Investigate available users"""
        try:
            self.log("🔍 Investigating available users...")
            
            response = self.session.get(
                f"{self.base_url}/api/admin/identity/users",
                params={"limit": 10},
                timeout=30
            )
            
            self.log(f"Users endpoint status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.log(f"Users response keys: {list(data.keys())}")
                users = data.get('users', [])
                self.log(f"Found {len(users)} users")
                
                if users:
                    user = users[0]
                    self.log(f"Sample user keys: {list(user.keys())}")
                    user_id = user.get('user_id') or user.get('id')
                    self.log(f"Sample user ID: {user_id}")
                    return user_id
            else:
                self.log(f"Users response: {response.text}")
                
        except Exception as e:
            self.log(f"❌ Error investigating users: {str(e)}")
        
        return None
    
    def investigate_approvals_request(self):
        """Investigate approvals request endpoint"""
        try:
            self.log("🔍 Investigating approvals request endpoint...")
            
            # Test with short reason
            request_data = {
                "action": "disable_user",
                "user_id": "test-user-id-12345",
                "request_reason": "bad"  # Too short
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/identity/approvals/request",
                json=request_data,
                timeout=30
            )
            
            self.log(f"Approvals request status: {response.status_code}")
            self.log(f"Approvals request response: {response.text}")
            
        except Exception as e:
            self.log(f"❌ Error investigating approvals request: {str(e)}")
    
    def investigate_bulk_preview(self):
        """Investigate bulk preview endpoint"""
        try:
            self.log("🔍 Investigating bulk preview endpoint...")
            
            request_data = {
                "user_ids": ["test-user-1", "test-user-2"],
                "action": "disable_user",
                "request_reason": "Bulk disable for security review"
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/identity/users/bulk-status/preview",
                json=request_data,
                timeout=30
            )
            
            self.log(f"Bulk preview status: {response.status_code}")
            self.log(f"Bulk preview response: {response.text}")
            
        except Exception as e:
            self.log(f"❌ Error investigating bulk preview: {str(e)}")
    
    def investigate_approvals_list(self):
        """Investigate approvals list endpoint"""
        try:
            self.log("🔍 Investigating approvals list endpoint...")
            
            response = self.session.get(
                f"{self.base_url}/api/admin/identity/approvals",
                params={"limit": 10},
                timeout=30
            )
            
            self.log(f"Approvals list status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.log(f"Approvals list keys: {list(data.keys())}")
                approvals = data.get('approvals', [])
                self.log(f"Found {len(approvals)} approvals")
                
                if approvals:
                    approval = approvals[0]
                    self.log(f"Sample approval keys: {list(approval.keys())}")
            else:
                self.log(f"Approvals list response: {response.text}")
                
        except Exception as e:
            self.log(f"❌ Error investigating approvals list: {str(e)}")
    
    def run_investigation(self):
        """Run all investigations"""
        self.log("🚀 Starting Identity Control Investigation...")
        
        # Login first
        if not self.login_admin():
            self.log("❌ Cannot proceed without admin login")
            return False
        
        # Run investigations
        user_id = self.investigate_users()
        self.investigate_approvals_request()
        self.investigate_bulk_preview()
        self.investigate_approvals_list()
        
        # Test observability endpoints if we have a user ID
        if user_id:
            self.test_observability_endpoints(user_id)
        
        return True
    
    def test_observability_endpoints(self, user_id):
        """Test observability endpoints with actual user ID"""
        self.log(f"📊 Testing observability endpoints with user ID: {user_id}")
        
        endpoints = [
            f"/api/admin/identity/users/{user_id}/activity-timeline",
            f"/api/admin/identity/users/{user_id}/security-telemetry", 
            f"/api/admin/identity/users/{user_id}/execution-metrics",
            f"/api/admin/identity/users/{user_id}/trading-observability"
        ]
        
        for endpoint in endpoints:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}", timeout=30)
                endpoint_name = endpoint.split('/')[-1]
                
                self.log(f"{endpoint_name}: {response.status_code}")
                if response.status_code != 200:
                    self.log(f"  Response: {response.text}")
                    
            except Exception as e:
                endpoint_name = endpoint.split('/')[-1]
                self.log(f"{endpoint_name}: ERROR - {str(e)}")

def main():
    investigator = IdentityControlInvestigator()
    
    if investigator.run_investigation():
        return 0
    else:
        print("❌ Investigation failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())