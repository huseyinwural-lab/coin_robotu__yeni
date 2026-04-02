#!/usr/bin/env python3
"""
FAZ C + P1 Backend Validation - Admin Commercial Overview API
Turkish Review Request: FAZ C + P1 sonrası backend doğrulaması yap

Focus Areas:
1. /api/admin/commercial/overview sözleşmesi (contract validation)
2. Default filterlar (last_30_days/live)
3. Query param davranışı (time_window/environment/from/to)
4. invalid_time_range=422 error handling
5. Financial/revenue/risk/data_quality blok tutarlılığı (block consistency)
6. TestClient tabanlı doğrulama (TestClient-based validation)
7. Preview URL 502 handling with infrastructure notes

Base URL: https://trade-trace-engine.preview.emergentagent.com
"""

import sys
import os
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Backend URL from frontend/.env
BACKEND_URL = "https://trade-trace-engine.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class CommercialOverviewValidator:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.test_results = []
        
    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.test_results.append(result)
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   {details}")
    
    def authenticate(self) -> bool:
        """Authenticate with admin credentials"""
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token") or data.get("token")
                if self.auth_token:
                    self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
                    self.log_test("Admin Authentication", "PASS", f"Token received: {self.auth_token[:20]}...")
                    return True
                else:
                    self.log_test("Admin Authentication", "FAIL", "No access token in response")
                    return False
            else:
                self.log_test("Admin Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_endpoint_accessibility(self) -> bool:
        """Test basic endpoint accessibility"""
        try:
            response = self.session.get(f"{API_BASE}/admin/commercial/overview", timeout=30)
            
            if response.status_code == 502:
                self.log_test("Endpoint Accessibility", "INFRA_NOTE", 
                             "502 Service Down - Infrastructure issue detected. Backend service unavailable.")
                return False
            elif response.status_code in [200, 401, 403]:
                self.log_test("Endpoint Accessibility", "PASS", 
                             f"Endpoint accessible (HTTP {response.status_code})")
                return True
            else:
                self.log_test("Endpoint Accessibility", "FAIL", 
                             f"Unexpected status: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Endpoint Accessibility", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_default_filters(self) -> bool:
        """Test default filter behavior (last_30_days/live)"""
        try:
            response = self.session.get(f"{API_BASE}/admin/commercial/overview", timeout=30)
            
            if response.status_code != 200:
                self.log_test("Default Filters", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            applied_filters = data.get("applied_filters", {})
            
            # Check default time_window
            time_window = applied_filters.get("time_window")
            if time_window != "last_30_days":
                self.log_test("Default Filters", "FAIL", 
                             f"Expected time_window=last_30_days, got {time_window}")
                return False
            
            # Check default environment
            environment = applied_filters.get("environment")
            if environment != "live":
                self.log_test("Default Filters", "FAIL", 
                             f"Expected environment=live, got {environment}")
                return False
            
            self.log_test("Default Filters", "PASS", 
                         f"time_window={time_window}, environment={environment}")
            return True
            
        except Exception as e:
            self.log_test("Default Filters", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_query_parameters(self) -> bool:
        """Test query parameter behavior (time_window/environment/from/to)"""
        test_cases = [
            # time_window parameter
            {"time_window": "last_7_days", "expected_time_window": "last_7_days"},
            {"time_window": "last_90_days", "expected_time_window": "last_90_days"},
            {"time_window": "all_time", "expected_time_window": "all_time"},
            
            # environment parameter
            {"environment": "live", "expected_environment": "live"},
            
            # time_window aliases
            {"time_window": "7d", "expected_time_window": "last_7_days"},
            {"time_window": "30d", "expected_time_window": "last_30_days"},
            {"time_window": "90d", "expected_time_window": "last_90_days"},
            {"time_window": "all", "expected_time_window": "all_time"},
        ]
        
        all_passed = True
        
        for case in test_cases:
            try:
                params = {k: v for k, v in case.items() if not k.startswith("expected_")}
                response = self.session.get(
                    f"{API_BASE}/admin/commercial/overview", 
                    params=params, 
                    timeout=30
                )
                
                if response.status_code != 200:
                    self.log_test(f"Query Param {params}", "FAIL", 
                                 f"HTTP {response.status_code}: {response.text}")
                    all_passed = False
                    continue
                
                data = response.json()
                applied_filters = data.get("applied_filters", {})
                
                # Check expected values
                for expected_key, expected_value in case.items():
                    if expected_key.startswith("expected_"):
                        actual_key = expected_key.replace("expected_", "")
                        actual_value = applied_filters.get(actual_key)
                        
                        if actual_value != expected_value:
                            self.log_test(f"Query Param {params}", "FAIL", 
                                         f"Expected {actual_key}={expected_value}, got {actual_value}")
                            all_passed = False
                            break
                else:
                    self.log_test(f"Query Param {params}", "PASS", 
                                 f"Applied correctly: {applied_filters}")
                    
            except Exception as e:
                self.log_test(f"Query Param {case}", "FAIL", f"Exception: {str(e)}")
                all_passed = False
        
        return all_passed
    
    def test_custom_time_range(self) -> bool:
        """Test custom from/to parameters"""
        try:
            now = datetime.utcnow()
            from_ts = (now - timedelta(days=7)).isoformat() + "Z"
            to_ts = now.isoformat() + "Z"
            
            response = self.session.get(
                f"{API_BASE}/admin/commercial/overview",
                params={"from": from_ts, "to": to_ts},
                timeout=30
            )
            
            if response.status_code != 200:
                self.log_test("Custom Time Range", "FAIL", 
                             f"HTTP {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            applied_filters = data.get("applied_filters", {})
            
            # Should set time_window to "custom"
            if applied_filters.get("time_window") != "custom":
                self.log_test("Custom Time Range", "FAIL", 
                             f"Expected time_window=custom, got {applied_filters.get('time_window')}")
                return False
            
            # Should have from_ts and to_ts
            if not applied_filters.get("from_ts") or not applied_filters.get("to_ts"):
                self.log_test("Custom Time Range", "FAIL", 
                             "Missing from_ts or to_ts in applied_filters")
                return False
            
            self.log_test("Custom Time Range", "PASS", 
                         f"Custom range applied: {applied_filters.get('from_ts')} to {applied_filters.get('to_ts')}")
            return True
            
        except Exception as e:
            self.log_test("Custom Time Range", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_invalid_time_range_422(self) -> bool:
        """Test invalid time range returns 422 invalid_time_range"""
        try:
            now = datetime.utcnow()
            from_ts = now.isoformat() + "Z"  # Now
            to_ts = (now - timedelta(days=7)).isoformat() + "Z"  # 7 days ago (invalid: from > to)
            
            response = self.session.get(
                f"{API_BASE}/admin/commercial/overview",
                params={"from": from_ts, "to": to_ts},
                timeout=30
            )
            
            if response.status_code != 422:
                self.log_test("Invalid Time Range 422", "FAIL", 
                             f"Expected HTTP 422, got {response.status_code}: {response.text}")
                return False
            
            # Check error detail contains invalid_time_range
            data = response.json()
            detail = str(data.get("detail", "")).lower()
            
            if "invalid_time_range" not in detail:
                self.log_test("Invalid Time Range 422", "FAIL", 
                             f"Expected 'invalid_time_range' in error detail, got: {detail}")
                return False
            
            self.log_test("Invalid Time Range 422", "PASS", 
                         f"Correctly returned 422 with invalid_time_range error")
            return True
            
        except Exception as e:
            self.log_test("Invalid Time Range 422", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_block_consistency(self) -> bool:
        """Test financial/revenue/risk/data_quality block consistency"""
        try:
            response = self.session.get(f"{API_BASE}/admin/commercial/overview", timeout=30)
            
            if response.status_code != 200:
                self.log_test("Block Consistency", "FAIL", 
                             f"HTTP {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            
            # Check all required blocks exist
            required_blocks = [
                "applied_filters", "financial_accuracy", "revenue_model", 
                "user_economics", "risk_summary", "usage_analytics", "data_quality"
            ]
            
            missing_blocks = []
            for block in required_blocks:
                if block not in data:
                    missing_blocks.append(block)
            
            if missing_blocks:
                self.log_test("Block Consistency", "FAIL", 
                             f"Missing blocks: {missing_blocks}")
                return False
            
            # Test financial_accuracy block consistency
            fa = data.get("financial_accuracy", {})
            
            # gross_total_usd = realized_gross_usd + unrealized_gross_usd
            realized_gross = fa.get("realized_gross_usd", 0)
            unrealized_gross = fa.get("unrealized_gross_usd", 0)
            gross_total = fa.get("gross_total_usd", 0)
            
            expected_gross = round(realized_gross + unrealized_gross, 6)
            actual_gross = round(gross_total, 6)
            
            if abs(expected_gross - actual_gross) > 0.000001:
                self.log_test("Block Consistency", "FAIL", 
                             f"Financial accuracy inconsistency: gross_total_usd={actual_gross}, expected={expected_gross}")
                return False
            
            # net_total_usd = realized_net_usd + unrealized_net_usd
            realized_net = fa.get("realized_net_usd", 0)
            unrealized_net = fa.get("unrealized_net_usd", 0)
            net_total = fa.get("net_total_usd", 0)
            
            expected_net = round(realized_net + unrealized_net, 6)
            actual_net = round(net_total, 6)
            
            if abs(expected_net - actual_net) > 0.000001:
                self.log_test("Block Consistency", "FAIL", 
                             f"Financial accuracy inconsistency: net_total_usd={actual_net}, expected={expected_net}")
                return False
            
            # Test revenue_model block consistency
            rm = data.get("revenue_model", {})
            total_revenue = rm.get("total_revenue_usd", 0)
            components = rm.get("component_breakdown", [])
            
            component_sum = sum(c.get("revenue_usd", 0) for c in components)
            
            if abs(round(total_revenue, 6) - round(component_sum, 6)) > 0.000001:
                self.log_test("Block Consistency", "FAIL", 
                             f"Revenue model inconsistency: total_revenue_usd={total_revenue}, component_sum={component_sum}")
                return False
            
            # Test risk_summary block safe defaults
            rs = data.get("risk_summary", {})
            
            if rs.get("open_position_count", -1) < 0:
                self.log_test("Block Consistency", "FAIL", 
                             "Risk summary: open_position_count should be >= 0")
                return False
            
            if rs.get("risk_exposure_usd", -1) < 0:
                self.log_test("Block Consistency", "FAIL", 
                             "Risk summary: risk_exposure_usd should be >= 0")
                return False
            
            # Test data_quality block status values
            dq = data.get("data_quality", {})
            status = dq.get("status")
            valid_statuses = ["healthy", "empty", "stale", "degraded"]
            
            if status not in valid_statuses:
                self.log_test("Block Consistency", "FAIL", 
                             f"Data quality: invalid status '{status}', expected one of {valid_statuses}")
                return False
            
            self.log_test("Block Consistency", "PASS", 
                         f"All blocks present and consistent. Financial: gross={actual_gross}, net={actual_net}. Revenue: total={total_revenue}. Data quality: {status}")
            return True
            
        except Exception as e:
            self.log_test("Block Consistency", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_contract_validation(self) -> bool:
        """Test complete contract validation"""
        try:
            response = self.session.get(f"{API_BASE}/admin/commercial/overview", timeout=30)
            
            if response.status_code != 200:
                self.log_test("Contract Validation", "FAIL", 
                             f"HTTP {response.status_code}: {response.text}")
                return False
            
            data = response.json()
            
            # Check top-level contract fields
            required_top_level = ["generated_at", "contract_version"]
            for field in required_top_level:
                if field not in data:
                    self.log_test("Contract Validation", "FAIL", 
                                 f"Missing top-level field: {field}")
                    return False
            
            # Check applied_filters structure
            af = data.get("applied_filters", {})
            required_filter_fields = ["time_window", "environment"]
            for field in required_filter_fields:
                if field not in af:
                    self.log_test("Contract Validation", "FAIL", 
                                 f"Missing applied_filters field: {field}")
                    return False
            
            # Check financial_accuracy structure
            fa = data.get("financial_accuracy", {})
            required_fa_fields = [
                "record_count", "trade_count",
                "realized_gross_usd", "unrealized_gross_usd", "gross_total_usd",
                "realized_net_usd", "unrealized_net_usd", "net_total_usd",
                "net_vs_gross_delta_usd",
                "trading_fee_total_usd", "funding_total_usd", "commission_total_usd"
            ]
            for field in required_fa_fields:
                if field not in fa:
                    self.log_test("Contract Validation", "FAIL", 
                                 f"Missing financial_accuracy field: {field}")
                    return False
            
            # Check revenue_model structure
            rm = data.get("revenue_model", {})
            required_rm_fields = ["total_revenue_usd", "component_breakdown", "top_symbols", "row_count"]
            for field in required_rm_fields:
                if field not in rm:
                    self.log_test("Contract Validation", "FAIL", 
                                 f"Missing revenue_model field: {field}")
                    return False
            
            # Check risk_summary structure
            rs = data.get("risk_summary", {})
            required_rs_fields = [
                "open_position_count", "risk_exposure_usd",
                "high_drift_reconciliation_count", "latest_daily_loss_limit_pct",
                "trading_enabled", "kill_switch_enabled", "top_exposure_symbols"
            ]
            for field in required_rs_fields:
                if field not in rs:
                    self.log_test("Contract Validation", "FAIL", 
                                 f"Missing risk_summary field: {field}")
                    return False
            
            # Check data_quality structure
            dq = data.get("data_quality", {})
            required_dq_fields = [
                "status", "empty_data", "stale_sources",
                "freshness_seconds", "stale_threshold_seconds",
                "latest_trade_at", "latest_pnl_at", "latest_reconciliation_at",
                "missing_data_alert", "trade_count", "pnl_record_count"
            ]
            for field in required_dq_fields:
                if field not in dq:
                    self.log_test("Contract Validation", "FAIL", 
                                 f"Missing data_quality field: {field}")
                    return False
            
            self.log_test("Contract Validation", "PASS", 
                         f"Complete contract validated. Contract version: {data.get('contract_version')}")
            return True
            
        except Exception as e:
            self.log_test("Contract Validation", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_validation(self):
        """Run complete validation suite"""
        print("=" * 80)
        print("FAZ C + P1 Backend Validation - Admin Commercial Overview API")
        print(f"Base URL: {BACKEND_URL}")
        print(f"Target Endpoint: /api/admin/commercial/overview")
        print("=" * 80)
        
        # Step 1: Test endpoint accessibility
        if not self.test_endpoint_accessibility():
            print("\n❌ CRITICAL: Endpoint not accessible. Stopping validation.")
            return self.generate_summary()
        
        # Step 2: Authenticate
        if not self.authenticate():
            print("\n❌ CRITICAL: Authentication failed. Stopping validation.")
            return self.generate_summary()
        
        # Step 3: Run all validation tests
        tests = [
            self.test_default_filters,
            self.test_query_parameters,
            self.test_custom_time_range,
            self.test_invalid_time_range_422,
            self.test_block_consistency,
            self.test_contract_validation
        ]
        
        for test in tests:
            test()
        
        return self.generate_summary()
    
    def generate_summary(self):
        """Generate validation summary"""
        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        infra_notes = len([r for r in self.test_results if r["status"] == "INFRA_NOTE"])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️ Infrastructure Notes: {infra_notes}")
        
        if failed_tests == 0 and infra_notes == 0:
            print(f"\n🎉 ALL TESTS PASSED ({passed_tests}/{total_tests} - 100% SUCCESS RATE)")
            overall_status = "PASS"
        elif infra_notes > 0:
            print(f"\n⚠️ INFRASTRUCTURE ISSUES DETECTED")
            overall_status = "INFRA_ISSUE"
        else:
            success_rate = (passed_tests / total_tests) * 100
            print(f"\n❌ SOME TESTS FAILED ({passed_tests}/{total_tests} - {success_rate:.1f}% SUCCESS RATE)")
            overall_status = "PARTIAL"
        
        # Detailed results
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_icon} {result['test']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        return {
            "overall_status": overall_status,
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "infra_notes": infra_notes,
            "success_rate": (passed_tests / total_tests) * 100 if total_tests > 0 else 0,
            "results": self.test_results
        }

if __name__ == "__main__":
    validator = CommercialOverviewValidator()
    summary = validator.run_validation()
    
    # Exit with appropriate code
    if summary["overall_status"] == "PASS":
        exit(0)
    elif summary["overall_status"] == "INFRA_ISSUE":
        exit(2)  # Infrastructure issue
    else:
        exit(1)  # Test failures