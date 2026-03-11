#!/usr/bin/env python3

import requests
import json
import os
import sys
from datetime import datetime

# Get backend URL from environment variable
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "https://quant-platform-core.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"

class AdminDomainRegressionTest:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, test_name, success, details):
        """Log test result"""
        status = "PASS" if success else "FAIL"
        self.test_results.append({
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        print(f"[{status}] {test_name}: {details}")
        
    def login_admin(self):
        """Test admin login with provided credentials"""
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    # Set authorization header for subsequent requests
                    self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                    self.log_result("Admin Login", True, f"Successfully logged in as {ADMIN_EMAIL}")
                    return True
                else:
                    self.log_result("Admin Login", False, "No access token received")
                    return False
            else:
                self.log_result("Admin Login", False, f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Login", False, f"Exception: {str(e)}")
            return False
            
    def test_admin_users_flow(self):
        """Test /admin/users endpoints: listing, filters, PATCH role, PATCH status"""
        
        # Test 1: List users - basic functionality
        try:
            response = self.session.get(f"{API_BASE}/admin/users")
            if response.status_code == 200:
                users = response.json()
                self.log_result("Admin Users - List", True, f"Retrieved {len(users)} users")
            else:
                self.log_result("Admin Users - List", False, f"Status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_result("Admin Users - List", False, f"Exception: {str(e)}")
            return False
            
        # Test 2: List with filters
        try:
            filters = {
                "search": "admin",
                "status": "active", 
                "sort_by": "email",
                "sort_dir": "asc"
            }
            response = self.session.get(f"{API_BASE}/admin/users", params=filters)
            if response.status_code == 200:
                filtered_users = response.json()
                self.log_result("Admin Users - Filters", True, f"Filtered results: {len(filtered_users)} users")
            else:
                self.log_result("Admin Users - Filters", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Admin Users - Filters", False, f"Exception: {str(e)}")
            
        # Find a test user to modify (not the admin user)
        test_user_id = None
        if users:
            for user in users:
                if user.get("email") != ADMIN_EMAIL:
                    test_user_id = user.get("id")
                    original_role = user.get("role") 
                    original_status = user.get("status")
                    break
                    
        if test_user_id:
            # Test 3: PATCH role - valid role change
            try:
                new_role = "ops" if original_role != "ops" else "user"
                response = self.session.patch(
                    f"{API_BASE}/admin/users/{test_user_id}/role",
                    json={"role": new_role}
                )
                if response.status_code == 200:
                    self.log_result("Admin Users - PATCH Role (valid)", True, f"Changed role to {new_role}")
                    
                    # Revert back
                    self.session.patch(
                        f"{API_BASE}/admin/users/{test_user_id}/role",
                        json={"role": original_role}
                    )
                else:
                    self.log_result("Admin Users - PATCH Role (valid)", False, f"Status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("Admin Users - PATCH Role (valid)", False, f"Exception: {str(e)}")
                
            # Test 4: PATCH role - invalid role (should fail)
            try:
                response = self.session.patch(
                    f"{API_BASE}/admin/users/{test_user_id}/role",
                    json={"role": "invalid_role"}
                )
                if response.status_code == 400:
                    self.log_result("Admin Users - PATCH Role (invalid)", True, "Correctly rejected invalid role")
                else:
                    self.log_result("Admin Users - PATCH Role (invalid)", False, f"Expected 400, got {response.status_code}")
            except Exception as e:
                self.log_result("Admin Users - PATCH Role (invalid)", False, f"Exception: {str(e)}")
                
            # Test 5: PATCH status - valid status change
            try:
                new_status = "disabled" if original_status == "active" else "active"
                response = self.session.patch(
                    f"{API_BASE}/admin/users/{test_user_id}/status",
                    json={"status": new_status}
                )
                if response.status_code == 200:
                    self.log_result("Admin Users - PATCH Status (valid)", True, f"Changed status to {new_status}")
                    
                    # Revert back
                    self.session.patch(
                        f"{API_BASE}/admin/users/{test_user_id}/status",
                        json={"status": original_status}
                    )
                else:
                    self.log_result("Admin Users - PATCH Status (valid)", False, f"Status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("Admin Users - PATCH Status (valid)", False, f"Exception: {str(e)}")
                
            # Test 6: PATCH status - invalid status (should fail)
            try:
                response = self.session.patch(
                    f"{API_BASE}/admin/users/{test_user_id}/status",
                    json={"status": "invalid_status"}
                )
                if response.status_code == 400:
                    self.log_result("Admin Users - PATCH Status (invalid)", True, "Correctly rejected invalid status")
                else:
                    self.log_result("Admin Users - PATCH Status (invalid)", False, f"Expected 400, got {response.status_code}")
            except Exception as e:
                self.log_result("Admin Users - PATCH Status (invalid)", False, f"Exception: {str(e)}")
        else:
            self.log_result("Admin Users - User Modifications", False, "No suitable test user found for modifications")
            
        return True
        
    def test_system_alerts_flow(self):
        """Test /admin/system-alerts endpoints: listing, filters, timeline, bulk-ack, single ack/resolve"""
        
        # Test 1: List system alerts
        try:
            response = self.session.get(f"{API_BASE}/admin/system-alerts")
            if response.status_code == 200:
                alerts = response.json()
                self.log_result("System Alerts - List", True, f"Retrieved {len(alerts)} alerts")
            else:
                self.log_result("System Alerts - List", False, f"Status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_result("System Alerts - List", False, f"Exception: {str(e)}")
            return False
            
        # Test 2: List with filters
        try:
            filters = {
                "status_filter": "open",
                "severity": "CRITICAL",
                "limit": 10
            }
            response = self.session.get(f"{API_BASE}/admin/system-alerts", params=filters)
            if response.status_code == 200:
                filtered_alerts = response.json()
                self.log_result("System Alerts - Filters", True, f"Filtered results: {len(filtered_alerts)} alerts")
            else:
                self.log_result("System Alerts - Filters", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("System Alerts - Filters", False, f"Exception: {str(e)}")
            
        # Test 3: Timeline
        try:
            response = self.session.get(f"{API_BASE}/admin/system-alerts/timeline", params={"days": 7})
            if response.status_code == 200:
                timeline_data = response.json()
                points = timeline_data.get("points", [])
                self.log_result("System Alerts - Timeline", True, f"Retrieved timeline with {len(points)} data points")
            else:
                self.log_result("System Alerts - Timeline", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("System Alerts - Timeline", False, f"Exception: {str(e)}")
            
        # Create test alert for acknowledgment tests
        test_alert_id = None
        try:
            # First simulate an alert to have something to ack/resolve
            response = self.session.post(f"{API_BASE}/ops-alerts/simulate")
            if response.status_code == 200:
                sim_data = response.json()
                test_alert_id = sim_data.get("alert_id")
                self.log_result("System Alerts - Create Test Alert", True, f"Created test alert: {test_alert_id}")
            else:
                self.log_result("System Alerts - Create Test Alert", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("System Alerts - Create Test Alert", False, f"Exception: {str(e)}")
            
        # Test 4: Single acknowledge
        if test_alert_id:
            try:
                response = self.session.post(f"{API_BASE}/admin/system-alerts/{test_alert_id}/ack")
                if response.status_code == 200:
                    self.log_result("System Alerts - Single Ack", True, "Successfully acknowledged alert")
                else:
                    self.log_result("System Alerts - Single Ack", False, f"Status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("System Alerts - Single Ack", False, f"Exception: {str(e)}")
                
            # Test 5: Single resolve
            try:
                response = self.session.post(f"{API_BASE}/admin/system-alerts/{test_alert_id}/resolve")
                if response.status_code == 200:
                    self.log_result("System Alerts - Single Resolve", True, "Successfully resolved alert")
                else:
                    self.log_result("System Alerts - Single Resolve", False, f"Status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("System Alerts - Single Resolve", False, f"Exception: {str(e)}")
        
        # Test 6: Bulk acknowledge
        if alerts:
            alert_ids = [alert["id"] for alert in alerts[:2]]  # Use first 2 alerts
            try:
                response = self.session.post(
                    f"{API_BASE}/admin/system-alerts/bulk-ack",
                    json={"ids": alert_ids}
                )
                if response.status_code == 200:
                    bulk_result = response.json()
                    count = bulk_result.get("count", 0)
                    self.log_result("System Alerts - Bulk Ack", True, f"Bulk acknowledged {count} alerts")
                else:
                    self.log_result("System Alerts - Bulk Ack", False, f"Status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("System Alerts - Bulk Ack", False, f"Exception: {str(e)}")
                
        # Test 7: Bulk acknowledge with empty IDs (should fail)
        try:
            response = self.session.post(
                f"{API_BASE}/admin/system-alerts/bulk-ack",
                json={"ids": []}
            )
            if response.status_code == 400:
                self.log_result("System Alerts - Bulk Ack (empty)", True, "Correctly rejected empty IDs")
            else:
                self.log_result("System Alerts - Bulk Ack (empty)", False, f"Expected 400, got {response.status_code}")
        except Exception as e:
            self.log_result("System Alerts - Bulk Ack (empty)", False, f"Exception: {str(e)}")
            
        return True
        
    def test_system_alerts_config(self):
        """Test /admin/system-alerts/config: GET + POST payload saving, response channel status/config"""
        
        # Test 1: GET config
        try:
            response = self.session.get(f"{API_BASE}/admin/system-alerts/config")
            if response.status_code == 200:
                config_data = response.json()
                channels = config_data.get("channels", {})
                config = config_data.get("config", {})
                self.log_result("System Alerts Config - GET", True, 
                               f"Retrieved config with channels: {list(channels.keys())}")
            else:
                self.log_result("System Alerts Config - GET", False, f"Status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_result("System Alerts Config - GET", False, f"Exception: {str(e)}")
            return False
            
        # Test 2: POST config update
        try:
            test_config = {
                "resend_api_key": "test_key_123",
                "alert_from": "test@example.com",
                "alert_to": "admin@example.com",
                "slack_webhook_url": "https://hooks.slack.com/test"
            }
            response = self.session.post(
                f"{API_BASE}/admin/system-alerts/config",
                json=test_config
            )
            if response.status_code == 200:
                updated_config = response.json()
                self.log_result("System Alerts Config - POST", True, 
                               "Successfully updated configuration")
                
                # Verify the structure includes channels and config
                if "channels" in updated_config and "config" in updated_config:
                    self.log_result("System Alerts Config - Response Structure", True,
                                   "Response includes channels and config sections")
                else:
                    self.log_result("System Alerts Config - Response Structure", False,
                                   "Missing channels or config in response")
            else:
                self.log_result("System Alerts Config - POST", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("System Alerts Config - POST", False, f"Exception: {str(e)}")
            
        return True
        
    def test_ops_alerts_simulate(self):
        """Test /ops-alerts/simulate: delivery_status return check"""
        
        try:
            response = self.session.post(f"{API_BASE}/ops-alerts/simulate")
            if response.status_code == 200:
                sim_data = response.json()
                alert_id = sim_data.get("alert_id")
                delivery_status = sim_data.get("delivery_status")
                
                if alert_id and delivery_status is not None:
                    self.log_result("Ops Alerts - Simulate", True, 
                                   f"Alert created: {alert_id}, delivery_status: {delivery_status}")
                else:
                    self.log_result("Ops Alerts - Simulate", False, 
                                   "Missing alert_id or delivery_status in response")
            else:
                self.log_result("Ops Alerts - Simulate", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Ops Alerts - Simulate", False, f"Exception: {str(e)}")
            
        return True
        
    def test_frontend_smoke(self):
        """Frontend smoke test: Check if /admin/users and /admin/system-alerts pages are accessible"""
        
        # This is a backend test, but we can test if the API endpoints that power
        # these frontend pages are working correctly
        
        endpoints_to_test = [
            ("/admin/users", "Admin Users Page API"),
            ("/admin/system-alerts", "System Alerts Page API"),
            ("/admin/system-alerts/config", "System Alerts Config API"),
            ("/admin/system-alerts/timeline", "System Alerts Timeline API")
        ]
        
        for endpoint, name in endpoints_to_test:
            try:
                response = self.session.get(f"{API_BASE}{endpoint}")
                if response.status_code == 200:
                    self.log_result(f"Frontend Smoke - {name}", True, 
                                   f"API endpoint accessible")
                else:
                    self.log_result(f"Frontend Smoke - {name}", False, 
                                   f"Status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result(f"Frontend Smoke - {name}", False, f"Exception: {str(e)}")
                
        return True
        
    def run_all_tests(self):
        """Run all regression tests"""
        print("=" * 80)
        print("ADMIN DOMAIN REGRESSION TEST SUITE")
        print("=" * 80)
        print(f"Backend URL: {BACKEND_URL}")
        print(f"Admin Credentials: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Login first
        if not self.login_admin():
            print("\n❌ CRITICAL: Admin login failed - cannot continue with tests")
            return False
            
        # Run test suites
        print("\n🔄 Running admin/users flow tests...")
        self.test_admin_users_flow()
        
        print("\n🔄 Running system-alerts flow tests...")  
        self.test_system_alerts_flow()
        
        print("\n🔄 Running system-alerts config tests...")
        self.test_system_alerts_config()
        
        print("\n🔄 Running ops-alerts simulate tests...")
        self.test_ops_alerts_simulate()
        
        print("\n🔄 Running frontend smoke tests...")
        self.test_frontend_smoke()
        
        # Summary
        print("\n" + "=" * 80)
        print("TEST RESULTS SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for result in self.test_results if result["status"] == "PASS")
        failed = sum(1 for result in self.test_results if result["status"] == "FAIL")
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
        
        if failed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  - {result['test']}: {result['details']}")
        
        print("\n" + "=" * 80)
        
        return failed == 0


def main():
    """Main test runner"""
    tester = AdminDomainRegressionTest()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()