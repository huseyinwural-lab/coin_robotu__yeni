#!/usr/bin/env python3
"""
User Live Trading Dashboard Backend API Deep Testing
Test live trading dashboard backend APIs for functionality, security, and user isolation
"""

import csv
import json
import os
import uuid
from pathlib import Path
from typing import Dict, Any

import requests


def resolve_base_url() -> str:
    """Resolve backend URL from environment or frontend/.env file"""
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    
    raise RuntimeError("REACT_APP_BACKEND_URL bulunamadı")


BASE_URL = resolve_base_url()
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"

print(f"🔗 Testing Backend URL: {BASE_URL}")
print(f"👤 Admin Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")

# Admin-scope fields that should NOT appear in user responses
FORBIDDEN_ADMIN_TOKENS = [
    "queue_depth", 
    "fallback_state", 
    "kill_switch", 
    "cluster_exposure", 
    "global", 
    "risk_veto", 
    "admin_scope",
    "system_wide",
    "raw_diagnostics"
]


class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        
    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append(f"✅ {test_name}: {details}")
        
    def add_fail(self, test_name: str, error: str):
        self.failed.append(f"❌ {test_name}: {error}")
        
    def print_summary(self):
        print("\n" + "="*80)
        print("🎯 LIVE TRADING DASHBOARD API TEST SONUÇLARI")
        print("="*80)
        
        if self.passed:
            print(f"\n✅ BAŞARILI TESTLER ({len(self.passed)}):")
            for result in self.passed:
                print(f"   {result}")
                
        if self.failed:
            print(f"\n❌ BAŞARISIZ TESTLER ({len(self.failed)}):")
            for result in self.failed:
                print(f"   {result}")
                
        total = len(self.passed) + len(self.failed)
        success_rate = (len(self.passed) / total * 100) if total > 0 else 0
        
        print(f"\n📊 ÖZET: {len(self.passed)}/{total} test başarılı (%{success_rate:.1f})")
        
        return len(self.failed) == 0


def get_admin_headers() -> Dict[str, str]:
    """Get admin authentication headers"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Admin login failed: {response.status_code} - {response.text}")
            
        token = response.json().get("access_token")
        if not token:
            raise Exception("access_token missing from admin login response")
            
        return {"Authorization": f"Bearer {token}"}
        
    except Exception as e:
        raise Exception(f"Admin auth error: {str(e)}")


def register_approve_login_user(admin_headers: Dict[str, str], email_prefix: str) -> Dict[str, Any]:
    """Register, approve, and login a new user"""
    try:
        email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
        password = "TestUser123!"
        
        # 1. Register user
        register_resp = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password},
            timeout=30
        )
        
        if register_resp.status_code != 200:
            raise Exception(f"User registration failed: {register_resp.status_code} - {register_resp.text}")
            
        user_data = register_resp.json()
        user_id = user_data.get("id")
        
        if not user_id:
            raise Exception("User ID missing from registration response")
        
        # 2. Admin approve user
        approve_resp = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers=admin_headers,
            timeout=30
        )
        
        if approve_resp.status_code != 200:
            raise Exception(f"User approval failed: {approve_resp.status_code} - {approve_resp.text}")
        
        # 3. Login as user
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
            timeout=30
        )
        
        if login_resp.status_code != 200:
            raise Exception(f"User login failed: {login_resp.status_code} - {login_resp.text}")
            
        user_token = login_resp.json().get("access_token")
        if not user_token:
            raise Exception("User access_token missing from login response")
            
        return {
            "headers": {"Authorization": f"Bearer {user_token}"},
            "email": email,
            "user_id": user_id
        }
        
    except Exception as e:
        raise Exception(f"User setup error: {str(e)}")


def create_bot_profile(user_headers: Dict[str, str], bot_name: str, symbol: str) -> str:
    """Create a bot profile for a user"""
    try:
        bot_data = {
            "name": bot_name,
            "exchange": "binance",
            "market_type": "spot",
            "symbols": [symbol],
            "strategy_type": "spot_pullback_v1",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True,
            "is_running": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            headers=user_headers,
            json=bot_data,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Bot creation failed: {response.status_code} - {response.text}")
            
        bot_id = response.json().get("id")
        if not bot_id:
            raise Exception("Bot ID missing from response")
            
        return bot_id
        
    except Exception as e:
        raise Exception(f"Bot creation error: {str(e)}")


def test_live_dashboard_endpoints(results: TestResults):
    """Test 1: All live dashboard endpoints return 200 with valid windows"""
    
    print("\n🔍 1. ENDPOINT STATUS KONTROLÜ")
    print("-" * 50)
    
    try:
        # Get admin and user credentials
        admin_headers = get_admin_headers()
        user_a = register_approve_login_user(admin_headers, "live_test_a")
        
        # Create bot for user to have some data
        try:
            create_bot_profile(user_a["headers"], "TestBot-A", "BTCUSDT")
        except:
            # Bot creation may fail but endpoint testing can continue
            pass
        
        endpoints = [
            "/api/user/live/summary",
            "/api/user/live/positions", 
            "/api/user/live/performance",
            "/api/user/live/risk",
            "/api/user/live/execution-quality",
            "/api/user/live/strategies",
            "/api/user/live/trades",
            "/api/user/live/daily-report"
        ]
        
        windows = ["1h", "6h", "24h"]
        
        endpoint_results = []
        for endpoint in endpoints:
            for window in windows:
                try:
                    params = {"window": window} if "positions" not in endpoint else {}
                    response = requests.get(
                        f"{BASE_URL}{endpoint}",
                        params=params,
                        headers=user_a["headers"],
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        endpoint_results.append(f"✅ {endpoint}?window={window}")
                    else:
                        endpoint_results.append(f"❌ {endpoint}?window={window} - {response.status_code}")
                        
                except Exception as e:
                    endpoint_results.append(f"❌ {endpoint}?window={window} - Error: {str(e)}")
        
        failed_count = len([r for r in endpoint_results if "❌" in r])
        passed_count = len(endpoint_results) - failed_count
        
        if failed_count == 0:
            results.add_pass("Endpoint Status", f"Tüm {passed_count} endpoint/window kombinasyonu çalışıyor")
        else:
            results.add_fail("Endpoint Status", f"{failed_count}/{len(endpoint_results)} endpoint başarısız")
            
        # Print details
        for result in endpoint_results[:10]:  # Show first 10 for brevity
            print(f"   {result}")
        if len(endpoint_results) > 10:
            print(f"   ... ve {len(endpoint_results) - 10} daha")
            
    except Exception as e:
        results.add_fail("Endpoint Status", f"Test setup error: {str(e)}")


def test_user_data_isolation(results: TestResults):
    """Test 2: User A data should not appear in User B responses"""
    
    print("\n🔍 2. KULLANICI VERİ İZOLASYONU")
    print("-" * 50)
    
    try:
        admin_headers = get_admin_headers()
        
        # Create two separate users
        user_a = register_approve_login_user(admin_headers, "isolation_a")
        user_b = register_approve_login_user(admin_headers, "isolation_b")
        
        print(f"   User A: {user_a['email']}")
        print(f"   User B: {user_b['email']}")
        
        # Create distinctive bots for each user
        bot_a_name = f"IsolationBot-A-{uuid.uuid4().hex[:6]}"
        bot_b_name = f"IsolationBot-B-{uuid.uuid4().hex[:6]}"
        
        try:
            create_bot_profile(user_a["headers"], bot_a_name, "ADAUSDT")
            create_bot_profile(user_b["headers"], bot_b_name, "ETHUSDT")
        except:
            # Continue testing even if bot creation fails
            pass
        
        # Test User A cannot see User B data
        test_endpoints = [
            "/api/user/live/summary",
            "/api/user/live/trades", 
            "/api/user/live/daily-report/export?format=json"
        ]
        
        isolation_violations = []
        
        for endpoint in test_endpoints:
            try:
                response = requests.get(
                    f"{BASE_URL}{endpoint}",
                    params={"window": "24h"},
                    headers=user_a["headers"],
                    timeout=30
                )
                
                if response.status_code == 200:
                    response_text = str(response.json() if endpoint.endswith("json") else response.text).lower()
                    
                    # Check if User A sees User B's data
                    if user_b["email"].lower() in response_text:
                        isolation_violations.append(f"User A görüyor User B email in {endpoint}")
                    
                    if bot_b_name.lower() in response_text:
                        isolation_violations.append(f"User A görüyor User B bot in {endpoint}")
                    
                    # Check if User A sees their own data (should)
                    if bot_a_name.lower() not in response_text and "summary" in endpoint:
                        print(f"   ⚠️  User A kendi bot'ını görmüyor: {endpoint}")
                        
            except Exception as e:
                print(f"   ⚠️  Error testing {endpoint}: {str(e)}")
        
        if not isolation_violations:
            results.add_pass("User Data Isolation", "User A ve User B verileri birbirinden izole")
        else:
            results.add_fail("User Data Isolation", f"{len(isolation_violations)} izolasyon ihlali: " + "; ".join(isolation_violations[:3]))
            
    except Exception as e:
        results.add_fail("User Data Isolation", f"Test error: {str(e)}")


def test_admin_scope_security(results: TestResults):
    """Test 3: No admin-scope fields in user responses"""
    
    print("\n🔍 3. ADMİN SCOPE GÜVENLİK KONTROLÜ")
    print("-" * 50)
    
    try:
        admin_headers = get_admin_headers()
        user = register_approve_login_user(admin_headers, "security_test")
        
        # Test all user endpoints for admin token leakage
        test_endpoints = [
            "/api/user/live/summary",
            "/api/user/live/positions",
            "/api/user/live/performance", 
            "/api/user/live/risk",
            "/api/user/live/execution-quality",
            "/api/user/live/strategies",
            "/api/user/live/trades",
            "/api/user/live/daily-report",
            "/api/user/live/daily-report/export?format=json"
        ]
        
        admin_leaks = []
        
        for endpoint in test_endpoints:
            try:
                response = requests.get(
                    f"{BASE_URL}{endpoint}",
                    params={"window": "24h"},
                    headers=user["headers"],
                    timeout=30
                )
                
                if response.status_code == 200:
                    response_lower = str(response.json() if "json" in endpoint else response.text).lower()
                    
                    for forbidden_token in FORBIDDEN_ADMIN_TOKENS:
                        if forbidden_token in response_lower:
                            admin_leaks.append(f"'{forbidden_token}' leaked in {endpoint}")
                            
            except Exception as e:
                print(f"   ⚠️  Error testing {endpoint}: {str(e)}")
        
        if not admin_leaks:
            results.add_pass("Admin Scope Security", f"Admin-scope alanlar user response'larında yok ({len(FORBIDDEN_ADMIN_TOKENS)} token kontrol edildi)")
        else:
            results.add_fail("Admin Scope Security", f"{len(admin_leaks)} admin token leaked: " + "; ".join(admin_leaks[:3]))
            
        # Show some checked tokens
        print(f"   Kontrol edilen admin tokenlar: {', '.join(FORBIDDEN_ADMIN_TOKENS[:5])}...")
            
    except Exception as e:
        results.add_fail("Admin Scope Security", f"Test error: {str(e)}")


def test_admin_access_control(results: TestResults):
    """Test 4: Admin tokens should get 403 on user endpoints (require_user)"""
    
    print("\n🔍 4. ADMİN ACCESS CONTROL")
    print("-" * 50)
    
    try:
        admin_headers = get_admin_headers()
        
        # Try to access user endpoints with admin token
        user_endpoints = [
            "/api/user/live/summary",
            "/api/user/live/positions",
            "/api/user/live/performance"
        ]
        
        access_violations = []
        correct_denials = []
        
        for endpoint in user_endpoints:
            try:
                response = requests.get(
                    f"{BASE_URL}{endpoint}",
                    params={"window": "1h"},
                    headers=admin_headers,
                    timeout=30
                )
                
                if response.status_code == 403:
                    correct_denials.append(endpoint)
                else:
                    access_violations.append(f"{endpoint} returned {response.status_code} (expected 403)")
                    
            except Exception as e:
                access_violations.append(f"{endpoint} error: {str(e)}")
        
        if not access_violations:
            results.add_pass("Admin Access Control", f"Admin token doğru şekilde {len(correct_denials)} user endpoint'ten 403 alıyor")
        else:
            results.add_fail("Admin Access Control", f"{len(access_violations)} access control ihlali: " + "; ".join(access_violations))
            
        print(f"   Admin'e doğru şekilde yasaklanan endpoint sayısı: {len(correct_denials)}")
            
    except Exception as e:
        results.add_fail("Admin Access Control", f"Test error: {str(e)}")


def test_csv_export_functionality(results: TestResults):
    """Test 5: CSV export content-type and structure validation"""
    
    print("\n🔍 5. CSV EXPORT KONTROLÜ") 
    print("-" * 50)
    
    try:
        admin_headers = get_admin_headers()
        user = register_approve_login_user(admin_headers, "csv_test")
        
        # Test both JSON and CSV formats
        export_results = []
        
        for format_type in ["json", "csv"]:
            try:
                response = requests.get(
                    f"{BASE_URL}/api/user/live/daily-report/export",
                    params={"format": format_type, "window": "24h"},
                    headers=user["headers"],
                    timeout=30
                )
                
                if response.status_code == 200:
                    if format_type == "csv":
                        # Check content-type for CSV
                        content_type = response.headers.get("content-type", "")
                        if "text/csv" in content_type:
                            export_results.append(f"✅ CSV content-type correct: {content_type}")
                        else:
                            export_results.append(f"❌ CSV content-type wrong: {content_type}")
                        
                        # Check CSV structure
                        csv_content = response.text
                        lines = csv_content.strip().split('\n')
                        if len(lines) >= 2:  # Header + data row
                            header_line = lines[0]
                            expected_headers = ["date", "window", "trades_today", "win_rate", "pnl_today"]
                            
                            header_check = all(header in header_line for header in expected_headers)
                            if header_check:
                                export_results.append(f"✅ CSV headers valid: {len(expected_headers)} required headers present")
                            else:
                                export_results.append(f"❌ CSV headers missing some required fields")
                        else:
                            export_results.append(f"❌ CSV structure invalid: {len(lines)} lines")
                    
                    elif format_type == "json":
                        # JSON format check
                        try:
                            json_data = response.json()
                            if isinstance(json_data, dict) and "report_id" in json_data:
                                export_results.append(f"✅ JSON format valid with report_id")
                            else:
                                export_results.append(f"❌ JSON format invalid structure")
                        except:
                            export_results.append(f"❌ JSON format parse error")
                else:
                    export_results.append(f"❌ Export {format_type} failed: {response.status_code}")
                    
            except Exception as e:
                export_results.append(f"❌ Export {format_type} error: {str(e)}")
        
        # Count results
        failed_exports = len([r for r in export_results if "❌" in r])
        
        if failed_exports == 0:
            results.add_pass("CSV Export", "JSON ve CSV export formatları çalışıyor, content-type ve headers doğru")
        else:
            results.add_fail("CSV Export", f"{failed_exports} export validation hatası")
            
        # Show export test details
        for result in export_results:
            print(f"   {result}")
            
    except Exception as e:
        results.add_fail("CSV Export", f"Test error: {str(e)}")


def main():
    """Run all live trading dashboard API tests"""
    
    print("🚀 USER LIVE TRADING DASHBOARD API DEEP TEST")
    print("=" * 80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test Admin: {ADMIN_EMAIL}")
    
    results = TestResults()
    
    try:
        # Test 1: Endpoint status and windows
        test_live_dashboard_endpoints(results)
        
        # Test 2: User data isolation (scope)
        test_user_data_isolation(results)
        
        # Test 3: Admin-scope field security
        test_admin_scope_security(results)
        
        # Test 4: Admin access control (require_user)
        test_admin_access_control(results)
        
        # Test 5: CSV export functionality
        test_csv_export_functionality(results)
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Critical test error: {str(e)}")
        results.add_fail("Test Framework", str(e))
    
    # Print final results
    success = results.print_summary()
    
    if success:
        print("\n🎉 TÜM TESTLER BAŞARILI! Live Trading Dashboard API'leri production ready.")
    else:
        print(f"\n⚠️  {len(results.failed)} test başarısız. Lütfen hataları düzeltin.")
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())