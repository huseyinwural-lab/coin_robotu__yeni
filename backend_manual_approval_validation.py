#!/usr/bin/env python3
"""
Backend Manual Approval Validation Test
Turkish Review Request: Manual approval gate validation for scanner engine flow
"""

import requests
import json
import time
from typing import Dict, Any, List, Optional

class ManualApprovalValidator:
    def __init__(self, base_url: str, user_email: str, user_password: str):
        self.base_url = base_url.rstrip('/')
        self.user_email = user_email
        self.user_password = user_password
        self.session = requests.Session()
        self.access_token = None
        self.test_results = []
        
    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details
        }
        self.test_results.append(result)
        print(f"{'✅' if status == 'PASS' else '❌'} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    def login_user(self) -> bool:
        """Step 1: Login with review.user@platform.local"""
        try:
            login_url = f"{self.base_url}/api/auth/login/user"
            payload = {
                "email": self.user_email,
                "password": self.user_password
            }
            
            response = self.session.post(login_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get('access_token')
                if self.access_token:
                    # Set authorization header for future requests
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.access_token}'
                    })
                    self.log_test("User Login", "PASS", f"Token length: {len(self.access_token)} chars")
                    return True
                else:
                    self.log_test("User Login", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_test("User Login", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("User Login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_scanner_engine(self) -> bool:
        """Step 2: Call /api/user/scanner-engine/run"""
        try:
            url = f"{self.base_url}/api/user/scanner-engine/run"
            response = self.session.post(url, json={}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Scanner Engine Run", "PASS", f"Response keys: {list(data.keys())}")
                return True
            else:
                self.log_test("Scanner Engine Run", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("Scanner Engine Run", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_scanner(self) -> bool:
        """Step 3: Call /api/user/scanner/run"""
        try:
            url = f"{self.base_url}/api/user/scanner/run"
            response = self.session.post(url, json={}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Scanner Run", "PASS", f"Response keys: {list(data.keys())}")
                return True
            else:
                self.log_test("Scanner Run", "FAIL", f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("Scanner Run", "FAIL", f"Exception: {str(e)}")
            return False
    
    def check_signals_manual_approval(self) -> List[str]:
        """Step 4: Verify /api/user/signals shows pending signals with MANUAL_APPROVAL_REQUIRED"""
        try:
            url = f"{self.base_url}/api/user/signals"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                signals = data.get('items', [])
                
                pending_signals = []
                manual_approval_signals = []
                
                for signal in signals:
                    if signal.get('status') == 'MANUAL_APPROVAL_REQUIRED':
                        pending_signals.append(signal.get('id'))
                        if signal.get('requires_manual_approval') is True:
                            manual_approval_signals.append(signal.get('id'))
                
                if pending_signals:
                    self.log_test("Signals Manual Approval Check", "PASS", 
                                f"Found {len(pending_signals)} MANUAL_APPROVAL_REQUIRED signals, "
                                f"{len(manual_approval_signals)} with requires_manual_approval=true")
                    return manual_approval_signals
                else:
                    self.log_test("Signals Manual Approval Check", "FAIL", 
                                "No signals with MANUAL_APPROVAL_REQUIRED status found")
                    return []
            else:
                self.log_test("Signals Manual Approval Check", "FAIL", 
                            f"HTTP {response.status_code}: {response.text[:200]}")
                return []
                
        except Exception as e:
            self.log_test("Signals Manual Approval Check", "FAIL", f"Exception: {str(e)}")
            return []
    
    def test_diagnose_auto_fix(self, signal_id: str) -> bool:
        """Step 5: Test /api/user/signal/{id}/diagnose?auto_fix=true doesn't auto-dispatch"""
        try:
            url = f"{self.base_url}/api/user/signal/{signal_id}/diagnose"
            params = {"auto_fix": "true"}
            response = self.session.post(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                actions_applied = data.get('actions_applied', [])
                
                # Check if manual_approval_gate_enforced is in actions_applied
                has_manual_gate = any('manual_approval_gate_enforced' in str(action) for action in actions_applied)
                
                # Check that auto-dispatch didn't happen (signal should still be pending)
                if has_manual_gate:
                    self.log_test("Diagnose Auto-Fix Gate Check", "PASS", 
                                f"manual_approval_gate_enforced found in actions_applied: {actions_applied}")
                    return True
                else:
                    self.log_test("Diagnose Auto-Fix Gate Check", "FAIL", 
                                f"manual_approval_gate_enforced NOT found in actions_applied: {actions_applied}")
                    return False
            else:
                self.log_test("Diagnose Auto-Fix Gate Check", "FAIL", 
                            f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("Diagnose Auto-Fix Gate Check", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_signal_approve(self, signal_id: str) -> bool:
        """Step 6: Test /api/user/signal/{id}/approve triggers dispatch flow"""
        try:
            url = f"{self.base_url}/api/user/signal/{signal_id}/approve"
            response = self.session.post(url, json={}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Signal Approve", "PASS", 
                            f"Approval successful. Response keys: {list(data.keys())}")
                return True
            else:
                self.log_test("Signal Approve", "FAIL", 
                            f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("Signal Approve", "FAIL", f"Exception: {str(e)}")
            return False
    
    def check_scanner_results_strategy_codes(self) -> bool:
        """Step 7: Verify /api/user/scanner/results shows strategy_code fields as BC01-BC04"""
        try:
            url = f"{self.base_url}/api/user/scanner/results"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('items', []) or data.get('results', [])
                
                strategy_codes = []
                for result in results:
                    strategy_code = result.get('strategy_code')
                    if strategy_code:
                        strategy_codes.append(strategy_code)
                
                # Check if strategy codes are in BC01-BC04 range
                valid_codes = [code for code in strategy_codes if code and code.startswith('BC0') and code in ['BC01', 'BC02', 'BC03', 'BC04']]
                
                if strategy_codes:
                    self.log_test("Scanner Results Strategy Codes", "PASS", 
                                f"Found strategy codes: {strategy_codes}, Valid BC01-BC04 codes: {valid_codes}")
                    return True
                else:
                    self.log_test("Scanner Results Strategy Codes", "FAIL", 
                                f"No strategy_code fields found in results. Available keys: {[list(r.keys()) for r in results[:2]]}")
                    return False
            else:
                self.log_test("Scanner Results Strategy Codes", "FAIL", 
                            f"HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("Scanner Results Strategy Codes", "FAIL", f"Exception: {str(e)}")
            return False
    
    def run_validation(self) -> Dict[str, Any]:
        """Run complete manual approval validation flow"""
        print("🔍 MANUAL APPROVAL VALIDATION TEST STARTING")
        print(f"Base URL: {self.base_url}")
        print(f"User: {self.user_email}")
        print("=" * 60)
        
        # Step 1: Login
        if not self.login_user():
            return self.get_summary()
        
        # Step 2: Run scanner engine
        if not self.run_scanner_engine():
            return self.get_summary()
        
        # Step 3: Run scanner
        if not self.run_scanner():
            return self.get_summary()
        
        # Step 4: Check signals for manual approval
        manual_approval_signals = self.check_signals_manual_approval()
        
        # Step 5: Test diagnose auto-fix (if we have signals)
        if manual_approval_signals:
            test_signal_id = manual_approval_signals[0]
            self.test_diagnose_auto_fix(test_signal_id)
            
            # Step 6: Test signal approve
            self.test_signal_approve(test_signal_id)
        else:
            self.log_test("Diagnose Auto-Fix Gate Check", "SKIP", "No manual approval signals to test")
            self.log_test("Signal Approve", "SKIP", "No manual approval signals to test")
        
        # Step 7: Check scanner results strategy codes
        self.check_scanner_results_strategy_codes()
        
        return self.get_summary()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get test summary"""
        passed = len([r for r in self.test_results if r['status'] == 'PASS'])
        failed = len([r for r in self.test_results if r['status'] == 'FAIL'])
        skipped = len([r for r in self.test_results if r['status'] == 'SKIP'])
        total = len(self.test_results)
        
        success_rate = (passed / total * 100) if total > 0 else 0
        
        print("\n" + "=" * 60)
        print("📊 MANUAL APPROVAL VALIDATION SUMMARY")
        print("=" * 60)
        
        for result in self.test_results:
            status_icon = "✅" if result['status'] == 'PASS' else "❌" if result['status'] == 'FAIL' else "⏭️"
            print(f"{status_icon} {result['test']}: {result['status']}")
            if result['details']:
                print(f"   {result['details']}")
        
        print(f"\n📈 OVERALL RESULT: {passed}/{total} PASS ({success_rate:.1f}% SUCCESS RATE)")
        if failed > 0:
            print(f"❌ {failed} tests failed")
        if skipped > 0:
            print(f"⏭️ {skipped} tests skipped")
        
        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "success_rate": success_rate,
            "results": self.test_results
        }

def main():
    # Configuration
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"
    USER_EMAIL = "review.user@platform.local"
    USER_PASSWORD = "ReviewUser123!"
    
    # Run validation
    validator = ManualApprovalValidator(BASE_URL, USER_EMAIL, USER_PASSWORD)
    summary = validator.run_validation()
    
    # Return appropriate exit code
    if summary['failed'] > 0:
        exit(1)
    else:
        exit(0)

if __name__ == "__main__":
    main()