#!/usr/bin/env python3
"""
Backend Identity Control P1/P2 Quick Verification Test
Base URL: https://unified-orchestrator.preview.emergentagent.com
Admin creds: canary.admin@platform.local / CanaryAdmin123!

Test cases:
1) Observability endpoints return 200:
   - /api/admin/identity/users/{id}/activity-timeline
   - /api/admin/identity/users/{id}/security-telemetry
   - /api/admin/identity/users/{id}/execution-metrics
   - /api/admin/identity/users/{id}/trading-observability
2) Mandatory reason enforce:
   - approvals/request disable_user with short reason should 400 request_reason_too_short
3) High-risk override reason enforce:
   - approvals/request grant_privileged_role without override_reason should 400 override_reason_required_for_high_risk_action
4) Bulk preview summary includes blocker_breakdown and risk_score_total
5) /api/admin/identity/approvals list includes impact_delta object
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class IdentityControlTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = {}
        
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
    
    def get_test_user_id(self):
        """Get a test user ID for observability endpoint testing"""
        try:
            self.log("🔍 Getting test user ID...")
            
            response = self.session.get(
                f"{self.base_url}/api/admin/identity/users",
                params={"limit": 1},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                users = data.get('users', [])
                if users:
                    user_id = users[0].get('user_id')
                    self.log(f"✅ Found test user ID: {user_id}")
                    return user_id
                else:
                    self.log("⚠️ No users found for testing")
                    return None
            else:
                self.log(f"❌ Failed to get users: {response.status_code}")
                return None
                
        except Exception as e:
            self.log(f"❌ Error getting test user ID: {str(e)}")
            return None
    
    def test_observability_endpoints(self):
        """Test case 1: Observability endpoints return 200"""
        self.log("📊 Testing observability endpoints...")
        
        user_id = self.get_test_user_id()
        if not user_id:
            self.test_results['observability_endpoints'] = 'FAIL - No test user ID available'
            return
        
        endpoints = [
            f"/api/admin/identity/users/{user_id}/activity-timeline",
            f"/api/admin/identity/users/{user_id}/security-telemetry", 
            f"/api/admin/identity/users/{user_id}/execution-metrics",
            f"/api/admin/identity/users/{user_id}/trading-observability"
        ]
        
        results = []
        for endpoint in endpoints:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}", timeout=30)
                endpoint_name = endpoint.split('/')[-1]
                
                if response.status_code == 200:
                    results.append(f"{endpoint_name}: PASS")
                    self.log(f"✅ {endpoint_name}: 200 OK")
                else:
                    results.append(f"{endpoint_name}: FAIL ({response.status_code})")
                    self.log(f"❌ {endpoint_name}: {response.status_code}")
                    
            except Exception as e:
                endpoint_name = endpoint.split('/')[-1]
                results.append(f"{endpoint_name}: ERROR")
                self.log(f"❌ {endpoint_name}: {str(e)}")
        
        # Check if all passed
        all_passed = all("PASS" in result for result in results)
        self.test_results['observability_endpoints'] = 'PASS' if all_passed else f'FAIL - {"; ".join(results)}'
    
    def test_mandatory_reason_enforce(self):
        """Test case 2: Mandatory reason enforce - disable_user with short reason should 400"""
        self.log("⚖️ Testing mandatory reason enforcement...")
        
        try:
            # Test with short reason (should fail)
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
            
            if response.status_code == 400:
                response_data = response.json()
                error_code = response_data.get('error_code', '')
                
                if 'request_reason_too_short' in error_code:
                    self.test_results['mandatory_reason_enforce'] = 'PASS'
                    self.log("✅ Mandatory reason enforcement working - got request_reason_too_short")
                else:
                    self.test_results['mandatory_reason_enforce'] = f'FAIL - Wrong error code: {error_code}'
                    self.log(f"❌ Wrong error code: {error_code}")
            else:
                self.test_results['mandatory_reason_enforce'] = f'FAIL - Expected 400, got {response.status_code}'
                self.log(f"❌ Expected 400, got {response.status_code}")
                
        except Exception as e:
            self.test_results['mandatory_reason_enforce'] = f'ERROR - {str(e)}'
            self.log(f"❌ Error testing mandatory reason: {str(e)}")
    
    def test_high_risk_override_reason(self):
        """Test case 3: High-risk override reason enforce"""
        self.log("🚨 Testing high-risk override reason enforcement...")
        
        try:
            # Test grant_privileged_role without override_reason (should fail)
            request_data = {
                "action": "grant_privileged_role",
                "user_id": "test-user-id-12345",
                "request_reason": "Need privileged access for testing operations",
                "role": "super_admin"
                # Missing override_reason for high-risk action
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/identity/approvals/request",
                json=request_data,
                timeout=30
            )
            
            if response.status_code == 400:
                response_data = response.json()
                error_code = response_data.get('error_code', '')
                
                if 'override_reason_required_for_high_risk_action' in error_code:
                    self.test_results['high_risk_override_reason'] = 'PASS'
                    self.log("✅ High-risk override reason enforcement working")
                else:
                    self.test_results['high_risk_override_reason'] = f'FAIL - Wrong error code: {error_code}'
                    self.log(f"❌ Wrong error code: {error_code}")
            else:
                self.test_results['high_risk_override_reason'] = f'FAIL - Expected 400, got {response.status_code}'
                self.log(f"❌ Expected 400, got {response.status_code}")
                
        except Exception as e:
            self.test_results['high_risk_override_reason'] = f'ERROR - {str(e)}'
            self.log(f"❌ Error testing high-risk override: {str(e)}")
    
    def test_bulk_preview_summary(self):
        """Test case 4: Bulk preview summary includes blocker_breakdown and risk_score_total"""
        self.log("📋 Testing bulk preview summary fields...")
        
        try:
            # Test bulk preview with sample data
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
            
            if response.status_code == 200:
                data = response.json()
                
                has_blocker_breakdown = 'blocker_breakdown' in data
                has_risk_score_total = 'risk_score_total' in data
                
                if has_blocker_breakdown and has_risk_score_total:
                    self.test_results['bulk_preview_summary'] = 'PASS'
                    self.log("✅ Bulk preview summary has required fields")
                else:
                    missing = []
                    if not has_blocker_breakdown:
                        missing.append('blocker_breakdown')
                    if not has_risk_score_total:
                        missing.append('risk_score_total')
                    
                    self.test_results['bulk_preview_summary'] = f'FAIL - Missing: {", ".join(missing)}'
                    self.log(f"❌ Missing fields: {', '.join(missing)}")
            else:
                self.test_results['bulk_preview_summary'] = f'FAIL - HTTP {response.status_code}'
                self.log(f"❌ Bulk preview failed: {response.status_code}")
                
        except Exception as e:
            self.test_results['bulk_preview_summary'] = f'ERROR - {str(e)}'
            self.log(f"❌ Error testing bulk preview: {str(e)}")
    
    def test_approvals_list_impact_delta(self):
        """Test case 5: /api/admin/identity/approvals list includes impact_delta object"""
        self.log("📈 Testing approvals list impact_delta field...")
        
        try:
            response = self.session.get(
                f"{self.base_url}/api/admin/identity/approvals",
                params={"limit": 10},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                approvals = data.get('approvals', [])
                
                if approvals:
                    # Check if any approval has impact_delta
                    has_impact_delta = any('impact_delta' in approval for approval in approvals)
                    
                    if has_impact_delta:
                        self.test_results['approvals_list_impact_delta'] = 'PASS'
                        self.log("✅ Approvals list includes impact_delta object")
                    else:
                        self.test_results['approvals_list_impact_delta'] = 'FAIL - No impact_delta found'
                        self.log("❌ No impact_delta found in approvals")
                else:
                    self.test_results['approvals_list_impact_delta'] = 'SKIP - No approvals to test'
                    self.log("⚠️ No approvals found for testing")
            else:
                self.test_results['approvals_list_impact_delta'] = f'FAIL - HTTP {response.status_code}'
                self.log(f"❌ Approvals list failed: {response.status_code}")
                
        except Exception as e:
            self.test_results['approvals_list_impact_delta'] = f'ERROR - {str(e)}'
            self.log(f"❌ Error testing approvals list: {str(e)}")
    
    def run_all_tests(self):
        """Run all test cases"""
        self.log("🚀 Starting Identity Control P1/P2 Backend Verification...")
        
        # Login first
        if not self.login_admin():
            self.log("❌ Cannot proceed without admin login")
            return False
        
        # Run all test cases
        self.test_observability_endpoints()
        self.test_mandatory_reason_enforce()
        self.test_high_risk_override_reason()
        self.test_bulk_preview_summary()
        self.test_approvals_list_impact_delta()
        
        return True
    
    def print_results(self):
        """Print concise PASS/FAIL matrix"""
        self.log("\n" + "="*60)
        self.log("IDENTITY CONTROL P1/P2 BACKEND VERIFICATION RESULTS")
        self.log("="*60)
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result == "PASS" else f"❌ {result}"
            self.log(f"{test_name.replace('_', ' ').title()}: {status}")
        
        # Summary
        passed = sum(1 for result in self.test_results.values() if result == "PASS")
        total = len(self.test_results)
        
        self.log("="*60)
        self.log(f"SUMMARY: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        self.log("="*60)

def main():
    tester = IdentityControlTester()
    
    if tester.run_all_tests():
        tester.print_results()
        return 0
    else:
        print("❌ Test execution failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())