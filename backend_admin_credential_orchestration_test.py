#!/usr/bin/env python3
"""
Admin Credential Orchestration Layer Backend Test
Sprint A backend validation run after Admin Credential Orchestration Layer.

Test Requirements:
1. Orchestration endpoints (GET/POST/PATCH credentials, approve, probe, disable, rules, preview)
2. User response enrichment (effective_source, routing_preview, environment_valid)
3. P0 testnet closure chain (spot+futures)

Base URL: https://dry-run-shadow.preview.emergentagent.com
Admin: canary.admin@platform.local / CanaryAdmin123!
User: huseyinwural@gmail.com
"""

import requests
import json
import sys
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "huseyinwural@gmail.com"

class AdminCredentialOrchestrationTester:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.test_results = []
        self.created_credential_id = None
        
    def log_result(self, test_name, status, details=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    def admin_login(self):
        """Login as admin and get access token"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("access_token"):
                    self.admin_token = data["access_token"]
                    self.log_result("Admin Login", "PASS", f"Token received, user: {data.get('user', {}).get('email', 'N/A')}")
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
    
    def user_login(self):
        """Login as user and get access token"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/user",
                json={
                    "email": USER_EMAIL,
                    "password": "HuseyinWural123!"  # Assuming standard password
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("access_token"):
                    self.user_token = data["access_token"]
                    self.log_result("User Login", "PASS", f"Token received, user: {data.get('user', {}).get('email', 'N/A')}")
                    return True
                else:
                    self.log_result("User Login", "FAIL", f"No access token in response: {data}")
                    return False
            else:
                self.log_result("User Login", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("User Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_orchestration_endpoints(self):
        """Test 1: Orchestration endpoints"""
        print("\n=== TEST 1: ORCHESTRATION ENDPOINTS ===")
        
        if not self.admin_token:
            self.log_result("Orchestration Endpoints", "FAIL", "No admin token available")
            return
        
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Test GET /api/venues/admin/credentials
        try:
            response = requests.get(f"{BASE_URL}/api/venues/admin/credentials", headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # Handle both list and dict responses
                if isinstance(data, list):
                    self.log_result("GET /api/venues/admin/credentials", "PASS", f"Retrieved {len(data)} credentials")
                elif isinstance(data, dict):
                    items = data.get('items', data.get('credentials', []))
                    self.log_result("GET /api/venues/admin/credentials", "PASS", f"Retrieved {len(items)} credentials")
                else:
                    self.log_result("GET /api/venues/admin/credentials", "PASS", f"Retrieved credentials data: {type(data)}")
            else:
                self.log_result("GET /api/venues/admin/credentials", "FAIL", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("GET /api/venues/admin/credentials", "FAIL", f"Exception: {str(e)}")
        
        # Test POST /api/venues/admin/credentials
        try:
            test_credential = {
                "exchange": "binance",
                "environment": "testnet",
                "market_type": "futures",
                "api_key": "test_api_key_12345",
                "api_secret": "test_api_secret_67890",
                "description": "Test credential for orchestration validation"
            }
            
            response = requests.post(
                f"{BASE_URL}/api/venues/admin/credentials",
                json=test_credential,
                headers=headers,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.created_credential_id = data.get("id")
                self.log_result("POST /api/venues/admin/credentials", "PASS", f"Created credential ID: {self.created_credential_id}")
            else:
                self.log_result("POST /api/venues/admin/credentials", "FAIL", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("POST /api/venues/admin/credentials", "FAIL", f"Exception: {str(e)}")
        
        # Test PATCH /api/venues/admin/credentials/{id} (if we have a credential ID)
        if self.created_credential_id:
            try:
                update_data = {"description": "Updated test credential description"}
                response = requests.patch(
                    f"{BASE_URL}/api/venues/admin/credentials/{self.created_credential_id}",
                    json=update_data,
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    self.log_result("PATCH /api/venues/admin/credentials/{id}", "PASS", "Credential updated successfully")
                else:
                    self.log_result("PATCH /api/venues/admin/credentials/{id}", "FAIL", f"HTTP {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("PATCH /api/venues/admin/credentials/{id}", "FAIL", f"Exception: {str(e)}")
            
            # Test POST /api/venues/admin/credentials/{id}/approve
            try:
                response = requests.post(
                    f"{BASE_URL}/api/venues/admin/credentials/{self.created_credential_id}/approve",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    self.log_result("POST /api/venues/admin/credentials/{id}/approve", "PASS", "Credential approved successfully")
                else:
                    self.log_result("POST /api/venues/admin/credentials/{id}/approve", "FAIL", f"HTTP {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("POST /api/venues/admin/credentials/{id}/approve", "FAIL", f"Exception: {str(e)}")
            
            # Test POST /api/venues/admin/credentials/{id}/probe
            try:
                response = requests.post(
                    f"{BASE_URL}/api/venues/admin/credentials/{self.created_credential_id}/probe",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.log_result("POST /api/venues/admin/credentials/{id}/probe", "PASS", f"Probe result: {data.get('status', 'N/A')}")
                else:
                    self.log_result("POST /api/venues/admin/credentials/{id}/probe", "FAIL", f"HTTP {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("POST /api/venues/admin/credentials/{id}/probe", "FAIL", f"Exception: {str(e)}")
            
            # Test POST /api/venues/admin/credentials/{id}/disable
            try:
                response = requests.post(
                    f"{BASE_URL}/api/venues/admin/credentials/{self.created_credential_id}/disable",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    self.log_result("POST /api/venues/admin/credentials/{id}/disable", "PASS", "Credential disabled successfully")
                else:
                    self.log_result("POST /api/venues/admin/credentials/{id}/disable", "FAIL", f"HTTP {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("POST /api/venues/admin/credentials/{id}/disable", "FAIL", f"Exception: {str(e)}")
        
        # Test GET /api/venues/admin/credential-rules
        try:
            response = requests.get(f"{BASE_URL}/api/venues/admin/credential-rules", headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # Handle both list and dict responses
                if isinstance(data, list):
                    self.log_result("GET /api/venues/admin/credential-rules", "PASS", f"Retrieved credential rules: {len(data)} rules")
                elif isinstance(data, dict):
                    rules = data.get('rules', data.get('items', []))
                    self.log_result("GET /api/venues/admin/credential-rules", "PASS", f"Retrieved credential rules: {len(rules)} rules")
                else:
                    self.log_result("GET /api/venues/admin/credential-rules", "PASS", f"Retrieved rules data: {type(data)}")
            else:
                self.log_result("GET /api/venues/admin/credential-rules", "FAIL", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("GET /api/venues/admin/credential-rules", "FAIL", f"Exception: {str(e)}")
        
        # Test PUT /api/venues/admin/credential-rules
        try:
            test_rules = {
                "rules": [
                    {
                        "exchange": "binance",
                        "environment": "testnet",
                        "market_type": "futures",
                        "priority": 1,
                        "assignment_strategy": "round_robin"
                    }
                ]
            }
            
            response = requests.put(
                f"{BASE_URL}/api/venues/admin/credential-rules",
                json=test_rules,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                self.log_result("PUT /api/venues/admin/credential-rules", "PASS", "Credential rules updated successfully")
            else:
                self.log_result("PUT /api/venues/admin/credential-rules", "FAIL", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("PUT /api/venues/admin/credential-rules", "FAIL", f"Exception: {str(e)}")
        
        # Test GET /api/venues/admin/credential-resolution-preview
        try:
            params = {
                "user_id": "test-user",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet"
            }
            
            response = requests.get(
                f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
                params=params,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("GET /api/venues/admin/credential-resolution-preview", "PASS", f"Preview generated with source: {data.get('selected_source', 'N/A')}")
            else:
                self.log_result("GET /api/venues/admin/credential-resolution-preview", "FAIL", f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("GET /api/venues/admin/credential-resolution-preview", "FAIL", f"Exception: {str(e)}")
    
    def test_user_response_enrichment(self):
        """Test 2: User response enrichment"""
        print("\n=== TEST 2: USER RESPONSE ENRICHMENT ===")
        
        if not self.user_token:
            self.log_result("User Response Enrichment", "FAIL", "No user token available")
            return
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        
        try:
            response = requests.get(f"{BASE_URL}/api/user/exchange-connections", headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                # Handle both list and dict responses
                if isinstance(data, list):
                    connections = data
                elif isinstance(data, dict):
                    connections = data.get("connections", data.get("items", []))
                else:
                    connections = []
                
                if connections:
                    # Check for required enrichment fields
                    sample_connection = connections[0]
                    required_fields = ["effective_source", "routing_preview", "environment_valid"]
                    missing_fields = []
                    
                    for field in required_fields:
                        if field not in sample_connection:
                            missing_fields.append(field)
                    
                    if not missing_fields:
                        self.log_result("GET /api/user/exchange-connections", "PASS", f"All enrichment fields present: {required_fields}")
                    else:
                        self.log_result("GET /api/user/exchange-connections", "FAIL", f"Missing enrichment fields: {missing_fields}")
                else:
                    self.log_result("GET /api/user/exchange-connections", "PARTIAL", "No connections found to verify enrichment fields")
            else:
                self.log_result("GET /api/user/exchange-connections", "FAIL", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("GET /api/user/exchange-connections", "FAIL", f"Exception: {str(e)}")
    
    def test_p0_testnet_closure_chain(self):
        """Test 3: P0 testnet closure chain (spot+futures)"""
        print("\n=== TEST 3: P0 TESTNET CLOSURE CHAIN ===")
        
        if not self.admin_token:
            self.log_result("P0 Testnet Closure Chain", "FAIL", "No admin token available")
            return
        
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Test POST /api/admin/commercial/p0/ingest/binance
        try:
            ingest_data = {
                "environment": "testnet",
                "market_types": ["spot", "futures"],
                "target_user_email": USER_EMAIL
            }
            
            response = requests.post(
                f"{BASE_URL}/api/admin/commercial/p0/ingest/binance",
                json=ingest_data,
                headers=headers,
                timeout=60  # Longer timeout for ingest
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("POST /api/admin/commercial/p0/ingest/binance", "PASS", f"Ingest completed: {data.get('status', 'N/A')}")
            elif response.status_code == 451:
                # Regional restriction is expected for spot
                self.log_result("POST /api/admin/commercial/p0/ingest/binance", "PARTIAL", f"Regional restriction (451): {response.text}")
            else:
                self.log_result("POST /api/admin/commercial/p0/ingest/binance", "FAIL", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("POST /api/admin/commercial/p0/ingest/binance", "FAIL", f"Exception: {str(e)}")
        
        # Test GET /api/admin/commercial/p0/pnl/latest
        try:
            params = {"target_user_email": USER_EMAIL}
            response = requests.get(f"{BASE_URL}/api/admin/commercial/p0/pnl/latest", params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                pnl_data = data.get("pnl", {})
                self.log_result("GET /api/admin/commercial/p0/pnl/latest", "PASS", f"PnL data retrieved: realized={pnl_data.get('realized', {}).get('gross_usd', 'N/A')}")
            else:
                self.log_result("GET /api/admin/commercial/p0/pnl/latest", "FAIL", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("GET /api/admin/commercial/p0/pnl/latest", "FAIL", f"Exception: {str(e)}")
        
        # Test POST /api/admin/commercial/p0/reconciliation/run
        try:
            reconciliation_data = {
                "drift_tolerance_pct": 0.3,
                "start_ts": (datetime.now() - timedelta(days=120)).isoformat(),
                "target_user_email": USER_EMAIL
            }
            
            response = requests.post(
                f"{BASE_URL}/api/admin/commercial/p0/reconciliation/run",
                json=reconciliation_data,
                headers=headers,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("POST /api/admin/commercial/p0/reconciliation/run", "PASS", f"Reconciliation completed: drift_within_tolerance={data.get('drift_within_tolerance', 'N/A')}")
            else:
                self.log_result("POST /api/admin/commercial/p0/reconciliation/run", "FAIL", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("POST /api/admin/commercial/p0/reconciliation/run", "FAIL", f"Exception: {str(e)}")
        
        # Test GET /api/admin/commercial/p0/data-quality
        try:
            params = {"target_user_email": USER_EMAIL}
            response = requests.get(f"{BASE_URL}/api/admin/commercial/p0/data-quality", params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("GET /api/admin/commercial/p0/data-quality", "PASS", f"Data quality retrieved: futures_freshness={data.get('futures_freshness', 'N/A')} seconds")
            else:
                self.log_result("GET /api/admin/commercial/p0/data-quality", "FAIL", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("GET /api/admin/commercial/p0/data-quality", "FAIL", f"Exception: {str(e)}")
        
        # Test GET /api/admin/commercial/p0/live-gate
        try:
            params = {
                "required_market_types": ["spot", "futures"],
                "target_user_email": USER_EMAIL
            }
            
            response = requests.get(
                f"{BASE_URL}/api/admin/commercial/p0/live-gate",
                params=params,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("GET /api/admin/commercial/p0/live-gate", "PASS", f"Live gate status: ready={data.get('ready', 'N/A')}")
            else:
                self.log_result("GET /api/admin/commercial/p0/live-gate", "FAIL", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("GET /api/admin/commercial/p0/live-gate", "FAIL", f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("ADMIN CREDENTIAL ORCHESTRATION LAYER BACKEND TEST")
        print("=" * 60)
        print(f"Base URL: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print(f"User: {USER_EMAIL}")
        print(f"Test Start: {datetime.now().isoformat()}")
        print()
        
        # Login first
        admin_login_success = self.admin_login()
        user_login_success = self.user_login()
        
        if not admin_login_success:
            print("❌ Cannot proceed without admin login")
            return
        
        # Run tests
        self.test_orchestration_endpoints()
        self.test_user_response_enrichment()
        self.test_p0_testnet_closure_chain()
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        pass_count = sum(1 for r in self.test_results if r["status"] == "PASS")
        fail_count = sum(1 for r in self.test_results if r["status"] == "FAIL")
        partial_count = sum(1 for r in self.test_results if r["status"] == "PARTIAL")
        total_count = len(self.test_results)
        
        print(f"Total Tests: {total_count}")
        print(f"✅ PASS: {pass_count}")
        print(f"❌ FAIL: {fail_count}")
        print(f"⚠️ PARTIAL: {partial_count}")
        print(f"Success Rate: {(pass_count / total_count * 100):.1f}%")
        
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_symbol} {result['test']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        # Determine overall result
        if fail_count == 0:
            if partial_count == 0:
                print(f"\n🎯 OVERALL RESULT: ✅ ALL PASS - Admin Credential Orchestration Layer backend validation successful")
            else:
                print(f"\n🎯 OVERALL RESULT: ⚠️ MOSTLY PASS - {pass_count} PASS, {partial_count} PARTIAL, 0 FAIL")
        else:
            print(f"\n🎯 OVERALL RESULT: ❌ ISSUES DETECTED - {fail_count} tests failed")
        
        return fail_count == 0

if __name__ == "__main__":
    tester = AdminCredentialOrchestrationTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)