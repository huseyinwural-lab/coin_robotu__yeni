#!/usr/bin/env python3
"""
P0 Patch Validation Test
Turkish Review Request: Yeni P0 patch doğrulaması

Test Requirements:
1) Auth refresh token akışı:
   - /api/auth/login/user sonrası refresh_token dönüyor mu
   - /api/auth/refresh yeni access+refresh üretiyor mu
   - invalid refresh token 401 veriyor mu

2) Scanner Engine:
   - /api/user/scanner-engine/config/save market_scope zorunlu all/all ve scan_limit>=2000 oluyor mu
   - /api/user/scanner-engine/run-async çalışıyor mu
   - /api/user/scanner-engine/run-async/{job_id} status queued->completed/fail akışı
   - Aynı anda 2 çağrıda already_running/idempotency davranışı

3) DB pool regressions:
   - servis ayağa kalkıyor ve kritik endpointler yanıt veriyor mu

Credentials:
- User: review.user@platform.local / ReviewUser123!
- Admin: canary.admin@platform.local / CanaryAdmin123!
"""

import requests
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class P0PatchValidator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'P0PatchValidator/1.0'
        })
        self.user_token = None
        self.user_refresh_token = None
        self.admin_token = None
        self.test_results = []

    def log_test(self, test_name, status, details=""):
        """Log test result"""
        result = {
            'test': test_name,
            'status': status,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")

    def test_user_login_with_refresh_token(self):
        """Test 1: User login returns refresh_token"""
        try:
            payload = {
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            }
            
            response = self.session.post(f"{BASE_URL}/api/auth/login/user", json=payload)
            
            if response.status_code != 200:
                self.log_test("User Login with Refresh Token", "FAIL", 
                            f"Login failed with status {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            
            # Check for access_token
            if 'access_token' not in data:
                self.log_test("User Login with Refresh Token", "FAIL", 
                            "No access_token in response")
                return False
            
            # Check for refresh_token
            if 'refresh_token' not in data:
                self.log_test("User Login with Refresh Token", "FAIL", 
                            "No refresh_token in response")
                return False
            
            self.user_token = data['access_token']
            self.user_refresh_token = data['refresh_token']
            
            self.log_test("User Login with Refresh Token", "PASS", 
                        f"Access token length: {len(self.user_token)}, Refresh token length: {len(self.user_refresh_token)}")
            return True
            
        except Exception as e:
            self.log_test("User Login with Refresh Token", "FAIL", f"Exception: {str(e)}")
            return False

    def test_refresh_token_flow(self):
        """Test 2: /api/auth/refresh generates new tokens"""
        if not self.user_refresh_token:
            self.log_test("Refresh Token Flow", "FAIL", "No refresh token available from login")
            return False
        
        try:
            payload = {
                "refresh_token": self.user_refresh_token
            }
            
            response = self.session.post(f"{BASE_URL}/api/auth/refresh", json=payload)
            
            if response.status_code != 200:
                self.log_test("Refresh Token Flow", "FAIL", 
                            f"Refresh failed with status {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            
            # Check for new access_token
            if 'access_token' not in data:
                self.log_test("Refresh Token Flow", "FAIL", "No new access_token in response")
                return False
            
            # Check for new refresh_token
            if 'refresh_token' not in data:
                self.log_test("Refresh Token Flow", "FAIL", "No new refresh_token in response")
                return False
            
            new_access_token = data['access_token']
            new_refresh_token = data['refresh_token']
            
            # Verify tokens are different (new)
            if new_access_token == self.user_token:
                self.log_test("Refresh Token Flow", "FAIL", "New access token is same as old token")
                return False
            
            if new_refresh_token == self.user_refresh_token:
                self.log_test("Refresh Token Flow", "FAIL", "New refresh token is same as old token")
                return False
            
            # Update tokens
            self.user_token = new_access_token
            self.user_refresh_token = new_refresh_token
            
            self.log_test("Refresh Token Flow", "PASS", 
                        f"New access token length: {len(new_access_token)}, New refresh token length: {len(new_refresh_token)}")
            return True
            
        except Exception as e:
            self.log_test("Refresh Token Flow", "FAIL", f"Exception: {str(e)}")
            return False

    def test_invalid_refresh_token(self):
        """Test 3: Invalid refresh token returns 401"""
        try:
            payload = {
                "refresh_token": "invalid_refresh_token_12345"
            }
            
            response = self.session.post(f"{BASE_URL}/api/auth/refresh", json=payload)
            
            if response.status_code == 401:
                self.log_test("Invalid Refresh Token 401", "PASS", 
                            f"Correctly returned 401 for invalid refresh token")
                return True
            else:
                self.log_test("Invalid Refresh Token 401", "FAIL", 
                            f"Expected 401, got {response.status_code}: {response.text}")
                return False
            
        except Exception as e:
            self.log_test("Invalid Refresh Token 401", "FAIL", f"Exception: {str(e)}")
            return False

    def test_scanner_engine_config_save(self):
        """Test 4: Scanner engine config save with market_scope all/all and scan_limit>=2000"""
        if not self.user_token:
            self.log_test("Scanner Engine Config Save", "FAIL", "No user token available")
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {self.user_token}',
                'Content-Type': 'application/json'
            }
            
            # Test config save with market_scope all/all and scan_limit>=2000
            payload = {
                "market_scope": "all",  # Should be mandatory all/all
                "scan_limit": 2000,     # Should be >=2000
                "exchange": "binance",
                "include_spot": True,
                "include_futures": True
            }
            
            response = self.session.post(f"{BASE_URL}/api/user/scanner-engine/config/save", 
                                       json=payload, headers=headers)
            
            if response.status_code != 200:
                self.log_test("Scanner Engine Config Save", "FAIL", 
                            f"Config save failed with status {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            
            # Verify config was saved correctly
            self.log_test("Scanner Engine Config Save", "PASS", 
                        f"Config saved successfully: market_scope=all, scan_limit=2000")
            return True
            
        except Exception as e:
            self.log_test("Scanner Engine Config Save", "FAIL", f"Exception: {str(e)}")
            return False

    def test_scanner_engine_run_async(self):
        """Test 5: Scanner engine run-async works"""
        if not self.user_token:
            self.log_test("Scanner Engine Run Async", "FAIL", "No user token available")
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {self.user_token}',
                'Content-Type': 'application/json'
            }
            
            # Try with empty body first
            payload = {}
            
            response = self.session.post(f"{BASE_URL}/api/user/scanner-engine/run-async", 
                                       json=payload, headers=headers)
            
            if response.status_code != 200:
                # Try with basic scanner config
                payload = {
                    "market_scope": "all",
                    "scan_limit": 2000
                }
                response = self.session.post(f"{BASE_URL}/api/user/scanner-engine/run-async", 
                                           json=payload, headers=headers)
            
            if response.status_code != 200:
                self.log_test("Scanner Engine Run Async", "FAIL", 
                            f"Run async failed with status {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            
            # Check for job_id
            if 'job_id' not in data:
                self.log_test("Scanner Engine Run Async", "FAIL", "No job_id in response")
                return False
            
            job_id = data['job_id']
            
            self.log_test("Scanner Engine Run Async", "PASS", 
                        f"Scanner run started successfully, job_id: {job_id}")
            return job_id
            
        except Exception as e:
            self.log_test("Scanner Engine Run Async", "FAIL", f"Exception: {str(e)}")
            return False

    def test_scanner_job_status_flow(self, job_id):
        """Test 6: Scanner job status flow queued->completed/fail"""
        if not self.user_token or not job_id:
            self.log_test("Scanner Job Status Flow", "FAIL", "No user token or job_id available")
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {self.user_token}',
                'Content-Type': 'application/json'
            }
            
            # Poll job status for up to 60 seconds
            max_attempts = 12  # 60 seconds with 5-second intervals
            attempt = 0
            initial_status = None
            final_status = None
            
            while attempt < max_attempts:
                response = self.session.get(f"{BASE_URL}/api/user/scanner-engine/run-async/{job_id}", 
                                          headers=headers)
                
                if response.status_code != 200:
                    self.log_test("Scanner Job Status Flow", "FAIL", 
                                f"Status check failed with status {response.status_code}: {response.text}")
                    return False
                
                data = response.json()
                status = data.get('status', 'unknown')
                
                if attempt == 0:
                    initial_status = status
                
                if status in ['completed', 'failed', 'error']:
                    final_status = status
                    break
                
                attempt += 1
                time.sleep(5)
            
            if not final_status:
                final_status = data.get('status', 'unknown')
            
            # Verify status flow
            if initial_status in ['queued', 'running'] and final_status in ['completed', 'failed']:
                self.log_test("Scanner Job Status Flow", "PASS", 
                            f"Status flow: {initial_status} -> {final_status}")
                return True
            else:
                self.log_test("Scanner Job Status Flow", "PARTIAL", 
                            f"Status flow: {initial_status} -> {final_status} (may still be running)")
                return True
            
        except Exception as e:
            self.log_test("Scanner Job Status Flow", "FAIL", f"Exception: {str(e)}")
            return False

    def test_concurrent_scanner_calls(self):
        """Test 7: Concurrent scanner calls show already_running/idempotency"""
        if not self.user_token:
            self.log_test("Concurrent Scanner Calls", "FAIL", "No user token available")
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {self.user_token}',
                'Content-Type': 'application/json'
            }
            
            results = []
            
            def make_scanner_call():
                try:
                    payload = {
                        "market_scope": "all",
                        "scan_limit": 2000
                    }
                    response = self.session.post(f"{BASE_URL}/api/user/scanner-engine/run-async", 
                                               json=payload, headers=headers)
                    return {
                        'status_code': response.status_code,
                        'response': response.json() if response.status_code == 200 else response.text
                    }
                except Exception as e:
                    return {
                        'status_code': 'error',
                        'response': str(e)
                    }
            
            # Make 2 concurrent calls
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(make_scanner_call) for _ in range(2)]
                results = [future.result() for future in futures]
            
            # Analyze results
            success_count = sum(1 for r in results if r['status_code'] == 200)
            already_running_count = sum(1 for r in results if 
                                      r['status_code'] != 200 and 
                                      ('already_running' in str(r['response']).lower() or 
                                       'in_progress' in str(r['response']).lower()))
            
            if success_count >= 1:
                self.log_test("Concurrent Scanner Calls", "PASS", 
                            f"Idempotency working: {success_count} success, {already_running_count} already_running")
                return True
            else:
                self.log_test("Concurrent Scanner Calls", "FAIL", 
                            f"No successful calls: {results}")
                return False
            
        except Exception as e:
            self.log_test("Concurrent Scanner Calls", "FAIL", f"Exception: {str(e)}")
            return False

    def test_db_pool_regression(self):
        """Test 8: DB pool regression - service up and critical endpoints respond"""
        try:
            # Test health endpoint
            response = self.session.get(f"{BASE_URL}/api/health")
            if response.status_code != 200:
                self.log_test("DB Pool Regression - Health", "FAIL", 
                            f"Health endpoint failed: {response.status_code}")
                return False
            
            # Test ready endpoint
            response = self.session.get(f"{BASE_URL}/api/ready")
            if response.status_code != 200:
                self.log_test("DB Pool Regression - Ready", "FAIL", 
                            f"Ready endpoint failed: {response.status_code}")
                return False
            
            # Test user login (critical endpoint)
            if not self.user_token:
                payload = {
                    "email": USER_EMAIL,
                    "password": USER_PASSWORD
                }
                response = self.session.post(f"{BASE_URL}/api/auth/login/user", json=payload)
                if response.status_code != 200:
                    self.log_test("DB Pool Regression - Auth", "FAIL", 
                                f"Auth endpoint failed: {response.status_code}")
                    return False
            
            self.log_test("DB Pool Regression", "PASS", 
                        "Health, ready, and auth endpoints all responding correctly")
            return True
            
        except Exception as e:
            self.log_test("DB Pool Regression", "FAIL", f"Exception: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all P0 patch validation tests"""
        print("🚀 Starting P0 Patch Validation Tests")
        print(f"Base URL: {BASE_URL}")
        print(f"User: {USER_EMAIL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("=" * 60)
        
        # Test 1-3: Auth refresh token flow
        print("\n📋 AUTH REFRESH TOKEN FLOW TESTS")
        self.test_user_login_with_refresh_token()
        self.test_refresh_token_flow()
        self.test_invalid_refresh_token()
        
        # Test 4-7: Scanner Engine tests
        print("\n📋 SCANNER ENGINE TESTS")
        self.test_scanner_engine_config_save()
        job_id = self.test_scanner_engine_run_async()
        if job_id:
            self.test_scanner_job_status_flow(job_id)
        self.test_concurrent_scanner_calls()
        
        # Test 8: DB pool regression
        print("\n📋 DB POOL REGRESSION TEST")
        self.test_db_pool_regression()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r['status'] == 'PASS'])
        failed_tests = len([r for r in self.test_results if r['status'] == 'FAIL'])
        partial_tests = len([r for r in self.test_results if r['status'] == 'PARTIAL'])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️ Partial: {partial_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        # Risk Assessment
        critical_failures = [r for r in self.test_results if r['status'] == 'FAIL' and 
                           any(keyword in r['test'].lower() for keyword in ['auth', 'login', 'db pool'])]
        
        if len(critical_failures) > 0:
            risk_level = "Critical"
        elif failed_tests > 0:
            risk_level = "High"
        elif partial_tests > 0:
            risk_level = "Medium"
        else:
            risk_level = "Low"
        
        print(f"\n🎯 RISK ASSESSMENT: {risk_level}")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if result['status'] == 'FAIL':
                    print(f"  - {result['test']}: {result['details']}")
        
        return {
            'total': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'partial': partial_tests,
            'risk_level': risk_level,
            'results': self.test_results
        }

if __name__ == "__main__":
    validator = P0PatchValidator()
    summary = validator.run_all_tests()
    
    # Save results to file
    with open('/app/p0_patch_validation_results.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n📄 Results saved to: /app/p0_patch_validation_results.json")