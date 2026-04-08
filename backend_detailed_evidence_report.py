#!/usr/bin/env python3
"""
Turkish Review Request - Detailed Evidence Report
Detailed evidence extraction for the 5 critical areas
"""

import requests
import json
import time
import concurrent.futures
import psutil
from datetime import datetime

class DetailedEvidenceReport:
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

    def log(self, message: str):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def authenticate(self):
        """Authenticate both admin and user"""
        # Admin auth
        admin_response = self.session.post(
            f"{self.base_url}/api/auth/login/admin",
            json=self.admin_credentials,
            timeout=15
        )
        if admin_response.status_code == 200:
            self.admin_token = admin_response.json().get("access_token")
            self.log(f"✅ Admin authenticated (token: {len(self.admin_token)} chars)")
        
        # User auth
        user_response = self.session.post(
            f"{self.base_url}/api/auth/login/user",
            json=self.user_credentials,
            timeout=15
        )
        if user_response.status_code == 200:
            self.user_token = user_response.json().get("access_token")
            self.log(f"✅ User authenticated (token: {len(self.user_token)} chars)")
        
        return self.admin_token and self.user_token

    def make_request(self, method: str, endpoint: str, token: str = None, **kwargs):
        """Make authenticated request"""
        headers = kwargs.pop('headers', {})
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        url = f"{self.base_url}{endpoint}"
        return self.session.request(method, url, headers=headers, **kwargs)

    def detailed_evidence_collection(self):
        """Collect detailed evidence for all 5 areas"""
        
        self.log("🔍 DETAILED EVIDENCE COLLECTION")
        self.log("="*60)
        
        # 1. Advisory Mode Evidence
        self.log("\n1) ADVISORY MODE BLOCKED/NON-TRADEABLE RULES:")
        try:
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
                self.log(f"   ✅ Trading validation: {validation_data}")
                violations = validation_data.get("violations", [])
                self.log(f"   📊 Violations count: {len(violations)}")
                self.log(f"   📊 Advisory mode: {validation_data.get('advisory_mode', False)}")
                self.log(f"   📊 Execution mode: {validation_data.get('execution_mode', 'unknown')}")
                
                blocking_violations = [v for v in violations if v.get("severity") == "BLOCK"]
                self.log(f"   🚫 Blocking violations: {len(blocking_violations)}")
                if blocking_violations:
                    for violation in blocking_violations:
                        self.log(f"      - {violation}")
                else:
                    self.log("   ✅ No blocking violations found")
            else:
                self.log(f"   ❌ Validation failed: {validation_response.status_code}")
                
        except Exception as e:
            self.log(f"   ❌ Advisory mode test error: {str(e)}")

        # 2. Mock/Static JSON Evidence
        self.log("\n2) MOCK/STUB/STATIC JSON USAGE:")
        try:
            # Market data test
            market_response = self.make_request(
                "GET", "/api/market/ticker",
                token=self.user_token,
                params={"symbol": "BTCUSDT"}
            )
            
            if market_response.status_code == 200:
                market_data = market_response.json()
                self.log(f"   📈 Market ticker data: {market_data}")
                price = market_data.get("price", 0)
                self.log(f"   💰 BTCUSDT price: {price}")
                self.log(f"   🌍 Environment: {market_data.get('environment', 'unknown')}")
                self.log(f"   ⏰ Timestamp: {market_data.get('timestamp', 'none')}")
                
                # Check if price is realistic
                is_real_price = price > 10000 and price < 200000
                self.log(f"   ✅ Price appears real: {is_real_price}")
            else:
                self.log(f"   ❌ Market ticker failed: {market_response.status_code}")
            
            # Scanner test
            scanner_response = self.make_request(
                "POST", "/api/user/scanner/run",
                token=self.user_token,
                json={
                    "market_type": "spot",
                    "scan_limit": 3,
                    "strategy_type": "momentum"
                },
                timeout=15
            )
            
            if scanner_response.status_code == 200:
                scanner_data = scanner_response.json()
                results = scanner_data.get("results", [])
                self.log(f"   🔍 Scanner results count: {len(results)}")
                
                if results:
                    for i, result in enumerate(results[:2]):  # Show first 2 results
                        symbol = result.get("symbol", "unknown")
                        long_score = result.get("long_score", 0)
                        short_score = result.get("short_score", 0)
                        classification = result.get("classification", "")
                        self.log(f"   📊 Result {i+1}: {symbol} - long:{long_score}, short:{short_score}, class:{classification}")
                    
                    # Check for suspicious patterns
                    all_zero_scores = all(r.get("long_score", 0) == 0 and r.get("short_score", 0) == 0 for r in results)
                    self.log(f"   ⚠️ All zero scores (suspicious): {all_zero_scores}")
                    
                    if all_zero_scores:
                        self.log("   🚨 CRITICAL: Scanner analysis appears MOCKED/STATIC")
                    else:
                        self.log("   ✅ Scanner analysis appears REAL")
                else:
                    self.log("   ⚠️ No scanner results returned")
            else:
                self.log(f"   ❌ Scanner failed: {scanner_response.status_code}")
                if scanner_response.status_code == 500:
                    self.log("   🚨 CRITICAL: Scanner endpoint returning 500 errors")
                    
        except Exception as e:
            self.log(f"   ❌ Mock/static test error: {str(e)}")

        # 3. Race Conditions/Idempotency Evidence
        self.log("\n3) RACE CONDITIONS/IDEMPOTENCY:")
        try:
            # Test scanner engine idempotency
            def run_scanner_test():
                try:
                    response = self.make_request(
                        "POST", "/api/user/scanner-engine/run",
                        token=self.user_token,
                        json={"scan_limit": 10, "market_scope": {"spot_mode": "all", "futures_mode": "all"}},
                        timeout=3
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return response.status_code, data.get("run_id"), data.get("status")
                    else:
                        return response.status_code, None, None
                except Exception as e:
                    return 500, None, str(e)
            
            # Run concurrent tests
            self.log("   🔄 Running concurrent scanner engine tests...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(run_scanner_test) for _ in range(5)]
                results = []
                for f in concurrent.futures.as_completed(futures, timeout=10):
                    try:
                        results.append(f.result())
                    except Exception as e:
                        results.append((500, None, str(e)))
            
            success_count = sum(1 for status, _, _ in results if status == 200)
            self.log(f"   📊 Concurrent calls: {len(results)} total, {success_count} successful")
            
            # Show results
            for i, (status, run_id, scanner_status) in enumerate(results):
                self.log(f"   📋 Call {i+1}: HTTP {status}, run_id: {run_id}, status: {scanner_status}")
            
            # Check idempotency
            successful_run_ids = [run_id for status, run_id, _ in results if status == 200 and run_id]
            if len(successful_run_ids) >= 2:
                unique_run_ids = len(set(successful_run_ids))
                self.log(f"   🔄 Unique run_ids: {unique_run_ids} (idempotency check)")
                if unique_run_ids == 1:
                    self.log("   ✅ IDEMPOTENCY WORKING - Same run_id returned")
                else:
                    self.log("   ⚠️ POTENTIAL RACE CONDITION - Different run_ids")
            
            if success_count < 3:
                self.log("   🚨 CRITICAL: Concurrency handling issues detected")
                
        except Exception as e:
            self.log(f"   ❌ Race condition test error: {str(e)}")

        # 4. Scalability Evidence
        self.log("\n4) SCALABILITY:")
        try:
            # System resources
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            self.log(f"   💻 CPU usage: {cpu_percent}%")
            self.log(f"   🧠 Memory: {memory.percent}% ({memory.used/1024/1024/1024:.2f}GB/{memory.total/1024/1024/1024:.2f}GB)")
            self.log(f"   💾 Disk: {disk.percent}% ({disk.used/1024/1024/1024:.2f}GB/{disk.total/1024/1024/1024:.2f}GB)")
            
            # Load test
            def api_load_test():
                try:
                    start_time = time.time()
                    response = self.make_request("GET", "/api/health", timeout=5)
                    end_time = time.time()
                    return response.status_code, end_time - start_time
                except Exception:
                    return 500, 5.0
            
            self.log("   🔄 Running load test (10 concurrent calls)...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(api_load_test) for _ in range(10)]
                load_results = [f.result() for f in concurrent.futures.as_completed(futures, timeout=15)]
            
            successful_calls = sum(1 for status, _ in load_results if status == 200)
            avg_response_time = sum(time for _, time in load_results) / len(load_results)
            
            self.log(f"   📊 Load test results: {successful_calls}/10 successful")
            self.log(f"   ⏱️ Average response time: {avg_response_time:.3f}s")
            
            # API performance tests
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
                    self.log(f"   ⚡ {description}: {response.status_code} in {response_time:.3f}s")
                except Exception as e:
                    self.log(f"   ❌ {description}: Error - {str(e)}")
            
            # Risk assessment
            risk_factors = []
            if cpu_percent > 80:
                risk_factors.append("High CPU usage")
            if memory.percent > 80:
                risk_factors.append("High memory usage")
            if avg_response_time > 2.0:
                risk_factors.append("Slow response times")
            if successful_calls < 8:
                risk_factors.append("High failure rate")
                
            self.log(f"   ⚠️ 10x load risk factors: {len(risk_factors)} - {risk_factors}")
            
        except Exception as e:
            self.log(f"   ❌ Scalability test error: {str(e)}")

        # 5. Auth Persistence Evidence
        self.log("\n5) AUTH PERSISTENCE:")
        try:
            # JWT analysis
            if self.user_token:
                import base64
                try:
                    parts = self.user_token.split('.')
                    if len(parts) >= 2:
                        header = json.loads(base64.urlsafe_b64decode(parts[0] + '=='))
                        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
                        
                        self.log(f"   🔐 JWT algorithm: {header.get('alg', 'unknown')}")
                        self.log(f"   📋 JWT claims: {list(payload.keys())}")
                        self.log(f"   ⏰ JWT expiration: {payload.get('exp', 'none')}")
                        self.log(f"   👤 User role: {payload.get('role', 'unknown')}")
                        self.log(f"   📧 User email: {payload.get('email', 'unknown')}")
                        
                        # Security fields check
                        security_fields = ['sub', 'role', 'email', 'exp', 'mfa_verified', 'device_id']
                        present_fields = [f for f in security_fields if f in payload]
                        self.log(f"   🔒 Security fields: {present_fields}")
                        
                except Exception as e:
                    self.log(f"   ❌ JWT analysis error: {str(e)}")
            
            # Session persistence test
            me_response = self.make_request("GET", "/api/auth/me", token=self.user_token)
            self.log(f"   🔍 Session persistence test: {me_response.status_code}")
            if me_response.status_code == 200:
                user_data = me_response.json()
                self.log(f"   👤 Session user: {user_data.get('email', 'unknown')}")
                self.log("   ✅ Session persistence working")
            else:
                self.log("   ❌ Session persistence broken")
            
            # Refresh token test
            refresh_response = self.make_request(
                "POST", "/api/auth/refresh",
                json={"refresh_token": "test_refresh_token"}
            )
            self.log(f"   🔄 Refresh endpoint: {refresh_response.status_code}")
            
            # Concurrent sessions test (security concern)
            session1 = requests.Session()
            session2 = requests.Session()
            
            login1 = session1.post(f"{self.base_url}/api/auth/login/user", json=self.user_credentials)
            login2 = session2.post(f"{self.base_url}/api/auth/login/user", json=self.user_credentials)
            
            if login1.status_code == 200 and login2.status_code == 200:
                token1 = login1.json().get("access_token")
                token2 = login2.json().get("access_token")
                
                me1 = session1.get(f"{self.base_url}/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
                me2 = session2.get(f"{self.base_url}/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
                
                self.log(f"   🔄 Concurrent session 1: {me1.status_code}")
                self.log(f"   🔄 Concurrent session 2: {me2.status_code}")
                
                if me1.status_code == 200 and me2.status_code == 200:
                    self.log("   ⚠️ SECURITY CONCERN: Multiple concurrent sessions allowed")
                else:
                    self.log("   ✅ Concurrent sessions properly restricted")
            
            # CDN/WAF independence test
            headers_test = self.make_request(
                "GET", "/api/auth/me", 
                token=self.user_token,
                headers={"X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "5.6.7.8"}
            )
            self.log(f"   🌐 CDN/WAF independence: {headers_test.status_code}")
            
        except Exception as e:
            self.log(f"   ❌ Auth persistence test error: {str(e)}")

    def run_detailed_report(self):
        """Run detailed evidence collection"""
        self.log("🚀 TURKISH REVIEW REQUEST - DETAILED EVIDENCE COLLECTION")
        self.log(f"🎯 Target: {self.base_url}")
        self.log(f"👤 Admin: {self.admin_credentials['email']}")
        self.log(f"👤 User: {self.user_credentials['email']}")
        
        if not self.authenticate():
            self.log("❌ Authentication failed - aborting")
            return False
        
        self.detailed_evidence_collection()
        
        self.log("\n" + "="*60)
        self.log("📋 DETAILED EVIDENCE COLLECTION COMPLETE")
        self.log("="*60)
        
        return True

if __name__ == "__main__":
    report = DetailedEvidenceReport()
    report.run_detailed_report()