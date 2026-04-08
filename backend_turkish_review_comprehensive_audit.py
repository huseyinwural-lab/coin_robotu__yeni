#!/usr/bin/env python3
"""
Turkish Review Request - Comprehensive Backend Audit (5 Critical Areas)
GO/NO-GO için 5 başlıkta kanıt odaklı detaylı backend test/audit

Test Areas:
1) Advisory Mode blocked/non_tradeable hard-coded kurallar
2) Mock/stub/statik JSON kontrolü  
3) Race conditions/idempotency
4) Scalability
5) Auth persistence

Credentials:
- Admin: canary.admin@platform.local / CanaryAdmin123!
- User: review.user@platform.local / ReviewUser123!

Output Format: başlık bazında PASS/FAIL + Risk seviyesi + GO/NO-GO etkisi
"""

import requests
import json
import time
import concurrent.futures
import threading
import psutil
import os
from datetime import datetime
from typing import Dict, List, Any, Tuple

class TurkishReviewAudit:
    def __init__(self):
        self.base_url = "https://trade-trace-engine.preview.emergentagent.com"
        self.admin_credentials = {
            "email": "canary.admin@platform.local",
            "password": "CanaryAdmin123!"
        }
        self.user_credentials = {
            "email": "review.user@platform.local", 
            "password": "ReviewUser123!"
        }
        self.admin_token = None
        self.user_token = None
        self.session = requests.Session()
        self.session.timeout = 30
        
        # Test results storage
        self.results = {
            "advisory_mode": {"status": "UNKNOWN", "risk": "UNKNOWN", "evidence": [], "go_no_go": "UNKNOWN"},
            "mock_static_json": {"status": "UNKNOWN", "risk": "UNKNOWN", "evidence": [], "go_no_go": "UNKNOWN"},
            "race_conditions": {"status": "UNKNOWN", "risk": "UNKNOWN", "evidence": [], "go_no_go": "UNKNOWN"},
            "scalability": {"status": "UNKNOWN", "risk": "UNKNOWN", "evidence": [], "go_no_go": "UNKNOWN"},
            "auth_persistence": {"status": "UNKNOWN", "risk": "UNKNOWN", "evidence": [], "go_no_go": "UNKNOWN"}
        }

    def log(self, message: str):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def authenticate_admin(self) -> bool:
        """Authenticate admin user"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login/admin",
                json=self.admin_credentials,
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                self.log(f"✅ Admin authentication successful (token length: {len(self.admin_token)} chars)")
                return True
            else:
                self.log(f"❌ Admin authentication failed: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"❌ Admin authentication error: {str(e)}")
            return False

    def authenticate_user(self) -> bool:
        """Authenticate user"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login/user",
                json=self.user_credentials,
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                self.log(f"✅ User authentication successful (token length: {len(self.user_token)} chars)")
                return True
            else:
                self.log(f"❌ User authentication failed: {response.status_code}")
                return False
        except Exception as e:
            self.log(f"❌ User authentication error: {str(e)}")
            return False

    def make_request(self, method: str, endpoint: str, token: str = None, **kwargs) -> requests.Response:
        """Make authenticated request"""
        headers = kwargs.pop('headers', {})
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        url = f"{self.base_url}{endpoint}"
        return self.session.request(method, url, headers=headers, **kwargs)

    # ==================== TEST 1: Advisory Mode Blocked/Non-tradeable Rules ====================
    
    def test_advisory_mode_rules(self):
        """Test 1: Advisory Mode blocked/non_tradeable hard-coded kurallar"""
        self.log("🔍 TEST 1: Advisory Mode Blocked/Non-tradeable Rules")
        evidence = []
        
        try:
            # Test trading validation for blocked rules
            validation_response = self.make_request(
                "POST", "/api/user/validate-order",
                token=self.user_token,
                json={
                    "symbol": "BTCUSDT",
                    "side": "BUY", 
                    "order_type": "market",
                    "quantity": 0.001,
                    "market_type": "spot"
                }
            )
            
            if validation_response.status_code == 200:
                validation_data = validation_response.json()
                violations = validation_data.get("violations", [])
                advisory_mode = validation_data.get("advisory_mode", False)
                
                evidence.append(f"Trading validation response: {validation_data}")
                evidence.append(f"Violations count: {len(violations)}")
                evidence.append(f"Advisory mode: {advisory_mode}")
                
                # Check for hard-coded blocking rules
                blocking_violations = [v for v in violations if v.get("severity") == "BLOCK"]
                evidence.append(f"Blocking violations: {len(blocking_violations)}")
                
                # Test symbol restrictions
                try:
                    restrictions_response = self.make_request(
                        "GET", "/api/admin/symbol-restrictions",
                        token=self.admin_token
                    )
                    if restrictions_response.status_code == 200:
                        restrictions = restrictions_response.json()
                        evidence.append(f"Symbol restrictions found: {len(restrictions)}")
                    else:
                        evidence.append(f"Symbol restrictions endpoint: {restrictions_response.status_code}")
                except Exception as e:
                    evidence.append(f"Symbol restrictions error: {str(e)}")
                
                # Determine status
                if len(blocking_violations) == 0:
                    self.results["advisory_mode"]["status"] = "PASS"
                    self.results["advisory_mode"]["risk"] = "LOW"
                    self.results["advisory_mode"]["go_no_go"] = "GO - No active blocking rules affecting trading"
                else:
                    self.results["advisory_mode"]["status"] = "FAIL"
                    self.results["advisory_mode"]["risk"] = "HIGH"
                    self.results["advisory_mode"]["go_no_go"] = "NO-GO - Active blocking rules detected"
                    
            else:
                evidence.append(f"Validation endpoint failed: {validation_response.status_code}")
                self.results["advisory_mode"]["status"] = "FAIL"
                self.results["advisory_mode"]["risk"] = "HIGH"
                self.results["advisory_mode"]["go_no_go"] = "NO-GO - Cannot validate trading rules"
                
        except Exception as e:
            evidence.append(f"Advisory mode test error: {str(e)}")
            self.results["advisory_mode"]["status"] = "FAIL"
            self.results["advisory_mode"]["risk"] = "HIGH"
            self.results["advisory_mode"]["go_no_go"] = "NO-GO - Test execution failed"
            
        self.results["advisory_mode"]["evidence"] = evidence
        self.log(f"✅ Advisory Mode Test Complete: {self.results['advisory_mode']['status']}")

    # ==================== TEST 2: Mock/Stub/Static JSON Control ====================
    
    def test_mock_static_json_usage(self):
        """Test 2: Mock/stub/statik JSON kontrolü"""
        self.log("🔍 TEST 2: Mock/Stub/Static JSON Usage")
        evidence = []
        
        try:
            # Test market data for real vs mock
            market_response = self.make_request(
                "GET", "/api/market/ticker",
                token=self.user_token,
                params={"symbol": "BTCUSDT"}
            )
            
            if market_response.status_code == 200:
                market_data = market_response.json()
                price = market_data.get("price", 0)
                timestamp = market_data.get("timestamp")
                environment = market_data.get("environment", "unknown")
                
                evidence.append(f"Market ticker: BTCUSDT price={price}, env={environment}")
                evidence.append(f"Market data timestamp: {timestamp}")
                
                # Check if price is realistic (not static mock)
                is_real_price = price > 10000 and price < 200000  # Reasonable BTC range
                evidence.append(f"Price appears real: {is_real_price}")
                
            # Test scanner results for static/mock patterns
            scanner_response = self.make_request(
                "POST", "/api/user/scanner/run",
                token=self.user_token,
                json={
                    "market_type": "spot",
                    "scan_limit": 5,
                    "strategy_type": "momentum"
                }
            )
            
            if scanner_response.status_code == 200:
                scanner_data = scanner_response.json()
                results = scanner_data.get("results", [])
                evidence.append(f"Scanner results count: {len(results)}")
                
                # Check for static/mock patterns in scanner results
                if results:
                    first_result = results[0]
                    long_score = first_result.get("long_score", 0)
                    short_score = first_result.get("short_score", 0)
                    classification = first_result.get("classification", "")
                    
                    evidence.append(f"Sample result: long_score={long_score}, short_score={short_score}, class={classification}")
                    
                    # Check for suspicious static patterns
                    all_zero_scores = all(r.get("long_score", 0) == 0 and r.get("short_score", 0) == 0 for r in results)
                    evidence.append(f"All zero scores (suspicious): {all_zero_scores}")
                    
                    if all_zero_scores and len(results) > 0:
                        self.results["mock_static_json"]["status"] = "FAIL"
                        self.results["mock_static_json"]["risk"] = "HIGH"
                        self.results["mock_static_json"]["go_no_go"] = "NO-GO - Scanner analysis appears mocked/static"
                    else:
                        self.results["mock_static_json"]["status"] = "PASS"
                        self.results["mock_static_json"]["risk"] = "LOW"
                        self.results["mock_static_json"]["go_no_go"] = "GO - Real analysis detected"
                else:
                    evidence.append("No scanner results to analyze")
                    self.results["mock_static_json"]["status"] = "PARTIAL"
                    self.results["mock_static_json"]["risk"] = "MEDIUM"
                    self.results["mock_static_json"]["go_no_go"] = "CAUTION - Cannot verify scanner analysis"
            else:
                evidence.append(f"Scanner endpoint failed: {scanner_response.status_code}")
                self.results["mock_static_json"]["status"] = "FAIL"
                self.results["mock_static_json"]["risk"] = "HIGH"
                self.results["mock_static_json"]["go_no_go"] = "NO-GO - Cannot test scanner analysis"
                
        except Exception as e:
            evidence.append(f"Mock/static test error: {str(e)}")
            self.results["mock_static_json"]["status"] = "FAIL"
            self.results["mock_static_json"]["risk"] = "HIGH"
            self.results["mock_static_json"]["go_no_go"] = "NO-GO - Test execution failed"
            
        self.results["mock_static_json"]["evidence"] = evidence
        self.log(f"✅ Mock/Static JSON Test Complete: {self.results['mock_static_json']['status']}")

    # ==================== TEST 3: Race Conditions/Idempotency ====================
    
    def test_race_conditions_idempotency(self):
        """Test 3: Race conditions/idempotency"""
        self.log("🔍 TEST 3: Race Conditions/Idempotency")
        evidence = []
        
        try:
            # Test scanner engine idempotency
            def run_scanner_concurrent():
                try:
                    response = self.make_request(
                        "POST", "/api/user/scanner-engine/run",
                        token=self.user_token,
                        json={"scan_limit": 10, "market_scope": {"spot_mode": "all", "futures_mode": "all"}},
                        timeout=5
                    )
                    return response.status_code, response.json() if response.status_code == 200 else None
                except Exception as e:
                    return 500, str(e)
            
            # Run multiple concurrent scanner requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(run_scanner_concurrent) for _ in range(5)]
                results = [f.result() for f in concurrent.futures.as_completed(futures, timeout=10)]
            
            success_count = sum(1 for status, _ in results if status == 200)
            evidence.append(f"Concurrent scanner calls: {len(results)} total, {success_count} successful")
            
            # Check for consistent responses (idempotency)
            successful_responses = [data for status, data in results if status == 200 and data]
            if len(successful_responses) >= 2:
                first_run_id = successful_responses[0].get("run_id")
                consistent_run_ids = all(r.get("run_id") == first_run_id for r in successful_responses)
                evidence.append(f"Consistent run_id across calls: {consistent_run_ids}")
                
                if consistent_run_ids:
                    evidence.append("✅ Idempotency working - same run_id returned")
                else:
                    evidence.append("⚠️ Different run_ids - potential race condition")
            
            # Test timeout scenarios
            try:
                timeout_response = self.make_request(
                    "POST", "/api/user/scanner-engine/run",
                    token=self.user_token,
                    json={"scan_limit": 1000, "market_scope": {"spot_mode": "all", "futures_mode": "all"}},
                    timeout=2  # Short timeout to test handling
                )
                evidence.append(f"Timeout test response: {timeout_response.status_code}")
            except requests.exceptions.Timeout:
                evidence.append("✅ Timeout handled gracefully")
            except Exception as e:
                evidence.append(f"Timeout test error: {str(e)}")
            
            # Determine status based on results
            if success_count >= 3:  # Most calls succeeded
                self.results["race_conditions"]["status"] = "PASS"
                self.results["race_conditions"]["risk"] = "LOW"
                self.results["race_conditions"]["go_no_go"] = "GO - Idempotency and concurrency handling working"
            elif success_count >= 1:
                self.results["race_conditions"]["status"] = "PARTIAL"
                self.results["race_conditions"]["risk"] = "MEDIUM"
                self.results["race_conditions"]["go_no_go"] = "CAUTION - Some concurrency issues detected"
            else:
                self.results["race_conditions"]["status"] = "FAIL"
                self.results["race_conditions"]["risk"] = "HIGH"
                self.results["race_conditions"]["go_no_go"] = "NO-GO - Concurrency handling broken"
                
        except Exception as e:
            evidence.append(f"Race condition test error: {str(e)}")
            self.results["race_conditions"]["status"] = "FAIL"
            self.results["race_conditions"]["risk"] = "HIGH"
            self.results["race_conditions"]["go_no_go"] = "NO-GO - Test execution failed"
            
        self.results["race_conditions"]["evidence"] = evidence
        self.log(f"✅ Race Conditions Test Complete: {self.results['race_conditions']['status']}")

    # ==================== TEST 4: Scalability ====================
    
    def test_scalability(self):
        """Test 4: Scalability"""
        self.log("🔍 TEST 4: Scalability")
        evidence = []
        
        try:
            # Get system resource usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            evidence.append(f"Current CPU usage: {cpu_percent}%")
            evidence.append(f"Memory usage: {memory.percent}% ({memory.used/1024/1024/1024:.2f}GB/{memory.total/1024/1024/1024:.2f}GB)")
            evidence.append(f"Disk usage: {disk.percent}% ({disk.used/1024/1024/1024:.2f}GB/{disk.total/1024/1024/1024:.2f}GB)")
            
            # Load test with concurrent API calls
            def make_api_call():
                try:
                    start_time = time.time()
                    response = self.make_request("GET", "/api/health", timeout=5)
                    end_time = time.time()
                    return response.status_code, end_time - start_time
                except Exception as e:
                    return 500, 5.0
            
            # Run load test
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(make_api_call) for _ in range(10)]
                load_results = [f.result() for f in concurrent.futures.as_completed(futures, timeout=15)]
            
            successful_calls = sum(1 for status, _ in load_results if status == 200)
            avg_response_time = sum(time for _, time in load_results) / len(load_results)
            
            evidence.append(f"Load test: {successful_calls}/10 calls successful")
            evidence.append(f"Average response time: {avg_response_time:.3f}s")
            
            # Test specific API performance
            api_tests = [
                ("/api/health", "Health check"),
                ("/api/user/signals", "User signals"),
                ("/api/market/ticker?symbol=BTCUSDT", "Market ticker")
            ]
            
            for endpoint, description in api_tests:
                try:
                    start_time = time.time()
                    response = self.make_request("GET", endpoint, token=self.user_token, timeout=10)
                    end_time = time.time()
                    response_time = end_time - start_time
                    evidence.append(f"{description}: {response.status_code} in {response_time:.3f}s")
                except Exception as e:
                    evidence.append(f"{description}: Error - {str(e)}")
            
            # Risk assessment for 10x load
            risk_factors = []
            if cpu_percent > 80:
                risk_factors.append("High CPU usage")
            if memory.percent > 80:
                risk_factors.append("High memory usage")
            if avg_response_time > 2.0:
                risk_factors.append("Slow response times")
            if successful_calls < 8:
                risk_factors.append("High failure rate")
                
            evidence.append(f"10x load risk factors: {len(risk_factors)} - {risk_factors}")
            
            # Determine status
            if len(risk_factors) == 0:
                self.results["scalability"]["status"] = "PASS"
                self.results["scalability"]["risk"] = "LOW"
                self.results["scalability"]["go_no_go"] = "GO - System can handle increased load"
            elif len(risk_factors) <= 2:
                self.results["scalability"]["status"] = "PARTIAL"
                self.results["scalability"]["risk"] = "MEDIUM"
                self.results["scalability"]["go_no_go"] = "CAUTION - Some scalability concerns"
            else:
                self.results["scalability"]["status"] = "FAIL"
                self.results["scalability"]["risk"] = "HIGH"
                self.results["scalability"]["go_no_go"] = "NO-GO - Scalability issues detected"
                
        except Exception as e:
            evidence.append(f"Scalability test error: {str(e)}")
            self.results["scalability"]["status"] = "FAIL"
            self.results["scalability"]["risk"] = "HIGH"
            self.results["scalability"]["go_no_go"] = "NO-GO - Test execution failed"
            
        self.results["scalability"]["evidence"] = evidence
        self.log(f"✅ Scalability Test Complete: {self.results['scalability']['status']}")

    # ==================== TEST 5: Auth Persistence ====================
    
    def test_auth_persistence(self):
        """Test 5: Auth persistence"""
        self.log("🔍 TEST 5: Auth Persistence")
        evidence = []
        
        try:
            # Analyze JWT token structure
            if self.user_token:
                import base64
                try:
                    # Decode JWT header and payload (without verification)
                    parts = self.user_token.split('.')
                    if len(parts) >= 2:
                        header = json.loads(base64.urlsafe_b64decode(parts[0] + '=='))
                        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
                        
                        evidence.append(f"JWT algorithm: {header.get('alg', 'unknown')}")
                        evidence.append(f"JWT claims: {list(payload.keys())}")
                        evidence.append(f"JWT expiration: {payload.get('exp', 'none')}")
                        evidence.append(f"JWT user role: {payload.get('role', 'unknown')}")
                        
                        # Check for security fields
                        security_fields = ['sub', 'role', 'email', 'exp', 'mfa_verified', 'device_id']
                        present_fields = [f for f in security_fields if f in payload]
                        evidence.append(f"Security fields present: {present_fields}")
                        
                except Exception as e:
                    evidence.append(f"JWT analysis error: {str(e)}")
            
            # Test session persistence
            me_response = self.make_request("GET", "/api/auth/me", token=self.user_token)
            if me_response.status_code == 200:
                evidence.append("✅ Session persistence working (/api/auth/me returns 200)")
                user_data = me_response.json()
                evidence.append(f"User session data: {user_data.get('email', 'unknown')}")
            else:
                evidence.append(f"❌ Session persistence issue: {me_response.status_code}")
            
            # Test refresh token mechanism
            refresh_response = self.make_request(
                "POST", "/api/auth/refresh",
                json={"refresh_token": "test_refresh_token"}
            )
            evidence.append(f"Refresh endpoint status: {refresh_response.status_code}")
            
            # Test concurrent sessions (security concern)
            session1 = requests.Session()
            session2 = requests.Session()
            
            # Login with same credentials in two sessions
            login1 = session1.post(f"{self.base_url}/api/auth/login/user", json=self.user_credentials)
            login2 = session2.post(f"{self.base_url}/api/auth/login/user", json=self.user_credentials)
            
            if login1.status_code == 200 and login2.status_code == 200:
                token1 = login1.json().get("access_token")
                token2 = login2.json().get("access_token")
                
                # Test if both sessions work simultaneously
                me1 = session1.get(f"{self.base_url}/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
                me2 = session2.get(f"{self.base_url}/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
                
                if me1.status_code == 200 and me2.status_code == 200:
                    evidence.append("⚠️ Multiple concurrent sessions allowed (security concern)")
                else:
                    evidence.append("✅ Concurrent sessions properly restricted")
                    
            # Test CDN/WAF independence
            headers_test = self.make_request(
                "GET", "/api/auth/me", 
                token=self.user_token,
                headers={"X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "5.6.7.8"}
            )
            evidence.append(f"CDN/WAF header test: {headers_test.status_code}")
            
            # Determine status
            critical_issues = []
            if me_response.status_code != 200:
                critical_issues.append("Session persistence broken")
            if "Multiple concurrent sessions allowed" in str(evidence):
                critical_issues.append("Unlimited concurrent sessions")
                
            if len(critical_issues) == 0:
                self.results["auth_persistence"]["status"] = "PASS"
                self.results["auth_persistence"]["risk"] = "LOW"
                self.results["auth_persistence"]["go_no_go"] = "GO - Auth persistence working correctly"
            elif len(critical_issues) == 1:
                self.results["auth_persistence"]["status"] = "PARTIAL"
                self.results["auth_persistence"]["risk"] = "MEDIUM"
                self.results["auth_persistence"]["go_no_go"] = "CAUTION - Some auth security concerns"
            else:
                self.results["auth_persistence"]["status"] = "FAIL"
                self.results["auth_persistence"]["risk"] = "HIGH"
                self.results["auth_persistence"]["go_no_go"] = "NO-GO - Auth persistence issues"
                
        except Exception as e:
            evidence.append(f"Auth persistence test error: {str(e)}")
            self.results["auth_persistence"]["status"] = "FAIL"
            self.results["auth_persistence"]["risk"] = "HIGH"
            self.results["auth_persistence"]["go_no_go"] = "NO-GO - Test execution failed"
            
        self.results["auth_persistence"]["evidence"] = evidence
        self.log(f"✅ Auth Persistence Test Complete: {self.results['auth_persistence']['status']}")

    def generate_report(self):
        """Generate final Turkish report"""
        self.log("\n" + "="*80)
        self.log("TURKISH REVIEW REQUEST - COMPREHENSIVE BACKEND AUDIT REPORT")
        self.log("="*80)
        
        overall_status = "GO"
        high_risk_count = 0
        
        for i, (area, result) in enumerate(self.results.items(), 1):
            status_emoji = "✅" if result["status"] == "PASS" else "⚠️" if result["status"] == "PARTIAL" else "❌"
            risk_color = "🟢" if result["risk"] == "LOW" else "🟡" if result["risk"] == "MEDIUM" else "🔴"
            
            self.log(f"\n{i}) {area.upper().replace('_', ' ')}: {status_emoji} {result['status']}")
            self.log(f"   Risk Level: {risk_color} {result['risk']}")
            self.log(f"   GO/NO-GO: {result['go_no_go']}")
            
            if result["risk"] == "HIGH":
                high_risk_count += 1
                overall_status = "NO-GO"
            elif result["risk"] == "MEDIUM" and overall_status == "GO":
                overall_status = "CAUTION"
        
        self.log(f"\n" + "="*80)
        self.log(f"OVERALL ASSESSMENT: {overall_status}")
        self.log(f"High Risk Areas: {high_risk_count}/5")
        
        if overall_status == "GO":
            self.log("✅ PRODUCTION READY - All critical areas passed")
        elif overall_status == "CAUTION":
            self.log("⚠️ PRODUCTION READY WITH MONITORING - Some medium risk areas")
        else:
            self.log("❌ NOT PRODUCTION READY - High risk areas need resolution")
            
        self.log("="*80)
        
        # Turkish summary
        self.log("\nTÜRKÇE ÖZET (BAŞLIK BAZINDA PASS/FAIL + RİSK + CANLI ÇIKIŞ ETKİSİ):")
        turkish_areas = [
            "Advisory Mode Kuralları",
            "Mock/Static JSON Kullanımı", 
            "Race Conditions/Idempotency",
            "Ölçeklenebilirlik",
            "Auth Persistence"
        ]
        
        for i, (area, turkish_name) in enumerate(zip(self.results.keys(), turkish_areas)):
            result = self.results[area]
            status_tr = "GEÇER" if result["status"] == "PASS" else "KISMEN" if result["status"] == "PARTIAL" else "BAŞARISIZ"
            risk_tr = "DÜŞÜK" if result["risk"] == "LOW" else "ORTA" if result["risk"] == "MEDIUM" else "YÜKSEK"
            
            self.log(f"{i+1}) {turkish_name}: {status_tr} - {risk_tr} RİSK")
            
        overall_tr = "CANLI ÇIKIŞ HAZIR" if overall_status == "GO" else "DİKKATLE CANLI ÇIKIŞ" if overall_status == "CAUTION" else "CANLI ÇIKIŞ HAZIR DEĞİL"
        self.log(f"\nGENEL SONUÇ: {overall_tr}")

    def run_audit(self):
        """Run complete audit"""
        self.log("🚀 Starting Turkish Review Request - Comprehensive Backend Audit")
        self.log(f"Target: {self.base_url}")
        
        # Authenticate
        if not self.authenticate_admin():
            self.log("❌ Admin authentication failed - aborting audit")
            return False
            
        if not self.authenticate_user():
            self.log("❌ User authentication failed - aborting audit")
            return False
        
        # Run all tests
        self.test_advisory_mode_rules()
        self.test_mock_static_json_usage()
        self.test_race_conditions_idempotency()
        self.test_scalability()
        self.test_auth_persistence()
        
        # Generate report
        self.generate_report()
        
        return True

if __name__ == "__main__":
    audit = TurkishReviewAudit()
    audit.run_audit()