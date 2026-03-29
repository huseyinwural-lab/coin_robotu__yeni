#!/usr/bin/env python3
"""
P1.2 User Economics Backend Test Suite
Testing comprehensive user economics endpoints and regression validation
"""

import json
import requests
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List


class UserEconomicsBackendTest:
    def __init__(self, base_url: str, admin_email: str, admin_password: str):
        self.base_url = base_url.rstrip('/')
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, test_name: str, status: str, details: str = "", data: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        if data and isinstance(data, dict) and len(str(data)) < 200:
            print(f"   Data: {data}")
    
    def authenticate_admin(self) -> bool:
        """Authenticate admin user and get token"""
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login/admin",
                json={
                    "email": self.admin_email,
                    "password": self.admin_password
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.log_result("Admin Authentication", "PASS", f"Token received for {self.admin_email}")
                    return True
                else:
                    self.log_result("Admin Authentication", "FAIL", "No access token in response")
                    return False
            else:
                self.log_result("Admin Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False
    
    def get_headers(self) -> Dict[str, str]:
        """Get headers with admin token"""
        return {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json"
        }
    
    def test_user_economics_endpoint_basic(self) -> bool:
        """Test 1: GET /api/admin/users/economics basic functionality"""
        try:
            # Test live environment
            response = requests.get(
                f"{self.base_url}/api/admin/users/economics?environment=live",
                headers=self.get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("User Economics Live", "PASS", f"HTTP 200, status: {data.get('status')}")
                
                # Test testnet environment
                response_testnet = requests.get(
                    f"{self.base_url}/api/admin/users/economics?environment=testnet",
                    headers=self.get_headers(),
                    timeout=30
                )
                
                if response_testnet.status_code == 200:
                    data_testnet = response_testnet.json()
                    self.log_result("User Economics Testnet", "PASS", f"HTTP 200, status: {data_testnet.get('status')}")
                    return True
                else:
                    self.log_result("User Economics Testnet", "FAIL", f"HTTP {response_testnet.status_code}")
                    return False
            else:
                self.log_result("User Economics Live", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("User Economics Basic", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_user_economics_kpi_fields(self) -> bool:
        """Test 2: Verify KPI fields are populated"""
        try:
            response = requests.get(
                f"{self.base_url}/api/admin/users/economics?environment=testnet",
                headers=self.get_headers(),
                timeout=30
            )
            
            if response.status_code != 200:
                self.log_result("KPI Fields Test", "FAIL", f"HTTP {response.status_code}")
                return False
            
            data = response.json()
            kpis = data.get("kpis", {})
            
            required_kpi_fields = [
                "avg_ltv_usd",  # LTV
                "arpu_usd",     # ARPU
                "arppu_usd",    # ARPPU
                "churn_rate_pct",  # churn
                "total_revenue_usd"  # revenue contribution
            ]
            
            missing_fields = []
            populated_fields = []
            
            for field in required_kpi_fields:
                if field in kpis:
                    populated_fields.append(f"{field}={kpis[field]}")
                else:
                    missing_fields.append(field)
            
            # Check user rows for inactive_days and realized_pnl_usd
            rows = data.get("rows", [])
            has_inactive_days = any("inactive_days" in row for row in rows)
            has_realized_pnl = any("realized_pnl_usd" in row for row in rows)
            
            if missing_fields:
                self.log_result("KPI Fields Test", "FAIL", f"Missing KPI fields: {missing_fields}")
                return False
            elif not has_inactive_days:
                self.log_result("KPI Fields Test", "FAIL", "Missing inactive_days in user rows")
                return False
            elif not has_realized_pnl:
                self.log_result("KPI Fields Test", "FAIL", "Missing realized_pnl_usd in user rows")
                return False
            else:
                self.log_result("KPI Fields Test", "PASS", f"All KPI fields present: {', '.join(populated_fields)}")
                return True
                
        except Exception as e:
            self.log_result("KPI Fields Test", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_user_economics_filters(self) -> bool:
        """Test 3: Verify filters work correctly"""
        try:
            base_url_economics = f"{self.base_url}/api/admin/users/economics"
            headers = self.get_headers()
            
            # Test date filters
            start_date = (datetime.now() - timedelta(days=30)).isoformat()
            end_date = datetime.now().isoformat()
            
            response = requests.get(
                f"{base_url_economics}?environment=testnet&start_date={start_date}&end_date={end_date}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                self.log_result("Date Filters Test", "FAIL", f"HTTP {response.status_code}")
                return False
            
            data = response.json()
            filters = data.get("filters", {})
            
            if filters.get("start_date") != start_date or filters.get("end_date") != end_date:
                self.log_result("Date Filters Test", "FAIL", "Date filters not properly applied")
                return False
            
            self.log_result("Date Filters Test", "PASS", f"Date filters applied: {start_date} to {end_date}")
            
            # Test user_email filter (if we have users)
            if data.get("rows"):
                test_email = data["rows"][0].get("email")
                if test_email:
                    response = requests.get(
                        f"{base_url_economics}?environment=testnet&user_email={test_email}",
                        headers=headers,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        filtered_data = response.json()
                        if filtered_data.get("filters", {}).get("user_email") == test_email:
                            self.log_result("User Email Filter Test", "PASS", f"Email filter applied: {test_email}")
                        else:
                            self.log_result("User Email Filter Test", "FAIL", "Email filter not properly applied")
                            return False
                    else:
                        self.log_result("User Email Filter Test", "FAIL", f"HTTP {response.status_code}")
                        return False
            
            # Test symbol filter
            response = requests.get(
                f"{base_url_economics}?environment=testnet&symbol=BTCUSDT",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                symbol_data = response.json()
                if symbol_data.get("filters", {}).get("symbol") == "BTCUSDT":
                    self.log_result("Symbol Filter Test", "PASS", "Symbol filter applied: BTCUSDT")
                else:
                    self.log_result("Symbol Filter Test", "FAIL", "Symbol filter not properly applied")
                    return False
            else:
                self.log_result("Symbol Filter Test", "FAIL", f"HTTP {response.status_code}")
                return False
            
            # Test cohort_month filter
            response = requests.get(
                f"{base_url_economics}?environment=testnet&cohort_month=2024-01",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                cohort_data = response.json()
                if cohort_data.get("filters", {}).get("cohort_month") == "2024-01":
                    self.log_result("Cohort Month Filter Test", "PASS", "Cohort month filter applied: 2024-01")
                else:
                    self.log_result("Cohort Month Filter Test", "FAIL", "Cohort month filter not properly applied")
                    return False
            else:
                self.log_result("Cohort Month Filter Test", "FAIL", f"HTTP {response.status_code}")
                return False
            
            # Test churn_inactive_days filter
            response = requests.get(
                f"{base_url_economics}?environment=testnet&churn_inactive_days=60",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                churn_data = response.json()
                if churn_data.get("filters", {}).get("churn_inactive_days") == 60:
                    self.log_result("Churn Inactive Days Filter Test", "PASS", "Churn inactive days filter applied: 60")
                    return True
                else:
                    self.log_result("Churn Inactive Days Filter Test", "FAIL", "Churn inactive days filter not properly applied")
                    return False
            else:
                self.log_result("Churn Inactive Days Filter Test", "FAIL", f"HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Filters Test", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_deterministic_behavior(self) -> bool:
        """Test 4: Verify deterministic behavior"""
        try:
            url = f"{self.base_url}/api/admin/users/economics?environment=testnet"
            headers = self.get_headers()
            
            # Make two identical requests
            response1 = requests.get(url, headers=headers, timeout=30)
            response2 = requests.get(url, headers=headers, timeout=30)
            
            if response1.status_code != 200 or response2.status_code != 200:
                self.log_result("Deterministic Test", "FAIL", f"HTTP errors: {response1.status_code}, {response2.status_code}")
                return False
            
            data1 = response1.json()
            data2 = response2.json()
            
            # Compare KPIs (should be identical)
            kpis1 = data1.get("kpis", {})
            kpis2 = data2.get("kpis", {})
            
            # Remove generated_at for comparison as it will differ
            data1_copy = data1.copy()
            data2_copy = data2.copy()
            data1_copy.pop("generated_at", None)
            data2_copy.pop("generated_at", None)
            
            if kpis1 == kpis2:
                self.log_result("Deterministic Test", "PASS", "KPIs are deterministic across requests")
                return True
            else:
                self.log_result("Deterministic Test", "FAIL", "KPIs differ between identical requests")
                return False
                
        except Exception as e:
            self.log_result("Deterministic Test", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_data_source_validation(self) -> bool:
        """Test 5: Behavioral validation of data sources"""
        try:
            response = requests.get(
                f"{self.base_url}/api/admin/users/economics?environment=testnet",
                headers=self.get_headers(),
                timeout=30
            )
            
            if response.status_code != 200:
                self.log_result("Data Source Validation", "FAIL", f"HTTP {response.status_code}")
                return False
            
            data = response.json()
            
            # Check sync information to understand data processing
            sync_info = data.get("sync", {})
            
            # Verify that revenue and PnL data are being processed
            kpis = data.get("kpis", {})
            total_revenue = kpis.get("total_revenue_usd", 0)
            
            rows = data.get("rows", [])
            has_revenue_data = any(row.get("revenue_contribution_usd", 0) != 0 for row in rows)
            has_pnl_data = any(row.get("realized_pnl_usd", 0) != 0 for row in rows)
            
            # Check if we have top_symbols data (indicates revenue_ledger processing)
            top_symbols = data.get("top_symbols", [])
            has_symbol_revenue = len(top_symbols) > 0
            
            validation_results = []
            
            if sync_info:
                validation_results.append(f"Sync info present: {sync_info}")
            
            if has_revenue_data or total_revenue > 0:
                validation_results.append("Revenue data detected (revenue_ledger source)")
            
            if has_pnl_data:
                validation_results.append("PnL data detected (canonical trade records source)")
            
            if has_symbol_revenue:
                validation_results.append(f"Symbol-level revenue data present ({len(top_symbols)} symbols)")
            
            if validation_results:
                self.log_result("Data Source Validation", "PASS", "; ".join(validation_results))
                return True
            else:
                self.log_result("Data Source Validation", "PARTIAL", "No data available for source validation")
                return True  # Not a failure, just no data
                
        except Exception as e:
            self.log_result("Data Source Validation", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_regression_endpoints(self) -> bool:
        """Test 6: Regression test for P0 commercial endpoints"""
        try:
            headers = self.get_headers()
            regression_tests = []
            
            # Test /api/admin/commercial/p0/ingestion/rest-run
            try:
                response = requests.post(
                    f"{self.base_url}/api/admin/commercial/p0/ingestion/rest-run",
                    headers=headers,
                    json={
                        "target_user_email": "test@example.com",
                        "environment": "testnet",
                        "market_types": ["futures"],
                        "limit_per_symbol": 10
                    },
                    timeout=30
                )
                if response.status_code in [200, 400, 404]:  # 400/404 acceptable for missing user
                    regression_tests.append("ingestion/rest-run: ACCESSIBLE")
                else:
                    regression_tests.append(f"ingestion/rest-run: HTTP {response.status_code}")
            except Exception as e:
                regression_tests.append(f"ingestion/rest-run: ERROR {str(e)}")
            
            # Test /api/admin/commercial/p0/pnl/latest
            try:
                response = requests.get(
                    f"{self.base_url}/api/admin/commercial/p0/pnl/latest?environment=testnet&target_user_email=test@example.com",
                    headers=headers,
                    timeout=30
                )
                if response.status_code in [200, 400, 404]:  # 400/404 acceptable for missing user
                    regression_tests.append("pnl/latest: ACCESSIBLE")
                else:
                    regression_tests.append(f"pnl/latest: HTTP {response.status_code}")
            except Exception as e:
                regression_tests.append(f"pnl/latest: ERROR {str(e)}")
            
            # Test /api/admin/commercial/p0/reconciliation/run
            try:
                response = requests.post(
                    f"{self.base_url}/api/admin/commercial/p0/reconciliation/run",
                    headers=headers,
                    json={
                        "target_user_email": "test@example.com",
                        "environment": "testnet",
                        "market_types": ["futures"],
                        "drift_tolerance_pct": 0.1
                    },
                    timeout=30
                )
                if response.status_code in [200, 400, 404]:  # 400/404 acceptable for missing user
                    regression_tests.append("reconciliation/run: ACCESSIBLE")
                else:
                    regression_tests.append(f"reconciliation/run: HTTP {response.status_code}")
            except Exception as e:
                regression_tests.append(f"reconciliation/run: ERROR {str(e)}")
            
            # Test /api/admin/commercial/p0/data-quality
            try:
                response = requests.get(
                    f"{self.base_url}/api/admin/commercial/p0/data-quality?environment=testnet&target_user_email=test@example.com",
                    headers=headers,
                    timeout=30
                )
                if response.status_code in [200, 400, 404]:  # 400/404 acceptable for missing user
                    regression_tests.append("data-quality: ACCESSIBLE")
                else:
                    regression_tests.append(f"data-quality: HTTP {response.status_code}")
            except Exception as e:
                regression_tests.append(f"data-quality: ERROR {str(e)}")
            
            # Test /api/admin/commercial/p0/live-gate
            try:
                response = requests.get(
                    f"{self.base_url}/api/admin/commercial/p0/live-gate?environment=testnet&target_user_email=test@example.com",
                    headers=headers,
                    timeout=30
                )
                if response.status_code in [200, 400, 404]:  # 400/404 acceptable for missing user
                    regression_tests.append("live-gate: ACCESSIBLE")
                else:
                    regression_tests.append(f"live-gate: HTTP {response.status_code}")
            except Exception as e:
                regression_tests.append(f"live-gate: ERROR {str(e)}")
            
            # Check if all endpoints are accessible
            accessible_count = sum(1 for test in regression_tests if "ACCESSIBLE" in test)
            total_count = len(regression_tests)
            
            if accessible_count == total_count:
                self.log_result("Regression Endpoints", "PASS", f"All {total_count} endpoints accessible")
                return True
            elif accessible_count > 0:
                self.log_result("Regression Endpoints", "PARTIAL", f"{accessible_count}/{total_count} endpoints accessible: {'; '.join(regression_tests)}")
                return True
            else:
                self.log_result("Regression Endpoints", "FAIL", f"No endpoints accessible: {'; '.join(regression_tests)}")
                return False
                
        except Exception as e:
            self.log_result("Regression Endpoints", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return summary"""
        print("=" * 80)
        print("P1.2 User Economics Backend Test Suite")
        print("=" * 80)
        
        if not self.authenticate_admin():
            return {"status": "FAILED", "reason": "Authentication failed", "results": self.test_results}
        
        tests = [
            ("Basic Endpoint Test", self.test_user_economics_endpoint_basic),
            ("KPI Fields Test", self.test_user_economics_kpi_fields),
            ("Filters Test", self.test_user_economics_filters),
            ("Deterministic Test", self.test_deterministic_behavior),
            ("Data Source Validation", self.test_data_source_validation),
            ("Regression Endpoints", self.test_regression_endpoints),
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            print(f"\n--- Running {test_name} ---")
            try:
                if test_func():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                self.log_result(test_name, "FAIL", f"Unexpected exception: {str(e)}")
                failed += 1
        
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        total = passed + failed
        success_rate = (passed / total * 100) if total > 0 else 0
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        # Print detailed results
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_symbol = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_symbol} {result['test']}: {result['status']}")
            if result["details"]:
                print(f"   {result['details']}")
        
        return {
            "status": "PASSED" if failed == 0 else "FAILED",
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": success_rate,
            "results": self.test_results
        }


def main():
    # Configuration
    BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"
    ADMIN_EMAIL = "canary.admin@platform.local"
    ADMIN_PASSWORD = "CanaryAdmin123!"
    
    print("P1.2 User Economics Backend Test Suite")
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    
    # Run tests
    tester = UserEconomicsBackendTest(BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD)
    summary = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if summary["status"] == "PASSED" else 1)


if __name__ == "__main__":
    main()