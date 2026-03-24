#!/usr/bin/env python3
"""
Commercial Ops P0 Backend Validation Test
Comprehensive testing for Binance REST ingestion + canonical schema + PnL + reconciliation + data quality + standardized CSV export + websocket bootstrap
"""

import json
import requests
import sys
from datetime import datetime
from typing import Dict, Any, List

# Test Configuration
BASE_URL = "https://binance-reconcile.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Test Credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
TARGET_USER_EMAIL = "huseyinwural@gmail.com"
ENVIRONMENT = "testnet"

class CommercialOpsP0Tester:
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 30
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, test_name: str, status: str, details: str = "", response_data: Dict = None):
        """Log test result with timestamp"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "response_data": response_data
        }
        self.test_results.append(result)
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if response_data and status == "FAIL":
            print(f"   Response: {json.dumps(response_data, indent=2)[:500]}...")
    
    def admin_login(self) -> bool:
        """Authenticate as admin and get access token"""
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("access_token"):
                    self.admin_token = data["access_token"]
                    self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                    self.log_result("Admin Login", "PASS", f"Successfully authenticated as {ADMIN_EMAIL}")
                    return True
                else:
                    self.log_result("Admin Login", "FAIL", f"No access token in response: {data}")
                    return False
            else:
                self.log_result("Admin Login", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_health_check(self) -> bool:
        """Test basic health endpoint"""
        try:
            response = self.session.get(f"{API_BASE}/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    self.log_result("Health Check", "PASS", "Backend service is healthy")
                    return True
                else:
                    self.log_result("Health Check", "FAIL", f"Unhealthy status: {data}")
                    return False
            else:
                self.log_result("Health Check", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_result("Health Check", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_ingestion_rest_run(self) -> bool:
        """Test POST /api/admin/commercial/p0/ingestion/rest-run"""
        try:
            # Test successful scenario
            payload = {
                "target_user_email": TARGET_USER_EMAIL,
                "environment": ENVIRONMENT,
                "market_types": ["spot", "futures"],
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "limit_per_symbol": 200
            }
            
            response = self.session.post(
                f"{API_BASE}/admin/commercial/p0/ingestion/rest-run",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["status", "user_id", "user_email", "environment", "market_types", "symbols", "fetched", "inserted", "duplicate", "market_summary", "source", "generated_at"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    self.log_result("REST Ingestion - Success Case", "PASS", 
                                  f"Fetched: {data.get('fetched', 0)}, Inserted: {data.get('inserted', 0)}, Duplicate: {data.get('duplicate', 0)}")
                    
                    # Test error scenarios
                    self.test_ingestion_error_scenarios()
                    return True
                else:
                    self.log_result("REST Ingestion - Success Case", "FAIL", f"Missing fields: {missing_fields}", data)
                    return False
            else:
                self.log_result("REST Ingestion - Success Case", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("REST Ingestion - Success Case", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_ingestion_error_scenarios(self):
        """Test error scenarios for ingestion endpoint"""
        error_scenarios = [
            {
                "name": "Missing User",
                "payload": {
                    "target_user_email": "nonexistent@example.com",
                    "environment": ENVIRONMENT,
                    "market_types": ["spot"],
                    "symbols": ["BTCUSDT"],
                    "limit_per_symbol": 100
                },
                "expected_status": 404,
                "expected_detail": "target_user_not_found"
            },
            {
                "name": "Spot Symbols Required",
                "payload": {
                    "target_user_email": TARGET_USER_EMAIL,
                    "environment": ENVIRONMENT,
                    "market_types": ["spot"],
                    "symbols": [],  # Empty symbols for spot
                    "limit_per_symbol": 100
                },
                "expected_status": 400,
                "expected_detail": "spot_symbols_required"
            }
        ]
        
        for scenario in error_scenarios:
            try:
                response = self.session.post(
                    f"{API_BASE}/admin/commercial/p0/ingestion/rest-run",
                    json=scenario["payload"]
                )
                
                if response.status_code == scenario["expected_status"]:
                    data = response.json()
                    if data.get("detail") == scenario["expected_detail"]:
                        self.log_result(f"REST Ingestion - {scenario['name']}", "PASS", 
                                      f"Correctly returned {scenario['expected_status']} with detail: {scenario['expected_detail']}")
                    else:
                        self.log_result(f"REST Ingestion - {scenario['name']}", "FAIL", 
                                      f"Wrong error detail. Expected: {scenario['expected_detail']}, Got: {data.get('detail')}")
                else:
                    self.log_result(f"REST Ingestion - {scenario['name']}", "FAIL", 
                                  f"Wrong status code. Expected: {scenario['expected_status']}, Got: {response.status_code}")
                    
            except Exception as e:
                self.log_result(f"REST Ingestion - {scenario['name']}", "FAIL", f"Exception: {str(e)}")
    
    def test_pnl_latest(self) -> bool:
        """Test GET /api/admin/commercial/p0/pnl/latest"""
        try:
            params = {
                "target_user_email": TARGET_USER_EMAIL,
                "environment": ENVIRONMENT
            }
            
            response = self.session.get(
                f"{API_BASE}/admin/commercial/p0/pnl/latest",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["status", "user_id", "user_email", "environment", "trade_count", "realized", "unrealized", "fee_breakdown", "net_total_usd", "record_id"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    # Validate fee breakdown structure
                    fee_breakdown = data.get("fee_breakdown", {})
                    fee_fields = ["trading_fee_usd", "commission_usd", "funding_usd"]
                    missing_fee_fields = [field for field in fee_fields if field not in fee_breakdown]
                    
                    if not missing_fee_fields:
                        self.log_result("PnL Latest", "PASS", 
                                      f"Trade count: {data.get('trade_count', 0)}, Net total: ${data.get('net_total_usd', 0)}")
                        return True
                    else:
                        self.log_result("PnL Latest", "FAIL", f"Missing fee breakdown fields: {missing_fee_fields}", data)
                        return False
                else:
                    self.log_result("PnL Latest", "FAIL", f"Missing fields: {missing_fields}", data)
                    return False
            else:
                self.log_result("PnL Latest", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("PnL Latest", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_reconciliation_run(self) -> bool:
        """Test POST /api/admin/commercial/p0/reconciliation/run"""
        try:
            payload = {
                "target_user_email": TARGET_USER_EMAIL,
                "environment": ENVIRONMENT,
                "market_types": ["spot", "futures"],
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "limit_per_symbol": 200,
                "drift_tolerance_usd": 5.0
            }
            
            response = self.session.post(
                f"{API_BASE}/admin/commercial/p0/reconciliation/run",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["status", "log_id", "user_id", "user_email", "environment", "markets", 
                                 "internal_trade_count", "exchange_trade_count", "missing_trade_count", 
                                 "duplicate_trade_count", "balance_drift_usd", "position_drift_usd", 
                                 "pnl_drift_usd", "drift_tolerance_usd", "drift_within_tolerance", 
                                 "missing_data_alert"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    # Validate drift fields and tolerance
                    drift_fields = ["balance_drift_usd", "position_drift_usd", "pnl_drift_usd"]
                    drift_info = {field: data.get(field, 0) for field in drift_fields}
                    tolerance = data.get("drift_tolerance_usd", 0)
                    freshness = data.get("freshness_seconds")
                    
                    self.log_result("Reconciliation Run", "PASS", 
                                  f"Drift info: {drift_info}, Tolerance: {tolerance}, Freshness: {freshness}s")
                    return True
                else:
                    self.log_result("Reconciliation Run", "FAIL", f"Missing fields: {missing_fields}", data)
                    return False
            else:
                self.log_result("Reconciliation Run", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Reconciliation Run", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_data_quality(self) -> bool:
        """Test GET /api/admin/commercial/p0/data-quality"""
        try:
            params = {
                "target_user_email": TARGET_USER_EMAIL,
                "environment": ENVIRONMENT
            }
            
            response = self.session.get(
                f"{API_BASE}/admin/commercial/p0/data-quality",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["status", "user_id", "user_email", "environment", "freshness_seconds", 
                                 "missing_data_alert", "market_alerts", "latest_reconciliation"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    # Validate freshness and missing_data_alert fields
                    freshness = data.get("freshness_seconds", {})
                    market_alerts = data.get("market_alerts", {})
                    missing_data_alert = data.get("missing_data_alert", False)
                    
                    self.log_result("Data Quality", "PASS", 
                                  f"Freshness: {freshness}, Missing data alert: {missing_data_alert}")
                    return True
                else:
                    self.log_result("Data Quality", "FAIL", f"Missing fields: {missing_fields}", data)
                    return False
            else:
                self.log_result("Data Quality", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Data Quality", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_live_gate(self) -> bool:
        """Test GET /api/admin/commercial/p0/live-gate"""
        try:
            params = {
                "target_user_email": TARGET_USER_EMAIL,
                "environment": ENVIRONMENT
            }
            
            response = self.session.get(
                f"{API_BASE}/admin/commercial/p0/live-gate",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["status", "user_id", "user_email", "environment", "controls", 
                                 "live_transition_ready", "evidence"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    # Validate controls structure
                    controls = data.get("controls", {})
                    required_controls = ["trade_ingest_ok", "pnl_ok", "reconciliation_ok"]
                    missing_controls = [field for field in required_controls if field not in controls]
                    
                    if not missing_controls:
                        live_ready = data.get("live_transition_ready", False)
                        self.log_result("Live Gate", "PASS", 
                                      f"Controls: {controls}, Live ready: {live_ready}")
                        return True
                    else:
                        self.log_result("Live Gate", "FAIL", f"Missing control fields: {missing_controls}", data)
                        return False
                else:
                    self.log_result("Live Gate", "FAIL", f"Missing fields: {missing_fields}", data)
                    return False
            else:
                self.log_result("Live Gate", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Live Gate", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_websocket_bootstrap(self) -> bool:
        """Test POST /api/admin/commercial/p0/websocket/bootstrap"""
        try:
            payload = {
                "target_user_email": TARGET_USER_EMAIL,
                "environment": ENVIRONMENT,
                "market_types": ["spot", "futures"]
            }
            
            response = self.session.post(
                f"{API_BASE}/admin/commercial/p0/websocket/bootstrap",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["status", "user_id", "user_email", "environment", "streams", "note", "generated_at"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    # Validate streams structure (listen_key and ws_url)
                    streams = data.get("streams", {})
                    stream_validation = True
                    stream_details = {}
                    
                    for market_type in ["spot", "futures"]:
                        if market_type in streams:
                            stream = streams[market_type]
                            if "listen_key" in stream and "ws_url" in stream:
                                stream_details[market_type] = {
                                    "has_listen_key": bool(stream.get("listen_key")),
                                    "has_ws_url": bool(stream.get("ws_url"))
                                }
                            else:
                                stream_validation = False
                                break
                    
                    if stream_validation:
                        self.log_result("Websocket Bootstrap", "PASS", 
                                      f"Stream details: {stream_details}")
                        return True
                    else:
                        self.log_result("Websocket Bootstrap", "FAIL", f"Invalid stream structure: {streams}", data)
                        return False
                else:
                    self.log_result("Websocket Bootstrap", "FAIL", f"Missing fields: {missing_fields}", data)
                    return False
            else:
                self.log_result("Websocket Bootstrap", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Websocket Bootstrap", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_trades_export_csv(self) -> bool:
        """Test GET /api/admin/commercial/p0/trades/export.csv"""
        try:
            params = {
                "target_user_email": TARGET_USER_EMAIL,
                "environment": ENVIRONMENT
            }
            
            response = self.session.get(
                f"{API_BASE}/admin/commercial/p0/trades/export.csv",
                params=params
            )
            
            if response.status_code == 200:
                # Validate CSV content-type
                content_type = response.headers.get("content-type", "")
                if "text/csv" in content_type:
                    # Check if content is non-empty and has proper CSV structure
                    content = response.text
                    if content and len(content) > 0:
                        lines = content.split('\n')
                        if len(lines) >= 1:  # At least header
                            header = lines[0]
                            # Validate standardized CSV headers
                            expected_headers = ["trade_id", "user_id", "exchange", "market_type", "environment", 
                                              "symbol", "base_asset", "quote_asset", "side", "position_side", 
                                              "trade_time", "executed_qty", "executed_price", "commission_usd", 
                                              "realized_pnl_usd", "source", "ingested_at"]
                            
                            header_validation = all(h in header for h in expected_headers[:5])  # Check first 5 critical headers
                            
                            if header_validation:
                                self.log_result("CSV Export", "PASS", 
                                              f"Content-type: {content_type}, Lines: {len(lines)}, Header standardized")
                                return True
                            else:
                                self.log_result("CSV Export", "FAIL", f"Header standardization issue. Header: {header[:200]}...")
                                return False
                        else:
                            self.log_result("CSV Export", "FAIL", "Empty CSV content")
                            return False
                    else:
                        self.log_result("CSV Export", "FAIL", "No content in CSV response")
                        return False
                else:
                    self.log_result("CSV Export", "FAIL", f"Wrong content-type: {content_type}")
                    return False
            else:
                self.log_result("CSV Export", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("CSV Export", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_environment_degradation_check(self) -> bool:
        """Check if environment is degraded (502 errors)"""
        try:
            # Test multiple endpoints for 502 errors
            test_endpoints = [
                f"{API_BASE}/health",
                f"{API_BASE}/ready",
                f"{BASE_URL}/"
            ]
            
            degraded_endpoints = []
            for endpoint in test_endpoints:
                try:
                    response = self.session.get(endpoint, timeout=10)
                    if response.status_code == 502:
                        degraded_endpoints.append(endpoint)
                except Exception:
                    degraded_endpoints.append(endpoint)
            
            if degraded_endpoints:
                self.log_result("Environment Degradation Check", "FAIL", 
                              f"502/degraded endpoints detected: {degraded_endpoints}")
                return False
            else:
                self.log_result("Environment Degradation Check", "PASS", "No 502/degraded endpoints detected")
                return True
                
        except Exception as e:
            self.log_result("Environment Degradation Check", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all Commercial Ops P0 tests"""
        print("=" * 80)
        print("COMMERCIAL OPS P0 BACKEND VALIDATION")
        print(f"Target URL: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print(f"Target User: {TARGET_USER_EMAIL}")
        print(f"Environment: {ENVIRONMENT}")
        print("=" * 80)
        
        # Environment check first
        if not self.test_environment_degradation_check():
            print("\n🚨 CRITICAL BLOCKER: Environment is degraded (502 errors detected)")
            print("Cannot proceed with endpoint validation until environment is restored.")
            return False
        
        # Health check
        if not self.test_health_check():
            print("\n🚨 CRITICAL BLOCKER: Health check failed")
            return False
        
        # Admin authentication
        if not self.admin_login():
            print("\n🚨 CRITICAL BLOCKER: Admin authentication failed")
            return False
        
        # Run all Commercial Ops P0 endpoint tests
        tests = [
            ("REST Ingestion", self.test_ingestion_rest_run),
            ("PnL Latest", self.test_pnl_latest),
            ("Reconciliation Run", self.test_reconciliation_run),
            ("Data Quality", self.test_data_quality),
            ("Live Gate", self.test_live_gate),
            ("Websocket Bootstrap", self.test_websocket_bootstrap),
            ("CSV Export", self.test_trades_export_csv)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        print(f"\n📋 Running {total_tests} Commercial Ops P0 endpoint tests...")
        
        for test_name, test_func in tests:
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                self.log_result(test_name, "FAIL", f"Unexpected exception: {str(e)}")
        
        # Summary
        print("\n" + "=" * 80)
        print("COMMERCIAL OPS P0 BACKEND VALIDATION SUMMARY")
        print("=" * 80)
        
        success_rate = (passed_tests / total_tests) * 100
        print(f"Overall Success Rate: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        
        # Categorize results
        passed = [r for r in self.test_results if r["status"] == "PASS"]
        failed = [r for r in self.test_results if r["status"] == "FAIL"]
        
        if failed:
            print(f"\n❌ FAILED TESTS ({len(failed)}):")
            for result in failed:
                print(f"   • {result['test']}: {result['details']}")
        
        if passed:
            print(f"\n✅ PASSED TESTS ({len(passed)}):")
            for result in passed:
                print(f"   • {result['test']}")
        
        # Final verdict
        if success_rate >= 85:
            print(f"\n🎉 OVERALL RESULT: ✅ PASS - Commercial Ops P0 backend validation successful ({success_rate:.1f}% success rate)")
            return True
        else:
            print(f"\n🚨 OVERALL RESULT: ❌ FAIL - Commercial Ops P0 backend validation failed ({success_rate:.1f}% success rate)")
            return False

def main():
    """Main test execution"""
    tester = CommercialOpsP0Tester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()