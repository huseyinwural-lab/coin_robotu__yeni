#!/usr/bin/env python3
"""
FAZ-4 + FAZ-5 + FAZ-6 Backend Validation Test Suite
Comprehensive testing for doğrulama paketi requirements.
"""
import requests
import subprocess
import json
import sys
import os
import time
from typing import Dict, Any, List, Tuple

# Configuration
BACKEND_URL = "https://error-tracker-80.preview.emergentagent.com/api"
ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "Admin12345!")


class ValidationResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []
    
    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append((test_name, details))
        print(f"✅ PASS: {test_name}")
        if details:
            print(f"   {details}")
    
    def add_fail(self, test_name: str, error: str):
        self.failed.append((test_name, error))
        print(f"❌ FAIL: {test_name}")
        print(f"   Error: {error}")
    
    def add_skip(self, test_name: str, reason: str):
        self.skipped.append((test_name, reason))
        print(f"⏭️ SKIP: {test_name}")
        print(f"   Reason: {reason}")
    
    def summary(self):
        total = len(self.passed) + len(self.failed) + len(self.skipped)
        print(f"\n=== VALIDATION SUMMARY ===")
        print(f"Total tests: {total}")
        print(f"✅ Passed: {len(self.passed)}")
        print(f"❌ Failed: {len(self.failed)}")
        print(f"⏭️ Skipped: {len(self.skipped)}")
        
        if self.failed:
            print(f"\nFAILED TESTS:")
            for test_name, error in self.failed:
                print(f"  - {test_name}: {error}")
        
        return len(self.failed) == 0


def get_admin_token() -> str:
    """Get admin authentication token"""
    login_data = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    response = requests.post(f"{BACKEND_URL}/auth/login/admin", json=login_data)
    if response.status_code != 200:
        raise Exception(f"Admin login failed: {response.status_code} - {response.text}")
    
    return response.json().get("access_token")


def create_and_approve_user() -> Tuple[str, str]:
    """Create a new user and approve them. Returns (user_email, user_token)"""
    import random
    import time
    
    # Generate unique user email
    timestamp = int(time.time())
    user_email = f"test_user_faz_{timestamp}@test.com"
    user_password = "TestPassword123!"
    
    # Register user
    register_data = {
        "email": user_email,
        "password": user_password,
        "first_name": "Test",
        "last_name": "User",
        "phone_number": "+90555123456"
    }
    
    response = requests.post(f"{BACKEND_URL}/auth/register", json=register_data)
    if response.status_code != 200:
        raise Exception(f"User registration failed: {response.status_code} - {response.text}")
    
    # Get admin token for approval
    admin_token = get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Get pending users to find our user
    response = requests.get(f"{BACKEND_URL}/admin/user-approvals?status_filter=pending", headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to get pending approvals: {response.status_code}")
    
    pending_users = response.json()
    target_user = None
    for user in pending_users:
        if user["email"] == user_email:
            target_user = user
            break
    
    if not target_user:
        raise Exception(f"Newly registered user {user_email} not found in pending approvals")
    
    # Approve user
    approve_data = {"user_ids": [target_user["id"]]}
    response = requests.post(f"{BACKEND_URL}/admin/user-approvals/bulk-approve", 
                            json=approve_data, headers=headers)
    if response.status_code != 200:
        raise Exception(f"User approval failed: {response.status_code}")
    
    # Login as approved user
    login_data = {
        "email": user_email,
        "password": user_password
    }
    response = requests.post(f"{BACKEND_URL}/auth/login", json=login_data)
    if response.status_code != 200:
        raise Exception(f"User login failed: {response.status_code}")
    
    user_token = response.json().get("access_token")
    return user_email, user_token


class FAZValidator:
    def __init__(self):
        self.results = ValidationResults()
        self.admin_token = None
        self.user_token = None
        self.user_email = None
    
    def setup_authentication(self):
        """Setup admin and user authentication"""
        try:
            print("🔧 Setting up authentication...")
            self.admin_token = get_admin_token()
            self.user_email, self.user_token = create_and_approve_user()
            print(f"✅ Authentication setup complete. User: {self.user_email}")
        except Exception as e:
            print(f"❌ Authentication setup failed: {e}")
            sys.exit(1)
    
    def test_ci_gates(self):
        """1) Gate/CI validation"""
        print("\n=== 1) GATE/CI VALIDATION ===")
        
        # Test ci_alembic_drift_gate.sh
        try:
            result = subprocess.run(['/bin/bash', '/app/scripts/ci_alembic_drift_gate.sh'], 
                                 capture_output=True, text=True, cwd='/app')
            if result.returncode == 0:
                self.results.add_pass("bash /app/scripts/ci_alembic_drift_gate.sh", 
                                    f"Output: {result.stdout.strip()}")
            else:
                self.results.add_fail("bash /app/scripts/ci_alembic_drift_gate.sh", 
                                    f"Exit code: {result.returncode}, Output: {result.stderr}")
        except Exception as e:
            self.results.add_fail("bash /app/scripts/ci_alembic_drift_gate.sh", str(e))
        
        # Test ci_stage_gate.sh
        try:
            result = subprocess.run(['/bin/bash', '/app/scripts/ci_stage_gate.sh'], 
                                 capture_output=True, text=True, cwd='/app')
            if result.returncode == 0:
                self.results.add_pass("bash /app/scripts/ci_stage_gate.sh", 
                                    f"Output: {result.stdout.strip()}")
            else:
                self.results.add_fail("bash /app/scripts/ci_stage_gate.sh", 
                                    f"Exit code: {result.returncode}, Output: {result.stderr}")
        except Exception as e:
            self.results.add_fail("bash /app/scripts/ci_stage_gate.sh", str(e))
        
        # Test ci_prod_gate.sh
        try:
            result = subprocess.run(['/bin/bash', '/app/scripts/ci_prod_gate.sh'], 
                                 capture_output=True, text=True, cwd='/app')
            if result.returncode == 0:
                self.results.add_pass("bash /app/scripts/ci_prod_gate.sh", 
                                    f"Output: {result.stdout.strip()}")
            else:
                self.results.add_fail("bash /app/scripts/ci_prod_gate.sh", 
                                    f"Exit code: {result.returncode}, Output: {result.stderr}")
        except Exception as e:
            self.results.add_fail("bash /app/scripts/ci_prod_gate.sh", str(e))
    
    def test_hermetic_tests(self):
        """2) Hermetic test package validation"""
        print("\n=== 2) HERMETIC TEST PACKAGE ===")
        
        hermetic_tests = [
            "backend/tests/test_full_market_scan.py",
            "backend/tests/test_top_volume_fallback.py", 
            "backend/tests/test_decision_contract.py",
            "backend/tests/test_runtime_candidate_persistence.py",
            "backend/tests/test_freshness_policy.py",
            "backend/tests/test_event_priority_scheduler.py"
        ]
        
        for test_file in hermetic_tests:
            try:
                result = subprocess.run(['python', '-m', 'pytest', '-q', test_file], 
                                      capture_output=True, text=True, cwd='/app/backend',
                                      env=dict(os.environ, PYTHONPATH='/app/backend'))
                if result.returncode == 0:
                    self.results.add_pass(f"pytest {test_file}", 
                                        f"Output: {result.stdout.strip()}")
                else:
                    self.results.add_fail(f"pytest {test_file}", 
                                        f"Exit code: {result.returncode}, Output: {result.stderr}")
            except Exception as e:
                self.results.add_fail(f"pytest {test_file}", str(e))
    
    def test_endpoint_regressions(self):
        """3) Endpoint regression validation"""
        print("\n=== 3) ENDPOINT REGRESSIONS ===")
        
        # Health endpoint
        try:
            response = requests.get(f"{BACKEND_URL}/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    self.results.add_pass("GET /api/health", 
                                        f"Status: {response.status_code}, Response: {data}")
                else:
                    self.results.add_fail("GET /api/health", 
                                        f"Unexpected response: {data}")
            else:
                self.results.add_fail("GET /api/health", 
                                    f"Status: {response.status_code}, Body: {response.text}")
        except Exception as e:
            self.results.add_fail("GET /api/health", str(e))
        
        # Admin login
        try:
            login_data = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            response = requests.post(f"{BACKEND_URL}/auth/login/admin", json=login_data)
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.results.add_pass("POST /api/auth/login/admin", 
                                        f"Status: {response.status_code}, Token received")
                else:
                    self.results.add_fail("POST /api/auth/login/admin", 
                                        f"No access_token in response: {data}")
            else:
                self.results.add_fail("POST /api/auth/login/admin", 
                                    f"Status: {response.status_code}, Body: {response.text}")
        except Exception as e:
            self.results.add_fail("POST /api/auth/login/admin", str(e))
        
        # Universe monitor (admin endpoint)
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{BACKEND_URL}/admin/universe-monitor", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.results.add_pass("GET /api/admin/universe-monitor", 
                                    f"Status: {response.status_code}, Fields: {len(data.keys())}")
            else:
                self.results.add_fail("GET /api/admin/universe-monitor", 
                                    f"Status: {response.status_code}, Body: {response.text}")
        except Exception as e:
            self.results.add_fail("GET /api/admin/universe-monitor", str(e))
        
        # User scanner symbol selection (requires user registration + approval + login)
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = requests.get(f"{BACKEND_URL}/user/scanner/symbol-selection", headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.results.add_pass("GET /api/user/scanner/symbol-selection", 
                                    f"Status: {response.status_code}, User: {self.user_email}")
            else:
                self.results.add_fail("GET /api/user/scanner/symbol-selection", 
                                    f"Status: {response.status_code}, Body: {response.text}")
        except Exception as e:
            self.results.add_fail("GET /api/user/scanner/symbol-selection", str(e))
    
    def test_faz4_runtime_fields(self):
        """4) FAZ-4 runtime fields validation"""
        print("\n=== 4) FAZ-4 RUNTIME FIELDS ===")
        
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{BACKEND_URL}/admin/universe/runtime-summary", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check required FAZ-4 runtime fields
                required_fields = [
                    "freshness_sla_bucket",
                    "stale_skip_count", 
                    "queue_depth_state",
                    "backpressure_active",
                    "event_priority_distribution",
                    "fallback_reason_code"
                ]
                
                missing_fields = []
                present_fields = []
                
                for field in required_fields:
                    if field in data:
                        present_fields.append(field)
                    else:
                        missing_fields.append(field)
                
                if not missing_fields:
                    self.results.add_pass("FAZ-4 runtime fields in /api/admin/universe/runtime-summary",
                                        f"All required fields present: {present_fields}")
                else:
                    self.results.add_fail("FAZ-4 runtime fields in /api/admin/universe/runtime-summary",
                                        f"Missing fields: {missing_fields}, Present: {present_fields}")
            else:
                self.results.add_fail("FAZ-4 runtime fields test", 
                                    f"Status: {response.status_code}, Body: {response.text}")
        except Exception as e:
            self.results.add_fail("FAZ-4 runtime fields test", str(e))
    
    def test_faz5_decision_explainability(self):
        """5) FAZ-5 decision explainability contract validation"""
        print("\n=== 5) FAZ-5 DECISION EXPLAINABILITY ===")
        
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = requests.post(f"{BACKEND_URL}/user/scanner/runtime/run", 
                                   json={"max_results": 5}, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                if "decisions" in data and len(data["decisions"]) > 0:
                    decision = data["decisions"][0]
                    
                    # Check required FAZ-5 explainability fields
                    required_fields = [
                        "strategy_name",
                        "signal_strength",
                        "risk_filter_reason", 
                        "decision_reason"
                    ]
                    
                    missing_fields = []
                    present_fields = []
                    
                    for field in required_fields:
                        if field in decision:
                            present_fields.append(field)
                        else:
                            missing_fields.append(field)
                    
                    if not missing_fields:
                        self.results.add_pass("FAZ-5 explainability fields in /api/user/scanner/runtime/run decisions[]",
                                            f"All required fields present: {present_fields}")
                    else:
                        self.results.add_fail("FAZ-5 explainability fields in /api/user/scanner/runtime/run decisions[]",
                                            f"Missing fields: {missing_fields}, Present: {present_fields}")
                else:
                    self.results.add_fail("FAZ-5 explainability test", 
                                        f"No decisions in response: {data}")
            else:
                self.results.add_fail("FAZ-5 explainability test", 
                                    f"Status: {response.status_code}, Body: {response.text}")
        except Exception as e:
            self.results.add_fail("FAZ-5 explainability test", str(e))
    
    def test_faz6_ci_validation(self):
        """6) FAZ-6 CI validation"""
        print("\n=== 6) FAZ-6 CI VALIDATION ===")
        
        # Check if workflow scripts contain runtime test package
        scripts_to_check = [
            '/app/scripts/ci_stage_gate.sh',
            '/app/scripts/ci_prod_gate.sh'
        ]
        
        runtime_tests = [
            'test_full_market_scan.py',
            'test_top_volume_fallback.py',
            'test_decision_contract.py',
            'test_runtime_candidate_persistence.py',
            'test_freshness_policy.py',
            'test_event_priority_scheduler.py'
        ]
        
        for script_path in scripts_to_check:
            try:
                with open(script_path, 'r') as f:
                    content = f.read()
                
                missing_tests = []
                present_tests = []
                
                for test in runtime_tests:
                    if test in content:
                        present_tests.append(test)
                    else:
                        missing_tests.append(test)
                
                if not missing_tests:
                    self.results.add_pass(f"FAZ-6 runtime tests in {script_path}",
                                        f"All runtime tests found: {len(present_tests)}/6")
                else:
                    self.results.add_fail(f"FAZ-6 runtime tests in {script_path}",
                                        f"Missing tests: {missing_tests}")
                    
            except Exception as e:
                self.results.add_fail(f"FAZ-6 CI validation for {script_path}", str(e))
    
    def run_all_tests(self):
        """Run complete FAZ validation suite"""
        print("🚀 Starting FAZ-4 + FAZ-5 + FAZ-6 Doğrulama Paketi")
        print("=" * 60)
        
        self.setup_authentication()
        
        self.test_ci_gates()
        self.test_hermetic_tests() 
        self.test_endpoint_regressions()
        self.test_faz4_runtime_fields()
        self.test_faz5_decision_explainability()
        self.test_faz6_ci_validation()
        
        success = self.results.summary()
        
        if success:
            print("\n🎉 ALL FAZ VALIDATION TESTS PASSED!")
        else:
            print("\n💥 SOME VALIDATION TESTS FAILED!")
        
        return success


def main():
    validator = FAZValidator()
    success = validator.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()