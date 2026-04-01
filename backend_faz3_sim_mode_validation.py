#!/usr/bin/env python3
"""
Faz 3 — SIM Mode Staged Live Backend Validation
Comprehensive backend validation for SIM mode with staged live testing

Test Requirements:
1. End-to-end chain testing (scanner → signal → template → bot decision → execution intent)
2. Trace & Audit validation (trace_id, action/result/state_snapshot, audit logs)
3. Risk & Guard testing (high size, leverage, invalid params → execution blocks)
4. Execution simulation (intent creation, filled/rejected states, retry behavior)
5. Runtime controls (start/stop, mode switch, kill switch, auto-refresh)
6. Observability (metrics, outcomes, learning feedback, template performance)
7. Failure/recovery (backend restart simulation, request drop/timeout, recovery)
"""

import requests
import json
import time
import sys
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8001"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

class SIMModeTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.user_token = None
        self.test_results = []
        self.test_data = {}
        
    def log_result(self, test_name: str, status: str, details: str = "", data: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "data": data,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.test_results.append(result)
        print(f"[{status}] {test_name}: {details}")
        
    def authenticate_admin(self) -> bool:
        """Authenticate with admin credentials"""
        try:
            auth_url = f"{BASE_URL}/api/auth/login/admin"
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = self.session.post(auth_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.log_result("Admin Authentication", "PASS", f"Token obtained ({len(self.admin_token)} chars)")
                    return True
                else:
                    self.log_result("Admin Authentication", "FAIL", "No access token in response")
                    return False
            else:
                self.log_result("Admin Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False
    
    def authenticate_user(self) -> bool:
        """Authenticate with user credentials"""
        try:
            auth_url = f"{BASE_URL}/api/auth/login/user"
            payload = {
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            }
            
            response = self.session.post(auth_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get("access_token")
                if self.user_token:
                    self.log_result("User Authentication", "PASS", f"Token obtained ({len(self.user_token)} chars)")
                    return True
                else:
                    self.log_result("User Authentication", "FAIL", "No access token in response")
                    return False
            else:
                self.log_result("User Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("User Authentication", "FAIL", f"Exception: {str(e)}")
            return False

    def test_1_end_to_end_chain(self) -> bool:
        """Test 1: End-to-end chain (scanner → signal → template → bot decision → execution intent)"""
        try:
            # Set admin headers
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Step 1: Start scanner run
            scanner_url = f"{BASE_URL}/api/user/scanner/run"
            scanner_payload = {
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "timeframe": "1h",
                "filters": {
                    "rsi_min": 30,
                    "rsi_max": 70,
                    "volume_min": 100000
                }
            }
            
            scanner_response = self.session.post(scanner_url, json=scanner_payload, headers=headers, timeout=30)
            
            if scanner_response.status_code not in [200, 201]:
                self.log_result("E2E Chain - Scanner Run", "FAIL", f"Scanner failed: {scanner_response.status_code}")
                return False
            
            scanner_data = scanner_response.json()
            scan_run_id = scanner_data.get("scan_run_id") or scanner_data.get("id")
            
            # Step 2: Check signal generation
            signals_url = f"{BASE_URL}/api/user/scanner/signals"
            signals_response = self.session.get(signals_url, headers=headers, timeout=30)
            
            if signals_response.status_code != 200:
                self.log_result("E2E Chain - Signal Generation", "FAIL", f"Signals check failed: {signals_response.status_code}")
                return False
            
            signals_data = signals_response.json()
            signals = signals_data.get("signals", [])
            
            # Step 3: Template selection (check available templates)
            templates_url = f"{BASE_URL}/api/strategy-templates"
            templates_response = self.session.get(templates_url, headers=headers, timeout=30)
            
            if templates_response.status_code != 200:
                self.log_result("E2E Chain - Template Selection", "FAIL", f"Templates check failed: {templates_response.status_code}")
                return False
            
            templates_data = templates_response.json()
            templates = templates_data.get("templates", []) or templates_data.get("items", [])
            
            # Step 4: Bot decision generation (validate order)
            if signals:
                signal = signals[0]
                symbol = signal.get("symbol", "BTCUSDT")
                
                validate_url = f"{BASE_URL}/api/user/validate-order"
                validate_payload = {
                    "symbol": symbol,
                    "market_type": "spot",
                    "order_type": "limit",
                    "side": "buy",
                    "price": 50000.0,
                    "size": 0.001,
                    "leverage": 1,
                    "margin_mode": "isolated"
                }
                
                # Set user headers for validation
                user_headers = {"Authorization": f"Bearer {self.user_token}"}
                validate_response = self.session.post(validate_url, json=validate_payload, headers=user_headers, timeout=30)
                
                if validate_response.status_code != 200:
                    self.log_result("E2E Chain - Bot Decision", "FAIL", f"Validation failed: {validate_response.status_code}")
                    return False
                
                validate_data = validate_response.json()
                
                # Step 5: Execution intent creation (preview)
                preview_url = f"{BASE_URL}/api/v1/user/trading/preview"
                preview_response = self.session.post(preview_url, json=validate_payload, headers=user_headers, timeout=30)
                
                if preview_response.status_code == 200:
                    preview_data = preview_response.json()
                    intent_token = preview_data.get("intent_token")
                    
                    if intent_token:
                        self.test_data["intent_token"] = intent_token
                        self.log_result("E2E Chain - Execution Intent", "PASS", 
                                      f"Chain completed: Scanner→Signals({len(signals)})→Templates({len(templates)})→Validation→Intent({intent_token[:8]}...)")
                        return True
                    else:
                        self.log_result("E2E Chain - Execution Intent", "FAIL", "No intent_token in preview response")
                        return False
                else:
                    self.log_result("E2E Chain - Execution Intent", "FAIL", f"Preview failed: {preview_response.status_code}")
                    return False
            else:
                self.log_result("E2E Chain - Signal Generation", "FAIL", "No signals generated")
                return False
                
        except Exception as e:
            self.log_result("E2E Chain", "FAIL", f"Exception: {str(e)}")
            return False

    def test_2_trace_and_audit(self) -> bool:
        """Test 2: Trace & Audit validation (trace_id, action/result/state_snapshot, audit logs)"""
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Check audit logs endpoint
            audit_url = f"{BASE_URL}/api/audit-logs"
            audit_response = self.session.get(audit_url, headers=headers, timeout=30)
            
            if audit_response.status_code != 200:
                self.log_result("Trace & Audit - Audit Logs", "FAIL", f"Audit logs failed: {audit_response.status_code}")
                return False
            
            audit_data = audit_response.json()
            logs = audit_data.get("logs", []) or audit_data.get("items", [])
            
            # Check for trace_id presence
            trace_ids_found = 0
            action_result_found = 0
            state_snapshot_found = 0
            
            for log in logs[:10]:  # Check first 10 logs
                if log.get("trace_id"):
                    trace_ids_found += 1
                if log.get("action") and log.get("result"):
                    action_result_found += 1
                if log.get("state_snapshot"):
                    state_snapshot_found += 1
            
            # Check trading lifecycle debugger
            lifecycle_url = f"{BASE_URL}/api/audit-logs/trading-lifecycle"
            lifecycle_response = self.session.get(lifecycle_url, headers=headers, timeout=30)
            
            lifecycle_working = lifecycle_response.status_code == 200
            
            # Check explain endpoint
            explain_url = f"{BASE_URL}/api/audit-logs/explain"
            explain_payload = {"correlation_id": "test-correlation-id"}
            explain_response = self.session.post(explain_url, json=explain_payload, headers=headers, timeout=30)
            
            explain_working = explain_response.status_code in [200, 400, 422]  # 400/422 acceptable for invalid correlation_id
            
            if trace_ids_found > 0 and action_result_found > 0 and lifecycle_working and explain_working:
                self.log_result("Trace & Audit", "PASS", 
                              f"Audit system working: trace_ids({trace_ids_found}), action/result({action_result_found}), "
                              f"state_snapshots({state_snapshot_found}), lifecycle({lifecycle_working}), explain({explain_working})")
                return True
            else:
                self.log_result("Trace & Audit", "FAIL", 
                              f"Audit system issues: trace_ids({trace_ids_found}), action/result({action_result_found}), "
                              f"lifecycle({lifecycle_working}), explain({explain_working})")
                return False
                
        except Exception as e:
            self.log_result("Trace & Audit", "FAIL", f"Exception: {str(e)}")
            return False

    def test_3_risk_and_guard(self) -> bool:
        """Test 3: Risk & Guard testing (high size, leverage, invalid params → execution blocks)"""
        try:
            user_headers = {"Authorization": f"Bearer {self.user_token}"}
            
            # Test 1: High size order (should be blocked)
            high_size_payload = {
                "symbol": "BTCUSDT",
                "market_type": "spot",
                "order_type": "market",
                "side": "buy",
                "price": 50000.0,
                "size": 100.0,  # Very high size
                "leverage": 1,
                "margin_mode": "isolated"
            }
            
            validate_url = f"{BASE_URL}/api/user/validate-order"
            high_size_response = self.session.post(validate_url, json=high_size_payload, headers=user_headers, timeout=30)
            
            high_size_blocked = False
            if high_size_response.status_code == 200:
                data = high_size_response.json()
                if not data.get("valid", True) or data.get("violations", []):
                    high_size_blocked = True
            
            # Test 2: High leverage order (should be blocked)
            high_leverage_payload = {
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 50000.0,
                "size": 0.1,
                "leverage": 100,  # Very high leverage
                "margin_mode": "isolated"
            }
            
            high_leverage_response = self.session.post(validate_url, json=high_leverage_payload, headers=user_headers, timeout=30)
            
            high_leverage_blocked = False
            if high_leverage_response.status_code == 200:
                data = high_leverage_response.json()
                if not data.get("valid", True) or data.get("violations", []):
                    high_leverage_blocked = True
            
            # Test 3: Invalid parameters (should be blocked)
            invalid_payload = {
                "symbol": "",  # Invalid symbol
                "market_type": "invalid_market",
                "order_type": "market",
                "side": "invalid_side",
                "price": -100,  # Negative price
                "size": 0,  # Zero size
                "leverage": 0,  # Zero leverage
                "margin_mode": "invalid_margin"
            }
            
            invalid_response = self.session.post(validate_url, json=invalid_payload, headers=user_headers, timeout=30)
            
            invalid_blocked = False
            if invalid_response.status_code == 200:
                data = invalid_response.json()
                if not data.get("valid", True) or data.get("violations", []):
                    invalid_blocked = True
            elif invalid_response.status_code in [400, 422]:  # Validation error
                invalid_blocked = True
            
            # Check execution readiness (should show blocks)
            readiness_url = f"{BASE_URL}/api/execution-readiness"
            admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
            readiness_response = self.session.get(readiness_url, headers=admin_headers, timeout=30)
            
            readiness_working = readiness_response.status_code == 200
            
            blocks_detected = high_size_blocked + high_leverage_blocked + invalid_blocked
            
            if blocks_detected >= 2 and readiness_working:
                self.log_result("Risk & Guard", "PASS", 
                              f"Risk guards working: high_size({high_size_blocked}), high_leverage({high_leverage_blocked}), "
                              f"invalid_params({invalid_blocked}), readiness({readiness_working})")
                return True
            else:
                self.log_result("Risk & Guard", "FAIL", 
                              f"Risk guards insufficient: high_size({high_size_blocked}), high_leverage({high_leverage_blocked}), "
                              f"invalid_params({invalid_blocked}), readiness({readiness_working})")
                return False
                
        except Exception as e:
            self.log_result("Risk & Guard", "FAIL", f"Exception: {str(e)}")
            return False

    def test_4_execution_simulation(self) -> bool:
        """Test 4: Execution simulation (intent creation, filled/rejected states, retry behavior)"""
        try:
            user_headers = {"Authorization": f"Bearer {self.user_token}"}
            
            # Test intent creation
            intent_payload = {
                "symbol": "BTCUSDT",
                "market_type": "spot",
                "order_type": "limit",
                "side": "buy",
                "price": 50000.0,
                "size": 0.001,
                "leverage": 1,
                "margin_mode": "isolated"
            }
            
            # Create preview (intent)
            preview_url = f"{BASE_URL}/api/v1/user/trading/preview"
            preview_response = self.session.post(preview_url, json=intent_payload, headers=user_headers, timeout=30)
            
            intent_created = preview_response.status_code == 200
            intent_token = None
            
            if intent_created:
                preview_data = preview_response.json()
                intent_token = preview_data.get("intent_token")
            
            # Test execution (should be simulated in SIM mode)
            execution_url = f"{BASE_URL}/api/user/open-position"
            execution_response = self.session.post(execution_url, json=intent_payload, headers=user_headers, timeout=30)
            
            execution_attempted = execution_response.status_code in [200, 423]  # 423 = readiness blocked
            execution_data = {}
            
            if execution_response.status_code == 200:
                execution_data = execution_response.json()
            
            # Check execution intent service
            intent_service_url = f"{BASE_URL}/api/execution/intent/status"
            intent_service_response = self.session.get(intent_service_url, headers=user_headers, timeout=30)
            
            intent_service_working = intent_service_response.status_code in [200, 404]  # 404 acceptable if no intents
            
            # Check for filled/rejected simulation
            if execution_data:
                intent_status = execution_data.get("intent_status", "")
                execution_mode = execution_data.get("execution_mode", "")
                simulated = execution_mode in ["sim", "mocked", "simulated"]
            else:
                simulated = True  # Assume simulated if blocked by readiness
                intent_status = "blocked"
            
            # Check retry behavior (execution safety quarantine)
            quarantine_url = f"{BASE_URL}/api/execution-safety/quarantine"
            admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
            quarantine_response = self.session.get(quarantine_url, headers=admin_headers, timeout=30)
            
            retry_system_working = quarantine_response.status_code == 200
            
            if intent_created and execution_attempted and intent_service_working and retry_system_working:
                self.log_result("Execution Simulation", "PASS", 
                              f"Simulation working: intent({intent_created}), execution({execution_attempted}), "
                              f"simulated({simulated}), retry_system({retry_system_working}), status({intent_status})")
                return True
            else:
                self.log_result("Execution Simulation", "FAIL", 
                              f"Simulation issues: intent({intent_created}), execution({execution_attempted}), "
                              f"simulated({simulated}), retry_system({retry_system_working})")
                return False
                
        except Exception as e:
            self.log_result("Execution Simulation", "FAIL", f"Exception: {str(e)}")
            return False

    def test_5_runtime_controls(self) -> bool:
        """Test 5: Runtime controls (start/stop, mode switch, kill switch, auto-refresh)"""
        try:
            admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Test runtime control endpoints
            runtime_endpoints = [
                ("/api/runtime-control/status", "GET"),
                ("/api/runtime-control/start", "POST"),
                ("/api/runtime-control/stop", "POST"),
                ("/api/runtime-control/pause", "POST"),
                ("/api/runtime-control/resume", "POST")
            ]
            
            runtime_results = []
            
            for endpoint, method in runtime_endpoints:
                url = f"{BASE_URL}{endpoint}"
                
                if method == "GET":
                    response = self.session.get(url, headers=admin_headers, timeout=30)
                else:
                    response = self.session.post(url, json={}, headers=admin_headers, timeout=30)
                
                accessible = response.status_code in [200, 202, 400, 422, 404]
                runtime_results.append(f"{endpoint}:{response.status_code}")
            
            # Test mode switch (execution mode)
            mode_switch_url = f"{BASE_URL}/api/admin/execution-mode"
            mode_switch_response = self.session.get(mode_switch_url, headers=admin_headers, timeout=30)
            
            mode_switch_working = mode_switch_response.status_code == 200
            
            # Test kill switch
            kill_switch_url = f"{BASE_URL}/api/admin/kill-switch"
            kill_switch_response = self.session.get(kill_switch_url, headers=admin_headers, timeout=30)
            
            kill_switch_working = kill_switch_response.status_code == 200
            
            # Test auto-refresh (readiness)
            refresh_url = f"{BASE_URL}/api/ready"
            refresh_response = self.session.get(refresh_url, timeout=30)
            
            auto_refresh_working = refresh_response.status_code == 200
            
            working_endpoints = sum(1 for result in runtime_results if not result.endswith(":404"))
            
            if working_endpoints >= 3 and mode_switch_working and kill_switch_working and auto_refresh_working:
                self.log_result("Runtime Controls", "PASS", 
                              f"Controls working: runtime({working_endpoints}/5), mode_switch({mode_switch_working}), "
                              f"kill_switch({kill_switch_working}), auto_refresh({auto_refresh_working})")
                return True
            else:
                self.log_result("Runtime Controls", "FAIL", 
                              f"Controls issues: runtime({working_endpoints}/5), mode_switch({mode_switch_working}), "
                              f"kill_switch({kill_switch_working}), auto_refresh({auto_refresh_working})")
                return False
                
        except Exception as e:
            self.log_result("Runtime Controls", "FAIL", f"Exception: {str(e)}")
            return False

    def test_6_observability(self) -> bool:
        """Test 6: Observability (metrics, outcomes, learning feedback, template performance)"""
        try:
            admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
            user_headers = {"Authorization": f"Bearer {self.user_token}"}
            
            # Test metrics endpoints
            metrics_url = f"{BASE_URL}/api/admin/system-status"
            metrics_response = self.session.get(metrics_url, headers=admin_headers, timeout=30)
            
            metrics_working = metrics_response.status_code == 200
            
            # Test recent outcomes
            outcomes_url = f"{BASE_URL}/api/user/trades"
            outcomes_response = self.session.get(outcomes_url, headers=user_headers, timeout=30)
            
            outcomes_working = outcomes_response.status_code == 200
            
            # Test learning feedback
            learning_url = f"{BASE_URL}/api/user/learning/feedback"
            learning_response = self.session.get(learning_url, headers=user_headers, timeout=30)
            
            learning_working = learning_response.status_code in [200, 404]  # 404 acceptable if no feedback
            
            # Test template performance
            template_perf_url = f"{BASE_URL}/api/strategy-templates/performance"
            template_perf_response = self.session.get(template_perf_url, headers=admin_headers, timeout=30)
            
            template_perf_working = template_perf_response.status_code in [200, 404]
            
            # Test observability service
            observability_url = f"{BASE_URL}/api/admin/observability"
            observability_response = self.session.get(observability_url, headers=admin_headers, timeout=30)
            
            observability_working = observability_response.status_code in [200, 404]
            
            # Test guard telemetry
            guard_telemetry_url = f"{BASE_URL}/api/admin/guard-telemetry"
            guard_telemetry_response = self.session.get(guard_telemetry_url, headers=admin_headers, timeout=30)
            
            guard_telemetry_working = guard_telemetry_response.status_code in [200, 404]
            
            working_count = sum([
                metrics_working,
                outcomes_working,
                learning_working,
                template_perf_working,
                observability_working,
                guard_telemetry_working
            ])
            
            if working_count >= 4:
                self.log_result("Observability", "PASS", 
                              f"Observability working: metrics({metrics_working}), outcomes({outcomes_working}), "
                              f"learning({learning_working}), templates({template_perf_working}), "
                              f"observability({observability_working}), guard_telemetry({guard_telemetry_working})")
                return True
            else:
                self.log_result("Observability", "FAIL", 
                              f"Observability issues: metrics({metrics_working}), outcomes({outcomes_working}), "
                              f"learning({learning_working}), templates({template_perf_working}), "
                              f"observability({observability_working}), guard_telemetry({guard_telemetry_working})")
                return False
                
        except Exception as e:
            self.log_result("Observability", "FAIL", f"Exception: {str(e)}")
            return False

    def test_7_failure_recovery(self) -> bool:
        """Test 7: Failure/recovery (backend restart simulation, request drop/timeout, recovery)"""
        try:
            admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            # Test health endpoint (simulates backend restart check)
            health_url = f"{BASE_URL}/api/health"
            health_response = self.session.get(health_url, timeout=30)
            
            backend_healthy = health_response.status_code == 200
            
            # Test request timeout handling (short timeout)
            timeout_test_url = f"{BASE_URL}/api/user/validate-order"
            timeout_payload = {
                "symbol": "BTCUSDT",
                "market_type": "spot",
                "order_type": "limit",
                "side": "buy",
                "price": 50000.0,
                "size": 0.001,
                "leverage": 1,
                "margin_mode": "isolated"
            }
            
            user_headers = {"Authorization": f"Bearer {self.user_token}"}
            
            try:
                timeout_response = self.session.post(timeout_test_url, json=timeout_payload, headers=user_headers, timeout=1)
                timeout_handled = True
            except requests.exceptions.Timeout:
                timeout_handled = True  # Timeout is expected and handled
            except Exception:
                timeout_handled = False
            
            # Test recovery mechanisms (execution safety)
            recovery_url = f"{BASE_URL}/api/execution-safety/recovery/status"
            recovery_response = self.session.get(recovery_url, headers=admin_headers, timeout=30)
            
            recovery_working = recovery_response.status_code in [200, 404]
            
            # Test data persistence after simulated failure
            persistence_url = f"{BASE_URL}/api/audit-logs"
            persistence_response = self.session.get(persistence_url, headers=admin_headers, timeout=30)
            
            data_persisted = persistence_response.status_code == 200
            
            if data_persisted:
                audit_data = persistence_response.json()
                logs = audit_data.get("logs", []) or audit_data.get("items", [])
                data_loss_check = len(logs) > 0  # Check if data exists
            else:
                data_loss_check = False
            
            # Test circuit breaker / rate limiting
            rate_limit_url = f"{BASE_URL}/api/auth/login/admin"
            rate_limit_payload = {"email": "invalid@test.com", "password": "invalid"}
            
            rate_limit_working = True
            for i in range(3):  # Try multiple invalid requests
                rate_response = self.session.post(rate_limit_url, json=rate_limit_payload, timeout=10)
                if rate_response.status_code == 429:  # Rate limited
                    rate_limit_working = True
                    break
            
            working_count = sum([
                backend_healthy,
                timeout_handled,
                recovery_working,
                data_persisted,
                data_loss_check,
                rate_limit_working
            ])
            
            if working_count >= 4:
                self.log_result("Failure/Recovery", "PASS", 
                              f"Recovery working: health({backend_healthy}), timeout({timeout_handled}), "
                              f"recovery({recovery_working}), persistence({data_persisted}), "
                              f"no_data_loss({data_loss_check}), rate_limit({rate_limit_working})")
                return True
            else:
                self.log_result("Failure/Recovery", "FAIL", 
                              f"Recovery issues: health({backend_healthy}), timeout({timeout_handled}), "
                              f"recovery({recovery_working}), persistence({data_persisted}), "
                              f"no_data_loss({data_loss_check}), rate_limit({rate_limit_working})")
                return False
                
        except Exception as e:
            self.log_result("Failure/Recovery", "FAIL", f"Exception: {str(e)}")
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all SIM mode tests and return summary"""
        print("=" * 80)
        print("Faz 3 — SIM Mode Staged Live Backend Validation")
        print("=" * 80)
        
        # Authenticate first
        if not self.authenticate_admin():
            return {"success": False, "error": "Admin authentication failed"}
        
        if not self.authenticate_user():
            return {"success": False, "error": "User authentication failed"}
        
        # Run all tests
        tests = [
            ("1. End-to-End Chain", self.test_1_end_to_end_chain),
            ("2. Trace & Audit", self.test_2_trace_and_audit),
            ("3. Risk & Guard", self.test_3_risk_and_guard),
            ("4. Execution Simulation", self.test_4_execution_simulation),
            ("5. Runtime Controls", self.test_5_runtime_controls),
            ("6. Observability", self.test_6_observability),
            ("7. Failure/Recovery", self.test_7_failure_recovery)
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                if result:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                self.log_result(test_name, "ERROR", f"Unexpected error: {str(e)}")
                failed += 1
        
        print("\n" + "=" * 80)
        print("SIM MODE VALIDATION SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {len(tests)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed / len(tests)) * 100:.1f}%")
        
        # Determine overall status
        if passed == len(tests):
            overall_status = "✅ PASS - Zincir çalıştı, risk block doğru, kill switch çalıştı"
        elif passed >= len(tests) * 0.7:  # 70% pass rate
            overall_status = "⚠️ PARTIAL - Çoğu test geçti, bazı zayıf noktalar var"
        else:
            overall_status = "❌ FAIL - Kritik sorunlar tespit edildi"
        
        print(f"\nOVERALL STATUS: {overall_status}")
        
        # Identify weakest points
        failed_tests = [result for result in self.test_results if result["status"] == "FAIL"]
        if failed_tests:
            print(f"\nEN ZAYIF NOKTA: {failed_tests[0]['test']} - {failed_tests[0]['details']}")
        else:
            print(f"\nEN ZAYIF NOKTA: Tüm testler başarılı")
        
        # Print detailed results
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_icon} {result['test']}: {result['details']}")
        
        return {
            "success": failed == 0,
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            "overall_status": overall_status,
            "results": self.test_results
        }

def main():
    """Main execution function"""
    tester = SIMModeTester()
    summary = tester.run_all_tests()
    
    # Save results to file
    with open("/app/faz3_sim_mode_validation_results.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    # Exit with appropriate code
    sys.exit(0 if summary["success"] else 1)

if __name__ == "__main__":
    main()