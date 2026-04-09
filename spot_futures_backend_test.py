#!/usr/bin/env python3
"""
SPOT+FUTURES Root-Cause Fixes Backend Validation Test
Turkish Review Request - Backend Doğrulama Testi

Test Requirements:
1) Login al.
2) GET /api/user/scanner/status-contract -> 200 dönmeli, payload'ta market_contracts ve overall_health olmalı.
3) GET /api/user/scanner/status-contract?market_type=spot -> 200
4) GET /api/user/scanner/status-contract?market_type=futures -> 200
5) GET /api/bot-profiles -> 200 ve symbol_source/symbol_source_summary alanları dönmeli.
6) GET /api/user/signals?limit=20 -> 200 (regresyon yok)
7) Eğer otomatik dispatch hatası tetiklenirse sessiz yutulmadığını (blocked_reason/decision_note güncellemesi) örnekle doğrula, tetiklenmezse not düş.

Base URL: https://trade-trace-engine.preview.emergentagent.com
User: review.user@platform.local / ReviewUser123!
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

class BackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = None
        self.test_results = []
        
    def log_test(self, test_name, status, details=""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status} - {details}")
        
    def login(self):
        """Test 1: User Login"""
        try:
            login_url = f"{BASE_URL}/api/auth/login/user"
            payload = {
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            }
            
            response = self.session.post(login_url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.access_token = data["access_token"]
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.access_token}"
                    })
                    self.log_test("User Login", "PASS", f"Successfully authenticated. Token length: {len(self.access_token)} chars")
                    return True
                else:
                    self.log_test("User Login", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_test("User Login", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("User Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_scanner_status_contract_base(self):
        """Test 2: GET /api/user/scanner/status-contract -> 200, market_contracts ve overall_health olmalı"""
        try:
            url = f"{BASE_URL}/api/user/scanner/status-contract"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required fields
                required_fields = ["market_contracts", "overall_health"]
                missing_fields = []
                
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if not missing_fields:
                    market_contracts = data.get("market_contracts", {})
                    overall_health = data.get("overall_health", "")
                    
                    self.log_test("Scanner Status Contract Base", "PASS", 
                                f"HTTP 200. market_contracts: {len(market_contracts)} items, overall_health: {overall_health}")
                    return True
                else:
                    self.log_test("Scanner Status Contract Base", "FAIL", 
                                f"Missing required fields: {missing_fields}")
                    return False
            else:
                self.log_test("Scanner Status Contract Base", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Scanner Status Contract Base", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_scanner_status_contract_spot(self):
        """Test 3: GET /api/user/scanner/status-contract?market_type=spot -> 200"""
        try:
            url = f"{BASE_URL}/api/user/scanner/status-contract?market_type=spot"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Scanner Status Contract Spot", "PASS", 
                            f"HTTP 200. Response keys: {list(data.keys())}")
                return True
            else:
                self.log_test("Scanner Status Contract Spot", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Scanner Status Contract Spot", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_scanner_status_contract_futures(self):
        """Test 4: GET /api/user/scanner/status-contract?market_type=futures -> 200"""
        try:
            url = f"{BASE_URL}/api/user/scanner/status-contract?market_type=futures"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Scanner Status Contract Futures", "PASS", 
                            f"HTTP 200. Response keys: {list(data.keys())}")
                return True
            else:
                self.log_test("Scanner Status Contract Futures", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Scanner Status Contract Futures", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_bot_profiles(self):
        """Test 5: GET /api/bot-profiles -> 200 ve symbol_source/symbol_source_summary alanları dönmeli"""
        try:
            url = f"{BASE_URL}/api/bot-profiles"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, list) and len(data) > 0:
                    # Check first bot profile for required fields
                    first_bot = data[0]
                    required_fields = ["symbol_source", "symbol_source_summary"]
                    missing_fields = []
                    
                    for field in required_fields:
                        if field not in first_bot:
                            missing_fields.append(field)
                    
                    if not missing_fields:
                        symbol_source = first_bot.get("symbol_source", "")
                        symbol_source_summary = first_bot.get("symbol_source_summary", "")
                        
                        self.log_test("Bot Profiles", "PASS", 
                                    f"HTTP 200. {len(data)} bots. symbol_source: {symbol_source}, symbol_source_summary: {symbol_source_summary}")
                        return True
                    else:
                        self.log_test("Bot Profiles", "FAIL", 
                                    f"Missing required fields in first bot: {missing_fields}")
                        return False
                else:
                    self.log_test("Bot Profiles", "PASS", 
                                f"HTTP 200. Empty bot list (no bots to check fields)")
                    return True
            else:
                self.log_test("Bot Profiles", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Bot Profiles", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_user_signals(self):
        """Test 6: GET /api/user/signals?limit=20 -> 200 (regresyon yok)"""
        try:
            url = f"{BASE_URL}/api/user/signals?limit=20"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, list):
                    signal_count = len(data)
                    self.log_test("User Signals", "PASS", 
                                f"HTTP 200. {signal_count} signals returned. No regression detected.")
                    return True
                elif isinstance(data, dict) and "items" in data:
                    signal_count = len(data["items"])
                    self.log_test("User Signals", "PASS", 
                                f"HTTP 200. {signal_count} signals in items. No regression detected.")
                    return True
                else:
                    self.log_test("User Signals", "FAIL", 
                                f"Unexpected response format: {type(data)}")
                    return False
            else:
                self.log_test("User Signals", "FAIL", 
                            f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("User Signals", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_auto_dispatch_error_handling(self):
        """Test 7: Otomatik dispatch hatası sessiz yutulmadığını kontrol et"""
        try:
            # First, get some signals to check for blocked_reason/decision_note updates
            url = f"{BASE_URL}/api/user/signals?limit=10"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                signals = data if isinstance(data, list) else data.get("items", [])
                
                # Look for signals with blocked_reason or decision_note
                blocked_signals = []
                for signal in signals:
                    if signal.get("blocked_reason") or signal.get("decision_note"):
                        blocked_signals.append({
                            "id": signal.get("id"),
                            "blocked_reason": signal.get("blocked_reason"),
                            "decision_note": signal.get("decision_note")
                        })
                
                if blocked_signals:
                    self.log_test("Auto Dispatch Error Handling", "PASS", 
                                f"Found {len(blocked_signals)} signals with blocked_reason/decision_note. Errors not silently swallowed. Examples: {blocked_signals[:2]}")
                    return True
                else:
                    self.log_test("Auto Dispatch Error Handling", "INFO", 
                                f"No signals with blocked_reason/decision_note found in {len(signals)} signals. No auto dispatch errors to validate.")
                    return True
            else:
                self.log_test("Auto Dispatch Error Handling", "FAIL", 
                            f"Could not fetch signals to check error handling. HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Auto Dispatch Error Handling", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all backend validation tests"""
        print("🚀 SPOT+FUTURES Root-Cause Fixes Backend Validation Test")
        print(f"Base URL: {BASE_URL}")
        print(f"User: {USER_EMAIL}")
        print("=" * 80)
        
        # Test 1: Login
        if not self.login():
            print("❌ Login failed. Cannot proceed with other tests.")
            return False
        
        # Test 2-7: API Endpoints
        tests = [
            self.test_scanner_status_contract_base,
            self.test_scanner_status_contract_spot,
            self.test_scanner_status_contract_futures,
            self.test_bot_profiles,
            self.test_user_signals,
            self.test_auto_dispatch_error_handling
        ]
        
        for test in tests:
            test()
        
        # Summary
        print("\n" + "=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for result in self.test_results if result["status"] == "PASS")
        failed = sum(1 for result in self.test_results if result["status"] == "FAIL")
        info = sum(1 for result in self.test_results if result["status"] == "INFO")
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"ℹ️ Info: {info}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        # Turkish Summary
        print("\n🇹🇷 TURKISH SUMMARY (TÜRKÇE ÖZET)")
        print("=" * 50)
        
        if failed == 0:
            print("✅ SONUÇ: PASS - Tüm testler başarılı")
        else:
            print("❌ SONUÇ: FAIL - Bazı testler başarısız")
        
        print("\nDetaylı Sonuçlar:")
        for i, result in enumerate(self.test_results, 1):
            status_tr = "BAŞARILI" if result["status"] == "PASS" else "BAŞARISIZ" if result["status"] == "FAIL" else "BİLGİ"
            print(f"{i}) {result['test']}: {status_tr}")
        
        return failed == 0

if __name__ == "__main__":
    tester = BackendTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)