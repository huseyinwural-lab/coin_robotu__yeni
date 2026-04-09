#!/usr/bin/env python3
"""
Scanner Interval Feature Backend Test
Testing new auto_interval_minutes functionality per Turkish review request
"""

import requests
import json
import time
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

class ScannerIntervalTester:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.user_token = None
        self.results = []
        
    def log_result(self, test_name: str, status: str, details: str, response_data: Any = None):
        """Log test result"""
        result = {
            'test': test_name,
            'status': status,
            'details': details,
            'timestamp': datetime.now().isoformat(),
            'response_data': response_data
        }
        self.results.append(result)
        print(f"[{status}] {test_name}: {details}")
        
    def make_request(self, method: str, endpoint: str, token: str = None, **kwargs) -> requests.Response:
        """Make HTTP request with optional auth"""
        url = f"{self.base_url}{endpoint}"
        headers = kwargs.get('headers', {})
        
        if token:
            headers['Authorization'] = f'Bearer {token}'
            
        kwargs['headers'] = headers
        kwargs['timeout'] = kwargs.get('timeout', 30)
        
        try:
            response = self.session.request(method, url, **kwargs)
            return response
        except requests.exceptions.Timeout:
            raise Exception(f"Request timeout after 30s")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def test_user_login(self):
        """Test 1: User login with review.user@platform.local / ReviewUser123!"""
        try:
            login_data = {
                "email": "review.user@platform.local", 
                "password": "ReviewUser123!"
            }
            
            response = self.make_request('POST', '/api/auth/login/user', json=login_data)
            
            if response.status_code != 200:
                self.log_result("User Login", "FAIL", 
                              f"User login failed: HTTP {response.status_code}")
                return False
                
            login_result = response.json()
            self.user_token = login_result.get('access_token')
            
            if not self.user_token:
                self.log_result("User Login", "FAIL", 
                              "No access_token in user login response")
                return False
                
            self.log_result("User Login", "PASS", 
                          f"User login successful, token length: {len(self.user_token)} chars")
            return True
            
        except Exception as e:
            self.log_result("User Login", "FAIL", f"Exception: {str(e)}")
            return False

    def test_get_scanner_config_auto_interval(self):
        """Test 2: GET /api/user/scanner-engine/config - check auto_interval_minutes field"""
        if not self.user_token:
            self.log_result("GET Scanner Config", "SKIP", "No user token available")
            return False
            
        try:
            response = self.make_request('GET', '/api/user/scanner-engine/config', token=self.user_token)
            
            if response.status_code != 200:
                self.log_result("GET Scanner Config", "FAIL", 
                              f"GET config failed: HTTP {response.status_code}")
                return False
                
            config_data = response.json()
            
            # Check if auto_interval_minutes field exists
            if 'auto_interval_minutes' not in config_data:
                self.log_result("GET Scanner Config", "FAIL", 
                              "auto_interval_minutes field not found in config response")
                return False
                
            auto_interval_value = config_data.get('auto_interval_minutes')
            
            self.log_result("GET Scanner Config", "PASS", 
                          f"auto_interval_minutes field found with value: {auto_interval_value}")
            return True
            
        except Exception as e:
            self.log_result("GET Scanner Config", "FAIL", f"Exception: {str(e)}")
            return False

    def test_save_scanner_config_interval_1(self):
        """Test 3: POST /api/user/scanner-engine/config/save with auto_interval_minutes=1"""
        if not self.user_token:
            self.log_result("Save Config Interval=1", "SKIP", "No user token available")
            return False
            
        try:
            save_data = {
                "auto_interval_minutes": 1
            }
            
            response = self.make_request('POST', '/api/user/scanner-engine/config/save', 
                                       token=self.user_token, json=save_data)
            
            if response.status_code != 200:
                self.log_result("Save Config Interval=1", "FAIL", 
                              f"Save config failed: HTTP {response.status_code}")
                return False
                
            response_data = response.json()
            
            # Verify response contains config.auto_interval_minutes=1
            config = response_data.get('config', {})
            if config.get('auto_interval_minutes') != 1:
                self.log_result("Save Config Interval=1", "FAIL", 
                              f"Response config.auto_interval_minutes={config.get('auto_interval_minutes')}, expected 1")
                return False
                
            self.log_result("Save Config Interval=1", "PASS", 
                          f"Config saved successfully, response config.auto_interval_minutes=1")
            return True
            
        except Exception as e:
            self.log_result("Save Config Interval=1", "FAIL", f"Exception: {str(e)}")
            return False

    def test_scheduler_next_run_interval_1(self):
        """Test 4: GET /api/user/live/scheduler/next-run - verify auto_interval_minutes=1 and interval_seconds=60"""
        if not self.user_token:
            self.log_result("Scheduler Next Run Interval=1", "SKIP", "No user token available")
            return False
            
        try:
            response = self.make_request('GET', '/api/user/live/scheduler/next-run', token=self.user_token)
            
            if response.status_code != 200:
                self.log_result("Scheduler Next Run Interval=1", "FAIL", 
                              f"Scheduler next-run failed: HTTP {response.status_code}")
                return False
                
            scheduler_data = response.json()
            
            # Verify auto_interval_minutes=1
            auto_interval = scheduler_data.get('auto_interval_minutes')
            if auto_interval != 1:
                self.log_result("Scheduler Next Run Interval=1", "FAIL", 
                              f"auto_interval_minutes={auto_interval}, expected 1")
                return False
                
            # Verify interval_seconds=60
            interval_seconds = scheduler_data.get('interval_seconds')
            if interval_seconds != 60:
                self.log_result("Scheduler Next Run Interval=1", "FAIL", 
                              f"interval_seconds={interval_seconds}, expected 60")
                return False
                
            self.log_result("Scheduler Next Run Interval=1", "PASS", 
                          f"Scheduler verified: auto_interval_minutes=1, interval_seconds=60")
            return True
            
        except Exception as e:
            self.log_result("Scheduler Next Run Interval=1", "FAIL", f"Exception: {str(e)}")
            return False

    def test_save_scanner_config_interval_5(self):
        """Test 5: POST /api/user/scanner-engine/config/save with auto_interval_minutes=5"""
        if not self.user_token:
            self.log_result("Save Config Interval=5", "SKIP", "No user token available")
            return False
            
        try:
            save_data = {
                "auto_interval_minutes": 5
            }
            
            response = self.make_request('POST', '/api/user/scanner-engine/config/save', 
                                       token=self.user_token, json=save_data)
            
            if response.status_code != 200:
                self.log_result("Save Config Interval=5", "FAIL", 
                              f"Save config failed: HTTP {response.status_code}")
                return False
                
            response_data = response.json()
            
            # Verify response contains config.auto_interval_minutes=5
            config = response_data.get('config', {})
            if config.get('auto_interval_minutes') != 5:
                self.log_result("Save Config Interval=5", "FAIL", 
                              f"Response config.auto_interval_minutes={config.get('auto_interval_minutes')}, expected 5")
                return False
                
            self.log_result("Save Config Interval=5", "PASS", 
                          f"Config saved successfully, response config.auto_interval_minutes=5")
            return True
            
        except Exception as e:
            self.log_result("Save Config Interval=5", "FAIL", f"Exception: {str(e)}")
            return False

    def test_scheduler_next_run_interval_5(self):
        """Test 6: GET /api/user/live/scheduler/next-run - verify auto_interval_minutes=5 and interval_seconds=300"""
        if not self.user_token:
            self.log_result("Scheduler Next Run Interval=5", "SKIP", "No user token available")
            return False
            
        try:
            response = self.make_request('GET', '/api/user/live/scheduler/next-run', token=self.user_token)
            
            if response.status_code != 200:
                self.log_result("Scheduler Next Run Interval=5", "FAIL", 
                              f"Scheduler next-run failed: HTTP {response.status_code}")
                return False
                
            scheduler_data = response.json()
            
            # Verify auto_interval_minutes=5
            auto_interval = scheduler_data.get('auto_interval_minutes')
            if auto_interval != 5:
                self.log_result("Scheduler Next Run Interval=5", "FAIL", 
                              f"auto_interval_minutes={auto_interval}, expected 5")
                return False
                
            # Verify interval_seconds=300
            interval_seconds = scheduler_data.get('interval_seconds')
            if interval_seconds != 300:
                self.log_result("Scheduler Next Run Interval=5", "FAIL", 
                              f"interval_seconds={interval_seconds}, expected 300")
                return False
                
            self.log_result("Scheduler Next Run Interval=5", "PASS", 
                          f"Scheduler verified: auto_interval_minutes=5, interval_seconds=300")
            return True
            
        except Exception as e:
            self.log_result("Scheduler Next Run Interval=5", "FAIL", f"Exception: {str(e)}")
            return False

    def test_reset_scanner_config_interval_3(self):
        """Test 7: Reset auto_interval_minutes to 3 as requested"""
        if not self.user_token:
            self.log_result("Reset Config Interval=3", "SKIP", "No user token available")
            return False
            
        try:
            save_data = {
                "auto_interval_minutes": 3
            }
            
            response = self.make_request('POST', '/api/user/scanner-engine/config/save', 
                                       token=self.user_token, json=save_data)
            
            if response.status_code != 200:
                self.log_result("Reset Config Interval=3", "FAIL", 
                              f"Reset config failed: HTTP {response.status_code}")
                return False
                
            response_data = response.json()
            
            # Verify response contains config.auto_interval_minutes=3
            config = response_data.get('config', {})
            if config.get('auto_interval_minutes') != 3:
                self.log_result("Reset Config Interval=3", "FAIL", 
                              f"Response config.auto_interval_minutes={config.get('auto_interval_minutes')}, expected 3")
                return False
                
            self.log_result("Reset Config Interval=3", "PASS", 
                          f"Config reset successfully, auto_interval_minutes=3")
            return True
            
        except Exception as e:
            self.log_result("Reset Config Interval=3", "FAIL", f"Exception: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all scanner interval tests in sequence"""
        print("=== Scanner Interval Feature Backend Test Started ===")
        print(f"Base URL: {self.base_url}")
        print(f"User: review.user@platform.local / ReviewUser123!")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print()
        
        # Run tests in sequence
        tests = [
            self.test_user_login,
            self.test_get_scanner_config_auto_interval,
            self.test_save_scanner_config_interval_1,
            self.test_scheduler_next_run_interval_1,
            self.test_save_scanner_config_interval_5,
            self.test_scheduler_next_run_interval_5,
            self.test_reset_scanner_config_interval_3
        ]
        
        for test in tests:
            test()
            time.sleep(0.5)  # Brief pause between tests
        
        # Summary
        print("\n=== Test Summary ===")
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        failed = sum(1 for r in self.results if r['status'] == 'FAIL')
        skipped = sum(1 for r in self.results if r['status'] == 'SKIP')
        
        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Skipped: {skipped}")
        
        if len(self.results) - skipped > 0:
            success_rate = (passed / (len(self.results) - skipped)) * 100
            print(f"Success Rate: {success_rate:.1f}%")
        else:
            print("Success Rate: N/A")
        
        # Turkish summary as requested
        print("\n=== Turkish Summary ===")
        if failed == 0 and passed > 0:
            print("ÇIKTI: PASS")
        else:
            print("ÇIKTI: FAIL")
            
        print("Test Detayları:")
        for result in self.results:
            status_tr = "BAŞARILI" if result['status'] == 'PASS' else "BAŞARISIZ" if result['status'] == 'FAIL' else "ATLANDI"
            print(f"- {result['test']}: {status_tr}")
            
        if failed > 0:
            print("\nHata Detayları:")
            for result in self.results:
                if result['status'] == 'FAIL':
                    print(f"- {result['test']}: {result['details']}")
        
        return self.results

def main():
    base_url = "https://trade-trace-engine.preview.emergentagent.com"
    
    tester = ScannerIntervalTester(base_url)
    results = tester.run_all_tests()
    
    # Save results to file
    with open('/app/scanner_interval_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
        
    print(f"\nResults saved to /app/scanner_interval_test_results.json")

if __name__ == "__main__":
    main()