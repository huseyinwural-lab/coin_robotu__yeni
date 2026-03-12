#!/usr/bin/env python3

import requests
import json
import os
import sys
from datetime import datetime

# Get backend URL from environment variable
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "https://portfolio-pro-494.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"

class SpotStrategyFaz1Test:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.test_results = []
        
    def log_result(self, test_name, success, details):
        """Log test result"""
        status = "PASS" if success else "FAIL"
        self.test_results.append({
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        print(f"[{status}] {test_name}: {details}")
        
    def login_admin(self):
        """Test admin login with provided credentials"""
        try:
            response = self.session.post(
                f"{API_BASE}/auth/login",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    # Set authorization header for subsequent requests
                    self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                    self.log_result("Admin Login", True, f"Successfully logged in as {ADMIN_EMAIL}")
                    return True
                else:
                    self.log_result("Admin Login", False, "No access token received")
                    return False
            else:
                self.log_result("Admin Login", False, f"Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Login", False, f"Exception: {str(e)}")
            return False
            
    def test_spot_strategy_universe(self):
        """Test GET /api/spot-strategy/universe and POST /api/spot-strategy/universe/refresh"""
        
        # Test 1: GET universe - basic functionality
        try:
            response = self.session.get(f"{API_BASE}/spot-strategy/universe")
            if response.status_code == 200:
                universe = response.json()
                symbols = universe.get("symbols", [])
                self.log_result("Spot Strategy - GET Universe", True, f"Retrieved {len(symbols)} symbols")
                
                # Verify BTCUSDT is present
                if "BTCUSDT" in symbols:
                    self.log_result("Spot Strategy - Universe BTCUSDT Check", True, "BTCUSDT found in universe")
                else:
                    self.log_result("Spot Strategy - Universe BTCUSDT Check", False, "BTCUSDT missing from universe")
            else:
                self.log_result("Spot Strategy - GET Universe", False, f"Status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_result("Spot Strategy - GET Universe", False, f"Exception: {str(e)}")
            return False
            
        # Test 2: POST universe refresh - admin only
        try:
            response = self.session.post(f"{API_BASE}/spot-strategy/universe/refresh")
            if response.status_code == 200:
                refresh_data = response.json()
                universe_data = refresh_data.get("universe", {})
                bootstrap_data = refresh_data.get("bootstrap", {})
                symbol_count = universe_data.get("count", 0)
                
                self.log_result("Spot Strategy - POST Universe Refresh", True, 
                               f"Refreshed {symbol_count} symbols, bootstrap: {bootstrap_data}")
                
                # Verify expected structure
                if "universe" in refresh_data and "bootstrap" in refresh_data:
                    self.log_result("Spot Strategy - Refresh Response Structure", True, "Valid response structure")
                else:
                    self.log_result("Spot Strategy - Refresh Response Structure", False, "Missing universe or bootstrap data")
            else:
                self.log_result("Spot Strategy - POST Universe Refresh", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Spot Strategy - POST Universe Refresh", False, f"Exception: {str(e)}")
            
        return True
            
        # Test 2: List with filters
        try:
            filters = {
                "search": "admin",
                "status": "active", 
                "sort_by": "email",
                "sort_dir": "asc"
            }
            response = self.session.get(f"{API_BASE}/admin/users", params=filters)
            if response.status_code == 200:
                filtered_users = response.json()
                self.log_result("Admin Users - Filters", True, f"Filtered results: {len(filtered_users)} users")
            else:
                self.log_result("Admin Users - Filters", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Admin Users - Filters", False, f"Exception: {str(e)}")
            
        # Find a test user to modify (not the admin user)
        test_user_id = None
        if users:
            for user in users:
                if user.get("email") != ADMIN_EMAIL:
                    test_user_id = user.get("id")
                    original_role = user.get("role") 
                    original_status = user.get("status")
                    break
                    
        if test_user_id:
            # Test 3: PATCH role - valid role change
            try:
                new_role = "ops" if original_role != "ops" else "user"
                response = self.session.patch(
                    f"{API_BASE}/admin/users/{test_user_id}/role",
                    json={"role": new_role}
                )
                if response.status_code == 200:
                    self.log_result("Admin Users - PATCH Role (valid)", True, f"Changed role to {new_role}")
                    
                    # Revert back
                    self.session.patch(
                        f"{API_BASE}/admin/users/{test_user_id}/role",
                        json={"role": original_role}
                    )
                else:
                    self.log_result("Admin Users - PATCH Role (valid)", False, f"Status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("Admin Users - PATCH Role (valid)", False, f"Exception: {str(e)}")
                
            # Test 4: PATCH role - invalid role (should fail)
            try:
                response = self.session.patch(
                    f"{API_BASE}/admin/users/{test_user_id}/role",
                    json={"role": "invalid_role"}
                )
                if response.status_code == 400:
                    self.log_result("Admin Users - PATCH Role (invalid)", True, "Correctly rejected invalid role")
                else:
                    self.log_result("Admin Users - PATCH Role (invalid)", False, f"Expected 400, got {response.status_code}")
            except Exception as e:
                self.log_result("Admin Users - PATCH Role (invalid)", False, f"Exception: {str(e)}")
                
            # Test 5: PATCH status - valid status change
            try:
                new_status = "disabled" if original_status == "active" else "active"
                response = self.session.patch(
                    f"{API_BASE}/admin/users/{test_user_id}/status",
                    json={"status": new_status}
                )
                if response.status_code == 200:
                    self.log_result("Admin Users - PATCH Status (valid)", True, f"Changed status to {new_status}")
                    
                    # Revert back
                    self.session.patch(
                        f"{API_BASE}/admin/users/{test_user_id}/status",
                        json={"status": original_status}
                    )
                else:
                    self.log_result("Admin Users - PATCH Status (valid)", False, f"Status {response.status_code}: {response.text}")
            except Exception as e:
                self.log_result("Admin Users - PATCH Status (valid)", False, f"Exception: {str(e)}")
                
            # Test 6: PATCH status - invalid status (should fail)
            try:
                response = self.session.patch(
                    f"{API_BASE}/admin/users/{test_user_id}/status",
                    json={"status": "invalid_status"}
                )
                if response.status_code == 400:
                    self.log_result("Admin Users - PATCH Status (invalid)", True, "Correctly rejected invalid status")
                else:
                    self.log_result("Admin Users - PATCH Status (invalid)", False, f"Expected 400, got {response.status_code}")
            except Exception as e:
                self.log_result("Admin Users - PATCH Status (invalid)", False, f"Exception: {str(e)}")
        else:
            self.log_result("Admin Users - User Modifications", False, "No suitable test user found for modifications")
            
        return True

    def test_spot_strategy_market_data(self):
        """Test GET /api/spot-strategy/market-data/BTCUSDT?limit=50"""
        
        try:
            response = self.session.get(f"{API_BASE}/spot-strategy/market-data/BTCUSDT?limit=50")
            if response.status_code == 200:
                market_data = response.json()
                
                # Verify response structure
                required_fields = ["symbol", "timeframe", "count", "candles"]
                missing_fields = [field for field in required_fields if field not in market_data]
                
                if not missing_fields:
                    symbol = market_data.get("symbol")
                    timeframe = market_data.get("timeframe")
                    count = market_data.get("count")
                    candles = market_data.get("candles", [])
                    
                    self.log_result("Spot Strategy - Market Data BTCUSDT", True, 
                                   f"Symbol: {symbol}, Timeframe: {timeframe}, Count: {count}, Returned candles: {len(candles)}")
                    
                    # Verify candle structure if candles exist
                    if candles:
                        candle = candles[0]
                        candle_fields = ["open", "high", "low", "close", "volume"]
                        missing_candle_fields = [field for field in candle_fields if field not in candle]
                        
                        if not missing_candle_fields:
                            self.log_result("Spot Strategy - Candle Structure", True, "Valid candle structure")
                        else:
                            self.log_result("Spot Strategy - Candle Structure", False, f"Missing fields: {missing_candle_fields}")
                else:
                    self.log_result("Spot Strategy - Market Data BTCUSDT", False, f"Missing fields: {missing_fields}")
            elif response.status_code == 404:
                self.log_result("Spot Strategy - Market Data BTCUSDT", False, "Market data not found - may need universe refresh first")
            else:
                self.log_result("Spot Strategy - Market Data BTCUSDT", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Spot Strategy - Market Data BTCUSDT", False, f"Exception: {str(e)}")
            
        return True

    def test_spot_strategy_indicators(self):
        """Test GET /api/spot-strategy/indicators/BTCUSDT"""
        
        try:
            response = self.session.get(f"{API_BASE}/spot-strategy/indicators/BTCUSDT")
            if response.status_code == 200:
                indicators = response.json()
                
                # Verify required indicator fields
                required_indicators = ["ema50", "ema200", "rsi14", "atr14", "vwap", "close", "updated_at"]
                missing_indicators = [field for field in required_indicators if field not in indicators]
                
                if not missing_indicators:
                    ema50 = indicators.get("ema50")
                    ema200 = indicators.get("ema200") 
                    rsi14 = indicators.get("rsi14")
                    atr14 = indicators.get("atr14")
                    vwap = indicators.get("vwap")
                    
                    self.log_result("Spot Strategy - Indicators BTCUSDT", True, 
                                   f"EMA50: {ema50:.2f}, EMA200: {ema200:.2f}, RSI: {rsi14:.2f}, ATR: {atr14:.6f}, VWAP: {vwap:.2f}")
                    
                    # Validate indicator ranges
                    if 0 <= rsi14 <= 100:
                        self.log_result("Spot Strategy - RSI Range", True, f"RSI in valid range: {rsi14:.2f}")
                    else:
                        self.log_result("Spot Strategy - RSI Range", False, f"RSI out of range: {rsi14:.2f}")
                        
                    if atr14 >= 0:
                        self.log_result("Spot Strategy - ATR Positive", True, f"ATR is positive: {atr14:.6f}")
                    else:
                        self.log_result("Spot Strategy - ATR Positive", False, f"ATR is negative: {atr14:.6f}")
                else:
                    self.log_result("Spot Strategy - Indicators BTCUSDT", False, f"Missing indicators: {missing_indicators}")
            elif response.status_code == 404:
                self.log_result("Spot Strategy - Indicators BTCUSDT", False, "Indicators not found - may need universe refresh first")
            else:
                self.log_result("Spot Strategy - Indicators BTCUSDT", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Spot Strategy - Indicators BTCUSDT", False, f"Exception: {str(e)}")
            
        return True

    def test_spot_strategy_scan_run(self):
        """Test POST /api/spot-strategy/scan/run"""
        
        try:
            response = self.session.post(f"{API_BASE}/spot-strategy/scan/run")
            if response.status_code == 200:
                scan_result = response.json()
                
                # Verify required scan fields
                required_fields = ["symbol_count", "executable_count", "top_ranked", "generated_at"]
                missing_fields = [field for field in required_fields if field not in scan_result]
                
                if not missing_fields:
                    symbol_count = scan_result.get("symbol_count")
                    executable_count = scan_result.get("executable_count")
                    top_ranked = scan_result.get("top_ranked", [])
                    
                    self.log_result("Spot Strategy - Scan Run", True, 
                                   f"Scanned {symbol_count} symbols, {executable_count} executable, {len(top_ranked)} top ranked")
                    
                    # Verify top_ranked structure if present
                    if top_ranked:
                        first_ranked = top_ranked[0]
                        ranked_fields = ["symbol", "signal", "signal_score"]
                        missing_ranked_fields = [field for field in ranked_fields if field not in first_ranked]
                        
                        if not missing_ranked_fields:
                            self.log_result("Spot Strategy - Top Ranked Structure", True, 
                                           f"Valid structure: {first_ranked.get('symbol')} - {first_ranked.get('signal')} (score: {first_ranked.get('signal_score')})")
                        else:
                            self.log_result("Spot Strategy - Top Ranked Structure", False, f"Missing fields in top_ranked: {missing_ranked_fields}")
                else:
                    self.log_result("Spot Strategy - Scan Run", False, f"Missing fields: {missing_fields}")
            else:
                self.log_result("Spot Strategy - Scan Run", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Spot Strategy - Scan Run", False, f"Exception: {str(e)}")
            
        return True

    def test_spot_strategy_daily_report(self):
        """Test POST /api/spot-strategy/report/daily/generate"""
        
        try:
            response = self.session.post(f"{API_BASE}/spot-strategy/report/daily/generate")
            if response.status_code == 200:
                report = response.json()
                
                # Verify required report fields
                required_fields = ["date", "strategy", "win_rate", "profit_factor", "avg_trade_return", "max_drawdown", "daily_trades"]
                missing_fields = [field for field in required_fields if field not in report]
                
                if not missing_fields:
                    date = report.get("date")
                    strategy = report.get("strategy")
                    win_rate = report.get("win_rate")
                    profit_factor = report.get("profit_factor")
                    daily_trades = report.get("daily_trades")
                    max_drawdown = report.get("max_drawdown")
                    
                    self.log_result("Spot Strategy - Daily Report", True, 
                                   f"Date: {date}, Strategy: {strategy}, Trades: {daily_trades}, Win Rate: {win_rate}%, Max DD: {max_drawdown}")
                    
                    # Validate report ranges
                    if 0 <= win_rate <= 100:
                        self.log_result("Spot Strategy - Win Rate Range", True, f"Win rate in valid range: {win_rate}%")
                    else:
                        self.log_result("Spot Strategy - Win Rate Range", False, f"Win rate out of range: {win_rate}%")
                        
                    if max_drawdown >= 0:
                        self.log_result("Spot Strategy - Max Drawdown", True, f"Max drawdown is valid: {max_drawdown}")
                    else:
                        self.log_result("Spot Strategy - Max Drawdown", False, f"Max drawdown is negative: {max_drawdown}")
                else:
                    self.log_result("Spot Strategy - Daily Report", False, f"Missing fields: {missing_fields}")
            else:
                self.log_result("Spot Strategy - Daily Report", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Spot Strategy - Daily Report", False, f"Exception: {str(e)}")
            
        return True

    def test_pipeline_monitoring_regression(self):
        """Test GET /api/pipeline/monitoring regression"""
        
        try:
            response = self.session.get(f"{API_BASE}/pipeline/monitoring")
            if response.status_code == 200:
                monitoring = response.json()
                
                # Verify key monitoring fields
                expected_fields = ["websocket_status", "heartbeat", "signal_rate_last_5m", "paper_trades_last_5m", 
                                 "open_positions", "latency_ms", "queue_depth"]
                missing_fields = [field for field in expected_fields if field not in monitoring]
                
                if not missing_fields:
                    ws_status = monitoring.get("websocket_status")
                    heartbeat = monitoring.get("heartbeat")
                    queue_depth = monitoring.get("queue_depth")
                    latency = monitoring.get("latency_ms")
                    
                    self.log_result("Pipeline Monitoring - Regression", True, 
                                   f"WS Status: {ws_status}, Queue: {queue_depth}, Latency: {latency}ms, Heartbeat: {heartbeat}")
                else:
                    self.log_result("Pipeline Monitoring - Regression", False, f"Missing fields: {missing_fields}")
            else:
                self.log_result("Pipeline Monitoring - Regression", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            self.log_result("Pipeline Monitoring - Regression", False, f"Exception: {str(e)}")
            
        return True
        
    def run_all_tests(self):
        """Run all Spot Strategy Faz-1 tests"""
        print("=" * 80)
        print("SPOT STRATEGY FAZ-1 BACKEND VALIDATION")
        print("=" * 80)
        print(f"Backend URL: {BACKEND_URL}")
        print(f"Admin Credentials: {ADMIN_EMAIL}")
        print("=" * 80)
        
        # Login first
        if not self.login_admin():
            print("\n❌ CRITICAL: Admin login failed - cannot continue with tests")
            return False
            
        # Run Spot Strategy test suites
        print("\n🔄 Testing GET/POST /api/spot-strategy/universe...")
        self.test_spot_strategy_universe()
        
        print("\n🔄 Testing GET /api/spot-strategy/market-data/BTCUSDT?limit=50...")  
        self.test_spot_strategy_market_data()
        
        print("\n🔄 Testing GET /api/spot-strategy/indicators/BTCUSDT...")
        self.test_spot_strategy_indicators()
        
        print("\n🔄 Testing POST /api/spot-strategy/scan/run...")
        self.test_spot_strategy_scan_run()
        
        print("\n🔄 Testing POST /api/spot-strategy/report/daily/generate...")
        self.test_spot_strategy_daily_report()
        
        print("\n🔄 Testing GET /api/pipeline/monitoring regression...")
        self.test_pipeline_monitoring_regression()
        
        # Summary
        print("\n" + "=" * 80)
        print("SPOT STRATEGY FAZ-1 TEST RESULTS")
        print("=" * 80)
        
        passed = sum(1 for result in self.test_results if result["status"] == "PASS")
        failed = sum(1 for result in self.test_results if result["status"] == "FAIL")
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
        
        if failed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  - {result['test']}: {result['details']}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print("\n" + "=" * 80)
        
        return failed == 0


def main():
    """Main test runner"""
    tester = SpotStrategyFaz1Test()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()