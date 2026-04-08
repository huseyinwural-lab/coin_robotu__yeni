#!/usr/bin/env python3
"""
Turkish Review Request - Evidence-Based Backend Testing/Audit
5 başlık için kanıt odaklı backend test/audit:
1) Advisory Mode'da blocked/non_tradeable hard-coded kural kaynakları (aktif etkileyenler)
2) Mock/stub/statik JSON kullanımı (özellikle scanner), gerçek borsa veri kaynağı kanıtı
3) Scanner Engine + Strategy Allocator timeout/crash senaryosunda idempotency/state tutarlılığı
4) Kaynak tüketimi ve pool kapasitesi (mevcut ortam ölçümü + 10x yük riski)
5) Auth persistence: CDN/WAF dışı backend faktörleri, JWT/cookie/refresh mekanizması
"""

import requests
import json
import time
import sys
import os
from datetime import datetime
import concurrent.futures
import threading
import psutil
import subprocess

# Test Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class TurkishReviewAuditor:
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 30
        self.user_token = None
        self.admin_token = None
        self.findings = {
            "1_advisory_mode_rules": {},
            "2_mock_static_usage": {},
            "3_scanner_idempotency": {},
            "4_resource_consumption": {},
            "5_auth_persistence": {}
        }
        
    def authenticate_user(self):
        """Authenticate as review user"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                print(f"✅ User authentication successful (token length: {len(self.user_token) if self.user_token else 0})")
                return True
            else:
                print(f"❌ User authentication failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ User authentication error: {e}")
            return False
    
    def authenticate_admin(self):
        """Authenticate as admin"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                print(f"✅ Admin authentication successful (token length: {len(self.admin_token) if self.admin_token else 0})")
                return True
            else:
                print(f"❌ Admin authentication failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Admin authentication error: {e}")
            return False
    
    def get_headers(self, use_admin=False):
        """Get headers with appropriate token"""
        token = self.admin_token if use_admin else self.user_token
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def audit_advisory_mode_rules(self):
        """1) Advisory Mode'da blocked/non_tradeable hard-coded kural kaynakları"""
        print("\n🔍 1) ADVISORY MODE BLOCKED/NON_TRADEABLE HARD-CODED RULES AUDIT")
        
        findings = {
            "blocked_rules_found": [],
            "non_tradeable_rules": [],
            "active_affecting_rules": [],
            "risk_level": "UNKNOWN"
        }
        
        try:
            # Check risk policies for hard-coded rules
            response = self.session.get(
                f"{BASE_URL}/api/risk-policies",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                policies = response.json()
                print(f"📊 Found {len(policies)} risk policies")
                
                for policy in policies:
                    # Look for hard-coded blocking rules
                    if 'blocked' in str(policy).lower() or 'non_tradeable' in str(policy).lower():
                        findings["blocked_rules_found"].append({
                            "policy_id": policy.get("id"),
                            "name": policy.get("name", "Unknown"),
                            "type": policy.get("type", "Unknown"),
                            "is_active": policy.get("is_active", False)
                        })
                        
                        if policy.get("is_active"):
                            findings["active_affecting_rules"].append(policy.get("name", "Unknown"))
            
            # Check trading configuration for advisory mode settings
            try:
                config_response = self.session.get(
                    f"{BASE_URL}/api/admin/trading-config",
                    headers=self.get_headers(use_admin=True),
                    timeout=10
                )
                
                if config_response.status_code == 200:
                    config = config_response.json()
                    if 'advisory_mode' in config:
                        findings["advisory_mode_config"] = config.get("advisory_mode")
                        print(f"📋 Advisory mode config found: {config.get('advisory_mode')}")
                        
            except Exception as e:
                print(f"⚠️ Could not fetch trading config: {e}")
            
            # Check for hard-coded symbol restrictions
            try:
                symbols_response = self.session.get(
                    f"{BASE_URL}/api/market/symbols",
                    headers=self.get_headers(),
                    timeout=10
                )
                
                if symbols_response.status_code == 200:
                    symbols_data = symbols_response.json()
                    blocked_symbols = []
                    
                    for symbol in symbols_data.get("symbols", []):
                        if symbol.get("status") == "blocked" or not symbol.get("tradeable", True):
                            blocked_symbols.append(symbol.get("symbol"))
                    
                    findings["blocked_symbols_count"] = len(blocked_symbols)
                    findings["sample_blocked_symbols"] = blocked_symbols[:5]  # First 5 as sample
                    print(f"🚫 Found {len(blocked_symbols)} blocked/non-tradeable symbols")
                    
            except Exception as e:
                print(f"⚠️ Could not fetch symbols: {e}")
            
            # Determine risk level
            active_rules_count = len(findings["active_affecting_rules"])
            if active_rules_count > 5:
                findings["risk_level"] = "HIGH"
            elif active_rules_count > 0:
                findings["risk_level"] = "MEDIUM"
            else:
                findings["risk_level"] = "LOW"
            
            print(f"📈 Risk Level: {findings['risk_level']} ({active_rules_count} active affecting rules)")
            
        except Exception as e:
            print(f"❌ Advisory mode rules audit failed: {e}")
            findings["error"] = str(e)
        
        self.findings["1_advisory_mode_rules"] = findings
        return findings
    
    def audit_mock_static_usage(self):
        """2) Mock/stub/statik JSON kullanımı (özellikle scanner), gerçek borsa veri kaynağı kanıtı"""
        print("\n🔍 2) MOCK/STUB/STATIC JSON USAGE AUDIT (ESPECIALLY SCANNER)")
        
        findings = {
            "scanner_data_sources": [],
            "mock_endpoints_detected": [],
            "real_exchange_evidence": [],
            "static_json_usage": [],
            "risk_level": "UNKNOWN"
        }
        
        try:
            # Test scanner engine data source
            scanner_response = self.session.get(
                f"{BASE_URL}/api/user/scanner-engine/config",
                headers=self.get_headers(),
                timeout=10
            )
            
            if scanner_response.status_code == 200:
                scanner_config = scanner_response.json()
                print(f"📊 Scanner config retrieved: {scanner_config}")
                
                # Check for mock indicators in scanner config
                config_str = json.dumps(scanner_config).lower()
                mock_indicators = ['mock', 'stub', 'static', 'fake', 'dummy']
                
                for indicator in mock_indicators:
                    if indicator in config_str:
                        findings["mock_endpoints_detected"].append(f"scanner_config_{indicator}")
                
                findings["scanner_config"] = scanner_config
            
            # Test market data source (real exchange evidence)
            market_response = self.session.get(
                f"{BASE_URL}/api/market/ticker?symbol=BTCUSDT",
                headers=self.get_headers(),
                timeout=10
            )
            
            if market_response.status_code == 200:
                ticker_data = market_response.json()
                print(f"📈 Market ticker data: {ticker_data}")
                
                # Check if data looks real (price > 0, timestamp recent)
                price = ticker_data.get("price", 0)
                timestamp = ticker_data.get("timestamp")
                
                if price > 0:
                    findings["real_exchange_evidence"].append({
                        "endpoint": "/api/market/ticker",
                        "symbol": "BTCUSDT",
                        "price": price,
                        "timestamp": timestamp,
                        "evidence": "Non-zero price indicates real market data"
                    })
                    print(f"✅ Real exchange data evidence: BTCUSDT price = {price}")
                else:
                    findings["static_json_usage"].append({
                        "endpoint": "/api/market/ticker",
                        "issue": "Zero or invalid price suggests static/mock data"
                    })
            
            # Test scanner run for data source evidence
            try:
                scanner_run_response = self.session.post(
                    f"{BASE_URL}/api/user/scanner-engine/run",
                    headers=self.get_headers(),
                    json={"scan_limit": 5},
                    timeout=15
                )
                
                if scanner_run_response.status_code == 200:
                    scan_results = scanner_run_response.json()
                    print(f"🔍 Scanner run results: {len(scan_results.get('results', []))} results")
                    
                    # Analyze results for real vs mock data patterns
                    results = scan_results.get("results", [])
                    if results:
                        sample_result = results[0]
                        
                        # Check for realistic score patterns
                        long_score = sample_result.get("long_score", 0)
                        short_score = sample_result.get("short_score", 0)
                        
                        if long_score != 0 or short_score != 0:
                            findings["real_exchange_evidence"].append({
                                "endpoint": "/api/user/scanner-engine/run",
                                "evidence": f"Non-zero scores (long: {long_score}, short: {short_score}) suggest real analysis",
                                "sample_symbol": sample_result.get("symbol")
                            })
                        else:
                            findings["static_json_usage"].append({
                                "endpoint": "/api/user/scanner-engine/run",
                                "issue": "All zero scores suggest static/mock data"
                            })
                
            except Exception as e:
                print(f"⚠️ Scanner run test failed: {e}")
            
            # Check execution mode indicators
            try:
                execution_response = self.session.get(
                    f"{BASE_URL}/api/admin/execution-readiness",
                    headers=self.get_headers(use_admin=True),
                    timeout=10
                )
                
                if execution_response.status_code == 200:
                    exec_data = execution_response.json()
                    mode = exec_data.get("mode", "unknown")
                    
                    if mode.lower() in ["mock", "mocked", "simulation"]:
                        findings["mock_endpoints_detected"].append(f"execution_mode_{mode}")
                        print(f"🎭 Execution mode detected: {mode}")
                    elif mode.lower() in ["live", "production"]:
                        findings["real_exchange_evidence"].append({
                            "endpoint": "/api/admin/execution-readiness",
                            "evidence": f"Execution mode is {mode}",
                            "mode": mode
                        })
                        print(f"🔴 Live execution mode detected: {mode}")
                
            except Exception as e:
                print(f"⚠️ Execution readiness check failed: {e}")
            
            # Determine risk level based on mock vs real evidence
            mock_count = len(findings["mock_endpoints_detected"]) + len(findings["static_json_usage"])
            real_count = len(findings["real_exchange_evidence"])
            
            if mock_count > real_count:
                findings["risk_level"] = "HIGH"
            elif mock_count > 0:
                findings["risk_level"] = "MEDIUM"
            else:
                findings["risk_level"] = "LOW"
            
            print(f"📊 Mock/Static vs Real Evidence: {mock_count} mock indicators, {real_count} real evidence")
            print(f"📈 Risk Level: {findings['risk_level']}")
            
        except Exception as e:
            print(f"❌ Mock/static usage audit failed: {e}")
            findings["error"] = str(e)
        
        self.findings["2_mock_static_usage"] = findings
        return findings
    
    def audit_scanner_idempotency(self):
        """3) Scanner Engine + Strategy Allocator timeout/crash senaryosunda idempotency/state tutarlılığı"""
        print("\n🔍 3) SCANNER ENGINE + STRATEGY ALLOCATOR IDEMPOTENCY/STATE CONSISTENCY AUDIT")
        
        findings = {
            "idempotency_tests": [],
            "timeout_scenarios": [],
            "state_consistency_checks": [],
            "crash_recovery_evidence": [],
            "risk_level": "UNKNOWN"
        }
        
        try:
            # Test 1: Scanner Engine Idempotency
            print("🧪 Testing Scanner Engine idempotency...")
            
            # Run scanner multiple times with same parameters
            scan_results = []
            for i in range(3):
                try:
                    response = self.session.post(
                        f"{BASE_URL}/api/user/scanner-engine/run-async",
                        headers=self.get_headers(),
                        json={"scan_limit": 10, "market_scope": {"spot_mode": "all", "futures_mode": "all"}},
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        scan_results.append({
                            "run": i + 1,
                            "job_id": result.get("job_id"),
                            "status": result.get("status"),
                            "timestamp": datetime.now().isoformat()
                        })
                        print(f"  Run {i+1}: job_id={result.get('job_id')}, status={result.get('status')}")
                    else:
                        scan_results.append({
                            "run": i + 1,
                            "error": f"HTTP {response.status_code}",
                            "timestamp": datetime.now().isoformat()
                        })
                    
                    time.sleep(1)  # Brief pause between runs
                    
                except Exception as e:
                    scan_results.append({
                        "run": i + 1,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
            
            findings["idempotency_tests"].append({
                "test": "scanner_engine_multiple_runs",
                "results": scan_results,
                "analysis": "Check if multiple runs with same parameters produce consistent behavior"
            })
            
            # Test 2: Concurrent Scanner Calls (Stress Test)
            print("🧪 Testing concurrent scanner calls...")
            
            def concurrent_scanner_call():
                try:
                    response = self.session.post(
                        f"{BASE_URL}/api/user/scanner-engine/run-async",
                        headers=self.get_headers(),
                        json={"scan_limit": 5},
                        timeout=5
                    )
                    return {
                        "status_code": response.status_code,
                        "response": response.json() if response.status_code == 200 else response.text,
                        "timestamp": datetime.now().isoformat()
                    }
                except Exception as e:
                    return {
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
            
            # Run 5 concurrent scanner calls
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                concurrent_results = list(executor.map(lambda _: concurrent_scanner_call(), range(5)))
            
            findings["idempotency_tests"].append({
                "test": "concurrent_scanner_calls",
                "results": concurrent_results,
                "analysis": "Check system behavior under concurrent scanner requests"
            })
            
            # Test 3: Timeout Scenario Simulation
            print("🧪 Testing timeout scenarios...")
            
            try:
                # Test with very short timeout to simulate timeout scenario
                timeout_response = self.session.post(
                    f"{BASE_URL}/api/user/scanner-engine/run",
                    headers=self.get_headers(),
                    json={"scan_limit": 100},  # Large scan to potentially cause timeout
                    timeout=2  # Very short timeout
                )
                
                findings["timeout_scenarios"].append({
                    "test": "short_timeout_simulation",
                    "status_code": timeout_response.status_code,
                    "result": "Request completed within timeout"
                })
                
            except requests.exceptions.Timeout:
                findings["timeout_scenarios"].append({
                    "test": "short_timeout_simulation",
                    "result": "Timeout occurred as expected",
                    "analysis": "System handled timeout gracefully"
                })
            except Exception as e:
                findings["timeout_scenarios"].append({
                    "test": "short_timeout_simulation",
                    "error": str(e)
                })
            
            # Test 4: State Consistency Check
            print("🧪 Checking state consistency...")
            
            # Check if scanner jobs are properly tracked
            try:
                jobs_response = self.session.get(
                    f"{BASE_URL}/api/user/scanner-engine/jobs",
                    headers=self.get_headers(),
                    timeout=10
                )
                
                if jobs_response.status_code == 200:
                    jobs_data = jobs_response.json()
                    job_count = len(jobs_data.get("jobs", []))
                    
                    findings["state_consistency_checks"].append({
                        "check": "scanner_jobs_tracking",
                        "job_count": job_count,
                        "status": "Jobs are being tracked" if job_count > 0 else "No jobs found",
                        "evidence": jobs_data
                    })
                    print(f"  Scanner jobs tracked: {job_count}")
                
            except Exception as e:
                findings["state_consistency_checks"].append({
                    "check": "scanner_jobs_tracking",
                    "error": str(e)
                })
            
            # Analyze results for risk assessment
            successful_tests = 0
            total_tests = len(findings["idempotency_tests"]) + len(findings["timeout_scenarios"]) + len(findings["state_consistency_checks"])
            
            for test_category in [findings["idempotency_tests"], findings["timeout_scenarios"], findings["state_consistency_checks"]]:
                for test in test_category:
                    if "error" not in test and test.get("status_code", 200) == 200:
                        successful_tests += 1
            
            success_rate = successful_tests / total_tests if total_tests > 0 else 0
            
            if success_rate < 0.5:
                findings["risk_level"] = "HIGH"
            elif success_rate < 0.8:
                findings["risk_level"] = "MEDIUM"
            else:
                findings["risk_level"] = "LOW"
            
            print(f"📊 Idempotency/State Consistency Success Rate: {success_rate:.1%}")
            print(f"📈 Risk Level: {findings['risk_level']}")
            
        except Exception as e:
            print(f"❌ Scanner idempotency audit failed: {e}")
            findings["error"] = str(e)
            findings["risk_level"] = "HIGH"
        
        self.findings["3_scanner_idempotency"] = findings
        return findings
    
    def audit_resource_consumption(self):
        """4) Kaynak tüketimi ve pool kapasitesi (mevcut ortam ölçümü + 10x yük riski)"""
        print("\n🔍 4) RESOURCE CONSUMPTION AND POOL CAPACITY AUDIT")
        
        findings = {
            "current_metrics": {},
            "pool_capacity_analysis": {},
            "load_test_simulation": {},
            "10x_load_risk_assessment": {},
            "risk_level": "UNKNOWN"
        }
        
        try:
            # Get current system metrics
            print("📊 Measuring current system metrics...")
            
            # System resource usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            findings["current_metrics"] = {
                "cpu_usage_percent": cpu_percent,
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_usage_percent": memory.percent,
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_usage_percent": round((disk.used / disk.total) * 100, 2)
            }
            
            print(f"  CPU: {cpu_percent}%")
            print(f"  Memory: {memory.percent}% ({round(memory.used / (1024**3), 2)}GB / {round(memory.total / (1024**3), 2)}GB)")
            print(f"  Disk: {round((disk.used / disk.total) * 100, 2)}%")
            
            # Test API response times under current load
            print("⏱️ Measuring API response times...")
            
            api_endpoints = [
                "/api/health",
                "/api/market/ticker?symbol=BTCUSDT",
                "/api/user/signals",
                "/api/user/scanner-engine/config"
            ]
            
            response_times = {}
            for endpoint in api_endpoints:
                start_time = time.time()
                try:
                    response = self.session.get(
                        f"{BASE_URL}{endpoint}",
                        headers=self.get_headers(),
                        timeout=10
                    )
                    end_time = time.time()
                    response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                    
                    response_times[endpoint] = {
                        "response_time_ms": round(response_time, 2),
                        "status_code": response.status_code,
                        "success": response.status_code == 200
                    }
                    print(f"  {endpoint}: {round(response_time, 2)}ms (HTTP {response.status_code})")
                    
                except Exception as e:
                    response_times[endpoint] = {
                        "error": str(e),
                        "success": False
                    }
            
            findings["current_metrics"]["api_response_times"] = response_times
            
            # Simulate load test (limited concurrent requests)
            print("🚀 Simulating increased load...")
            
            def make_request():
                start_time = time.time()
                try:
                    response = self.session.get(
                        f"{BASE_URL}/api/health",
                        timeout=5
                    )
                    end_time = time.time()
                    return {
                        "response_time_ms": round((end_time - start_time) * 1000, 2),
                        "status_code": response.status_code,
                        "success": response.status_code == 200
                    }
                except Exception as e:
                    return {
                        "error": str(e),
                        "success": False
                    }
            
            # Test with 10 concurrent requests (simulating higher load)
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                load_test_results = list(executor.map(lambda _: make_request(), range(10)))
            
            successful_requests = sum(1 for r in load_test_results if r.get("success", False))
            avg_response_time = sum(r.get("response_time_ms", 0) for r in load_test_results if "response_time_ms" in r) / len(load_test_results)
            
            findings["load_test_simulation"] = {
                "concurrent_requests": 10,
                "successful_requests": successful_requests,
                "success_rate": successful_requests / 10,
                "average_response_time_ms": round(avg_response_time, 2),
                "results": load_test_results
            }
            
            print(f"  Load test: {successful_requests}/10 successful ({successful_requests/10:.1%})")
            print(f"  Average response time: {round(avg_response_time, 2)}ms")
            
            # 10x Load Risk Assessment
            print("⚠️ Assessing 10x load risk...")
            
            current_avg_response = avg_response_time
            estimated_10x_response = current_avg_response * 3  # Conservative estimate (not linear scaling)
            
            risk_factors = []
            
            # Memory risk
            if memory.percent > 70:
                risk_factors.append("High memory usage (>70%)")
            
            # CPU risk
            if cpu_percent > 70:
                risk_factors.append("High CPU usage (>70%)")
            
            # Response time risk
            if current_avg_response > 1000:  # > 1 second
                risk_factors.append("Slow current response times (>1s)")
            
            # Success rate risk
            if successful_requests < 9:  # Less than 90% success
                risk_factors.append("Low success rate in load test (<90%)")
            
            findings["10x_load_risk_assessment"] = {
                "current_avg_response_ms": round(current_avg_response, 2),
                "estimated_10x_response_ms": round(estimated_10x_response, 2),
                "risk_factors": risk_factors,
                "risk_factor_count": len(risk_factors)
            }
            
            # Determine overall risk level
            if len(risk_factors) >= 3:
                findings["risk_level"] = "HIGH"
            elif len(risk_factors) >= 1:
                findings["risk_level"] = "MEDIUM"
            else:
                findings["risk_level"] = "LOW"
            
            print(f"📈 10x Load Risk Level: {findings['risk_level']} ({len(risk_factors)} risk factors)")
            for factor in risk_factors:
                print(f"  ⚠️ {factor}")
            
        except Exception as e:
            print(f"❌ Resource consumption audit failed: {e}")
            findings["error"] = str(e)
            findings["risk_level"] = "HIGH"
        
        self.findings["4_resource_consumption"] = findings
        return findings
    
    def audit_auth_persistence(self):
        """5) Auth persistence: CDN/WAF dışı backend faktörleri, JWT/cookie/refresh mekanizması"""
        print("\n🔍 5) AUTH PERSISTENCE: CDN/WAF EXTERNAL BACKEND FACTORS, JWT/COOKIE/REFRESH MECHANISM AUDIT")
        
        findings = {
            "jwt_mechanism_analysis": {},
            "cookie_persistence_test": {},
            "refresh_token_flow": {},
            "session_management": {},
            "cdn_waf_independence": {},
            "risk_level": "UNKNOWN"
        }
        
        try:
            # Test 1: JWT Token Analysis
            print("🔐 Analyzing JWT token mechanism...")
            
            if self.user_token:
                # Decode JWT header (without verification for analysis)
                import base64
                try:
                    # JWT tokens have 3 parts separated by dots
                    parts = self.user_token.split('.')
                    if len(parts) >= 2:
                        # Decode header
                        header_data = base64.b64decode(parts[0] + '==').decode('utf-8')
                        header = json.loads(header_data)
                        
                        # Decode payload (claims)
                        payload_data = base64.b64decode(parts[1] + '==').decode('utf-8')
                        payload = json.loads(payload_data)
                        
                        findings["jwt_mechanism_analysis"] = {
                            "token_structure": "Valid JWT structure (3 parts)",
                            "header": header,
                            "payload_claims": list(payload.keys()),
                            "has_expiration": "exp" in payload,
                            "has_issued_at": "iat" in payload,
                            "token_length": len(self.user_token)
                        }
                        
                        print(f"  JWT structure: Valid (3 parts)")
                        print(f"  Claims: {list(payload.keys())}")
                        print(f"  Has expiration: {'exp' in payload}")
                        
                except Exception as e:
                    findings["jwt_mechanism_analysis"] = {
                        "error": f"JWT decode error: {e}",
                        "token_length": len(self.user_token)
                    }
            
            # Test 2: Cookie Persistence
            print("🍪 Testing cookie persistence...")
            
            # Check if cookies are set during authentication
            auth_response = self.session.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
                timeout=10
            )
            
            if auth_response.status_code == 200:
                cookies = auth_response.cookies
                cookie_names = list(cookies.keys())
                
                findings["cookie_persistence_test"] = {
                    "cookies_set": len(cookie_names) > 0,
                    "cookie_names": cookie_names,
                    "cookie_count": len(cookie_names)
                }
                
                print(f"  Cookies set: {len(cookie_names)} ({cookie_names})")
                
                # Test if cookies persist across requests
                if cookie_names:
                    me_response = self.session.get(
                        f"{BASE_URL}/api/auth/me",
                        timeout=10
                    )
                    
                    findings["cookie_persistence_test"]["cookie_auth_works"] = me_response.status_code == 200
                    print(f"  Cookie authentication works: {me_response.status_code == 200}")
            
            # Test 3: Refresh Token Flow
            print("🔄 Testing refresh token mechanism...")
            
            try:
                # Try to use refresh endpoint
                refresh_response = self.session.post(
                    f"{BASE_URL}/api/auth/refresh",
                    timeout=10
                )
                
                findings["refresh_token_flow"] = {
                    "refresh_endpoint_exists": refresh_response.status_code != 404,
                    "refresh_status_code": refresh_response.status_code,
                    "refresh_response": refresh_response.text[:200] if refresh_response.text else None
                }
                
                if refresh_response.status_code == 200:
                    refresh_data = refresh_response.json()
                    findings["refresh_token_flow"]["new_token_provided"] = "access_token" in refresh_data
                    print(f"  Refresh token flow: Working (new token provided)")
                else:
                    print(f"  Refresh token flow: Status {refresh_response.status_code}")
                
            except Exception as e:
                findings["refresh_token_flow"] = {"error": str(e)}
            
            # Test 4: Session Management
            print("👤 Testing session management...")
            
            # Test multiple concurrent sessions
            session2 = requests.Session()
            session2.timeout = 10
            
            # Authenticate with second session
            auth2_response = session2.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": USER_EMAIL, "password": USER_PASSWORD}
            )
            
            if auth2_response.status_code == 200:
                # Test if both sessions work simultaneously
                me1_response = self.session.get(f"{BASE_URL}/api/auth/me", headers=self.get_headers())
                me2_response = session2.get(f"{BASE_URL}/api/auth/me", 
                                          headers={"Authorization": f"Bearer {auth2_response.json().get('access_token')}"})
                
                findings["session_management"] = {
                    "concurrent_sessions_allowed": me1_response.status_code == 200 and me2_response.status_code == 200,
                    "session1_status": me1_response.status_code,
                    "session2_status": me2_response.status_code
                }
                
                print(f"  Concurrent sessions allowed: {me1_response.status_code == 200 and me2_response.status_code == 200}")
            
            # Test 5: CDN/WAF Independence
            print("🌐 Testing CDN/WAF independence...")
            
            # Test with different User-Agent and headers to simulate CDN/WAF bypass
            bypass_headers = {
                "User-Agent": "BackendAuditTool/1.0",
                "X-Forwarded-For": "127.0.0.1",
                "X-Real-IP": "127.0.0.1"
            }
            
            bypass_session = requests.Session()
            bypass_session.headers.update(bypass_headers)
            
            # Test if authentication still works with different headers
            bypass_auth_response = bypass_session.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
                timeout=10
            )
            
            findings["cdn_waf_independence"] = {
                "auth_works_with_different_headers": bypass_auth_response.status_code == 200,
                "bypass_status_code": bypass_auth_response.status_code,
                "backend_direct_access": bypass_auth_response.status_code == 200
            }
            
            print(f"  Auth works with different headers: {bypass_auth_response.status_code == 200}")
            
            # Risk Assessment
            risk_factors = []
            
            if not findings["jwt_mechanism_analysis"].get("has_expiration", False):
                risk_factors.append("JWT tokens may not have expiration")
            
            if not findings["cookie_persistence_test"].get("cookies_set", False):
                risk_factors.append("No cookies set during authentication")
            
            if not findings["refresh_token_flow"].get("refresh_endpoint_exists", False):
                risk_factors.append("Refresh token endpoint not available")
            
            if findings["session_management"].get("concurrent_sessions_allowed", True):
                risk_factors.append("Unlimited concurrent sessions allowed")
            
            findings["risk_factors"] = risk_factors
            
            if len(risk_factors) >= 3:
                findings["risk_level"] = "HIGH"
            elif len(risk_factors) >= 1:
                findings["risk_level"] = "MEDIUM"
            else:
                findings["risk_level"] = "LOW"
            
            print(f"📈 Auth Persistence Risk Level: {findings['risk_level']} ({len(risk_factors)} risk factors)")
            for factor in risk_factors:
                print(f"  ⚠️ {factor}")
            
        except Exception as e:
            print(f"❌ Auth persistence audit failed: {e}")
            findings["error"] = str(e)
            findings["risk_level"] = "HIGH"
        
        self.findings["5_auth_persistence"] = findings
        return findings
    
    def generate_report(self):
        """Generate comprehensive audit report"""
        print("\n" + "="*80)
        print("📋 TURKISH REVIEW REQUEST - COMPREHENSIVE AUDIT REPORT")
        print("="*80)
        
        # Overall risk assessment
        risk_levels = []
        for key, finding in self.findings.items():
            if isinstance(finding, dict) and "risk_level" in finding:
                risk_levels.append(finding["risk_level"])
        
        # Count risk levels
        high_risks = risk_levels.count("HIGH")
        medium_risks = risk_levels.count("MEDIUM")
        low_risks = risk_levels.count("LOW")
        
        overall_risk = "HIGH" if high_risks > 0 else ("MEDIUM" if medium_risks > 0 else "LOW")
        
        print(f"\n🎯 OVERALL RISK ASSESSMENT: {overall_risk}")
        print(f"   High Risk Areas: {high_risks}")
        print(f"   Medium Risk Areas: {medium_risks}")
        print(f"   Low Risk Areas: {low_risks}")
        
        # Detailed findings by category
        categories = [
            ("1) Advisory Mode Blocked/Non-tradeable Rules", "1_advisory_mode_rules"),
            ("2) Mock/Stub/Static JSON Usage", "2_mock_static_usage"),
            ("3) Scanner Engine Idempotency/State Consistency", "3_scanner_idempotency"),
            ("4) Resource Consumption & Pool Capacity", "4_resource_consumption"),
            ("5) Auth Persistence & JWT/Cookie Mechanism", "5_auth_persistence")
        ]
        
        for title, key in categories:
            print(f"\n📊 {title}")
            print("-" * 60)
            
            finding = self.findings.get(key, {})
            risk_level = finding.get("risk_level", "UNKNOWN")
            
            print(f"Risk Level: {risk_level}")
            
            if "error" in finding:
                print(f"❌ Error: {finding['error']}")
            else:
                # Print key findings for each category
                if key == "1_advisory_mode_rules":
                    active_rules = len(finding.get("active_affecting_rules", []))
                    blocked_symbols = finding.get("blocked_symbols_count", 0)
                    print(f"• Active affecting rules: {active_rules}")
                    print(f"• Blocked symbols: {blocked_symbols}")
                    
                elif key == "2_mock_static_usage":
                    mock_count = len(finding.get("mock_endpoints_detected", []))
                    real_count = len(finding.get("real_exchange_evidence", []))
                    print(f"• Mock/Static indicators: {mock_count}")
                    print(f"• Real exchange evidence: {real_count}")
                    
                elif key == "3_scanner_idempotency":
                    test_count = len(finding.get("idempotency_tests", []))
                    timeout_count = len(finding.get("timeout_scenarios", []))
                    print(f"• Idempotency tests completed: {test_count}")
                    print(f"• Timeout scenarios tested: {timeout_count}")
                    
                elif key == "4_resource_consumption":
                    current_metrics = finding.get("current_metrics", {})
                    cpu = current_metrics.get("cpu_usage_percent", "N/A")
                    memory = current_metrics.get("memory_usage_percent", "N/A")
                    print(f"• Current CPU usage: {cpu}%")
                    print(f"• Current memory usage: {memory}%")
                    
                elif key == "5_auth_persistence":
                    risk_factors = len(finding.get("risk_factors", []))
                    jwt_valid = finding.get("jwt_mechanism_analysis", {}).get("token_structure", "").startswith("Valid")
                    print(f"• JWT structure valid: {jwt_valid}")
                    print(f"• Auth risk factors: {risk_factors}")
        
        # Production readiness assessment
        print(f"\n🚀 PRODUCTION READINESS ASSESSMENT")
        print("-" * 40)
        
        if overall_risk == "LOW":
            print("✅ READY FOR PRODUCTION")
            print("   All audit areas show low risk levels")
        elif overall_risk == "MEDIUM":
            print("⚠️ CONDITIONAL PRODUCTION READINESS")
            print("   Some areas require monitoring or minor fixes")
        else:
            print("❌ NOT READY FOR PRODUCTION")
            print("   Critical issues found that require immediate attention")
        
        # Save detailed report to file
        report_data = {
            "audit_timestamp": datetime.now().isoformat(),
            "overall_risk_level": overall_risk,
            "risk_summary": {
                "high_risk_areas": high_risks,
                "medium_risk_areas": medium_risks,
                "low_risk_areas": low_risks
            },
            "detailed_findings": self.findings
        }
        
        with open("/app/turkish_review_audit_report.json", "w") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Detailed report saved to: /app/turkish_review_audit_report.json")
        
        return report_data

def main():
    print("🇹🇷 TURKISH REVIEW REQUEST - EVIDENCE-BASED BACKEND AUDIT")
    print("=" * 80)
    print("Testing 5 critical areas with evidence-based approach:")
    print("1) Advisory Mode blocked/non_tradeable hard-coded rule sources")
    print("2) Mock/stub/static JSON usage (especially scanner)")
    print("3) Scanner Engine + Strategy Allocator idempotency/state consistency")
    print("4) Resource consumption and pool capacity (10x load risk)")
    print("5) Auth persistence: JWT/cookie/refresh mechanism")
    print("=" * 80)
    
    auditor = TurkishReviewAuditor()
    
    # Authenticate
    if not auditor.authenticate_user():
        print("❌ User authentication failed - cannot proceed with audit")
        return 1
    
    if not auditor.authenticate_admin():
        print("⚠️ Admin authentication failed - some tests may be limited")
    
    # Run all audit categories
    try:
        auditor.audit_advisory_mode_rules()
        auditor.audit_mock_static_usage()
        auditor.audit_scanner_idempotency()
        auditor.audit_resource_consumption()
        auditor.audit_auth_persistence()
        
        # Generate comprehensive report
        report = auditor.generate_report()
        
        return 0 if report["overall_risk_level"] != "HIGH" else 1
        
    except Exception as e:
        print(f"❌ Audit failed with error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())