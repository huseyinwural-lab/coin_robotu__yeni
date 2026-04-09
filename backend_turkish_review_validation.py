#!/usr/bin/env python3
"""
Turkish Review Request Backend Validation
Hedefli backend doğrulama için specific endpoint testing

Test Requirements:
A) Admin tarafı 410 olmalı (10 endpoints)
B) User tarafı çalışmalı (4 endpoints)
"""

import requests
import json
import sys
from datetime import datetime

class TurkishReviewBackendValidator:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.admin_token = None
        self.user_token = None
        self.results = {
            'admin_endpoints': {},
            'user_endpoints': {},
            'summary': {},
            'timestamp': datetime.now().isoformat()
        }
        
    def authenticate_admin(self, email, password):
        """Authenticate admin user"""
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login/admin",
                json={"email": email, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get('access_token')
                print(f"✅ Admin authentication successful (token length: {len(self.admin_token)} chars)")
                return True
            else:
                print(f"❌ Admin authentication failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Admin authentication error: {e}")
            return False
    
    def authenticate_user(self, email, password):
        """Authenticate user"""
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login/user",
                json={"email": email, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get('access_token')
                print(f"✅ User authentication successful (token length: {len(self.user_token)} chars)")
                return True
            else:
                print(f"❌ User authentication failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ User authentication error: {e}")
            return False
    
    def test_admin_410_endpoints(self):
        """Test admin endpoints that should return 410"""
        print("\n🔍 Testing Admin Endpoints (Expected: 410 + PURE_LIVE_410)")
        
        admin_endpoints = [
            ("POST", "/api/admin/decision-requests/test-id/approve"),
            ("POST", "/api/admin/decision-requests/test-id/reject"),
            ("POST", "/api/admin/decision-requests/test-id/execute"),
            ("POST", "/api/admin/decision-requests/bulk-action"),
            ("POST", "/api/admin/decision-requests/test-id/assign-owner"),
            ("POST", "/api/admin/decision-requests/test-id/ack"),
            ("POST", "/api/admin/live-trading/control-layer/scanner/restart"),
            ("POST", "/api/admin/live-trading/control-layer/scanner/manual-trigger"),
            ("POST", "/api/admin/live-trading/control-layer/scanner/symbol-universe"),
            ("POST", "/api/admin/live-trading/control-layer/execution-quality/retry")
        ]
        
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        for method, endpoint in admin_endpoints:
            try:
                response = requests.request(
                    method, 
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    json={},  # Empty payload for POST requests
                    timeout=10
                )
                
                status = response.status_code
                self.results['admin_endpoints'][endpoint] = status
                
                # Check for PURE_LIVE_410 in response
                pure_live_410 = False
                try:
                    if response.text and 'PURE_LIVE_410' in response.text:
                        pure_live_410 = True
                except:
                    pass
                
                if status == 410:
                    print(f"✅ {endpoint} -> {status} {'(PURE_LIVE_410)' if pure_live_410 else ''}")
                else:
                    print(f"❌ {endpoint} -> {status} (Expected: 410)")
                    
            except Exception as e:
                print(f"❌ {endpoint} -> ERROR: {e}")
                self.results['admin_endpoints'][endpoint] = f"ERROR: {e}"
    
    def test_user_working_endpoints(self):
        """Test user endpoints that should work (not 410)"""
        print("\n🔍 Testing User Endpoints (Expected: Working, not 410)")
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        
        # Test 1: POST /api/user/scanner-engine/run-async
        try:
            response = requests.post(
                f"{self.base_url}/api/user/scanner-engine/run-async",
                headers=headers,
                json={},
                timeout=15
            )
            status = response.status_code
            self.results['user_endpoints']['/api/user/scanner-engine/run-async'] = status
            
            if status != 410:
                print(f"✅ /api/user/scanner-engine/run-async -> {status} (Not 410)")
            else:
                print(f"❌ /api/user/scanner-engine/run-async -> {status} (Should not be 410)")
                
        except Exception as e:
            print(f"❌ /api/user/scanner-engine/run-async -> ERROR: {e}")
            self.results['user_endpoints']['/api/user/scanner-engine/run-async'] = f"ERROR: {e}"
        
        # Test 2: POST /api/user/scanner/signal/{signal_id}/approve (404 acceptable if signal_id doesn't exist)
        try:
            response = requests.post(
                f"{self.base_url}/api/user/scanner/signal/non-existent-signal/approve",
                headers=headers,
                json={},
                timeout=10
            )
            status = response.status_code
            self.results['user_endpoints']['/api/user/scanner/signal/{signal_id}/approve'] = status
            
            if status == 404:
                print(f"✅ /api/user/scanner/signal/{{signal_id}}/approve -> {status} (404 acceptable for non-existent signal)")
            elif status != 410:
                print(f"✅ /api/user/scanner/signal/{{signal_id}}/approve -> {status} (Not 410)")
            else:
                print(f"❌ /api/user/scanner/signal/{{signal_id}}/approve -> {status} (Should not be 410)")
                
        except Exception as e:
            print(f"❌ /api/user/scanner/signal/{{signal_id}}/approve -> ERROR: {e}")
            self.results['user_endpoints']['/api/user/scanner/signal/{signal_id}/approve'] = f"ERROR: {e}"
        
        # Test 3: POST /api/user/execution/intent/preview
        try:
            response = requests.post(
                f"{self.base_url}/api/user/execution/intent/preview",
                headers=headers,
                json={
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": "0.001"
                },
                timeout=15
            )
            status = response.status_code
            self.results['user_endpoints']['/api/user/execution/intent/preview'] = status
            
            if status != 410:
                print(f"✅ /api/user/execution/intent/preview -> {status} (Not 410)")
            else:
                print(f"❌ /api/user/execution/intent/preview -> {status} (Should not be 410)")
                
        except Exception as e:
            print(f"❌ /api/user/execution/intent/preview -> ERROR: {e}")
            self.results['user_endpoints']['/api/user/execution/intent/preview'] = f"ERROR: {e}"
        
        # Test 4: POST /api/user/execution/intent/submit
        try:
            response = requests.post(
                f"{self.base_url}/api/user/execution/intent/submit",
                headers=headers,
                json={
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": "0.001"
                },
                timeout=15
            )
            status = response.status_code
            self.results['user_endpoints']['/api/user/execution/intent/submit'] = status
            
            if status != 410:
                print(f"✅ /api/user/execution/intent/submit -> {status} (Not 410)")
            else:
                print(f"❌ /api/user/execution/intent/submit -> {status} (Should not be 410)")
                
        except Exception as e:
            print(f"❌ /api/user/execution/intent/submit -> ERROR: {e}")
            self.results['user_endpoints']['/api/user/execution/intent/submit'] = f"ERROR: {e}"
    
    def generate_summary(self):
        """Generate test summary"""
        print("\n📊 TEST SUMMARY")
        print("=" * 50)
        
        # Admin endpoints summary
        admin_410_count = sum(1 for status in self.results['admin_endpoints'].values() if status == 410)
        admin_total = len(self.results['admin_endpoints'])
        
        print(f"\nA) Admin Endpoints (Expected: 410)")
        for endpoint, status in self.results['admin_endpoints'].items():
            print(f"   {endpoint} -> {status}")
        
        print(f"\nAdmin 410 Success Rate: {admin_410_count}/{admin_total} ({admin_410_count/admin_total*100:.1f}%)")
        
        # User endpoints summary
        user_non_410_count = sum(1 for status in self.results['user_endpoints'].values() 
                                if isinstance(status, int) and status != 410)
        user_total = len(self.results['user_endpoints'])
        
        print(f"\nB) User Endpoints (Expected: Not 410)")
        for endpoint, status in self.results['user_endpoints'].items():
            print(f"   {endpoint} -> {status}")
        
        print(f"\nUser Non-410 Success Rate: {user_non_410_count}/{user_total} ({user_non_410_count/user_total*100:.1f}%)")
        
        # Overall assessment
        admin_pass = admin_410_count == admin_total
        user_pass = user_non_410_count == user_total
        
        print(f"\n🎯 PASS/FAIL SUMMARY:")
        print(f"   Admin endpoints (410): {'✅ PASS' if admin_pass else '❌ FAIL'}")
        print(f"   User endpoints (not 410): {'✅ PASS' if user_pass else '❌ FAIL'}")
        
        overall_pass = admin_pass and user_pass
        print(f"   Overall: {'✅ PASS' if overall_pass else '❌ FAIL'}")
        
        # Critical blocks
        critical_blocks = []
        if not admin_pass:
            critical_blocks.append("Admin endpoints not returning 410")
        if not user_pass:
            critical_blocks.append("User endpoints returning 410 (should work)")
        
        if critical_blocks:
            print(f"\n⚠️ CRITICAL BLOCKS:")
            for block in critical_blocks:
                print(f"   - {block}")
        else:
            print(f"\n✅ NO CRITICAL BLOCKS DETECTED")
        
        # Store summary
        self.results['summary'] = {
            'admin_410_success_rate': f"{admin_410_count}/{admin_total}",
            'user_non_410_success_rate': f"{user_non_410_count}/{user_total}",
            'admin_pass': admin_pass,
            'user_pass': user_pass,
            'overall_pass': overall_pass,
            'critical_blocks': critical_blocks
        }
        
        return overall_pass

def main():
    print("🚀 Turkish Review Request Backend Validation")
    print("=" * 50)
    
    # Use local backend since preview environment is having connectivity issues
    base_url = "http://127.0.0.1:8001"
    admin_email = "canary.admin@platform.local"
    admin_password = "CanaryAdmin123!"
    user_email = "review.user@platform.local"
    user_password = "ReviewUser123!"
    
    validator = TurkishReviewBackendValidator(base_url)
    
    # Authenticate
    print("🔐 Authentication Phase")
    admin_auth = validator.authenticate_admin(admin_email, admin_password)
    user_auth = validator.authenticate_user(user_email, user_password)
    
    if not admin_auth or not user_auth:
        print("❌ Authentication failed. Cannot proceed with testing.")
        return False
    
    # Run tests
    validator.test_admin_410_endpoints()
    validator.test_user_working_endpoints()
    
    # Generate summary
    overall_pass = validator.generate_summary()
    
    # Save results
    with open('/app/turkish_review_backend_validation_results.json', 'w') as f:
        json.dump(validator.results, f, indent=2)
    
    print(f"\n📄 Results saved to: /app/turkish_review_backend_validation_results.json")
    
    return overall_pass

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)