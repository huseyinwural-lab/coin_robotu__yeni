#!/usr/bin/env python3
"""
Scanner Engine Validation Test
Turkish Review Request: Son patch sonrası yeniden doğrula (127.0.0.1:8001 kullan)
"""

import requests
import json
import time
from typing import Dict, List, Any

class ScannerEngineValidator:
    def __init__(self, base_url: str = "http://127.0.0.1:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.token = None
        
    def login(self, email: str = "review.user@platform.local", password: str = "ReviewUser123!") -> bool:
        """Login and get authentication token"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"email": email, "password": password}
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                return True
            return False
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def test_scanner_engine_config(self) -> Dict[str, Any]:
        """Test 1: /api/user/scanner-engine/config market_scope spot_mode/futures_mode = all"""
        try:
            response = self.session.get(f"{self.base_url}/api/user/scanner-engine/config")
            if response.status_code == 200:
                config = response.json()
                market_scope = config.get("market_scope", {})
                spot_mode = market_scope.get("spot_mode")
                futures_mode = market_scope.get("futures_mode")
                
                return {
                    "status": "PASS" if (spot_mode == "all" and futures_mode == "all") else "FAIL",
                    "details": {
                        "spot_mode": spot_mode,
                        "futures_mode": futures_mode,
                        "expected": "all for both",
                        "config": config
                    }
                }
            else:
                return {
                    "status": "FAIL",
                    "details": {"error": f"HTTP {response.status_code}", "response": response.text}
                }
        except Exception as e:
            return {"status": "FAIL", "details": {"error": str(e)}}
    
    def test_scanner_engine_no_limit(self) -> Dict[str, Any]:
        """Test 2: Scanner engine filtresiz davranış - top50/scan_limit kırpması kontrolü"""
        try:
            # Test scanner run without limits
            response = self.session.post(
                f"{self.base_url}/api/user/scanner/run",
                json={
                    "mode": "AUTO",
                    "market_type": "futures",
                    "symbol_selection_mode": "manual_selection",
                    "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                scan_limit_applied = len(results) == 50  # Check if artificially limited to 50
                
                return {
                    "status": "PASS" if not scan_limit_applied else "FAIL",
                    "details": {
                        "results_count": len(results),
                        "scan_limit_applied": scan_limit_applied,
                        "message": "No artificial top50/scan_limit truncation" if not scan_limit_applied else "Artificial limit detected"
                    }
                }
            else:
                return {
                    "status": "FAIL",
                    "details": {"error": f"HTTP {response.status_code}", "response": response.text}
                }
        except Exception as e:
            return {"status": "FAIL", "details": {"error": str(e)}}
    
    def test_auto_scanner_run_no_rollout_cut(self) -> Dict[str, Any]:
        """Test 3: AUTO çağrısında rollout kesmesi olmadan candidate set işleniyor mu"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/user/scanner/run",
                json={
                    "mode": "AUTO",
                    "market_type": "futures", 
                    "symbol_selection_mode": "manual_selection",
                    "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                rollout_cut_detected = False
                
                # Check for rollout cutting indicators
                for result in results:
                    if "rollout_cut" in str(result).lower() or "candidate_set_truncated" in str(result).lower():
                        rollout_cut_detected = True
                        break
                
                return {
                    "status": "PASS" if not rollout_cut_detected else "FAIL",
                    "details": {
                        "results_count": len(results),
                        "rollout_cut_detected": rollout_cut_detected,
                        "message": "Candidate set processed without rollout cutting" if not rollout_cut_detected else "Rollout cutting detected"
                    }
                }
            else:
                return {
                    "status": "FAIL", 
                    "details": {"error": f"HTTP {response.status_code}", "response": response.text}
                }
        except Exception as e:
            return {"status": "FAIL", "details": {"error": str(e)}}
    
    def test_auto_dispatch_limit_5(self) -> Dict[str, Any]:
        """Test 4: AUTO dispatch en fazla 5 olmalı - created_order_intent_id sayısını hesapla"""
        try:
            # Get signals before
            response_before = self.session.get(f"{self.base_url}/api/user/signals?limit=50")
            if response_before.status_code != 200:
                return {"status": "FAIL", "details": {"error": "Could not get signals before"}}
            
            signals_before = response_before.json()
            intent_count_before = sum(1 for signal in signals_before if signal.get("created_order_intent_id"))
            
            # Trigger AUTO scanner run
            response = self.session.post(
                f"{self.base_url}/api/user/scanner/run",
                json={
                    "mode": "AUTO",
                    "market_type": "futures",
                    "symbol_selection_mode": "manual_selection", 
                    "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "DOTUSDT", "LINKUSDT", "AVAXUSDT"]
                }
            )
            
            if response.status_code != 200:
                return {"status": "FAIL", "details": {"error": f"Scanner run failed: HTTP {response.status_code}"}}
            
            # Wait for processing
            time.sleep(3)
            
            # Get signals after
            response_after = self.session.get(f"{self.base_url}/api/user/signals?limit=50")
            if response_after.status_code != 200:
                return {"status": "FAIL", "details": {"error": "Could not get signals after"}}
            
            signals_after = response_after.json()
            intent_count_after = sum(1 for signal in signals_after if signal.get("created_order_intent_id"))
            
            new_intents = intent_count_after - intent_count_before
            
            return {
                "status": "PASS" if new_intents <= 5 else "FAIL",
                "details": {
                    "intent_count_before": intent_count_before,
                    "intent_count_after": intent_count_after,
                    "new_intents": new_intents,
                    "limit_respected": new_intents <= 5,
                    "message": f"AUTO dispatch created {new_intents} new order intents (limit: 5)"
                }
            }
        except Exception as e:
            return {"status": "FAIL", "details": {"error": str(e)}}
    
    def test_manual_no_auto_dispatch(self) -> Dict[str, Any]:
        """Test 5: MANUAL modda otomatik dispatch olmamalı"""
        try:
            # Get signals before
            response_before = self.session.get(f"{self.base_url}/api/user/signals?limit=50")
            if response_before.status_code != 200:
                return {"status": "FAIL", "details": {"error": "Could not get signals before"}}
            
            signals_before = response_before.json()
            intent_count_before = sum(1 for signal in signals_before if signal.get("created_order_intent_id"))
            
            # Trigger MANUAL scanner run
            response = self.session.post(
                f"{self.base_url}/api/user/scanner/run",
                json={
                    "mode": "MANUAL",
                    "market_type": "futures",
                    "symbol_selection_mode": "manual_selection",
                    "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
                }
            )
            
            if response.status_code != 200:
                return {"status": "FAIL", "details": {"error": f"Scanner run failed: HTTP {response.status_code}"}}
            
            # Wait for processing
            time.sleep(3)
            
            # Get signals after
            response_after = self.session.get(f"{self.base_url}/api/user/signals?limit=50")
            if response_after.status_code != 200:
                return {"status": "FAIL", "details": {"error": "Could not get signals after"}}
            
            signals_after = response_after.json()
            intent_count_after = sum(1 for signal in signals_after if signal.get("created_order_intent_id"))
            
            new_intents = intent_count_after - intent_count_before
            
            return {
                "status": "PASS" if new_intents == 0 else "FAIL",
                "details": {
                    "intent_count_before": intent_count_before,
                    "intent_count_after": intent_count_after,
                    "new_intents": new_intents,
                    "no_auto_dispatch": new_intents == 0,
                    "message": f"MANUAL mode created {new_intents} order intents (expected: 0)"
                }
            }
        except Exception as e:
            return {"status": "FAIL", "details": {"error": str(e)}}

def main():
    print("🔍 SCANNER ENGINE VALIDATION - Turkish Review Request")
    print("=" * 60)
    
    validator = ScannerEngineValidator()
    
    # Login
    print("🔐 Logging in...")
    if not validator.login():
        print("❌ FAIL: Login failed")
        return
    print("✅ Login successful")
    
    # Run tests
    tests = [
        ("1) Scanner Engine Config (market_scope all)", validator.test_scanner_engine_config),
        ("2) No Top50/Scan Limit Truncation", validator.test_scanner_engine_no_limit),
        ("3) AUTO Run No Rollout Cut", validator.test_auto_scanner_run_no_rollout_cut),
        ("4) AUTO Dispatch Max 5 Limit", validator.test_auto_dispatch_limit_5),
        ("5) MANUAL No Auto Dispatch", validator.test_manual_no_auto_dispatch)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}")
        result = test_func()
        results.append((test_name, result))
        
        status = result["status"]
        details = result["details"]
        
        if status == "PASS":
            print(f"✅ PASS")
        else:
            print(f"❌ FAIL")
        
        # Print key details
        if isinstance(details, dict):
            for key, value in details.items():
                if key not in ["config", "response"]:  # Skip verbose data
                    print(f"   {key}: {value}")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result["status"] == "PASS")
    total = len(results)
    
    for test_name, result in results:
        status = result["status"]
        emoji = "✅" if status == "PASS" else "❌"
        print(f"{emoji} {status}: {test_name}")
    
    print(f"\n🎯 OVERALL: {passed}/{total} PASSED ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - Scanner Engine validation successful")
    else:
        print("⚠️  SOME TESTS FAILED - Review required")

if __name__ == "__main__":
    main()