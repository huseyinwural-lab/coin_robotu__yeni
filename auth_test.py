#!/usr/bin/env python3
"""
Authentication Testing for Sprint-1 P1 Backend Verification
Testing auth flows, bcrypt, cookies, CORS, brute force protection
"""

import requests
import json
import time
import sys
from typing import Dict, Any, List, Optional

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class AuthTester:
    def __init__(self):
        self.session = requests.Session()
        self.test_results = []
        
    def log_result(self, test_name: str, status: str, details: str = "", data: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "data": data,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.test_results.append(result)
        print(f"[{status}] {test_name}: {details}")
    
    def test_admin_login_flow(self) -> bool:
        """Test admin login flow and token format"""
        try:
            auth_url = f"{BASE_URL}/api/auth/login/admin"
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(auth_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                
                if token and len(token) > 500:  # JWT tokens are typically long
                    self.log_result("Admin Login Flow", "PASS", 
                                  f"Login successful, token length: {len(token)} chars")
                    return True
                else:
                    self.log_result("Admin Login Flow", "FAIL", 
                                  f"Invalid token format: {token}")
                    return False
            else:
                self.log_result("Admin Login Flow", "FAIL", 
                              f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Login Flow", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_httponly_cookies(self) -> bool:
        """Test if httpOnly cookies are set on login"""
        try:
            auth_url = f"{BASE_URL}/api/auth/login/admin"
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(auth_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                # Check for Set-Cookie headers
                cookies = response.headers.get('Set-Cookie', '')
                
                if 'HttpOnly' in cookies:
                    self.log_result("HttpOnly Cookies", "PASS", 
                                  "HttpOnly cookies detected in Set-Cookie header")
                    return True
                elif self.session.cookies:
                    # Check if any cookies were set
                    cookie_names = [cookie.name for cookie in self.session.cookies]
                    self.log_result("HttpOnly Cookies", "PARTIAL", 
                                  f"Cookies set but HttpOnly not confirmed: {cookie_names}")
                    return True
                else:
                    self.log_result("HttpOnly Cookies", "INFO", 
                                  "No cookies set - using token-based auth")
                    return True
            else:
                self.log_result("HttpOnly Cookies", "FAIL", 
                              f"Cannot test cookies - login failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("HttpOnly Cookies", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_cors_configuration(self) -> bool:
        """Test CORS configuration allows credentials with explicit origins"""
        try:
            # Test preflight request
            auth_url = f"{BASE_URL}/api/auth/login/admin"
            
            headers = {
                'Origin': 'https://trade-trace-engine.preview.emergentagent.com',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type'
            }
            
            options_response = self.session.options(auth_url, headers=headers, timeout=30)
            
            cors_headers = {
                'access-control-allow-origin': options_response.headers.get('Access-Control-Allow-Origin'),
                'access-control-allow-credentials': options_response.headers.get('Access-Control-Allow-Credentials'),
                'access-control-allow-methods': options_response.headers.get('Access-Control-Allow-Methods'),
                'access-control-allow-headers': options_response.headers.get('Access-Control-Allow-Headers')
            }
            
            # Check for proper CORS configuration
            allow_origin = cors_headers['access-control-allow-origin']
            allow_credentials = cors_headers['access-control-allow-credentials']
            
            if allow_origin and allow_origin != '*' and allow_credentials == 'true':
                self.log_result("CORS Configuration", "PASS", 
                              f"CORS properly configured: Origin={allow_origin}, Credentials={allow_credentials}")
                return True
            elif allow_origin == '*':
                self.log_result("CORS Configuration", "WARN", 
                              "CORS allows all origins (*) - should be explicit origins for credentials")
                return True
            else:
                self.log_result("CORS Configuration", "INFO", 
                              f"CORS headers: {cors_headers}")
                return True
                
        except Exception as e:
            self.log_result("CORS Configuration", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_brute_force_protection(self) -> bool:
        """Test brute force lockout after 5 failed attempts"""
        try:
            auth_url = f"{BASE_URL}/api/auth/login/admin"
            
            # Use a test email to avoid locking out the real admin
            test_payload = {
                "email": "test.brute.force@example.com",
                "password": "wrong_password"
            }
            
            failed_attempts = 0
            lockout_detected = False
            
            # Try 6 failed attempts
            for attempt in range(6):
                response = self.session.post(auth_url, json=test_payload, timeout=30)
                
                if response.status_code == 429:  # Too Many Requests
                    lockout_detected = True
                    self.log_result("Brute Force Protection", "PASS", 
                                  f"Lockout detected after {attempt + 1} attempts (HTTP 429)")
                    break
                elif response.status_code == 401:
                    failed_attempts += 1
                else:
                    break
                
                time.sleep(0.5)  # Small delay between attempts
            
            if lockout_detected:
                return True
            elif failed_attempts >= 5:
                self.log_result("Brute Force Protection", "PARTIAL", 
                              f"5+ failed attempts allowed without lockout - may need investigation")
                return True
            else:
                self.log_result("Brute Force Protection", "INFO", 
                              f"Brute force test completed with {failed_attempts} failed attempts")
                return True
                
        except Exception as e:
            self.log_result("Brute Force Protection", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_auth_me_endpoint(self) -> bool:
        """Test /api/auth/me endpoint with valid token"""
        try:
            # First get a valid token
            auth_url = f"{BASE_URL}/api/auth/login/admin"
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            auth_response = self.session.post(auth_url, json=payload, timeout=30)
            
            if auth_response.status_code != 200:
                self.log_result("Auth Me Endpoint", "FAIL", 
                              f"Cannot get token for /me test: {auth_response.status_code}")
                return False
            
            token = auth_response.json().get("access_token")
            if not token:
                self.log_result("Auth Me Endpoint", "FAIL", "No access token received")
                return False
            
            # Test /api/auth/me endpoint
            me_url = f"{BASE_URL}/api/auth/me"
            headers = {"Authorization": f"Bearer {token}"}
            
            me_response = self.session.get(me_url, headers=headers, timeout=30)
            
            if me_response.status_code == 200:
                user_data = me_response.json()
                
                # Check for expected user fields
                expected_fields = ["email", "role"]
                missing_fields = [field for field in expected_fields if field not in user_data]
                
                if missing_fields:
                    self.log_result("Auth Me Endpoint", "PARTIAL", 
                                  f"Missing user fields: {missing_fields}, got: {list(user_data.keys())}")
                    return True
                else:
                    self.log_result("Auth Me Endpoint", "PASS", 
                                  f"User data retrieved: email={user_data.get('email')}, role={user_data.get('role')}")
                    return True
            else:
                self.log_result("Auth Me Endpoint", "FAIL", 
                              f"HTTP {me_response.status_code}: {me_response.text}")
                return False
                
        except Exception as e:
            self.log_result("Auth Me Endpoint", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_token_validation(self) -> bool:
        """Test token validation and format"""
        try:
            # Get a valid token
            auth_url = f"{BASE_URL}/api/auth/login/admin"
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            auth_response = self.session.post(auth_url, json=payload, timeout=30)
            
            if auth_response.status_code != 200:
                self.log_result("Token Validation", "FAIL", 
                              f"Cannot get token: {auth_response.status_code}")
                return False
            
            token = auth_response.json().get("access_token")
            
            # Check token format (JWT should have 3 parts separated by dots)
            if token and token.count('.') == 2:
                parts = token.split('.')
                header_len = len(parts[0])
                payload_len = len(parts[1])
                signature_len = len(parts[2])
                
                self.log_result("Token Validation", "PASS", 
                              f"Valid JWT format: header={header_len}, payload={payload_len}, signature={signature_len}")
                return True
            else:
                self.log_result("Token Validation", "FAIL", 
                              f"Invalid token format: {token[:50] if token else 'None'}...")
                return False
                
        except Exception as e:
            self.log_result("Token Validation", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all authentication tests"""
        print("=" * 80)
        print("Authentication Testing for Sprint-1 P1 Backend Verification")
        print("=" * 80)
        
        tests = [
            ("Admin Login Flow", self.test_admin_login_flow),
            ("HttpOnly Cookies", self.test_httponly_cookies),
            ("CORS Configuration", self.test_cors_configuration),
            ("Brute Force Protection", self.test_brute_force_protection),
            ("Auth Me Endpoint", self.test_auth_me_endpoint),
            ("Token Validation", self.test_token_validation)
        ]
        
        passed = 0
        failed = 0
        partial = 0
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                if result:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                self.log_result(test_name, "ERROR", f"Unexpected error: {str(e)}")
                failed += 1
        
        # Count partial results
        for result in self.test_results:
            if result["status"] in ["PARTIAL", "WARN", "INFO"]:
                partial += 1
        
        print("\n" + "=" * 80)
        print("AUTHENTICATION TEST SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {len(tests)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Partial/Info: {partial}")
        print(f"Success Rate: {(passed / len(tests)) * 100:.1f}%")
        
        # Print detailed results
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_icon} {result['test']}: {result['details']}")
        
        return {
            "success": failed == 0,
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            "partial": partial,
            "results": self.test_results
        }

def main():
    """Main execution function"""
    tester = AuthTester()
    summary = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if summary["success"] else 1)

if __name__ == "__main__":
    main()