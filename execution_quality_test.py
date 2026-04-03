#!/usr/bin/env python3
"""
Execution Quality Endpoint Validation Test
Turkish Review Request: Son düzeltme doğrulaması

Test Requirements:
1) Endpoint: /api/admin/live-trading/execution-quality?window=1h
2) Base URL: https://trade-trace-engine.preview.emergentagent.com
3) Admin: canary.admin@platform.local / CanaryAdmin123!

Beklenen:
1) Endpoint 200 dönmeli (500 olmamalı)
2) JSON yapısı şu anahtarları içermeli: `window`, `sample_count`, `execution_quality_score`, `strategy_stats`, `symbol_stats`, `recent_items`
3) Raw exception string response'ta olmamalı

Çıktı: PASS/FAIL kısa.
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BACKEND_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class ExecutionQualityValidator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'ExecutionQuality-Validator/1.0'
        })
        self.admin_token = None
        
    def admin_login(self):
        """Admin login to get authentication token"""
        try:
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
                "panel": "admin"
            }
            
            response = self.session.post(f"{BACKEND_URL}/api/auth/login", json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'access_token' in data:
                    self.admin_token = data['access_token']
                    print(f"✅ Admin login successful. Token length: {len(self.admin_token)} chars")
                    return True
                else:
                    print(f"❌ Admin login failed: No access_token in response")
                    return False
            else:
                print(f"❌ Admin login failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Admin login exception: {str(e)}")
            return False
    
    def test_execution_quality_endpoint(self):
        """Test the execution quality endpoint with window=1h parameter"""
        if not self.admin_token:
            print("❌ No admin token available for execution quality test")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.admin_token}'}
            params = {'window': '1h'}
            
            response = self.session.get(
                f"{BACKEND_URL}/api/admin/live-trading/execution-quality", 
                params=params,
                headers=headers, 
                timeout=30
            )
            
            print(f"📡 Request: GET /api/admin/live-trading/execution-quality?window=1h")
            print(f"📊 Response Status: {response.status_code}")
            
            # Check 1: Endpoint should return 200 (not 500)
            if response.status_code != 200:
                print(f"❌ FAIL - Expected 200, got {response.status_code}")
                print(f"Response: {response.text}")
                return False
            
            print("✅ Status Code: 200 OK")
            
            # Check 2: Response should be valid JSON
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                print(f"❌ FAIL - Invalid JSON response: {str(e)}")
                print(f"Response text: {response.text}")
                return False
            
            print("✅ Valid JSON response")
            
            # Check 3: Required keys should be present
            required_keys = ['window', 'sample_count', 'execution_quality_score', 'strategy_stats', 'symbol_stats', 'recent_items']
            missing_keys = []
            
            for key in required_keys:
                if key not in data:
                    missing_keys.append(key)
            
            if missing_keys:
                print(f"❌ FAIL - Missing required keys: {missing_keys}")
                print(f"Available keys: {list(data.keys())}")
                return False
            
            print(f"✅ All required keys present: {required_keys}")
            
            # Check 4: No raw exception strings in response
            response_text = response.text.lower()
            exception_indicators = ['traceback', 'exception:', 'error:', 'stacktrace', 'internal server error']
            
            found_exceptions = []
            for indicator in exception_indicators:
                if indicator in response_text:
                    found_exceptions.append(indicator)
            
            if found_exceptions:
                print(f"❌ FAIL - Raw exception strings found: {found_exceptions}")
                print(f"Response snippet: {response.text[:500]}...")
                return False
            
            print("✅ No raw exception strings detected")
            
            # Display response summary
            print(f"\n📋 Response Summary:")
            print(f"   window: {data.get('window', 'N/A')}")
            print(f"   sample_count: {data.get('sample_count', 'N/A')}")
            print(f"   execution_quality_score: {data.get('execution_quality_score', 'N/A')}")
            print(f"   strategy_stats: {type(data.get('strategy_stats', 'N/A')).__name__} with {len(data.get('strategy_stats', [])) if isinstance(data.get('strategy_stats'), list) else 'N/A'} items")
            print(f"   symbol_stats: {type(data.get('symbol_stats', 'N/A')).__name__} with {len(data.get('symbol_stats', [])) if isinstance(data.get('symbol_stats'), list) else 'N/A'} items")
            print(f"   recent_items: {type(data.get('recent_items', 'N/A')).__name__} with {len(data.get('recent_items', [])) if isinstance(data.get('recent_items'), list) else 'N/A'} items")
            
            return True
                
        except Exception as e:
            print(f"❌ FAIL - Exception during execution quality test: {str(e)}")
            return False
    
    def run_validation(self):
        """Run the complete validation"""
        print("=" * 80)
        print("EXECUTION QUALITY ENDPOINT VALIDATION")
        print("Turkish Review Request: Son düzeltme doğrulaması")
        print(f"Target: {BACKEND_URL}/api/admin/live-trading/execution-quality?window=1h")
        print(f"Admin: {ADMIN_EMAIL}")
        print(f"Test Time: {datetime.now().isoformat()}")
        print("=" * 80)
        print()
        
        # Step 1: Admin login
        if not self.admin_login():
            print("\n❌ OVERALL RESULT: FAIL - Admin login failed")
            return False
        
        print()
        
        # Step 2: Test execution quality endpoint
        if not self.test_execution_quality_endpoint():
            print("\n❌ OVERALL RESULT: FAIL - Execution quality endpoint test failed")
            return False
        
        print("\n✅ OVERALL RESULT: PASS - All validation criteria met")
        return True

def main():
    validator = ExecutionQualityValidator()
    success = validator.run_validation()
    
    # Turkish summary output as requested
    print("\n" + "=" * 50)
    print("TÜRKÇE ÖZET / TURKISH SUMMARY")
    print("=" * 50)
    
    if success:
        print("✅ PASS")
        print("1) ✅ Endpoint 200 döndü (500 değil)")
        print("2) ✅ JSON yapısı doğru - tüm gerekli anahtarlar mevcut:")
        print("   - window, sample_count, execution_quality_score")
        print("   - strategy_stats, symbol_stats, recent_items")
        print("3) ✅ Raw exception string yok")
    else:
        print("❌ FAIL")
        print("Yukarıdaki detayları kontrol edin.")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())