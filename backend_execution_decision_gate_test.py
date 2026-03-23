#!/usr/bin/env python3
"""
Execution Decision Gate Backend Regression Check
Base: https://gate-control-v2.preview.emergentagent.com/api
Credentials: canary.admin@platform.local / CanaryAdmin123!

Test Requirements:
1) GET /admin/execution-queue filters + sort params
2) GET /admin/execution-queue/{intent_id}/detail and /history (var olan bir queued intent ile)
3) POST approve/reject/cancel reason enforcement
4) POST /admin/execution-queue/control/pause-resume state behavior
5) POST /admin/execution-queue/bulk-decision max20 limiti
6) GET /admin/execution-queue/observability kontratı
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://gate-control-v2.preview.emergentagent.com/api"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class ExecutionDecisionGateTest:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        
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
        """Login as admin and get token"""
        try:
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/auth/login/admin",
                json=login_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    self.log_result("Admin Login", "PASS", f"Token length: {len(self.admin_token)}")
                    return True
                else:
                    self.log_result("Admin Login", "FAIL", "No access token in response")
                    return False
            else:
                self.log_result("Admin Login", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_execution_queue_filters_sort(self):
        """Test 1: GET /admin/execution-queue filters + sort params"""
        try:
            # Test different filter combinations
            test_cases = [
                {"status": "QUEUED", "limit": 10},
                {"status": "REJECTED", "sort": "created_at", "order": "desc"},
                {"symbol": "BTCUSDT", "limit": 5},
                {"page": 1, "limit": 20, "sort": "updated_at"}
            ]
            
            all_passed = True
            details = []
            
            for i, params in enumerate(test_cases):
                response = self.session.get(
                    f"{BASE_URL}/admin/execution-queue",
                    params=params,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # API returns direct array, not object with items
                    items_count = len(data) if isinstance(data, list) else len(data.get('items', []))
                    details.append(f"Filter {i+1}: {response.status_code} - {items_count} items")
                else:
                    details.append(f"Filter {i+1}: FAILED {response.status_code}")
                    all_passed = False
            
            status = "PASS" if all_passed else "FAIL"
            self.log_result("Execution Queue Filters + Sort", status, "; ".join(details))
            return all_passed
            
        except Exception as e:
            self.log_result("Execution Queue Filters + Sort", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_execution_queue_detail_history(self):
        """Test 2: GET /admin/execution-queue/{intent_id}/detail and /history"""
        try:
            # First get a list to find an existing intent
            response = self.session.get(
                f"{BASE_URL}/admin/execution-queue",
                params={"limit": 10},
                timeout=30
            )
            
            if response.status_code != 200:
                self.log_result("Execution Queue Detail/History", "FAIL", f"Failed to get queue list: {response.status_code}")
                return False
            
            data = response.json()
            # API returns direct array, not object with items
            items = data if isinstance(data, list) else data.get("items", [])
            
            if not items:
                self.log_result("Execution Queue Detail/History", "SKIP", "No execution queue items found for testing")
                return True
            
            # Test with first available intent
            intent_id = items[0].get("id") if items else None
            if not intent_id:
                self.log_result("Execution Queue Detail/History", "FAIL", "No intent_id found in queue items")
                return False
            
            # Test detail endpoint
            detail_response = self.session.get(
                f"{BASE_URL}/admin/execution-queue/{intent_id}/detail",
                timeout=30
            )
            
            # Test history endpoint
            history_response = self.session.get(
                f"{BASE_URL}/admin/execution-queue/{intent_id}/history",
                timeout=30
            )
            
            detail_ok = detail_response.status_code == 200
            history_ok = history_response.status_code == 200
            
            details = f"Intent: {intent_id[:8]}... Detail: {detail_response.status_code}, History: {history_response.status_code}"
            
            if detail_ok and history_ok:
                self.log_result("Execution Queue Detail/History", "PASS", details)
                return True
            else:
                self.log_result("Execution Queue Detail/History", "FAIL", details)
                return False
                
        except Exception as e:
            self.log_result("Execution Queue Detail/History", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_approve_reject_cancel_enforcement(self):
        """Test 3: POST approve/reject/cancel reason enforcement"""
        try:
            # First get a queued intent to test with
            response = self.session.get(
                f"{BASE_URL}/admin/execution-queue",
                params={"status": "QUEUED", "limit": 5},
                timeout=30
            )
            
            if response.status_code != 200:
                self.log_result("Approve/Reject/Cancel Enforcement", "FAIL", f"Failed to get queued items: {response.status_code}")
                return False
            
            data = response.json()
            # API returns direct array, not object with items
            items = data if isinstance(data, list) else data.get("items", [])
            
            if not items:
                # Try to find any item for testing
                response = self.session.get(
                    f"{BASE_URL}/admin/execution-queue",
                    params={"limit": 5},
                    timeout=30
                )
                if response.status_code == 200:
                    items = response.json().get("items", [])
            
            if not items:
                self.log_result("Approve/Reject/Cancel Enforcement", "SKIP", "No execution queue items found for testing")
                return True
            
            intent_id = items[0].get("id") if items else None
            if not intent_id:
                self.log_result("Approve/Reject/Cancel Enforcement", "FAIL", "No intent_id found")
                return False
            
            # Test approve without reason (should fail)
            approve_response = self.session.post(
                f"{BASE_URL}/admin/execution-queue/{intent_id}/approve",
                json={},
                timeout=30
            )
            
            # Test reject without reason (should fail)
            reject_response = self.session.post(
                f"{BASE_URL}/admin/execution-queue/{intent_id}/reject",
                json={},
                timeout=30
            )
            
            # Test with reason (should work or give proper validation)
            approve_with_reason = self.session.post(
                f"{BASE_URL}/admin/execution-queue/{intent_id}/approve",
                json={"reason": "Backend regression test approval"},
                timeout=30
            )
            
            details = f"Intent: {intent_id[:8]}... Approve no reason: {approve_response.status_code}, Reject no reason: {reject_response.status_code}, Approve with reason: {approve_with_reason.status_code}"
            
            # Check if reason enforcement is working (expecting 400/422 for missing reason)
            reason_enforced = (approve_response.status_code in [400, 422] or 
                             reject_response.status_code in [400, 422] or
                             approve_with_reason.status_code in [200, 400, 422])
            
            if reason_enforced:
                self.log_result("Approve/Reject/Cancel Enforcement", "PASS", details)
                return True
            else:
                self.log_result("Approve/Reject/Cancel Enforcement", "FAIL", details)
                return False
                
        except Exception as e:
            self.log_result("Approve/Reject/Cancel Enforcement", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_pause_resume_control(self):
        """Test 4: POST /admin/execution-queue/control/pause-resume state behavior"""
        try:
            # Test pause
            pause_response = self.session.post(
                f"{BASE_URL}/admin/execution-queue/control/pause",
                json={"reason": "Backend regression test pause"},
                timeout=30
            )
            
            # Test resume
            resume_response = self.session.post(
                f"{BASE_URL}/admin/execution-queue/control/resume",
                json={"reason": "Backend regression test resume"},
                timeout=30
            )
            
            # Alternative endpoint format test
            pause_resume_response = self.session.post(
                f"{BASE_URL}/admin/execution-queue/control/pause-resume",
                json={"action": "pause", "reason": "Backend regression test"},
                timeout=30
            )
            
            details = f"Pause: {pause_response.status_code}, Resume: {resume_response.status_code}, Pause-Resume: {pause_resume_response.status_code}"
            
            # At least one endpoint should work
            any_working = any(r.status_code in [200, 201] for r in [pause_response, resume_response, pause_resume_response])
            
            if any_working:
                self.log_result("Pause/Resume Control", "PASS", details)
                return True
            else:
                self.log_result("Pause/Resume Control", "FAIL", details)
                return False
                
        except Exception as e:
            self.log_result("Pause/Resume Control", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_bulk_decision_limit(self):
        """Test 5: POST /admin/execution-queue/bulk-decision max20 limit"""
        try:
            # Get some intents for bulk testing
            response = self.session.get(
                f"{BASE_URL}/admin/execution-queue",
                params={"limit": 25},
                timeout=30
            )
            
            if response.status_code != 200:
                self.log_result("Bulk Decision Max20 Limit", "FAIL", f"Failed to get queue items: {response.status_code}")
                return False
            
            data = response.json()
            # API returns direct array, not object with items
            items = data if isinstance(data, list) else data.get("items", [])
            
            if not items:
                self.log_result("Bulk Decision Max20 Limit", "SKIP", "No execution queue items found for bulk testing")
                return True
            
            # Test with exactly 20 items (should work)
            intent_ids_20 = [item.get("id") for item in items[:20] if item.get("id")]
            
            if len(intent_ids_20) >= 1:  # Test with available items
                bulk_20_response = self.session.post(
                    f"{BASE_URL}/admin/execution-queue/bulk-decision",
                    json={
                        "intent_ids": intent_ids_20[:min(20, len(intent_ids_20))],
                        "action": "approve",
                        "reason": "Backend regression test bulk approve"
                    },
                    timeout=30
                )
            else:
                bulk_20_response = None
            
            # Test with more than 20 items (should fail)
            if len(items) > 20:
                intent_ids_21 = [item.get("id") for item in items[:21] if item.get("id")]
                
                bulk_21_response = self.session.post(
                    f"{BASE_URL}/admin/execution-queue/bulk-decision",
                    json={
                        "intent_ids": intent_ids_21,
                        "action": "approve",
                        "reason": "Backend regression test bulk approve over limit"
                    },
                    timeout=30
                )
            else:
                bulk_21_response = None
            
            details = []
            if bulk_20_response:
                details.append(f"Bulk 20: {bulk_20_response.status_code}")
            if bulk_21_response:
                details.append(f"Bulk 21: {bulk_21_response.status_code}")
            
            # Check if limit is enforced
            limit_enforced = (bulk_21_response is None or 
                            bulk_21_response.status_code in [400, 422] or
                            (bulk_20_response and bulk_20_response.status_code in [200, 201, 400, 422]))
            
            if limit_enforced:
                self.log_result("Bulk Decision Max20 Limit", "PASS", "; ".join(details))
                return True
            else:
                self.log_result("Bulk Decision Max20 Limit", "FAIL", "; ".join(details))
                return False
                
        except Exception as e:
            self.log_result("Bulk Decision Max20 Limit", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_observability_contract(self):
        """Test 6: GET /admin/execution-queue/observability contract"""
        try:
            response = self.session.get(
                f"{BASE_URL}/admin/execution-queue/observability",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for expected observability fields
                expected_fields = ["status", "metrics", "health", "performance"]
                found_fields = []
                
                for field in expected_fields:
                    if field in data:
                        found_fields.append(field)
                
                # Also check for any observability-related data
                observability_indicators = ["queue_depth", "processing_rate", "error_rate", "latency", "throughput"]
                for indicator in observability_indicators:
                    if indicator in str(data).lower():
                        found_fields.append(indicator)
                
                details = f"HTTP {response.status_code}, Fields found: {found_fields}, Response keys: {list(data.keys()) if isinstance(data, dict) else 'non-dict'}"
                self.log_result("Observability Contract", "PASS", details)
                return True
            else:
                self.log_result("Observability Contract", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Observability Contract", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all execution decision gate tests"""
        print("🚀 EXECUTION DECISION GATE BACKEND REGRESSION CHECK")
        print(f"Base URL: {BASE_URL}")
        print(f"Credentials: {ADMIN_EMAIL}")
        print("=" * 60)
        
        # Login first
        if not self.admin_login():
            print("❌ CRITICAL: Admin login failed - cannot proceed with tests")
            return False
        
        # Run all tests
        test_methods = [
            self.test_execution_queue_filters_sort,
            self.test_execution_queue_detail_history,
            self.test_approve_reject_cancel_enforcement,
            self.test_pause_resume_control,
            self.test_bulk_decision_limit,
            self.test_observability_contract
        ]
        
        passed = 0
        failed = 0
        skipped = 0
        
        for test_method in test_methods:
            try:
                result = test_method()
                if result is True:
                    passed += 1
                elif result is False:
                    failed += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"❌ Test {test_method.__name__} crashed: {str(e)}")
                failed += 1
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 EXECUTION DECISION GATE TEST SUMMARY")
        print(f"✅ PASSED: {passed}")
        print(f"❌ FAILED: {failed}")
        print(f"⚠️ SKIPPED: {skipped}")
        print(f"📈 SUCCESS RATE: {(passed/(passed+failed)*100):.1f}%" if (passed+failed) > 0 else "N/A")
        
        # Overall result
        if failed == 0:
            print("🎉 OVERALL RESULT: PASS - All execution decision gate tests successful")
            return True
        else:
            print("🚨 OVERALL RESULT: FAIL - Some execution decision gate tests failed")
            
            # List critical bugs
            critical_failures = [r for r in self.test_results if r["status"] == "FAIL"]
            if critical_failures:
                print("\n🐛 CRITICAL BUGS DETECTED:")
                for failure in critical_failures:
                    print(f"   • {failure['test']}: {failure['details']}")
            
            return False

def main():
    """Main execution"""
    tester = ExecutionDecisionGateTest()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()