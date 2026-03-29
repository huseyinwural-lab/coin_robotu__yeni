#!/usr/bin/env python3
"""
Detailed Iteration 2 Backend Validation Test
Testing specific runtime endpoints with detailed response analysis
"""

import requests
import json
import time
import uuid
from datetime import datetime

# Configuration
BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

class DetailedIteration2Tester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        
    def authenticate(self):
        """Authenticate and get admin token"""
        try:
            login_data = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json=login_data,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.admin_token = data["access_token"]
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.admin_token}"
                    })
                    print(f"✅ Authentication successful - Role: {data.get('role', 'N/A')}")
                    return True
            
            print(f"❌ Authentication failed: HTTP {response.status_code}")
            return False
        except Exception as e:
            print(f"❌ Authentication exception: {str(e)}")
            return False
    
    def test_endpoint_detailed(self, endpoint, method="GET", data=None):
        """Test endpoint with detailed response analysis"""
        try:
            print(f"\n🔍 Testing {method} {endpoint}")
            
            if method == "GET":
                response = self.session.get(f"{BASE_URL}{endpoint}", timeout=30)
            elif method == "POST":
                response = self.session.post(f"{BASE_URL}{endpoint}", json=data, timeout=30)
            
            print(f"   Status: HTTP {response.status_code}")
            
            if response.status_code == 200:
                try:
                    json_data = response.json()
                    print(f"   Response size: {len(str(json_data))} chars")
                    
                    # Show first few keys/structure
                    if isinstance(json_data, dict):
                        keys = list(json_data.keys())[:5]
                        print(f"   Keys: {keys}")
                        if len(json_data.keys()) > 5:
                            print(f"   ... and {len(json_data.keys()) - 5} more keys")
                    elif isinstance(json_data, list):
                        print(f"   Array length: {len(json_data)}")
                        if len(json_data) > 0:
                            if isinstance(json_data[0], dict):
                                sample_keys = list(json_data[0].keys())[:3]
                                print(f"   Sample item keys: {sample_keys}")
                    
                    # Show sample data (first 200 chars)
                    sample_data = str(json_data)[:200]
                    if len(str(json_data)) > 200:
                        sample_data += "..."
                    print(f"   Sample: {sample_data}")
                    
                except json.JSONDecodeError:
                    print(f"   Non-JSON response: {response.text[:200]}")
            else:
                print(f"   Error: {response.text[:200]}")
            
            return response.status_code, response
            
        except Exception as e:
            print(f"   Exception: {str(e)}")
            return None, None
    
    def run_detailed_tests(self):
        """Run detailed tests on all required endpoints"""
        print("=" * 80)
        print("DETAILED ITERATION 2 BACKEND VALIDATION")
        print(f"Target: {BASE_URL}")
        print("=" * 80)
        
        # Authenticate
        if not self.authenticate():
            print("❌ Cannot proceed without authentication")
            return
        
        # Test all required endpoints
        endpoints_to_test = [
            ("/api/runtime/pnl/summary", "GET", None),
            ("/api/runtime/pnl/positions", "GET", None),
            ("/api/runtime/alerts", "GET", None),
            ("/api/runtime/health/smoke", "GET", None),
            ("/api/runtime/execution/submit", "POST", {
                "execution_id": str(uuid.uuid4()),
                "action": "submit",
                "symbol": "BTCUSDT",
                "quantity": 0.001,
                "side": "BUY",
                "order_type": "MARKET"
            }),
            ("/api/runtime/execution/worker/process-once", "POST", {})
        ]
        
        results = []
        for endpoint, method, data in endpoints_to_test:
            status_code, response = self.test_endpoint_detailed(endpoint, method, data)
            results.append((endpoint, method, status_code))
        
        # Summary
        print("\n" + "=" * 80)
        print("DETAILED TEST SUMMARY")
        print("=" * 80)
        
        for endpoint, method, status_code in results:
            if status_code == 200:
                print(f"✅ {method} {endpoint}: PASS (HTTP {status_code})")
            elif status_code in [422, 400]:
                print(f"⚠️ {method} {endpoint}: PARTIAL (HTTP {status_code} - validation error, endpoint accessible)")
            elif status_code == 404:
                print(f"❌ {method} {endpoint}: FAIL (HTTP {status_code} - not found)")
            elif status_code in [401, 403]:
                print(f"❌ {method} {endpoint}: FAIL (HTTP {status_code} - auth error)")
            elif status_code is None:
                print(f"❌ {method} {endpoint}: FAIL (Exception)")
            else:
                print(f"❌ {method} {endpoint}: FAIL (HTTP {status_code})")

if __name__ == "__main__":
    tester = DetailedIteration2Tester()
    tester.run_detailed_tests()