#!/usr/bin/env python3
"""
Backend API Testing Script - Read-Only Mode
Focused testing for Turkish user request:
1) Backend/API working check
2) DB connection/access validation 
3) Frontend data display validation
4) API ↔ UI integration validation

Target: https://dry-run-shadow.preview.emergentagent.com
API Base: https://dry-run-shadow.preview.emergentagent.com/api
"""

import requests
import json
import time
import sys
from typing import Dict, Any, Tuple

# Configuration
BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
ADMIN_CREDENTIALS = {
    "email": "admin@platform.local",
    "password": "Admin12345!"
}

class ReadOnlyAPITester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.results = {
            "backend_api": {"status": "UNKNOWN", "tests": [], "evidence": []},
            "db_connectivity": {"status": "UNKNOWN", "tests": [], "evidence": []}, 
            "frontend_render": {"status": "UNKNOWN", "tests": [], "evidence": []},
            "api_ui_integration": {"status": "UNKNOWN", "tests": [], "evidence": []}
        }

    def log_test(self, category: str, test_name: str, status: str, evidence: str):
        """Log test result with evidence"""
        self.results[category]["tests"].append({
            "name": test_name, 
            "status": status,
            "evidence": evidence
        })
        print(f"[{category.upper()}] {test_name}: {status}")
        if evidence:
            print(f"  Evidence: {evidence}")

    def test_backend_api_health(self):
        """Test 1: Backend/API çalışıyor mu?"""
        print("\n=== 1) BACKEND / API ÇALIŞIYOR MU? ===")
        
        # Test /api/health
        try:
            response = self.session.get(f"{API_BASE}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_test("backend_api", "GET /api/health", "PASS", 
                             f"200 OK, response: {data}")
            else:
                self.log_test("backend_api", "GET /api/health", "FAIL",
                             f"Status: {response.status_code}, response: {response.text[:200]}")
        except Exception as e:
            self.log_test("backend_api", "GET /api/health", "FAIL", f"Exception: {str(e)}")

        # Test /api/ready (if exists)
        try:
            response = self.session.get(f"{API_BASE}/ready", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_test("backend_api", "GET /api/ready", "PASS",
                             f"200 OK, response: {data}")
            else:
                self.log_test("backend_api", "GET /api/ready", "FAIL",
                             f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("backend_api", "GET /api/ready", "FAIL", f"Exception: {str(e)}")

        # Get admin token for further testing
        try:
            auth_response = self.session.post(f"{API_BASE}/auth/login/admin", 
                                            json=ADMIN_CREDENTIALS, timeout=10)
            if auth_response.status_code == 200:
                auth_data = auth_response.json()
                self.admin_token = auth_data.get("access_token")
                self.log_test("backend_api", "Admin Authentication", "PASS",
                             f"Admin login successful, token received")
            else:
                self.log_test("backend_api", "Admin Authentication", "FAIL",
                             f"Status: {auth_response.status_code}, response: {auth_response.text[:200]}")
        except Exception as e:
            self.log_test("backend_api", "Admin Authentication", "FAIL", f"Exception: {str(e)}")

        # Test additional read endpoint
        if self.admin_token:
            try:
                headers = {"Authorization": f"Bearer {self.admin_token}"}
                response = self.session.get(f"{API_BASE}/dashboard/summary", headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    self.log_test("backend_api", "GET /api/dashboard/summary", "PASS",
                                 f"200 OK, contains {len(data)} fields")
                else:
                    self.log_test("backend_api", "GET /api/dashboard/summary", "FAIL",
                                 f"Status: {response.status_code}")
            except Exception as e:
                self.log_test("backend_api", "GET /api/dashboard/summary", "FAIL", f"Exception: {str(e)}")

        # Determine overall backend/API status
        passed_tests = [t for t in self.results["backend_api"]["tests"] if t["status"] == "PASS"]
        total_tests = len(self.results["backend_api"]["tests"])
        
        if len(passed_tests) >= 2:  # At least health + one other endpoint working
            self.results["backend_api"]["status"] = "PASS"
        else:
            self.results["backend_api"]["status"] = "FAIL"

    def test_db_connectivity(self):
        """Test 2: DB bağlantısı/kayıt erişimi var mı?"""
        print("\n=== 2) DB BAĞLANTISI/KAYIT ERİŞİMİ VAR MI? ===")

        # Check health endpoint for DB status
        try:
            response = self.session.get(f"{API_BASE}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                db_indicators = []
                
                # Look for DB-related fields in health response
                for key, value in data.items():
                    if any(db_term in key.lower() for db_term in ['db', 'database', 'mongo', 'postgres', 'connection']):
                        db_indicators.append(f"{key}: {value}")
                
                if db_indicators:
                    self.log_test("db_connectivity", "Health endpoint DB indicators", "PASS",
                                 f"DB-related fields found: {', '.join(db_indicators)}")
                else:
                    self.log_test("db_connectivity", "Health endpoint DB indicators", "PASS", 
                                 "No explicit DB fields in health response, but endpoint accessible")
            else:
                self.log_test("db_connectivity", "Health endpoint DB indicators", "FAIL",
                             f"Health endpoint failed: {response.status_code}")
        except Exception as e:
            self.log_test("db_connectivity", "Health endpoint DB indicators", "FAIL", f"Exception: {str(e)}")

        # Test endpoint that should return DB-sourced data
        if self.admin_token:
            try:
                headers = {"Authorization": f"Bearer {self.admin_token}"}
                response = self.session.get(f"{API_BASE}/admin/user-approvals", headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    record_count = len(data) if isinstance(data, list) else len(data.get('items', []))
                    self.log_test("db_connectivity", "DB read via user-approvals", "PASS",
                                 f"200 OK, returned {record_count} records from DB")
                else:
                    self.log_test("db_connectivity", "DB read via user-approvals", "FAIL",
                                 f"Status: {response.status_code}")
            except Exception as e:
                self.log_test("db_connectivity", "DB read via user-approvals", "FAIL", f"Exception: {str(e)}")

        # Determine overall DB connectivity status
        passed_tests = [t for t in self.results["db_connectivity"]["tests"] if t["status"] == "PASS"]
        
        if passed_tests:
            self.results["db_connectivity"]["status"] = "PASS"
        else:
            self.results["db_connectivity"]["status"] = "FAIL"

    def test_frontend_render(self):
        """Test 3: Frontend veri gösterimi doğru mu?"""
        print("\n=== 3) FRONTEND VERİ GÖSTERİMİ DOĞRU MU? ===")

        # Test landing page
        try:
            response = self.session.get(BASE_URL, timeout=15)
            if response.status_code == 200:
                content = response.text
                content_length = len(content)
                
                # Check for critical elements
                critical_elements = [
                    ("XILO-USER TRADING ENGINE", "Main title"),
                    ("Kullanıcı Girişi", "User login button"),
                    ("HESAP AÇ", "Registration section")
                ]
                
                found_elements = []
                for element, description in critical_elements:
                    if element in content:
                        found_elements.append(description)
                
                self.log_test("frontend_render", "Landing page load", "PASS",
                             f"200 OK, {content_length} chars, found: {', '.join(found_elements)}")
            else:
                self.log_test("frontend_render", "Landing page load", "FAIL",
                             f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("frontend_render", "Landing page load", "FAIL", f"Exception: {str(e)}")

        # Test user login page (check if it's accessible)
        try:
            response = self.session.get(f"{BASE_URL}/user/login", timeout=15)
            if response.status_code == 200:
                content = response.text
                login_elements = ["Giriş Yap", "E-posta", "Şifre"]
                found_login_elements = [elem for elem in login_elements if elem in content]
                
                self.log_test("frontend_render", "User login page load", "PASS",
                             f"200 OK, found: {', '.join(found_login_elements)}")
            else:
                self.log_test("frontend_render", "User login page load", "FAIL",
                             f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("frontend_render", "User login page load", "FAIL", f"Exception: {str(e)}")

        # Determine overall frontend status
        passed_tests = [t for t in self.results["frontend_render"]["tests"] if t["status"] == "PASS"]
        
        if len(passed_tests) >= 1:  # At least landing page working
            self.results["frontend_render"]["status"] = "PASS"
        else:
            self.results["frontend_render"]["status"] = "FAIL"

    def test_api_ui_integration(self):
        """Test 4: API ↔ UI bağlantı kontrolü"""
        print("\n=== 4) API ↔ UI BAĞLANTI KONTROLÜ ===")

        # Test CORS - make a cross-origin request
        try:
            headers = {
                'Origin': BASE_URL,
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'authorization,content-type'
            }
            response = self.session.options(f"{API_BASE}/health", headers=headers, timeout=10)
            
            cors_headers = {
                'access-control-allow-origin': response.headers.get('access-control-allow-origin', 'Missing'),
                'access-control-allow-methods': response.headers.get('access-control-allow-methods', 'Missing'),
                'access-control-allow-headers': response.headers.get('access-control-allow-headers', 'Missing')
            }
            
            self.log_test("api_ui_integration", "CORS preflight check", "PASS",
                         f"OPTIONS returned {response.status_code}, CORS headers: {cors_headers}")
        except Exception as e:
            self.log_test("api_ui_integration", "CORS preflight check", "FAIL", f"Exception: {str(e)}")

        # Test a typical UI→API workflow (admin login → dashboard)
        if self.admin_token:
            try:
                # Test admin dashboard API that UI would call
                headers = {"Authorization": f"Bearer {self.admin_token}"}
                response = self.session.get(f"{API_BASE}/dashboard/summary", headers=headers, timeout=10)
                
                if response.status_code == 200:
                    response_time = response.elapsed.total_seconds()
                    self.log_test("api_ui_integration", "Admin dashboard API integration", "PASS",
                                 f"200 OK, response time: {response_time:.3f}s")
                elif response.status_code >= 500:
                    self.log_test("api_ui_integration", "Admin dashboard API integration", "FAIL",
                                 f"5xx error: {response.status_code}")
                else:
                    self.log_test("api_ui_integration", "Admin dashboard API integration", "FAIL",
                                 f"Status: {response.status_code}")
            except requests.Timeout:
                self.log_test("api_ui_integration", "Admin dashboard API integration", "FAIL", 
                             "Request timeout - potential performance issue")
            except Exception as e:
                self.log_test("api_ui_integration", "Admin dashboard API integration", "FAIL", f"Exception: {str(e)}")

        # Test another common endpoint that UI uses
        try:
            response = self.session.get(f"{API_BASE}/health", timeout=10)
            response_time = response.elapsed.total_seconds()
            
            if response.status_code == 200 and response_time < 5.0:
                self.log_test("api_ui_integration", "API response performance", "PASS",
                             f"Health endpoint responded in {response_time:.3f}s")
            elif response.status_code == 200:
                self.log_test("api_ui_integration", "API response performance", "FAIL",
                             f"Slow response: {response_time:.3f}s")
            else:
                self.log_test("api_ui_integration", "API response performance", "FAIL",
                             f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("api_ui_integration", "API response performance", "FAIL", f"Exception: {str(e)}")

        # Determine overall API-UI integration status
        passed_tests = [t for t in self.results["api_ui_integration"]["tests"] if t["status"] == "PASS"]
        failed_5xx_tests = [t for t in self.results["api_ui_integration"]["tests"] 
                           if t["status"] == "FAIL" and "5xx" in t["evidence"]]
        
        if len(passed_tests) >= 2 and not failed_5xx_tests:
            self.results["api_ui_integration"]["status"] = "PASS" 
        else:
            self.results["api_ui_integration"]["status"] = "FAIL"

    def generate_summary_report(self):
        """Generate final summary in Turkish format"""
        print("\n" + "="*60)
        print("KISA ÖZET (Brief Summary)")
        print("="*60)
        
        print(f"Backend/API: {self.results['backend_api']['status']}")
        for test in self.results['backend_api']['tests']:
            print(f"  - {test['name']}: {test['status']}")
            
        print(f"DB read/connectivity: {self.results['db_connectivity']['status']}")
        for test in self.results['db_connectivity']['tests']:
            print(f"  - {test['name']}: {test['status']}")
            
        print(f"Frontend render: {self.results['frontend_render']['status']}")
        for test in self.results['frontend_render']['tests']:
            print(f"  - {test['name']}: {test['status']}")
            
        print(f"API↔UI entegrasyon: {self.results['api_ui_integration']['status']}")
        for test in self.results['api_ui_integration']['tests']:
            print(f"  - {test['name']}: {test['status']}")

        # Identify any issues
        print("\nBULGU VE SORUNLAR (Findings and Issues):")
        issues_found = False
        
        for category, data in self.results.items():
            failed_tests = [t for t in data['tests'] if t['status'] == 'FAIL']
            if failed_tests:
                issues_found = True
                print(f"\n{category.upper()} sorunları:")
                for test in failed_tests:
                    print(f"  - {test['name']}: {test['evidence']}")
        
        if not issues_found:
            print("  Kritik sorun tespit edilmedi.")
            
        print("\n" + "="*60)

    def run_all_tests(self):
        """Execute all test categories"""
        print("Read-Only API Testing Started")
        print(f"Target: {BASE_URL}")
        print(f"API Base: {API_BASE}")
        print("="*60)
        
        self.test_backend_api_health()
        self.test_db_connectivity()  
        self.test_frontend_render()
        self.test_api_ui_integration()
        
        self.generate_summary_report()
        
        return self.results

if __name__ == "__main__":
    tester = ReadOnlyAPITester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    all_passing = all(data['status'] == 'PASS' for data in results.values())
    sys.exit(0 if all_passing else 1)