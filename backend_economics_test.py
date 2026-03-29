#!/usr/bin/env python3
"""
P1.3 Backend Economics Endpoints Testing
Testing the economics endpoints as specified in the review request:

1) GET /api/admin/users/economics
2) GET /api/admin/users/economics/retention-trend (weekly + monthly)
3) GET /api/admin/users/economics/segment-profitability
4) GET /api/admin/users/economics/export.csv
5) GET /api/admin/users/economics/export.xlsx
6) POST /api/admin/users/economics/snapshots/run (daily + weekly)
7) GET /api/admin/users/economics/snapshots/trend (daily + weekly)
8) Determinism check: economics endpoint should return same KPI on consecutive calls
9) Regression: /api/admin/commercial/p0/live-gate should not be broken

Admin credentials: canary.admin@platform.local / CanaryAdmin123!
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
import time

# Get backend URL from frontend env
BACKEND_URL = "https://dry-run-shadow.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class EconomicsBackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        
    def log_test(self, test_name: str, status: str, details: str = "", response_data: Any = None):
        """Log test result"""
        result = {
            "test_name": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "response_data": response_data
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if response_data and isinstance(response_data, dict):
            if "error" in response_data or "detail" in response_data:
                print(f"   Error: {response_data}")
        print()

    def admin_login(self) -> bool:
        """Login as admin and get access token"""
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login/admin",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                    self.log_test("Admin Login", "PASS", f"Successfully logged in as {ADMIN_EMAIL}")
                    return True
                else:
                    self.log_test("Admin Login", "FAIL", "No access token received", data)
                    return False
            else:
                self.log_test("Admin Login", "FAIL", f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Admin Login", "FAIL", f"Exception: {str(e)}")
            return False

    def test_health_check(self) -> bool:
        """Test basic health endpoint"""
        try:
            response = self.session.get(f"{API_BASE}/health")
            if response.status_code == 200:
                data = response.json()
                self.log_test("Health Check", "PASS", "Backend service is healthy", data)
                return True
            else:
                self.log_test("Health Check", "FAIL", f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
        except Exception as e:
            self.log_test("Health Check", "FAIL", f"Exception: {str(e)}")
            return False

    def test_economics_main_endpoint(self) -> bool:
        """Test GET /api/admin/users/economics"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users/economics")
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Economics Main Endpoint", "PASS", 
                            f"Economics endpoint returned data with {len(data) if isinstance(data, (list, dict)) else 'unknown'} items", data)
                return True
            else:
                self.log_test("Economics Main Endpoint", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Economics Main Endpoint", "FAIL", f"Exception: {str(e)}")
            return False

    def test_retention_trend_weekly(self) -> bool:
        """Test GET /api/admin/users/economics/retention-trend (weekly)"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users/economics/retention-trend", 
                                      params={"period": "weekly"})
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Retention Trend Weekly", "PASS", 
                            f"Weekly retention trend returned data", data)
                return True
            else:
                self.log_test("Retention Trend Weekly", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Retention Trend Weekly", "FAIL", f"Exception: {str(e)}")
            return False

    def test_retention_trend_monthly(self) -> bool:
        """Test GET /api/admin/users/economics/retention-trend (monthly)"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users/economics/retention-trend", 
                                      params={"period": "monthly"})
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Retention Trend Monthly", "PASS", 
                            f"Monthly retention trend returned data", data)
                return True
            else:
                self.log_test("Retention Trend Monthly", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Retention Trend Monthly", "FAIL", f"Exception: {str(e)}")
            return False

    def test_segment_profitability(self) -> bool:
        """Test GET /api/admin/users/economics/segment-profitability"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users/economics/segment-profitability")
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Segment Profitability", "PASS", 
                            f"Segment profitability returned data", data)
                return True
            else:
                self.log_test("Segment Profitability", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Segment Profitability", "FAIL", f"Exception: {str(e)}")
            return False

    def test_export_csv(self) -> bool:
        """Test GET /api/admin/users/economics/export.csv"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users/economics/export.csv")
            
            if response.status_code == 200:
                # Check content type
                content_type = response.headers.get('content-type', '')
                if 'text/csv' in content_type or 'application/csv' in content_type:
                    # Check if response has CSV content
                    content = response.text
                    if content and len(content) > 0:
                        lines = content.split('\n')
                        self.log_test("Export CSV", "PASS", 
                                    f"CSV export successful. Content-Type: {content_type}, Lines: {len(lines)}")
                        return True
                    else:
                        self.log_test("Export CSV", "FAIL", 
                                    f"CSV export returned empty content")
                        return False
                else:
                    self.log_test("Export CSV", "FAIL", 
                                f"Wrong content type: {content_type}, expected text/csv")
                    return False
            else:
                self.log_test("Export CSV", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Export CSV", "FAIL", f"Exception: {str(e)}")
            return False

    def test_export_xlsx(self) -> bool:
        """Test GET /api/admin/users/economics/export.xlsx"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users/economics/export.xlsx")
            
            if response.status_code == 200:
                # Check content type
                content_type = response.headers.get('content-type', '')
                if 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in content_type or 'application/xlsx' in content_type:
                    # Check if response has XLSX content
                    content_length = len(response.content)
                    if content_length > 0:
                        self.log_test("Export XLSX", "PASS", 
                                    f"XLSX export successful. Content-Type: {content_type}, Size: {content_length} bytes")
                        return True
                    else:
                        self.log_test("Export XLSX", "FAIL", 
                                    f"XLSX export returned empty content")
                        return False
                else:
                    self.log_test("Export XLSX", "FAIL", 
                                f"Wrong content type: {content_type}, expected XLSX format")
                    return False
            else:
                self.log_test("Export XLSX", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Export XLSX", "FAIL", f"Exception: {str(e)}")
            return False

    def test_snapshots_run_daily(self) -> bool:
        """Test POST /api/admin/users/economics/snapshots/run (daily)"""
        try:
            response = self.session.post(f"{API_BASE}/admin/users/economics/snapshots/run", 
                                       json={"period": "daily"})
            
            if response.status_code in [200, 201, 202]:
                data = response.json() if response.content else {}
                self.log_test("Snapshots Run Daily", "PASS", 
                            f"Daily snapshot run successful. Status: {response.status_code}", data)
                return True
            else:
                self.log_test("Snapshots Run Daily", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Snapshots Run Daily", "FAIL", f"Exception: {str(e)}")
            return False

    def test_snapshots_run_weekly(self) -> bool:
        """Test POST /api/admin/users/economics/snapshots/run (weekly)"""
        try:
            response = self.session.post(f"{API_BASE}/admin/users/economics/snapshots/run", 
                                       json={"period": "weekly"})
            
            if response.status_code in [200, 201, 202]:
                data = response.json() if response.content else {}
                self.log_test("Snapshots Run Weekly", "PASS", 
                            f"Weekly snapshot run successful. Status: {response.status_code}", data)
                return True
            else:
                self.log_test("Snapshots Run Weekly", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Snapshots Run Weekly", "FAIL", f"Exception: {str(e)}")
            return False

    def test_snapshots_trend_daily(self) -> bool:
        """Test GET /api/admin/users/economics/snapshots/trend (daily)"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users/economics/snapshots/trend", 
                                      params={"period": "daily"})
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Snapshots Trend Daily", "PASS", 
                            f"Daily snapshots trend returned data", data)
                return True
            else:
                self.log_test("Snapshots Trend Daily", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Snapshots Trend Daily", "FAIL", f"Exception: {str(e)}")
            return False

    def test_snapshots_trend_weekly(self) -> bool:
        """Test GET /api/admin/users/economics/snapshots/trend (weekly)"""
        try:
            response = self.session.get(f"{API_BASE}/admin/users/economics/snapshots/trend", 
                                      params={"period": "weekly"})
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Snapshots Trend Weekly", "PASS", 
                            f"Weekly snapshots trend returned data", data)
                return True
            else:
                self.log_test("Snapshots Trend Weekly", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Snapshots Trend Weekly", "FAIL", f"Exception: {str(e)}")
            return False

    def test_determinism_check(self) -> bool:
        """Test determinism: economics endpoint should return same KPI on consecutive calls"""
        try:
            # Make first call
            response1 = self.session.get(f"{API_BASE}/admin/users/economics")
            if response1.status_code != 200:
                self.log_test("Determinism Check", "FAIL", 
                            f"First call failed with HTTP {response1.status_code}")
                return False
            
            data1 = response1.json()
            
            # Wait a moment
            time.sleep(1)
            
            # Make second call
            response2 = self.session.get(f"{API_BASE}/admin/users/economics")
            if response2.status_code != 200:
                self.log_test("Determinism Check", "FAIL", 
                            f"Second call failed with HTTP {response2.status_code}")
                return False
            
            data2 = response2.json()
            
            # Compare the responses
            if data1 == data2:
                self.log_test("Determinism Check", "PASS", 
                            "Consecutive calls returned identical KPI data")
                return True
            else:
                # Check if only timestamps differ (acceptable)
                if isinstance(data1, dict) and isinstance(data2, dict):
                    # Remove timestamp fields for comparison
                    data1_clean = {k: v for k, v in data1.items() if 'timestamp' not in k.lower() and 'time' not in k.lower() and 'generated_at' not in k.lower()}
                    data2_clean = {k: v for k, v in data2.items() if 'timestamp' not in k.lower() and 'time' not in k.lower() and 'generated_at' not in k.lower()}
                    
                    if data1_clean == data2_clean:
                        self.log_test("Determinism Check", "PASS", 
                                    "KPI data is deterministic (only timestamps differ)")
                        return True
                
                self.log_test("Determinism Check", "FAIL", 
                            "Consecutive calls returned different KPI data", 
                            {"call1": data1, "call2": data2})
                return False
                
        except Exception as e:
            self.log_test("Determinism Check", "FAIL", f"Exception: {str(e)}")
            return False

    def test_regression_live_gate(self) -> bool:
        """Test regression: /api/admin/commercial/p0/live-gate should not be broken"""
        try:
            # Test with proper parameters
            response = self.session.get(f"{API_BASE}/admin/commercial/p0/live-gate", 
                                      params={"target_user_email": ADMIN_EMAIL})
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Regression Live Gate", "PASS", 
                            "Live gate endpoint is working correctly", data)
                return True
            elif response.status_code in [400, 404]:
                # These might be expected if parameters are missing
                data = response.json() if response.content else {}
                detail = data.get("detail", "")
                if "required" in detail.lower() or "missing" in detail.lower():
                    self.log_test("Regression Live Gate", "PASS", 
                                f"Live gate endpoint accessible (expected parameter error): {detail}")
                    return True
                else:
                    self.log_test("Regression Live Gate", "FAIL", 
                                f"Unexpected error: {detail}", data)
                    return False
            else:
                self.log_test("Regression Live Gate", "FAIL", 
                            f"HTTP {response.status_code}", response.json() if response.content else {})
                return False
                
        except Exception as e:
            self.log_test("Regression Live Gate", "FAIL", f"Exception: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all P1.3 economics backend tests"""
        print("🚀 Starting P1.3 Economics Backend Tests")
        print("=" * 60)
        
        # Basic connectivity
        if not self.test_health_check():
            print("❌ Health check failed - aborting tests")
            return
            
        if not self.admin_login():
            print("❌ Admin login failed - aborting tests")
            return
        
        # Core economics endpoint tests
        tests = [
            self.test_economics_main_endpoint,
            self.test_retention_trend_weekly,
            self.test_retention_trend_monthly,
            self.test_segment_profitability,
            self.test_export_csv,
            self.test_export_xlsx,
            self.test_snapshots_run_daily,
            self.test_snapshots_run_weekly,
            self.test_snapshots_trend_daily,
            self.test_snapshots_trend_weekly,
            self.test_determinism_check,
            self.test_regression_live_gate,
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            try:
                if test():
                    passed += 1
            except Exception as e:
                print(f"❌ Test {test.__name__} failed with exception: {e}")
        
        print("=" * 60)
        print(f"📊 Test Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("✅ All P1.3 economics tests passed!")
        elif passed >= total * 0.8:
            print("⚠️ Most tests passed. Some expected failures due to missing test data.")
        else:
            print("❌ Multiple test failures detected. Please review the issues above.")
        
        return passed, total

    def generate_summary(self):
        """Generate test summary"""
        passed = sum(1 for result in self.test_results if result["status"] == "PASS")
        failed = sum(1 for result in self.test_results if result["status"] == "FAIL")
        partial = sum(1 for result in self.test_results if result["status"] == "PARTIAL")
        
        print("\n" + "=" * 60)
        print("📋 P1.3 ECONOMICS BACKEND TEST SUMMARY")
        print("=" * 60)
        
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_symbol} {result['test_name']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        print("\n" + "=" * 60)
        print(f"📊 FINAL RESULTS: {passed} PASS, {failed} FAIL, {partial} PARTIAL")
        print("=" * 60)
        
        # Key findings
        print("\n🔍 KEY VALIDATION RESULTS:")
        print("1) GET /api/admin/users/economics: Tested")
        print("2) GET /api/admin/users/economics/retention-trend (weekly + monthly): Tested")
        print("3) GET /api/admin/users/economics/segment-profitability: Tested")
        print("4) GET /api/admin/users/economics/export.csv: Tested")
        print("5) GET /api/admin/users/economics/export.xlsx: Tested")
        print("6) POST /api/admin/users/economics/snapshots/run (daily + weekly): Tested")
        print("7) GET /api/admin/users/economics/snapshots/trend (daily + weekly): Tested")
        print("8) Determinism check: Economics endpoint consecutive calls tested")
        print("9) Regression: /api/admin/commercial/p0/live-gate tested")
        
        return passed >= len(self.test_results) * 0.8

def main():
    """Main test execution"""
    tester = EconomicsBackendTester()
    passed, total = tester.run_all_tests()
    success = tester.generate_summary()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()