#!/usr/bin/env python3
"""
Go/No-Go Backend Validation - Turkish Review Request
Rapor-only Go/No-Go backend doğrulaması (kod değişikliği yok).

Test Areas:
1) /api/user/scanner/status-contract ve /api/user/scanner-engine/last-run stabilitesi
2) /api/user/exchange-connections hata oranı (500 var mı)
3) /api/auth/refresh davranışı (device mismatch)
4) scanner run-async / run-async-both tamamlanma ve idempotency/job-state tutarlılığı
5) kısaca Go/No-Go backend verdict + blocker listesi
"""

import requests
import json
import time
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class GoNoGoValidator:
    def __init__(self):
        self.session = requests.Session()
        self.user_token = None
        self.admin_token = None
        self.refresh_token = None
        self.test_results = []
        self.blockers = []
        self.warnings = []
        
    def log_result(self, test_name, status, details, is_blocker=False):
        """Log test result"""
        result = {
            'test': test_name,
            'status': status,
            'details': details,
            'timestamp': datetime.now().isoformat(),
            'is_blocker': is_blocker
        }
        self.test_results.append(result)
        
        if is_blocker and status == 'FAIL':
            self.blockers.append(f"{test_name}: {details}")
        elif status == 'WARN':
            self.warnings.append(f"{test_name}: {details}")
            
        print(f"[{status}] {test_name}: {details}")
        
    def authenticate_user(self):
        """Authenticate user and get tokens"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                
                if self.user_token:
                    self.log_result("User Authentication", "PASS", 
                                  f"Successfully authenticated as {USER_EMAIL}")
                    return True
                else:
                    self.log_result("User Authentication", "FAIL", 
                                  "No access_token in response", is_blocker=True)
                    return False
            else:
                self.log_result("User Authentication", "FAIL", 
                              f"HTTP {response.status_code}: {response.text}", is_blocker=True)
                return False
                
        except Exception as e:
            self.log_result("User Authentication", "FAIL", 
                          f"Exception: {str(e)}", is_blocker=True)
            return False
    
    def authenticate_admin(self):
        """Authenticate admin"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get('access_token')
                
                if self.admin_token:
                    self.log_result("Admin Authentication", "PASS", 
                                  f"Successfully authenticated as {ADMIN_EMAIL}")
                    return True
                else:
                    self.log_result("Admin Authentication", "FAIL", 
                                  "No access_token in response", is_blocker=True)
                    return False
            else:
                self.log_result("Admin Authentication", "FAIL", 
                              f"HTTP {response.status_code}: {response.text}", is_blocker=True)
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", "FAIL", 
                          f"Exception: {str(e)}", is_blocker=True)
            return False

    def test_scanner_status_stability(self):
        """Test 1: Scanner status-contract ve scanner-engine/last-run stabilitesi"""
        print("\n=== TEST 1: Scanner Status Stability ===")
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        
        # Test scanner status-contract stability (multiple calls)
        try:
            status_responses = []
            for i in range(3):
                response = self.session.get(
                    f"{BASE_URL}/api/user/scanner/status-contract",
                    headers=headers,
                    timeout=30
                )
                status_responses.append({
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds(),
                    'call_number': i + 1
                })
                time.sleep(1)  # Brief pause between calls
            
            # Analyze stability
            status_codes = [r['status_code'] for r in status_responses]
            response_times = [r['response_time'] for r in status_responses]
            
            if all(code == 200 for code in status_codes):
                avg_time = sum(response_times) / len(response_times)
                max_time = max(response_times)
                
                if max_time > 10:  # More than 10 seconds is concerning
                    self.log_result("Scanner Status Contract Stability", "WARN", 
                                  f"Slow responses detected. Avg: {avg_time:.2f}s, Max: {max_time:.2f}s")
                else:
                    self.log_result("Scanner Status Contract Stability", "PASS", 
                                  f"Stable responses. Avg: {avg_time:.2f}s, Max: {max_time:.2f}s")
            else:
                self.log_result("Scanner Status Contract Stability", "FAIL", 
                              f"Inconsistent status codes: {status_codes}", is_blocker=True)
                
        except Exception as e:
            self.log_result("Scanner Status Contract Stability", "FAIL", 
                          f"Exception: {str(e)}", is_blocker=True)
        
        # Test scanner-engine/last-run
        try:
            response = self.session.get(
                f"{BASE_URL}/api/user/scanner-engine/last-run",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                # Check for required fields
                required_fields = ['status', 'last_run_at']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Scanner Engine Last Run", "WARN", 
                                  f"Missing fields: {missing_fields}")
                else:
                    self.log_result("Scanner Engine Last Run", "PASS", 
                                  f"Response OK with required fields")
            else:
                self.log_result("Scanner Engine Last Run", "FAIL", 
                              f"HTTP {response.status_code}: {response.text}", is_blocker=True)
                
        except Exception as e:
            self.log_result("Scanner Engine Last Run", "FAIL", 
                          f"Exception: {str(e)}", is_blocker=True)

    def test_exchange_connections_error_rate(self):
        """Test 2: Exchange connections hata oranı (500 var mı)"""
        print("\n=== TEST 2: Exchange Connections Error Rate ===")
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        
        try:
            # Test multiple calls to check for 500 errors
            error_count = 0
            total_calls = 5
            
            for i in range(total_calls):
                response = self.session.get(
                    f"{BASE_URL}/api/user/exchange-connections",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code >= 500:
                    error_count += 1
                    self.log_result(f"Exchange Connections Call {i+1}", "FAIL", 
                                  f"HTTP {response.status_code}: {response.text}")
                
                time.sleep(0.5)  # Brief pause between calls
            
            error_rate = (error_count / total_calls) * 100
            
            if error_count == 0:
                self.log_result("Exchange Connections Error Rate", "PASS", 
                              f"0% error rate (0/{total_calls} calls failed)")
            elif error_rate <= 20:  # Up to 20% might be acceptable
                self.log_result("Exchange Connections Error Rate", "WARN", 
                              f"{error_rate:.1f}% error rate ({error_count}/{total_calls} calls failed)")
            else:
                self.log_result("Exchange Connections Error Rate", "FAIL", 
                              f"{error_rate:.1f}% error rate ({error_count}/{total_calls} calls failed)", 
                              is_blocker=True)
                
        except Exception as e:
            self.log_result("Exchange Connections Error Rate", "FAIL", 
                          f"Exception: {str(e)}", is_blocker=True)

    def test_auth_refresh_behavior(self):
        """Test 3: Auth refresh davranışı (device mismatch)"""
        print("\n=== TEST 3: Auth Refresh Behavior ===")
        
        if not self.refresh_token:
            self.log_result("Auth Refresh Token Available", "FAIL", 
                          "No refresh token available from login", is_blocker=True)
            return
        
        # Test normal refresh
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/refresh",
                json={"refresh_token": self.refresh_token},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                new_access_token = data.get('access_token')
                new_refresh_token = data.get('refresh_token')
                
                if new_access_token and new_refresh_token:
                    self.log_result("Auth Refresh Normal", "PASS", 
                                  "Successfully refreshed tokens")
                    
                    # Update tokens for further tests
                    self.user_token = new_access_token
                    self.refresh_token = new_refresh_token
                else:
                    self.log_result("Auth Refresh Normal", "FAIL", 
                                  "Missing tokens in refresh response", is_blocker=True)
            else:
                self.log_result("Auth Refresh Normal", "FAIL", 
                              f"HTTP {response.status_code}: {response.text}", is_blocker=True)
                
        except Exception as e:
            self.log_result("Auth Refresh Normal", "FAIL", 
                          f"Exception: {str(e)}", is_blocker=True)
        
        # Test device mismatch scenario
        try:
            # Add a different device header to simulate device mismatch
            headers_with_device = {
                "X-Session-Device": "different-device-id-12345",
                "Content-Type": "application/json"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/refresh",
                json={"refresh_token": self.refresh_token},
                headers=headers_with_device,
                timeout=30
            )
            
            # Device mismatch should either work (if handled gracefully) or return specific error
            if response.status_code == 200:
                self.log_result("Auth Refresh Device Mismatch", "PASS", 
                              "Device mismatch handled gracefully")
            elif response.status_code == 401:
                # Check if it's a proper device mismatch error
                error_text = response.text.lower()
                if 'device' in error_text or 'mismatch' in error_text:
                    self.log_result("Auth Refresh Device Mismatch", "PASS", 
                                  "Device mismatch properly detected and rejected")
                else:
                    self.log_result("Auth Refresh Device Mismatch", "WARN", 
                                  f"401 but unclear if device-related: {response.text}")
            else:
                self.log_result("Auth Refresh Device Mismatch", "WARN", 
                              f"Unexpected response: HTTP {response.status_code}")
                
        except Exception as e:
            self.log_result("Auth Refresh Device Mismatch", "FAIL", 
                          f"Exception: {str(e)}")

    def test_scanner_run_async_idempotency(self):
        """Test 4: Scanner run-async / run-async-both tamamlanma ve idempotency"""
        print("\n=== TEST 4: Scanner Run Async Idempotency ===")
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        
        # Test run-async idempotency
        try:
            # First call
            response1 = self.session.post(
                f"{BASE_URL}/api/user/scanner-engine/run-async",
                json={"market_type": "spot", "scan_limit": 100},
                headers=headers,
                timeout=30
            )
            
            if response1.status_code == 200:
                data1 = response1.json()
                job_id1 = data1.get('job_id')
                
                if job_id1:
                    self.log_result("Scanner Run Async First Call", "PASS", 
                                  f"Job created: {job_id1}")
                    
                    # Immediate second call (should be idempotent)
                    response2 = self.session.post(
                        f"{BASE_URL}/api/user/scanner-engine/run-async",
                        json={"market_type": "spot", "scan_limit": 100},
                        headers=headers,
                        timeout=30
                    )
                    
                    if response2.status_code == 200:
                        data2 = response2.json()
                        job_id2 = data2.get('job_id')
                        
                        # Check idempotency behavior
                        if job_id1 == job_id2:
                            self.log_result("Scanner Run Async Idempotency", "PASS", 
                                          "Same job ID returned (idempotent)")
                        elif 'already_running' in str(data2).lower():
                            self.log_result("Scanner Run Async Idempotency", "PASS", 
                                          "Already running detected (idempotent)")
                        else:
                            self.log_result("Scanner Run Async Idempotency", "WARN", 
                                          f"Different job IDs: {job_id1} vs {job_id2}")
                    else:
                        self.log_result("Scanner Run Async Idempotency", "FAIL", 
                                      f"Second call failed: HTTP {response2.status_code}")
                    
                    # Check job status
                    time.sleep(2)  # Wait a bit for job to process
                    status_response = self.session.get(
                        f"{BASE_URL}/api/user/scanner-engine/run-async/{job_id1}",
                        headers=headers,
                        timeout=30
                    )
                    
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        job_status = status_data.get('status', 'unknown')
                        self.log_result("Scanner Job Status Check", "PASS", 
                                      f"Job status: {job_status}")
                    else:
                        self.log_result("Scanner Job Status Check", "WARN", 
                                      f"Status check failed: HTTP {status_response.status_code}")
                        
                else:
                    self.log_result("Scanner Run Async First Call", "FAIL", 
                                  "No job_id in response", is_blocker=True)
            else:
                self.log_result("Scanner Run Async First Call", "FAIL", 
                              f"HTTP {response1.status_code}: {response1.text}", is_blocker=True)
                
        except Exception as e:
            self.log_result("Scanner Run Async", "FAIL", 
                          f"Exception: {str(e)}", is_blocker=True)
        
        # Test run-async-both if available
        try:
            response = self.session.post(
                f"{BASE_URL}/api/user/scanner-engine/run-async-both",
                json={"scan_limit": 100},
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("Scanner Run Async Both", "PASS", 
                              f"Both markets scan initiated: {data}")
            elif response.status_code == 404:
                self.log_result("Scanner Run Async Both", "INFO", 
                              "Endpoint not available (404)")
            else:
                self.log_result("Scanner Run Async Both", "WARN", 
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Scanner Run Async Both", "WARN", 
                          f"Exception: {str(e)}")

    def generate_go_no_go_verdict(self):
        """Generate final Go/No-Go verdict"""
        print("\n" + "="*60)
        print("GO/NO-GO BACKEND VERDICT")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r['status'] == 'PASS'])
        failed_tests = len([r for r in self.test_results if r['status'] == 'FAIL'])
        warned_tests = len([r for r in self.test_results if r['status'] == 'WARN'])
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Warnings: {warned_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print(f"\nCRITICAL BLOCKERS: {len(self.blockers)}")
        for blocker in self.blockers:
            print(f"  ❌ {blocker}")
        
        print(f"\nWARNINGS: {len(self.warnings)}")
        for warning in self.warnings:
            print(f"  ⚠️ {warning}")
        
        # Determine verdict
        if len(self.blockers) == 0:
            if len(self.warnings) == 0:
                verdict = "✅ GO - All systems operational"
                risk_level = "LOW"
            elif len(self.warnings) <= 2:
                verdict = "✅ GO - Minor warnings acceptable"
                risk_level = "LOW-MEDIUM"
            else:
                verdict = "⚠️ CONDITIONAL GO - Multiple warnings need review"
                risk_level = "MEDIUM"
        else:
            verdict = "❌ NO-GO - Critical blockers detected"
            risk_level = "HIGH"
        
        print(f"\nFINAL VERDICT: {verdict}")
        print(f"RISK LEVEL: {risk_level}")
        
        # Turkish summary
        print(f"\nTÜRKÇE ÖZET:")
        print(f"Toplam Test: {total_tests}, Başarılı: {passed_tests}, Başarısız: {failed_tests}, Uyarı: {warned_tests}")
        print(f"Kritik Blokaj: {len(self.blockers)}, Uyarı: {len(self.warnings)}")
        print(f"Sonuç: {verdict}")
        print(f"Risk Seviyesi: {risk_level}")
        
        return len(self.blockers) == 0

    def run_all_tests(self):
        """Run all Go/No-Go validation tests"""
        print("Starting Go/No-Go Backend Validation...")
        print(f"Base URL: {BASE_URL}")
        print(f"User: {USER_EMAIL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print("="*60)
        
        # Authenticate
        if not self.authenticate_user():
            print("❌ User authentication failed - cannot proceed")
            return False
        
        if not self.authenticate_admin():
            print("⚠️ Admin authentication failed - some tests may be skipped")
        
        # Run tests
        self.test_scanner_status_stability()
        self.test_exchange_connections_error_rate()
        self.test_auth_refresh_behavior()
        self.test_scanner_run_async_idempotency()
        
        # Generate verdict
        return self.generate_go_no_go_verdict()

def main():
    validator = GoNoGoValidator()
    success = validator.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()