#!/usr/bin/env python3
"""
P1.4 Backend Endpoint Testing
Testing specific admin endpoints for revenue snapshot functionality
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://revenue-snapshot.preview.emergentagent.com/api"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P14BackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, endpoint, status, details, error=None):
        """Log test result"""
        result = {
            'endpoint': endpoint,
            'status': status,  # 'PASS', 'FAIL', 'ERROR'
            'details': details,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {endpoint}: {status} - {details}")
        if error:
            print(f"   Error: {error}")
    
    def admin_login(self):
        """Login as admin and get access token"""
        try:
            login_url = f"{BASE_URL}/auth/login/admin"
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            print(f"🔐 Attempting admin login to {login_url}")
            response = self.session.post(login_url, json=login_data, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'access_token' in data:
                    self.admin_token = data['access_token']
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.admin_token}'
                    })
                    self.log_result("Admin Login", "PASS", f"Successfully logged in as {ADMIN_EMAIL}")
                    return True
                else:
                    self.log_result("Admin Login", "FAIL", "No access_token in response", str(data))
                    return False
            else:
                self.log_result("Admin Login", "FAIL", f"HTTP {response.status_code}", response.text[:200])
                return False
                
        except Exception as e:
            self.log_result("Admin Login", "ERROR", "Login request failed", str(e))
            return False
    
    def test_endpoint(self, endpoint_path, method="GET", data=None, expected_status=200):
        """Test a specific endpoint"""
        try:
            url = f"{BASE_URL}{endpoint_path}"
            print(f"🔍 Testing {method} {url}")
            
            if method == "GET":
                response = self.session.get(url, timeout=30)
            elif method == "POST":
                response = self.session.post(url, json=data, timeout=30)
            else:
                self.log_result(endpoint_path, "ERROR", f"Unsupported method: {method}")
                return False
            
            # Check response
            if response.status_code == expected_status:
                try:
                    response_data = response.json()
                    self.log_result(endpoint_path, "PASS", 
                                  f"HTTP {response.status_code}, Response size: {len(str(response_data))} chars")
                    return True
                except:
                    # Non-JSON response but correct status
                    self.log_result(endpoint_path, "PASS", 
                                  f"HTTP {response.status_code}, Response size: {len(response.text)} chars")
                    return True
            else:
                # Check for specific error patterns
                error_details = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'detail' in error_data:
                        error_details += f" - {error_data['detail']}"
                    elif 'message' in error_data:
                        error_details += f" - {error_data['message']}"
                except:
                    error_details += f" - {response.text[:200]}"
                
                # Check for database unavailable patterns
                if "database" in response.text.lower() or "connection" in response.text.lower():
                    self.log_result(endpoint_path, "FAIL", "Database unavailable detected", error_details)
                elif response.status_code == 503:
                    self.log_result(endpoint_path, "FAIL", "Service unavailable", error_details)
                elif response.status_code == 500:
                    self.log_result(endpoint_path, "FAIL", "Internal server error", error_details)
                else:
                    self.log_result(endpoint_path, "FAIL", error_details)
                return False
                
        except requests.exceptions.ConnectTimeout:
            self.log_result(endpoint_path, "ERROR", "Connection timeout - service may be down")
            return False
        except requests.exceptions.ConnectionError as e:
            self.log_result(endpoint_path, "ERROR", "Connection error - service unreachable", str(e))
            return False
        except Exception as e:
            self.log_result(endpoint_path, "ERROR", "Request failed", str(e))
            return False
    
    def test_health_endpoints(self):
        """Test basic health endpoints first"""
        print("\n🏥 Testing Health Endpoints")
        self.test_endpoint("/health")
        self.test_endpoint("/ready")
    
    def test_p14_endpoints(self):
        """Test P1.4 specific endpoints"""
        print("\n📊 Testing P1.4 Revenue Snapshot Endpoints")
        
        # Test the 5 specific endpoints mentioned in the review request
        endpoints = [
            "/admin/snapshots",
            "/admin/snapshots/run", 
            "/admin/snapshots/compare",
            "/admin/export/revenue",
            "/admin/export/user-economics"
        ]
        
        for endpoint in endpoints:
            if endpoint == "/admin/snapshots/run":
                # This might be a POST endpoint
                self.test_endpoint(endpoint, method="POST", data={})
            else:
                self.test_endpoint(endpoint)
    
    def run_all_tests(self):
        """Run complete test suite"""
        print("🚀 Starting P1.4 Backend Endpoint Testing")
        print(f"Base URL: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 60)
        
        # Test health first
        self.test_health_endpoints()
        
        # Login as admin
        if not self.admin_login():
            print("❌ Cannot proceed without admin login")
            return False
        
        # Test P1.4 endpoints
        self.test_p14_endpoints()
        
        # Summary
        self.print_summary()
        return True
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📋 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed = len([r for r in self.test_results if r['status'] == 'PASS'])
        failed = len([r for r in self.test_results if r['status'] == 'FAIL'])
        errors = len([r for r in self.test_results if r['status'] == 'ERROR'])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️ Errors: {errors}")
        print(f"Success Rate: {(passed/total_tests)*100:.1f}%")
        
        # Detailed results
        print("\n📊 ENDPOINT STATUS:")
        for result in self.test_results:
            status_icon = "✅" if result['status'] == "PASS" else "❌" if result['status'] == "FAIL" else "⚠️"
            print(f"{status_icon} {result['endpoint']}: {result['details']}")
            if result['error']:
                print(f"   └─ {result['error']}")
        
        # Root cause analysis
        print("\n🔍 ROOT CAUSE ANALYSIS:")
        database_issues = [r for r in self.test_results if 'database' in str(r.get('error', '')).lower()]
        connection_issues = [r for r in self.test_results if 'connection' in str(r.get('error', '')).lower()]
        service_issues = [r for r in self.test_results if r['status'] == 'ERROR']
        
        if database_issues:
            print("🔴 DATABASE UNAVAILABLE: Multiple endpoints showing database connection issues")
        elif connection_issues:
            print("🔴 CONNECTION ISSUES: Service may be unreachable")
        elif service_issues:
            print("🔴 SERVICE ISSUES: Backend service may be down or misconfigured")
        elif failed > 0:
            print("🟡 ENDPOINT ISSUES: Some endpoints returning errors but service is reachable")
        else:
            print("🟢 ALL SYSTEMS OPERATIONAL: No major issues detected")

if __name__ == "__main__":
    tester = P14BackendTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)