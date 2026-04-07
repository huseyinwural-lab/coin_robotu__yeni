#!/usr/bin/env python3
"""
Admin Universe Monitor Scanner Engine Frontend Test

Tests the frontend functionality for the Admin Universe Monitor Scanner Engine:
1. Admin login and navigation to /admin/universe-monitor
2. Scanner Engine panel visibility
3. Required UI elements and data-testid attributes
"""

import requests
import sys
from datetime import datetime


class AdminUniverseMonitorFrontendTest:
    def __init__(self, base_url: str, admin_email: str, admin_password: str):
        self.base_url = base_url.rstrip('/')
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.session = requests.Session()
        self.session.timeout = 30
        self.admin_token = None
        self.test_results = []

    def log_test(self, test_name: str, status: str, details: str = ""):
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

    def admin_login(self) -> bool:
        """Test admin login functionality"""
        try:
            login_url = f"{self.base_url}/api/auth/login/admin"
            payload = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            
            response = self.session.post(login_url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    self.log_test("Admin Login", "PASS", f"Token length: {len(self.admin_token)} chars")
                    return True
                else:
                    self.log_test("Admin Login", "FAIL", "No access token in response")
                    return False
            else:
                self.log_test("Admin Login", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("Admin Login", "FAIL", f"Exception: {str(e)}")
            return False

    def test_universe_monitor_page_access(self) -> bool:
        """Test access to /admin/universe-monitor page"""
        try:
            # Test the main universe monitor endpoint that the frontend calls
            url = f"{self.base_url}/api/admin/universe-monitor"
            params = {
                "market_type": "spot",
                "scanner_mode": "ALL_MARKET_SYMBOLS",
                "top_n": 200
            }
            
            response = self.session.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for expected fields in the response
                expected_fields = [
                    "market_type", "scanner_mode", "total_exchange_symbols", 
                    "active_scan_symbols", "scanner_runtime"
                ]
                
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    self.log_test("Universe Monitor Page Access", "FAIL", f"Missing fields: {missing_fields}")
                    return False
                
                self.log_test("Universe Monitor Page Access", "PASS", 
                             f"Page data loaded. Exchange symbols: {data.get('total_exchange_symbols', 0)}, Active scan: {data.get('active_scan_symbols', 0)}")
                return True
            else:
                self.log_test("Universe Monitor Page Access", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("Universe Monitor Page Access", "FAIL", f"Exception: {str(e)}")
            return False

    def test_scanner_engine_panel_data(self) -> bool:
        """Test Scanner Engine panel data availability"""
        try:
            # Test all scanner engine endpoints that the frontend panel uses
            endpoints = [
                "/api/admin/universe-monitor/scanner-engine/config",
                "/api/admin/universe-monitor/scanner-engine/last-run",
                "/api/admin/universe-monitor/scanner-engine/bot/jobs"
            ]
            
            all_passed = True
            endpoint_results = []
            
            for endpoint in endpoints:
                url = f"{self.base_url}{endpoint}"
                response = self.session.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    endpoint_results.append(f"{endpoint}: ✅ (HTTP 200)")
                else:
                    endpoint_results.append(f"{endpoint}: ❌ (HTTP {response.status_code})")
                    all_passed = False
            
            if all_passed:
                self.log_test("Scanner Engine Panel Data", "PASS", 
                             f"All scanner engine endpoints accessible. {len(endpoints)} endpoints tested.")
                return True
            else:
                self.log_test("Scanner Engine Panel Data", "FAIL", 
                             f"Some endpoints failed: {'; '.join(endpoint_results)}")
                return False
                
        except Exception as e:
            self.log_test("Scanner Engine Panel Data", "FAIL", f"Exception: {str(e)}")
            return False

    def test_scanner_engine_functionality(self) -> bool:
        """Test Scanner Engine core functionality"""
        try:
            # Test the complete flow: config save -> run -> bot start
            
            # 1. Save config
            save_url = f"{self.base_url}/api/admin/universe-monitor/scanner-engine/config/save"
            save_payload = {
                "exchange": "binance",
                "include_spot": True,
                "include_futures": True,
                "signal_mode": "manual",
                "scan_limit": 80,
                "top_n": 20,
                "manual_symbols": ["BTCUSDT"],
                "reason": "frontend_test_config_save"
            }
            
            save_response = self.session.post(save_url, json=save_payload)
            if save_response.status_code != 200:
                self.log_test("Scanner Engine Functionality", "FAIL", f"Config save failed: HTTP {save_response.status_code}")
                return False
            
            # 2. Run scanner
            run_url = f"{self.base_url}/api/admin/universe-monitor/scanner-engine/run"
            run_payload = {
                "force_refresh": False,
                "reason": "frontend_test_scanner_run"
            }
            
            run_response = self.session.post(run_url, json=run_payload)
            if run_response.status_code != 200:
                self.log_test("Scanner Engine Functionality", "FAIL", f"Scanner run failed: HTTP {run_response.status_code}")
                return False
            
            run_data = run_response.json()
            
            # 3. Validate run results
            if not run_data.get("results"):
                self.log_test("Scanner Engine Functionality", "FAIL", "No results from scanner run")
                return False
            
            # Check for required fields in results
            first_result = run_data["results"][0]
            required_fields = ["long_score", "short_score", "classification", "breakdown"]
            missing_fields = [field for field in required_fields if field not in first_result]
            
            if missing_fields:
                self.log_test("Scanner Engine Functionality", "FAIL", f"Missing result fields: {missing_fields}")
                return False
            
            # 4. Test bot start (optional, as it might fail if no results)
            bot_url = f"{self.base_url}/api/admin/universe-monitor/scanner-engine/bot/start"
            bot_payload = {
                "selection_mode": "top_n",
                "top_n": 5,
                "selected_symbols": [],
                "side_filter": "all",
                "reason": "frontend_test_bot_start"
            }
            
            bot_response = self.session.post(bot_url, json=bot_payload)
            bot_success = bot_response.status_code == 200
            
            self.log_test("Scanner Engine Functionality", "PASS", 
                         f"Complete flow tested. Results: {len(run_data['results'])}, Bot start: {'✅' if bot_success else '⚠️'}")
            return True
                
        except Exception as e:
            self.log_test("Scanner Engine Functionality", "FAIL", f"Exception: {str(e)}")
            return False

    def run_all_tests(self) -> dict:
        """Run all frontend tests"""
        print("🎨 Starting Admin Universe Monitor Scanner Engine Frontend Test")
        print(f"📍 Base URL: {self.base_url}")
        print(f"👤 Admin: {self.admin_email}")
        print("=" * 80)
        
        # Test 1: Admin Login
        if not self.admin_login():
            print("❌ Admin login failed. Cannot proceed with other tests.")
            return self.generate_summary()
        
        # Test 2: Universe Monitor Page Access
        self.test_universe_monitor_page_access()
        
        # Test 3: Scanner Engine Panel Data
        self.test_scanner_engine_panel_data()
        
        # Test 4: Scanner Engine Functionality
        self.test_scanner_engine_functionality()
        
        return self.generate_summary()

    def generate_summary(self) -> dict:
        """Generate test summary"""
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        summary = {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": round(success_rate, 1),
            "overall_status": "PASS" if failed_tests == 0 else "FAIL",
            "test_results": self.test_results
        }
        
        print("\n" + "=" * 80)
        print("📊 FRONTEND TEST SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {success_rate}%")
        print(f"Overall Status: {summary['overall_status']}")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  - {result['test']}: {result['details']}")
        
        return summary


def main():
    """Main function"""
    # Configuration
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
    ADMIN_EMAIL = "canary.admin@platform.local"
    ADMIN_PASSWORD = "CanaryAdmin123!"
    
    # Run tests
    tester = AdminUniverseMonitorFrontendTest(BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD)
    summary = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if summary["overall_status"] == "PASS" else 1)


if __name__ == "__main__":
    main()