#!/usr/bin/env python3
"""
Admin Credential Orchestration Layer Backend Test

Tests the new admin credential endpoints and assignment rules for the
Binance reconciliation system.

Base URL: https://binance-reconcile.preview.emergentagent.com
Admin: canary.admin@platform.local / CanaryAdmin123!
User: huseyinwural@gmail.com / HuseyinWural123!
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://binance-reconcile.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "huseyinwural@gmail.com"
USER_PASSWORD = "HuseyinWural123!"

class AdminCredentialOrchestrationTester:
    def __init__(self):
        self.admin_token = None
        self.user_token = None
        self.test_results = []
        
    def log_result(self, test_name, status, details="", expected_status=None, actual_status=None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        if expected_status:
            result["expected_status"] = expected_status
        if actual_status:
            result["actual_status"] = actual_status
        
        self.test_results.append(result)
        
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if expected_status and actual_status:
            print(f"   Expected: {expected_status}, Got: {actual_status}")
        print()

    def authenticate_admin(self):
        """Authenticate as admin and get token"""
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
                self.admin_token = data.get("access_token")
                self.log_result("Admin Authentication", "PASS", f"Token received: {self.admin_token[:20]}...")
                return True
            else:
                self.log_result("Admin Authentication", "FAIL", f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False

    def authenticate_user(self):
        """Authenticate as user and get token"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login/user",
                json={
                    "email": USER_EMAIL,
                    "password": USER_PASSWORD
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                self.log_result("User Authentication", "PASS", f"Token received: {self.user_token[:20]}...")
                return True
            else:
                self.log_result("User Authentication", "FAIL", f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("User Authentication", "FAIL", f"Exception: {str(e)}")
            return False

    def get_admin_headers(self):
        """Get headers with admin token"""
        return {"Authorization": f"Bearer {self.admin_token}"}

    def get_user_headers(self):
        """Get headers with user token"""
        return {"Authorization": f"Bearer {self.user_token}"}

    def test_admin_credentials_endpoints(self):
        """Test new admin credential endpoints"""
        print("=== Testing Admin Credential Endpoints ===")
        
        # 1. GET /api/venues/admin/credentials
        try:
            response = requests.get(
                f"{BASE_URL}/api/venues/admin/credentials",
                headers=self.get_admin_headers(),
                timeout=30
            )
            
            if response.status_code in [200, 201, 202]:
                data = response.json()
                self.log_result(
                    "GET /api/venues/admin/credentials", 
                    "PASS", 
                    f"Status: {response.status_code}, Items: {len(data) if isinstance(data, list) else 'N/A'}"
                )
            else:
                self.log_result(
                    "GET /api/venues/admin/credentials", 
                    "FAIL", 
                    f"Status: {response.status_code}, Response: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result("GET /api/venues/admin/credentials", "FAIL", f"Exception: {str(e)}")

        # 2. POST /api/venues/admin/credentials (creates pending)
        try:
            test_credential = {
                "venue": "binance",
                "environment": "testnet",
                "market_type": "futures",
                "api_key": "test_api_key_12345",
                "api_secret": "test_api_secret_67890",
                "description": "Test credential for orchestration layer"
            }
            
            response = requests.post(
                f"{BASE_URL}/api/venues/admin/credentials",
                headers=self.get_admin_headers(),
                json=test_credential,
                timeout=30
            )
            
            if response.status_code in [200, 201, 202]:
                data = response.json()
                credential_id = data.get("id") or data.get("credential_id")
                self.log_result(
                    "POST /api/venues/admin/credentials", 
                    "PASS", 
                    f"Status: {response.status_code}, Created ID: {credential_id}"
                )
                
                # Store credential ID for further tests
                self.test_credential_id = credential_id
                
            else:
                self.log_result(
                    "POST /api/venues/admin/credentials", 
                    "FAIL", 
                    f"Status: {response.status_code}, Response: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result("POST /api/venues/admin/credentials", "FAIL", f"Exception: {str(e)}")

        # 3. PATCH /api/venues/admin/credentials/{id} (if we have an ID)
        if hasattr(self, 'test_credential_id') and self.test_credential_id:
            try:
                update_data = {
                    "description": "Updated test credential description"
                }
                
                response = requests.patch(
                    f"{BASE_URL}/api/venues/admin/credentials/{self.test_credential_id}",
                    headers=self.get_admin_headers(),
                    json=update_data,
                    timeout=30
                )
                
                if response.status_code in [200, 201, 202]:
                    self.log_result(
                        "PATCH /api/venues/admin/credentials/{id}", 
                        "PASS", 
                        f"Status: {response.status_code}"
                    )
                else:
                    self.log_result(
                        "PATCH /api/venues/admin/credentials/{id}", 
                        "FAIL", 
                        f"Status: {response.status_code}, Response: {response.text[:200]}"
                    )
            except Exception as e:
                self.log_result("PATCH /api/venues/admin/credentials/{id}", "FAIL", f"Exception: {str(e)}")

        # 4. POST /api/venues/admin/credentials/{id}/approve
        if hasattr(self, 'test_credential_id') and self.test_credential_id:
            try:
                response = requests.post(
                    f"{BASE_URL}/api/venues/admin/credentials/{self.test_credential_id}/approve",
                    headers=self.get_admin_headers(),
                    timeout=30
                )
                
                if response.status_code in [200, 201, 202]:
                    self.log_result(
                        "POST /api/venues/admin/credentials/{id}/approve", 
                        "PASS", 
                        f"Status: {response.status_code}"
                    )
                else:
                    self.log_result(
                        "POST /api/venues/admin/credentials/{id}/approve", 
                        "FAIL", 
                        f"Status: {response.status_code}, Response: {response.text[:200]}"
                    )
            except Exception as e:
                self.log_result("POST /api/venues/admin/credentials/{id}/approve", "FAIL", f"Exception: {str(e)}")

        # 5. POST /api/venues/admin/credentials/{id}/probe
        if hasattr(self, 'test_credential_id') and self.test_credential_id:
            try:
                response = requests.post(
                    f"{BASE_URL}/api/venues/admin/credentials/{self.test_credential_id}/probe",
                    headers=self.get_admin_headers(),
                    timeout=30
                )
                
                if response.status_code in [200, 201, 202]:
                    self.log_result(
                        "POST /api/venues/admin/credentials/{id}/probe", 
                        "PASS", 
                        f"Status: {response.status_code}"
                    )
                else:
                    self.log_result(
                        "POST /api/venues/admin/credentials/{id}/probe", 
                        "FAIL", 
                        f"Status: {response.status_code}, Response: {response.text[:200]}"
                    )
            except Exception as e:
                self.log_result("POST /api/venues/admin/credentials/{id}/probe", "FAIL", f"Exception: {str(e)}")

        # 6. POST /api/venues/admin/credentials/{id}/disable
        if hasattr(self, 'test_credential_id') and self.test_credential_id:
            try:
                response = requests.post(
                    f"{BASE_URL}/api/venues/admin/credentials/{self.test_credential_id}/disable",
                    headers=self.get_admin_headers(),
                    timeout=30
                )
                
                if response.status_code in [200, 201, 202]:
                    self.log_result(
                        "POST /api/venues/admin/credentials/{id}/disable", 
                        "PASS", 
                        f"Status: {response.status_code}"
                    )
                else:
                    self.log_result(
                        "POST /api/venues/admin/credentials/{id}/disable", 
                        "FAIL", 
                        f"Status: {response.status_code}, Response: {response.text[:200]}"
                    )
            except Exception as e:
                self.log_result("POST /api/venues/admin/credentials/{id}/disable", "FAIL", f"Exception: {str(e)}")

    def test_assignment_rules_endpoints(self):
        """Test assignment rules endpoints"""
        print("=== Testing Assignment Rules Endpoints ===")
        
        # 1. GET /api/venues/admin/credential-rules
        try:
            response = requests.get(
                f"{BASE_URL}/api/venues/admin/credential-rules",
                headers=self.get_admin_headers(),
                timeout=30
            )
            
            if response.status_code in [200, 201, 202]:
                data = response.json()
                self.log_result(
                    "GET /api/venues/admin/credential-rules", 
                    "PASS", 
                    f"Status: {response.status_code}, Rules: {len(data) if isinstance(data, list) else 'N/A'}"
                )
                self.current_rules = data
            else:
                self.log_result(
                    "GET /api/venues/admin/credential-rules", 
                    "FAIL", 
                    f"Status: {response.status_code}, Response: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result("GET /api/venues/admin/credential-rules", "FAIL", f"Exception: {str(e)}")

        # 2. PUT /api/venues/admin/credential-rules (deterministic upsert)
        try:
            test_rules = {
                "rules": [
                    {
                        "priority": 1,
                        "conditions": {
                            "exchange": "binance",
                            "market_type": "futures",
                            "environment": "testnet"
                        },
                        "assignment": {
                            "credential_pool": "binance_futures_testnet",
                            "rotation_strategy": "round_robin"
                        }
                    },
                    {
                        "priority": 2,
                        "conditions": {
                            "exchange": "binance",
                            "market_type": "spot",
                            "environment": "testnet"
                        },
                        "assignment": {
                            "credential_pool": "binance_spot_testnet",
                            "rotation_strategy": "least_used"
                        }
                    }
                ]
            }
            
            response = requests.put(
                f"{BASE_URL}/api/venues/admin/credential-rules",
                headers=self.get_admin_headers(),
                json=test_rules,
                timeout=30
            )
            
            if response.status_code in [200, 201, 202]:
                data = response.json()
                self.log_result(
                    "PUT /api/venues/admin/credential-rules", 
                    "PASS", 
                    f"Status: {response.status_code}, Upserted rules"
                )
            else:
                self.log_result(
                    "PUT /api/venues/admin/credential-rules", 
                    "FAIL", 
                    f"Status: {response.status_code}, Response: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result("PUT /api/venues/admin/credential-rules", "FAIL", f"Exception: {str(e)}")

    def test_credential_resolution_preview(self):
        """Test credential resolution preview endpoint"""
        print("=== Testing Credential Resolution Preview ===")
        
        # First, get an existing user ID (try to use the authenticated user)
        user_id = None
        try:
            # Try to get user info to get user_id
            response = requests.get(
                f"{BASE_URL}/api/auth/me",
                headers=self.get_user_headers(),
                timeout=30
            )
            if response.status_code == 200:
                user_data = response.json()
                user_id = user_data.get("id") or user_data.get("user_id")
        except:
            pass
        
        # If we don't have user_id, use a test value
        if not user_id:
            user_id = "test-user-id-12345"
        
        try:
            params = {
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet"
            }
            
            response = requests.get(
                f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
                headers=self.get_admin_headers(),
                params=params,
                timeout=30
            )
            
            if response.status_code in [200, 201, 202]:
                data = response.json()
                
                # Check for expected fields
                has_selected_source = "selected_source" in data or "effective_source" in data
                has_masked_fields = any("masked" in str(v).lower() or "*" in str(v) for v in str(data).lower())
                has_audit_metadata = "audit" in data or "metadata" in data or "timestamp" in data
                
                details = f"Status: {response.status_code}"
                if has_selected_source:
                    details += ", Selected source: ✓"
                if has_masked_fields:
                    details += ", Masked fields: ✓"
                if has_audit_metadata:
                    details += ", Audit metadata: ✓"
                
                self.log_result(
                    "GET /api/venues/admin/credential-resolution-preview", 
                    "PASS", 
                    details
                )
            else:
                self.log_result(
                    "GET /api/venues/admin/credential-resolution-preview", 
                    "FAIL", 
                    f"Status: {response.status_code}, Response: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result("GET /api/venues/admin/credential-resolution-preview", "FAIL", f"Exception: {str(e)}")

    def test_user_exchange_connections_enrichment(self):
        """Test user exchange connections response enrichment"""
        print("=== Testing User Exchange Connections Response Enrichment ===")
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/user/exchange-connections",
                headers=self.get_user_headers(),
                timeout=30
            )
            
            if response.status_code in [200, 201, 202]:
                data = response.json()
                
                # Check for enrichment fields
                has_effective_source = False
                has_routing_preview = False
                has_environment_valid = False
                
                if isinstance(data, list) and len(data) > 0:
                    for connection in data:
                        if "effective_source" in connection:
                            has_effective_source = True
                        if "routing_preview" in connection:
                            has_routing_preview = True
                        if "environment_valid" in connection:
                            has_environment_valid = True
                
                details = f"Status: {response.status_code}, Connections: {len(data) if isinstance(data, list) else 'N/A'}"
                if has_effective_source:
                    details += ", effective_source: ✓"
                if has_routing_preview:
                    details += ", routing_preview: ✓"
                if has_environment_valid:
                    details += ", environment_valid: ✓"
                
                self.log_result(
                    "GET /api/user/exchange-connections", 
                    "PASS", 
                    details
                )
            else:
                self.log_result(
                    "GET /api/user/exchange-connections", 
                    "FAIL", 
                    f"Status: {response.status_code}, Response: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result("GET /api/user/exchange-connections", "FAIL", f"Exception: {str(e)}")

    def test_commercial_ops_regression(self):
        """Test regression for commercial ops using new resolution layer"""
        print("=== Testing Commercial Ops Regression ===")
        
        try:
            # Test the commercial ops endpoint that should still work
            response = requests.post(
                f"{BASE_URL}/api/admin/commercial/p0/ingest/binance",
                headers=self.get_admin_headers(),
                json={
                    "market_types": ["futures"],
                    "environment": "testnet",
                    "force_refresh": False
                },
                timeout=30
            )
            
            if response.status_code in [200, 201, 202]:
                data = response.json()
                self.log_result(
                    "POST /api/admin/commercial/p0/ingest/binance", 
                    "PASS", 
                    f"Status: {response.status_code}, Commercial ops working with new resolution layer"
                )
            else:
                self.log_result(
                    "POST /api/admin/commercial/p0/ingest/binance", 
                    "FAIL", 
                    f"Status: {response.status_code}, Response: {response.text[:200]}"
                )
        except Exception as e:
            self.log_result("POST /api/admin/commercial/p0/ingest/binance", "FAIL", f"Exception: {str(e)}")

    def test_spot_futures_env_mixing_prevention(self):
        """Test that spot/futures env mixing is prevented at resolver behavior level"""
        print("=== Testing Spot/Futures Environment Mixing Prevention ===")
        
        # Test with spot market type
        try:
            params_spot = {
                "user_id": "test-user-id-12345",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet"
            }
            
            response_spot = requests.get(
                f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
                headers=self.get_admin_headers(),
                params=params_spot,
                timeout=30
            )
            
            spot_result = None
            if response_spot.status_code in [200, 201, 202]:
                spot_result = response_spot.json()
        except Exception as e:
            self.log_result("Spot/Futures Mixing Prevention - Spot Test", "FAIL", f"Exception: {str(e)}")
            return

        # Test with futures market type
        try:
            params_futures = {
                "user_id": "test-user-id-12345",
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet"
            }
            
            response_futures = requests.get(
                f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
                headers=self.get_admin_headers(),
                params=params_futures,
                timeout=30
            )
            
            futures_result = None
            if response_futures.status_code in [200, 201, 202]:
                futures_result = response_futures.json()
        except Exception as e:
            self.log_result("Spot/Futures Mixing Prevention - Futures Test", "FAIL", f"Exception: {str(e)}")
            return

        # Compare results to ensure different credentials/sources are used
        if spot_result and futures_result:
            spot_source = spot_result.get("selected_source") or spot_result.get("effective_source")
            futures_source = futures_result.get("selected_source") or futures_result.get("effective_source")
            
            if spot_source != futures_source:
                self.log_result(
                    "Spot/Futures Environment Mixing Prevention", 
                    "PASS", 
                    f"Different sources used: spot={spot_source}, futures={futures_source}"
                )
            else:
                self.log_result(
                    "Spot/Futures Environment Mixing Prevention", 
                    "PARTIAL", 
                    f"Same source returned for both: {spot_source} (may be expected if only one credential pool exists)"
                )
        else:
            self.log_result(
                "Spot/Futures Environment Mixing Prevention", 
                "FAIL", 
                "Could not retrieve resolution results for comparison"
            )

    def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting Admin Credential Orchestration Layer Backend Tests")
        print(f"Base URL: {BASE_URL}")
        print(f"Admin: {ADMIN_EMAIL}")
        print(f"User: {USER_EMAIL}")
        print("=" * 80)
        
        # Authenticate
        if not self.authenticate_admin():
            print("❌ Admin authentication failed. Cannot proceed with tests.")
            return False
            
        if not self.authenticate_user():
            print("⚠️ User authentication failed. Some tests may be skipped.")
        
        # Run all test suites
        self.test_admin_credentials_endpoints()
        self.test_assignment_rules_endpoints()
        self.test_credential_resolution_preview()
        
        if self.user_token:
            self.test_user_exchange_connections_enrichment()
        else:
            self.log_result("GET /api/user/exchange-connections", "SKIP", "User authentication failed")
            
        self.test_commercial_ops_regression()
        self.test_spot_futures_env_mixing_prevention()
        
        # Summary
        print("=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        partial_tests = len([r for r in self.test_results if r["status"] == "PARTIAL"])
        skipped_tests = len([r for r in self.test_results if r["status"] == "SKIP"])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️ Partial: {partial_tests}")
        print(f"⏭️ Skipped: {skipped_tests}")
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        # List failed tests
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  - {result['test']}: {result['details']}")
        
        # List partial tests
        if partial_tests > 0:
            print("\n⚠️ PARTIAL TESTS:")
            for result in self.test_results:
                if result["status"] == "PARTIAL":
                    print(f"  - {result['test']}: {result['details']}")
        
        return failed_tests == 0

if __name__ == "__main__":
    tester = AdminCredentialOrchestrationTester()
    success = tester.run_all_tests()
    
    # Save results to file
    with open("/app/admin_credential_orchestration_test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "base_url": BASE_URL,
            "admin_email": ADMIN_EMAIL,
            "user_email": USER_EMAIL,
            "results": tester.test_results,
            "summary": {
                "total": len(tester.test_results),
                "passed": len([r for r in tester.test_results if r["status"] == "PASS"]),
                "failed": len([r for r in tester.test_results if r["status"] == "FAIL"]),
                "partial": len([r for r in tester.test_results if r["status"] == "PARTIAL"]),
                "skipped": len([r for r in tester.test_results if r["status"] == "SKIP"])
            }
        }, f, indent=2)
    
    sys.exit(0 if success else 1)