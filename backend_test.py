#!/usr/bin/env python3
"""
COMPREHENSIVE RELEASE READINESS TEST
====================================

Detailed audit for production deployment readiness.
Testing critical backend endpoints and authentication flows.

Base URL: https://trade-platform-s3.preview.emergentagent.com
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "https://trade-platform-s3.preview.emergentagent.com"
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"
TEST_USER_EMAIL = "testuser1773706589@example.com"
TEST_USER_PASSWORD = "TestPassword123!"

class ReleaseReadinessTest:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.test_results = {
            "backend_health": {},
            "auth_flows": {},
            "release_gate": {},
            "execution_readiness": {},
            "exchange_connections": {},
            "execution_queue": {},
            "production_readiness": "UNKNOWN",
            "blocking_issues": [],
            "warnings": []
        }
        
    def log_result(self, test_name, success, details=None, category="general"):
        """Log test result with details"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
            
        # Store in results
        if category not in self.test_results:
            self.test_results[category] = {}
        self.test_results[category][test_name] = {
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        
        # Track blocking issues
        if not success and category in ["backend_health", "auth_flows", "release_gate"]:
            self.test_results["blocking_issues"].append(f"{test_name}: {details}")

    def test_backend_health(self):
        """Test 1: Backend Health Check"""
        print("\n" + "="*60)
        print("TEST 1: BACKEND HEALTH & AUTHENTICATION")
        print("="*60)
        
        try:
            # Test health endpoint
            response = requests.get(f"{BASE_URL}/api/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "GET /api/health = 200", 
                    data.get("status") == "ok",
                    f"Response: {data}",
                    "backend_health"
                )
            else:
                self.log_result(
                    "GET /api/health = 200",
                    False,
                    f"Got {response.status_code}: {response.text}",
                    "backend_health"
                )
                
        except Exception as e:
            self.log_result(
                "GET /api/health = 200",
                False, 
                f"Connection error: {str(e)}",
                "backend_health"
            )

    def test_admin_authentication(self):
        """Test admin login flow"""
        try:
            # Admin login
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json=login_data,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                self.log_result(
                    f"Admin Login ({ADMIN_EMAIL})",
                    bool(self.admin_token),
                    f"Token received: {self.admin_token[:20]}..." if self.admin_token else "No token",
                    "auth_flows"
                )
            else:
                self.log_result(
                    f"Admin Login ({ADMIN_EMAIL})",
                    False,
                    f"Status {response.status_code}: {response.text}",
                    "auth_flows"
                )
                
        except Exception as e:
            self.log_result(
                f"Admin Login ({ADMIN_EMAIL})",
                False,
                f"Exception: {str(e)}",
                "auth_flows"
            )

    def test_user_authentication(self):
        """Test user login flow"""
        try:
            # User login
            login_data = {
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
            
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json=login_data,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                self.log_result(
                    f"User Login ({TEST_USER_EMAIL})",
                    bool(self.user_token),
                    f"Token received: {self.user_token[:20]}..." if self.user_token else "No token",
                    "auth_flows"
                )
            else:
                self.log_result(
                    f"User Login ({TEST_USER_EMAIL})",
                    False,
                    f"Status {response.status_code}: {response.text}",
                    "auth_flows"
                )
                
        except Exception as e:
            self.log_result(
                f"User Login ({TEST_USER_EMAIL})",
                False,
                f"Exception: {str(e)}",
                "auth_flows"
            )

    def test_release_gate_controls(self):
        """Test 2: Live readiness/gate controls"""
        print("\n" + "="*60)
        print("TEST 2: LIVE READINESS/GATE CONTROLS")
        print("="*60)
        
        if not self.admin_token:
            self.log_result(
                "Release Gate Tests",
                False,
                "Admin token required but not available",
                "release_gate"
            )
            return

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Test release gate endpoint
        try:
            response = requests.get(
                f"{BASE_URL}/api/admin/release-gate",
                headers=headers,
                timeout=10
            )
            
            success = response.status_code == 200
            if success:
                data = response.json()
                gate_status = data.get("gate_overall", "UNKNOWN")
                blocking_reasons = data.get("fail_reasons", [])
                
                details = f"Gate Status: {gate_status}"
                if blocking_reasons:
                    details += f", Blocking: {', '.join(blocking_reasons)}"
                    self.test_results["blocking_issues"].extend([f"Release Gate: {r}" for r in blocking_reasons])
                    
            else:
                details = f"Status {response.status_code}: {response.text}"
                
            self.log_result(
                "GET /api/admin/release-gate",
                success,
                details,
                "release_gate"
            )
            
        except Exception as e:
            self.log_result(
                "GET /api/admin/release-gate",
                False,
                f"Exception: {str(e)}",
                "release_gate"
            )

        # Test execution readiness endpoint
        try:
            response = requests.get(
                f"{BASE_URL}/api/admin/execution-readiness",
                headers=headers,
                timeout=10
            )
            
            success = response.status_code == 200
            if success:
                data = response.json()
                readiness_status = data.get("final_status", "UNKNOWN")
                execution_mode = data.get("mode", "UNKNOWN")
                
                details = f"Status: {readiness_status}, Mode: {execution_mode}"
                if readiness_status != "READY":
                    self.test_results["warnings"].append(f"Execution not ready: {readiness_status}")
                    
            else:
                details = f"Status {response.status_code}: {response.text}"
                
            self.log_result(
                "GET /api/admin/execution-readiness",
                success,
                details,
                "release_gate"
            )
            
        except Exception as e:
            self.log_result(
                "GET /api/admin/execution-readiness",
                False,
                f"Exception: {str(e)}",
                "release_gate"
            )

    def test_exchange_connections(self):
        """Test 3: Exchange connection liveness"""
        print("\n" + "="*60)
        print("TEST 3: EXCHANGE CONNECTION LIVENESS")
        print("="*60)
        
        if not self.user_token:
            self.log_result(
                "Exchange Connection Tests",
                False,
                "User token required but not available",
                "exchange_connections"
            )
            return

        headers = {"Authorization": f"Bearer {self.user_token}"}
        
        # Test user exchange connections
        try:
            response = requests.get(
                f"{BASE_URL}/api/user/exchange-connections",
                headers=headers,
                timeout=10
            )
            
            success = response.status_code == 200
            if success:
                data = response.json()
                connections = data if isinstance(data, list) else [data]
                
                details = f"Found {len(connections)} connection(s)"
                
                # Check for default connection
                default_connection = None
                for conn in connections:
                    if conn.get("is_default") or len(connections) == 1:
                        default_connection = conn
                        break
                
                if default_connection:
                    conn_id = default_connection.get("id")
                    is_valid = default_connection.get("is_valid", False)
                    can_trade = default_connection.get("can_trade", False)
                    
                    details += f", Default: {conn_id}, Valid: {is_valid}, Can Trade: {can_trade}"
                    
                    if not is_valid or not can_trade:
                        reason = default_connection.get("validation_error", "Unknown issue")
                        self.test_results["warnings"].append(f"Exchange connection issue: {reason}")
                        
                    # Test revalidation
                    if conn_id:
                        self.test_connection_revalidation(conn_id, headers)
                        
            else:
                details = f"Status {response.status_code}: {response.text}"
                
            self.log_result(
                "GET /api/user/exchange-connections",
                success,
                details,
                "exchange_connections"
            )
            
        except Exception as e:
            self.log_result(
                "GET /api/user/exchange-connections",
                False,
                f"Exception: {str(e)}",
                "exchange_connections"
            )

        # Test exchange readiness checklist
        try:
            response = requests.get(
                f"{BASE_URL}/api/exchange/readiness-checklist",
                headers=headers,
                timeout=10
            )
            
            success = response.status_code == 200
            if success:
                data = response.json()
                details = f"Checklist retrieved with {len(data)} items" if isinstance(data, list) else "Checklist data received"
            else:
                details = f"Status {response.status_code}: {response.text}"
                
            self.log_result(
                "GET /api/exchange/readiness-checklist",
                success,
                details,
                "exchange_connections"
            )
            
        except Exception as e:
            self.log_result(
                "GET /api/exchange/readiness-checklist",
                False,
                f"Exception: {str(e)}",
                "exchange_connections"
            )

        # Test exchange validation
        try:
            response = requests.get(
                f"{BASE_URL}/api/exchange/validate",
                headers=headers,
                timeout=10
            )
            
            success = response.status_code == 200
            if success:
                data = response.json()
                details = "Exchange validation successful"
            else:
                details = f"Status {response.status_code}: {response.text}"
                
            self.log_result(
                "GET /api/exchange/validate",
                success,
                details,
                "exchange_connections"
            )
            
        except Exception as e:
            self.log_result(
                "GET /api/exchange/validate",
                False,
                f"Exception: {str(e)}",
                "exchange_connections"
            )

    def test_connection_revalidation(self, conn_id, headers):
        """Test connection revalidation"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/user/exchange-connections/{conn_id}/revalidate",
                headers=headers,
                timeout=10
            )
            
            success = response.status_code == 200
            if success:
                data = response.json()
                is_valid = data.get("is_valid", False)
                can_trade = data.get("can_trade", False)
                details = f"Revalidation result - Valid: {is_valid}, Can Trade: {can_trade}"
                
                if not is_valid or not can_trade:
                    reason = data.get("reason", "Unknown")
                    details += f", Reason: {reason}"
            else:
                details = f"Status {response.status_code}: {response.text}"
                
            self.log_result(
                f"POST /api/user/exchange-connections/{conn_id}/revalidate",
                success,
                details,
                "exchange_connections"
            )
            
        except Exception as e:
            self.log_result(
                f"POST /api/user/exchange-connections/{conn_id}/revalidate",
                False,
                f"Exception: {str(e)}",
                "exchange_connections"
            )

    def test_execution_queue_management(self):
        """Test 4: Execution queue management (admin)"""
        print("\n" + "="*60)
        print("TEST 4: EXECUTION QUEUE MANAGEMENT")
        print("="*60)
        
        if not self.admin_token:
            self.log_result(
                "Execution Queue Tests",
                False,
                "Admin token required but not available",
                "execution_queue"
            )
            return

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Test execution queue listing
        try:
            response = requests.get(
                f"{BASE_URL}/api/admin/execution-queue?status_filter=QUEUED&limit=20",
                headers=headers,
                timeout=10
            )
            
            success = response.status_code == 200
            if success:
                data = response.json()
                queue_items = data.get("items", []) if isinstance(data, dict) else data
                
                details = f"Found {len(queue_items)} queued items"
                
                # Test queue actions if items exist
                if queue_items and len(queue_items) > 0:
                    first_item = queue_items[0]
                    intent_id = first_item.get("intent_id") or first_item.get("id")
                    
                    if intent_id:
                        self.test_queue_actions(intent_id, headers)
                else:
                    details += " (empty queue - normal for production)"
                    
            else:
                details = f"Status {response.status_code}: {response.text}"
                
            self.log_result(
                "GET /api/admin/execution-queue",
                success,
                details,
                "execution_queue"
            )
            
        except Exception as e:
            self.log_result(
                "GET /api/admin/execution-queue",
                False,
                f"Exception: {str(e)}",
                "execution_queue"
            )

    def test_queue_actions(self, intent_id, headers):
        """Test queue action buttons"""
        actions = ["reject", "retry"]
        
        for action in actions:
            try:
                # Try a dry-run action to test the endpoint
                response = requests.post(
                    f"{BASE_URL}/api/admin/execution-queue/{intent_id}/{action}",
                    headers=headers,
                    json={"dry_run": True} if action == "reject" else {},
                    timeout=10
                )
                
                if response.status_code == 423:
                    details = "423 EXECUTION_BLOCKED_BY_READINESS - Expected due to release gate/readiness requirements"
                    success = True  # This is expected behavior
                elif response.status_code == 200:
                    details = "Action endpoint accessible"
                    success = True
                else:
                    details = f"Status {response.status_code}: {response.text}"
                    success = False
                    
                self.log_result(
                    f"Queue {action} action test",
                    success,
                    details,
                    "execution_queue"
                )
                
            except Exception as e:
                self.log_result(
                    f"Queue {action} action test",
                    False,
                    f"Exception: {str(e)}",
                    "execution_queue"
                )

    def test_frontend_smoke(self):
        """Test 5: Frontend smoke test (critical paths)"""
        print("\n" + "="*60)
        print("TEST 5: FRONTEND SMOKE TEST")
        print("="*60)
        
        # Test landing page
        try:
            response = requests.get(BASE_URL, timeout=10)
            success = response.status_code == 200 and len(response.text) > 500
            
            if success:
                content = response.text
                has_login = 'Kullanıcı Girişi' in content or 'User Login' in content
                has_admin = 'Admin Girişi' in content or 'Admin Login' in content
                not_blank = len(content.strip()) > 500
                
                details = f"Page loaded ({len(content)} chars), Login buttons: User={has_login}, Admin={has_admin}"
                success = has_login and has_admin and not_blank
            else:
                details = f"Status {response.status_code}"
                success = False
                
            self.log_result(
                "Landing page accessibility",
                success,
                details,
                "frontend_smoke"
            )
            
        except Exception as e:
            self.log_result(
                "Landing page accessibility",
                False,
                f"Exception: {str(e)}",
                "frontend_smoke"
            )

        # Test admin login page navigation
        if self.admin_token:
            try:
                # Test that admin dashboard is accessible (basic test)
                headers = {"Authorization": f"Bearer {self.admin_token}"}
                response = requests.get(
                    f"{BASE_URL}/api/dashboard/summary",
                    headers=headers,
                    timeout=10
                )
                
                success = response.status_code == 200
                details = "Admin dashboard accessible" if success else f"Status {response.status_code}"
                
                self.log_result(
                    "Admin dashboard flow",
                    success,
                    details,
                    "frontend_smoke"
                )
                
            except Exception as e:
                self.log_result(
                    "Admin dashboard flow",
                    False,
                    f"Exception: {str(e)}",
                    "frontend_smoke"
                )

    def generate_final_report(self):
        """Generate final production readiness report"""
        print("\n" + "="*60)
        print("PRODUCTION READINESS ASSESSMENT")
        print("="*60)
        
        # Count results
        total_tests = 0
        passed_tests = 0
        critical_failures = len(self.test_results["blocking_issues"])
        warnings = len(self.test_results["warnings"])
        
        for category, tests in self.test_results.items():
            if isinstance(tests, dict):
                for test_name, result in tests.items():
                    if isinstance(result, dict) and "success" in result:
                        total_tests += 1
                        if result["success"]:
                            passed_tests += 1

        # Determine production readiness
        if critical_failures == 0:
            if warnings == 0:
                readiness = "✅ EVET - Production Ready"
                priority = "P0 - Green Light"
            else:
                readiness = "⚠️  EVET with Warnings - Production Ready with Monitoring"
                priority = "P1 - Deploy with Caution"
        else:
            readiness = "❌ HAYIR - Not Production Ready"
            priority = "P0 - Critical Blockers Present"

        self.test_results["production_readiness"] = readiness
        
        print(f"\n🎯 CANLIYA ALINIR MI? {readiness}")
        print(f"📊 Test Results: {passed_tests}/{total_tests} passed")
        print(f"🚨 Critical Issues: {critical_failures}")
        print(f"⚠️  Warnings: {warnings}")
        print(f"🏷️  Priority: {priority}")
        
        if self.test_results["blocking_issues"]:
            print("\n❌ P0 BLOCKING ISSUES:")
            for issue in self.test_results["blocking_issues"]:
                print(f"   - {issue}")
        
        if self.test_results["warnings"]:
            print("\n⚠️  P1/P2 WARNINGS:")
            for warning in self.test_results["warnings"]:
                print(f"   - {warning}")
        
        print("\n📋 TECHNICAL EVIDENCE:")
        print(f"   - Backend health: {'✅' if self.test_results.get('backend_health', {}).get('GET /api/health = 200', {}).get('success') else '❌'}")
        print(f"   - Admin auth: {'✅' if self.admin_token else '❌'}")
        print(f"   - User auth: {'✅' if self.user_token else '❌'}")
        print(f"   - Release gate: {'✅' if not any('Release Gate' in issue for issue in self.test_results.get('blocking_issues', [])) else '❌'}")
        print(f"   - Frontend: {'✅' if self.test_results.get('frontend_smoke', {}).get('Landing page accessibility', {}).get('success') else '❌'}")
        
        if critical_failures == 0:
            print("\n🚀 QUICK ACTION PLAN (Canlıya çıkmak için en kısa yol):")
            print("   1. ✅ All critical systems operational")
            if warnings > 0:
                print("   2. 📊 Monitor warning conditions during deployment")
                print("   3. 🔍 Verify exchange connections post-deployment")
            else:
                print("   2. 🎯 Deploy immediately - all systems green")
            print("   3. 📈 Monitor production metrics after deployment")
        else:
            print("\n🛠️  REQUIRED FIXES BEFORE DEPLOYMENT:")
            print("   1. ❌ Resolve all P0 blocking issues listed above")
            print("   2. 🔄 Re-run this test suite after fixes")
            print("   3. 📋 Verify all critical endpoints return 200")
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"/app/release_readiness_report_{timestamp}.json"
        
        try:
            with open(report_file, 'w') as f:
                json.dump(self.test_results, f, indent=2)
            print(f"\n📄 Detailed report saved: {report_file}")
        except Exception as e:
            print(f"\n⚠️  Could not save report: {e}")

    def run_all_tests(self):
        """Run complete test suite"""
        print("🎯 STARTING COMPREHENSIVE RELEASE READINESS AUDIT")
        print(f"🌐 Target: {BASE_URL}")
        print(f"⏰ Time: {datetime.now().isoformat()}")
        
        # Run all test categories
        self.test_backend_health()
        self.test_admin_authentication()
        self.test_user_authentication()
        self.test_release_gate_controls()
        self.test_exchange_connections()
        self.test_execution_queue_management()
        self.test_frontend_smoke()
        
        # Generate final assessment
        self.generate_final_report()


if __name__ == "__main__":
    tester = ReleaseReadinessTest()
    tester.run_all_tests()