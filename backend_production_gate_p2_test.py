#!/usr/bin/env python3
"""
Production Gate P2 Hardening Backend Validation Test
====================================================

Turkish Review Request: Production Gate P2 Hardening backend doğrulaması yap.
Target URL: https://identity-control-1.preview.emergentagent.com
Credentials: canary.admin@platform.local / CanaryAdmin123!

Test Requirements:
1) GET /api/phase4/admin/production-gate/system/cross-check => 200 ve is_consistent=true
2) GET /api/phase4/admin/production-gate/analytics/cross-check => 200 ve is_consistent=true
3) Cross-check payload alanları: comparison_sources, consistency_rules, counts
4) GET /api/phase4/admin/production-gate/checks/history?limit=300 => flapping_detail içinde severity + window_sec
5) GET /api/phase4/admin/production-gate/checks/compare?limit=300 => en az bir check run_count>=3
6) GET /api/phase4/admin/production-gate/timeline?limit=300 => audit_id + request_id mevcut
7) POST /api/phase4/admin/production-gate/history/cleanup?force=true => cleaned alanı ve history_removed/compare_removed alanları

Expected Output: PASS/FAIL ve kısa bulgularla ver.
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://identity-control-1.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
CREDENTIALS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}

class ProductionGateP2Validator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'ProductionGateP2Validator/1.0'
        })
        self.auth_token = None
        self.test_results = []
        
    def log_test(self, test_name, status, details="", expected="", actual=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "expected": expected,
            "actual": actual,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        # Print immediate feedback
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if expected and actual:
            print(f"   Expected: {expected}")
            print(f"   Actual: {actual}")
        print()

    def authenticate(self):
        """Authenticate with admin credentials"""
        print("🔐 Authenticating with canary.admin@platform.local...")
        
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login/admin",
                json=CREDENTIALS,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'access_token' in data:
                    self.auth_token = data['access_token']
                    self.session.headers['Authorization'] = f'Bearer {self.auth_token}'
                    self.log_test("Admin Authentication", "PASS", 
                                f"Successfully authenticated as {CREDENTIALS['email']}")
                    return True
                else:
                    self.log_test("Admin Authentication", "FAIL", 
                                "No access_token in response", "access_token field", "missing")
                    return False
            else:
                self.log_test("Admin Authentication", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False

    def test_system_cross_check(self):
        """Test 1: GET /api/phase4/admin/production-gate/system/cross-check"""
        print("🔍 Testing System Cross-Check Endpoint...")
        
        try:
            response = self.session.get(
                f"{API_BASE}/phase4/admin/production-gate/system/cross-check",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check is_consistent=true
                is_consistent = data.get('is_consistent')
                if is_consistent is True:
                    # Check required fields
                    required_fields = ['comparison_sources', 'consistency_rules', 'counts']
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if not missing_fields:
                        self.log_test("System Cross-Check", "PASS", 
                                    f"is_consistent=true, all required fields present: {required_fields}")
                    else:
                        self.log_test("System Cross-Check", "FAIL", 
                                    f"Missing required fields: {missing_fields}", 
                                    str(required_fields), f"Missing: {missing_fields}")
                else:
                    self.log_test("System Cross-Check", "FAIL", 
                                f"is_consistent not true", "is_consistent=true", f"is_consistent={is_consistent}")
            else:
                self.log_test("System Cross-Check", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("System Cross-Check", "FAIL", f"Exception: {str(e)}")

    def test_analytics_cross_check(self):
        """Test 2: GET /api/phase4/admin/production-gate/analytics/cross-check"""
        print("📊 Testing Analytics Cross-Check Endpoint...")
        
        try:
            response = self.session.get(
                f"{API_BASE}/phase4/admin/production-gate/analytics/cross-check",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check is_consistent=true
                is_consistent = data.get('is_consistent')
                if is_consistent is True:
                    # Check required fields
                    required_fields = ['comparison_sources', 'consistency_rules', 'counts']
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if not missing_fields:
                        self.log_test("Analytics Cross-Check", "PASS", 
                                    f"is_consistent=true, all required fields present: {required_fields}")
                    else:
                        self.log_test("Analytics Cross-Check", "FAIL", 
                                    f"Missing required fields: {missing_fields}", 
                                    str(required_fields), f"Missing: {missing_fields}")
                else:
                    self.log_test("Analytics Cross-Check", "FAIL", 
                                f"is_consistent not true", "is_consistent=true", f"is_consistent={is_consistent}")
            else:
                self.log_test("Analytics Cross-Check", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Analytics Cross-Check", "FAIL", f"Exception: {str(e)}")

    def test_checks_history(self):
        """Test 3: GET /api/phase4/admin/production-gate/checks/history?limit=300"""
        print("📋 Testing Checks History Endpoint...")
        
        try:
            response = self.session.get(
                f"{API_BASE}/phase4/admin/production-gate/checks/history?limit=300",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Look for flapping_detail with severity + window_sec
                found_flapping_detail = False
                flapping_details = []
                
                if isinstance(data, dict) and 'items' in data:
                    items = data['items']
                elif isinstance(data, list):
                    items = data
                else:
                    items = []
                
                for item in items:
                    if 'flapping_detail' in item:
                        flapping_detail = item['flapping_detail']
                        if isinstance(flapping_detail, dict):
                            has_severity = 'severity' in flapping_detail
                            has_window_sec = 'window_sec' in flapping_detail
                            
                            if has_severity and has_window_sec:
                                found_flapping_detail = True
                                flapping_details.append({
                                    'severity': flapping_detail.get('severity'),
                                    'window_sec': flapping_detail.get('window_sec')
                                })
                
                if found_flapping_detail:
                    self.log_test("Checks History", "PASS", 
                                f"Found flapping_detail with severity + window_sec. Examples: {flapping_details[:3]}")
                else:
                    self.log_test("Checks History", "FAIL", 
                                "No flapping_detail found with both severity and window_sec fields", 
                                "flapping_detail with severity + window_sec", "Not found")
            else:
                self.log_test("Checks History", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Checks History", "FAIL", f"Exception: {str(e)}")

    def test_checks_compare(self):
        """Test 4: GET /api/phase4/admin/production-gate/checks/compare?limit=300"""
        print("🔄 Testing Checks Compare Endpoint...")
        
        try:
            response = self.session.get(
                f"{API_BASE}/phase4/admin/production-gate/checks/compare?limit=300",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Look for at least one check with run_count>=3
                found_high_run_count = False
                high_run_count_checks = []
                
                if isinstance(data, dict) and 'items' in data:
                    items = data['items']
                elif isinstance(data, list):
                    items = data
                else:
                    items = []
                
                for item in items:
                    run_count = item.get('run_count', 0)
                    if run_count >= 3:
                        found_high_run_count = True
                        high_run_count_checks.append({
                            'id': item.get('id', 'unknown'),
                            'run_count': run_count
                        })
                
                if found_high_run_count:
                    self.log_test("Checks Compare", "PASS", 
                                f"Found {len(high_run_count_checks)} checks with run_count>=3. Examples: {high_run_count_checks[:3]}")
                else:
                    self.log_test("Checks Compare", "FAIL", 
                                "No checks found with run_count>=3", 
                                "At least one check with run_count>=3", "None found")
            else:
                self.log_test("Checks Compare", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Checks Compare", "FAIL", f"Exception: {str(e)}")

    def test_timeline(self):
        """Test 5: GET /api/phase4/admin/production-gate/timeline?limit=300"""
        print("⏰ Testing Timeline Endpoint...")
        
        try:
            response = self.session.get(
                f"{API_BASE}/phase4/admin/production-gate/timeline?limit=300",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Look for audit_id + request_id
                found_audit_and_request = False
                timeline_items = []
                
                if isinstance(data, dict) and 'items' in data:
                    items = data['items']
                elif isinstance(data, list):
                    items = data
                else:
                    items = []
                
                for item in items:
                    has_audit_id = 'audit_id' in item and item['audit_id'] is not None
                    has_request_id = 'request_id' in item and item['request_id'] is not None
                    
                    if has_audit_id and has_request_id:
                        found_audit_and_request = True
                        timeline_items.append({
                            'audit_id': item.get('audit_id'),
                            'request_id': item.get('request_id')
                        })
                
                if found_audit_and_request:
                    self.log_test("Timeline", "PASS", 
                                f"Found {len(timeline_items)} items with both audit_id + request_id. Examples: {timeline_items[:3]}")
                else:
                    self.log_test("Timeline", "FAIL", 
                                "No timeline items found with both audit_id and request_id", 
                                "Items with audit_id + request_id", "None found")
            else:
                self.log_test("Timeline", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Timeline", "FAIL", f"Exception: {str(e)}")

    def test_history_cleanup(self):
        """Test 6: POST /api/phase4/admin/production-gate/history/cleanup?force=true"""
        print("🧹 Testing History Cleanup Endpoint...")
        
        try:
            response = self.session.post(
                f"{API_BASE}/phase4/admin/production-gate/history/cleanup?force=true",
                json={},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for required fields: cleaned, history_removed, compare_removed
                required_fields = ['cleaned', 'history_removed', 'compare_removed']
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    cleanup_summary = {
                        'cleaned': data.get('cleaned'),
                        'history_removed': data.get('history_removed'),
                        'compare_removed': data.get('compare_removed')
                    }
                    self.log_test("History Cleanup", "PASS", 
                                f"All required fields present: {cleanup_summary}")
                else:
                    self.log_test("History Cleanup", "FAIL", 
                                f"Missing required fields: {missing_fields}", 
                                str(required_fields), f"Missing: {missing_fields}")
            else:
                self.log_test("History Cleanup", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("History Cleanup", "FAIL", f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all Production Gate P2 Hardening tests"""
        print("=" * 80)
        print("🚀 PRODUCTION GATE P2 HARDENING BACKEND VALIDATION")
        print("=" * 80)
        print(f"Target URL: {BASE_URL}")
        print(f"Credentials: {CREDENTIALS['email']}")
        print(f"Test Time: {datetime.now().isoformat()}")
        print("=" * 80)
        print()
        
        # Step 1: Authenticate
        if not self.authenticate():
            print("❌ AUTHENTICATION FAILED - Cannot proceed with tests")
            return False
        
        print("=" * 80)
        print("🧪 RUNNING PRODUCTION GATE P2 TESTS")
        print("=" * 80)
        print()
        
        # Step 2: Run all tests
        self.test_system_cross_check()
        self.test_analytics_cross_check()
        self.test_checks_history()
        self.test_checks_compare()
        self.test_timeline()
        self.test_history_cleanup()
        
        # Step 3: Generate summary
        self.generate_summary()
        
        return True

    def generate_summary(self):
        """Generate final test summary"""
        print("=" * 80)
        print("📊 PRODUCTION GATE P2 HARDENING TEST SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        passed_tests = len([t for t in self.test_results if t['status'] == 'PASS'])
        failed_tests = len([t for t in self.test_results if t['status'] == 'FAIL'])
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        print()
        
        # Overall result
        if failed_tests == 0:
            overall_result = "PASS"
            print("🎉 OVERALL RESULT: ✅ PASS")
            print("✅ All Production Gate P2 Hardening requirements validated successfully")
        else:
            overall_result = "FAIL"
            print("⚠️ OVERALL RESULT: ❌ FAIL")
            print(f"❌ {failed_tests} test(s) failed - see details above")
        
        print()
        print("📋 DETAILED FINDINGS:")
        print("-" * 40)
        
        for result in self.test_results:
            status_symbol = "✅" if result['status'] == 'PASS' else "❌"
            print(f"{status_symbol} {result['test']}: {result['status']}")
            if result['details']:
                print(f"   {result['details']}")
        
        print()
        print("=" * 80)
        print(f"🏁 PRODUCTION GATE P2 HARDENING VALIDATION: {overall_result}")
        print("=" * 80)
        
        # Save results to file
        results_file = "/app/production_gate_p2_test_results.json"
        try:
            with open(results_file, 'w') as f:
                json.dump({
                    'overall_result': overall_result,
                    'summary': {
                        'total_tests': total_tests,
                        'passed': passed_tests,
                        'failed': failed_tests,
                        'success_rate': f"{(passed_tests/total_tests)*100:.1f}%"
                    },
                    'test_results': self.test_results,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            print(f"📄 Detailed results saved to: {results_file}")
        except Exception as e:
            print(f"⚠️ Could not save results file: {e}")

def main():
    """Main execution function"""
    validator = ProductionGateP2Validator()
    success = validator.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()