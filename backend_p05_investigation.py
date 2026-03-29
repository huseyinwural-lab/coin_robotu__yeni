#!/usr/bin/env python3
"""
P0.5 Closure Regression Investigation - Deep dive into failing tests
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P05Investigation:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.canary_user_id = None
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def authenticate_admin(self):
        """Authenticate admin and get access token"""
        try:
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=login_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("access_token"):
                    self.admin_token = data["access_token"]
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    self.log(f"✅ Admin authentication successful")
                    return True
                    
            self.log(f"❌ Admin login failed: {response.status_code} - {response.text}")
            return False
                
        except Exception as e:
            self.log(f"❌ Admin authentication error: {str(e)}")
            return False
    
    def get_canary_user_id(self):
        """Get canary admin user ID for testing"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/admin/identity/users",
                params={"search": "canary.admin", "limit": 10},
                timeout=30
            )
            
            if response.status_code == 200:
                users = response.json().get("items", [])
                for user in users:
                    if user.get("email") == ADMIN_EMAIL:
                        self.canary_user_id = user.get("id")
                        self.log(f"✅ Found canary user ID: {self.canary_user_id}")
                        return True
                        
            return False
                
        except Exception as e:
            self.log(f"❌ Error getting canary user ID: {str(e)}")
            return False
    
    def investigate_reason_validation(self):
        """Deep dive into reason validation failures"""
        self.log("🔍 Investigating reason validation failures...")
        
        # Test with different reason lengths
        test_reasons = [
            "bad",  # Very short
            "short",  # Short
            "This is a medium length reason for testing",  # Medium
            "This is a very long reason that should definitely pass any reasonable length validation requirements for administrative actions"  # Long
        ]
        
        for reason in test_reasons:
            self.log(f"\n--- Testing reason: '{reason}' (length: {len(reason)}) ---")
            
            # Test bulk status endpoint
            try:
                payload = {
                    "user_ids": [self.canary_user_id] if self.canary_user_id else ["test-id"],
                    "status": "disabled",
                    "reason": reason
                }
                
                response = self.session.post(
                    f"{BASE_URL}/api/admin/identity/users/bulk-status",
                    json=payload,
                    timeout=30
                )
                
                self.log(f"Bulk status - HTTP {response.status_code}")
                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        self.log(f"Error response: {json.dumps(error_data, indent=2)}")
                    except:
                        self.log(f"Error text: {response.text}")
                        
            except Exception as e:
                self.log(f"Error testing bulk status: {str(e)}")
    
    def investigate_contract_freeze(self):
        """Deep dive into contract freeze regression failures"""
        self.log("🔍 Investigating contract freeze regression...")
        
        # 1. Check approvals endpoint structure
        self.log("\n--- Approvals Endpoint Structure ---")
        try:
            response = self.session.get(
                f"{BASE_URL}/api/admin/identity/approvals",
                params={"limit": 5},
                timeout=30
            )
            
            self.log(f"Approvals - HTTP {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.log(f"Response structure: {json.dumps(data, indent=2)[:1000]}...")
                
                items = data.get("items", [])
                self.log(f"Number of approval items: {len(items)}")
                
                if items:
                    first_item = items[0]
                    self.log(f"First item keys: {list(first_item.keys())}")
                    if "impact_delta" in first_item:
                        self.log(f"impact_delta structure: {json.dumps(first_item['impact_delta'], indent=2)}")
                        
        except Exception as e:
            self.log(f"Error checking approvals: {str(e)}")
        
        # 2. Check bulk preview endpoint structure
        self.log("\n--- Bulk Preview Endpoint Structure ---")
        try:
            payload = {
                "user_ids": [self.canary_user_id] if self.canary_user_id else ["test-user-id"],
                "status": "disabled",
                "reason": "Test reason for contract validation - this is a longer reason to avoid validation issues"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/admin/identity/users/bulk-status/preview",
                json=payload,
                timeout=30
            )
            
            self.log(f"Bulk preview - HTTP {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.log(f"Response structure: {json.dumps(data, indent=2)[:1000]}...")
                
                summary = data.get("summary", {})
                self.log(f"Summary keys: {list(summary.keys())}")
                
                # Check for expected keys
                expected_keys = [
                    "total_users", "eligible_users", "approval_required_users", 
                    "blocked_users", "high_risk_users", "risk_distribution", "action_summary"
                ]
                
                for key in expected_keys:
                    if key in summary:
                        self.log(f"✅ {key}: {summary[key]}")
                    else:
                        self.log(f"❌ {key}: MISSING")
                        
            else:
                try:
                    error_data = response.json()
                    self.log(f"Error response: {json.dumps(error_data, indent=2)}")
                except:
                    self.log(f"Error text: {response.text}")
                    
        except Exception as e:
            self.log(f"Error checking bulk preview: {str(e)}")
    
    def investigate_audit_logs(self):
        """Deep dive into audit log structure"""
        self.log("🔍 Investigating audit log structure...")
        
        try:
            # Try different approaches to get audit logs
            endpoints = [
                "/api/audit-logs",
                "/api/admin/audit-logs", 
                "/api/audit-logs/timeline"
            ]
            
            for endpoint in endpoints:
                self.log(f"\n--- Testing {endpoint} ---")
                try:
                    response = self.session.get(
                        f"{BASE_URL}{endpoint}",
                        params={"limit": 5},
                        timeout=30
                    )
                    
                    self.log(f"HTTP {response.status_code}")
                    if response.status_code == 200:
                        data = response.json()
                        self.log(f"Response type: {type(data)}")
                        
                        if isinstance(data, dict):
                            self.log(f"Response keys: {list(data.keys())}")
                            if "items" in data:
                                items = data["items"]
                                self.log(f"Number of items: {len(items)}")
                                if items:
                                    self.log(f"First item keys: {list(items[0].keys())}")
                                    if "action" in items[0]:
                                        self.log(f"First item action: {items[0]['action']}")
                        elif isinstance(data, list):
                            self.log(f"Response is list with {len(data)} items")
                            if data:
                                self.log(f"First item keys: {list(data[0].keys())}")
                                if "action" in data[0]:
                                    self.log(f"First item action: {data[0]['action']}")
                                    
                    else:
                        self.log(f"Error: {response.text[:200]}")
                        
                except Exception as e:
                    self.log(f"Error with {endpoint}: {str(e)}")
                    
        except Exception as e:
            self.log(f"Error investigating audit logs: {str(e)}")
    
    def run_investigation(self):
        """Run all investigations"""
        self.log("🚀 Starting P0.5 Closure Regression Investigation...")
        
        # Authenticate
        if not self.authenticate_admin():
            self.log("❌ CRITICAL: Admin authentication failed")
            return False
        
        # Get canary user ID
        if not self.get_canary_user_id():
            self.log("⚠️ WARNING: Could not get canary user ID")
        
        # Run investigations
        self.investigate_reason_validation()
        self.investigate_contract_freeze()
        self.investigate_audit_logs()
        
        return True

def main():
    """Main investigation execution"""
    investigator = P05Investigation()
    
    try:
        investigator.run_investigation()
        return 0
        
    except KeyboardInterrupt:
        investigator.log("\n⚠️ Investigation interrupted by user")
        return 1
    except Exception as e:
        investigator.log(f"\n❌ Unexpected error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())