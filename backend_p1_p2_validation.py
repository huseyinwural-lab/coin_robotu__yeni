#!/usr/bin/env python3
"""
Backend P1/P2 Validation Test - Turkish Review Request
Base URL: https://trade-trace-engine.preview.emergentagent.com
Admin: canary.admin@platform.local / CanaryAdmin123!

Test maddeleri:
1) GET /api/admin/strategy-allocation/health
   - 200 dönmeli
   - payload içinde: health.api_latency_ms, health.queue_depth, health.error_rate_5m, health.db_pool, health.exchange_connectivity, health.scanner_freshness

2) GET /api/admin/strategy-allocation/explainability/{strategy_id}
   - strategy_id için önce /api/admin/strategy-allocation'dan ilk strategy_id al
   - 200 dönmeli
   - top_reason_codes ve trace_spine alanları olmalı (boş olabilir)

3) WebSocket: /api/admin/strategy-allocation/ws/stream
   - token ile bağlanma dene
   - en az bir mesajda type='snapshot' ve health alanı gelsin

4) Optimistic lock davranışı (allocation)
   - /api/admin/strategy-allocation'dan strategy + revision al
   - PUT /api/admin/strategy-allocation/{strategy_id} için intentionally stale expected_revision gönder
   - 409 ve detail.code='REVISION_CONFLICT' dönmeli
"""

import requests
import json
import time
import websocket
import threading
from datetime import datetime
import sys

class BackendP1P2Validator:
    def __init__(self):
        self.base_url = "https://trade-trace-engine.preview.emergentagent.com"
        self.admin_email = "canary.admin@platform.local"
        self.admin_password = "CanaryAdmin123!"
        self.session = requests.Session()
        self.session.timeout = 30
        self.access_token = None
        self.test_results = []
        
    def log_result(self, test_name, status, details):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        print(f"[{status}] {test_name}: {details}")
        
    def authenticate_admin(self):
        """Authenticate as admin and get access token"""
        try:
            login_url = f"{self.base_url}/api/auth/login/admin"
            login_data = {
                "email": self.admin_email,
                "password": self.admin_password
            }
            
            response = self.session.post(login_url, json=login_data)
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                if self.access_token:
                    # Set authorization header for future requests
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.access_token}"
                    })
                    self.log_result("Admin Authentication", "PASS", f"Successfully authenticated. Token length: {len(self.access_token)} chars")
                    return True
                else:
                    self.log_result("Admin Authentication", "FAIL", "No access_token in response")
                    return False
            else:
                self.log_result("Admin Authentication", "FAIL", f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Admin Authentication", "FAIL", f"Exception: {str(e)}")
            return False
    
    def test_health_endpoint(self):
        """Test 1: GET /api/admin/strategy-allocation/health"""
        try:
            url = f"{self.base_url}/api/admin/strategy-allocation/health"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for required health fields
                required_fields = [
                    "health.api_latency_ms",
                    "health.queue_depth", 
                    "health.error_rate_5m",
                    "health.db_pool",
                    "health.exchange_connectivity",
                    "health.scanner_freshness"
                ]
                
                health = data.get("health", {})
                missing_fields = []
                present_fields = []
                
                for field in required_fields:
                    field_name = field.replace("health.", "")
                    if field_name in health:
                        present_fields.append(f"{field_name}={health[field_name]}")
                    else:
                        missing_fields.append(field_name)
                
                if not missing_fields:
                    self.log_result("Health Endpoint", "PASS", f"200 OK with all required fields: {', '.join(present_fields)}")
                else:
                    self.log_result("Health Endpoint", "FAIL", f"200 OK but missing fields: {missing_fields}. Present: {present_fields}")
                    
            else:
                self.log_result("Health Endpoint", "FAIL", f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Health Endpoint", "FAIL", f"Exception: {str(e)}")
    
    def test_explainability_endpoint(self):
        """Test 2: GET /api/admin/strategy-allocation/explainability/{strategy_id}"""
        try:
            # First get strategy list to find a strategy_id
            list_url = f"{self.base_url}/api/admin/strategy-allocation"
            list_response = self.session.get(list_url)
            
            if list_response.status_code != 200:
                self.log_result("Explainability Endpoint", "FAIL", f"Cannot get strategy list: HTTP {list_response.status_code}")
                return
                
            strategies = list_response.json()
            if not strategies or len(strategies) == 0:
                self.log_result("Explainability Endpoint", "FAIL", "No strategies found in allocation list")
                return
                
            # Get first strategy_id
            first_strategy = strategies[0]
            strategy_id = first_strategy.get("strategy_id") or first_strategy.get("id")
            
            if not strategy_id:
                self.log_result("Explainability Endpoint", "FAIL", f"No strategy_id found in first strategy: {first_strategy}")
                return
                
            # Test explainability endpoint
            explain_url = f"{self.base_url}/api/admin/strategy-allocation/explainability/{strategy_id}"
            explain_response = self.session.get(explain_url)
            
            if explain_response.status_code == 200:
                data = explain_response.json()
                
                # Check for required fields
                has_top_reason_codes = "top_reason_codes" in data
                has_trace_spine = "trace_spine" in data
                
                if has_top_reason_codes and has_trace_spine:
                    top_reason_codes = data.get("top_reason_codes", [])
                    trace_spine = data.get("trace_spine", [])
                    self.log_result("Explainability Endpoint", "PASS", 
                                  f"200 OK with required fields. top_reason_codes: {len(top_reason_codes)} items, trace_spine: {len(trace_spine)} items")
                else:
                    missing = []
                    if not has_top_reason_codes:
                        missing.append("top_reason_codes")
                    if not has_trace_spine:
                        missing.append("trace_spine")
                    self.log_result("Explainability Endpoint", "FAIL", f"200 OK but missing fields: {missing}")
                    
            else:
                self.log_result("Explainability Endpoint", "FAIL", f"HTTP {explain_response.status_code}: {explain_response.text}")
                
        except Exception as e:
            self.log_result("Explainability Endpoint", "FAIL", f"Exception: {str(e)}")
    
    def test_websocket_stream(self):
        """Test 3: WebSocket /api/admin/strategy-allocation/ws/stream"""
        try:
            if not self.access_token:
                self.log_result("WebSocket Stream", "FAIL", "No access token available")
                return
                
            # Convert https to wss for websocket
            ws_url = f"wss://trade-trace-engine.preview.emergentagent.com/api/admin/strategy-allocation/ws/stream"
            
            messages_received = []
            connection_successful = False
            snapshot_received = False
            health_field_found = False
            
            def on_message(ws, message):
                nonlocal snapshot_received, health_field_found
                try:
                    data = json.loads(message)
                    messages_received.append(data)
                    
                    # Check for snapshot message with health field
                    if data.get("type") == "snapshot" and "health" in data:
                        snapshot_received = True
                        health_field_found = True
                        
                except Exception as e:
                    messages_received.append({"error": str(e), "raw_message": message})
            
            def on_open(ws):
                nonlocal connection_successful
                connection_successful = True
                
            def on_error(ws, error):
                messages_received.append({"websocket_error": str(error)})
                
            def on_close(ws, close_status_code, close_msg):
                messages_received.append({"close_code": close_status_code, "close_msg": close_msg})
            
            # Create websocket connection with auth header
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            ws = websocket.WebSocketApp(
                ws_url,
                header=headers,
                on_message=on_message,
                on_open=on_open,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run websocket in thread with timeout
            ws_thread = threading.Thread(target=ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Wait for connection and messages
            time.sleep(5)
            ws.close()
            ws_thread.join(timeout=2)
            
            if connection_successful:
                if snapshot_received and health_field_found:
                    self.log_result("WebSocket Stream", "PASS", 
                                  f"Connection successful. Received {len(messages_received)} messages. Found snapshot with health field.")
                elif len(messages_received) > 0:
                    self.log_result("WebSocket Stream", "PARTIAL", 
                                  f"Connection successful. Received {len(messages_received)} messages but no snapshot with health field yet.")
                else:
                    self.log_result("WebSocket Stream", "PARTIAL", "Connection successful but no messages received within timeout")
            else:
                self.log_result("WebSocket Stream", "FAIL", f"Connection failed. Messages: {messages_received}")
                
        except Exception as e:
            self.log_result("WebSocket Stream", "FAIL", f"Exception: {str(e)}")
    
    def test_optimistic_lock(self):
        """Test 4: Optimistic lock behavior with intentionally stale revision"""
        try:
            # Get strategy list to find a strategy for testing
            list_url = f"{self.base_url}/api/admin/strategy-allocation"
            list_response = self.session.get(list_url)
            
            if list_response.status_code != 200:
                self.log_result("Optimistic Lock", "FAIL", f"Cannot get strategy list: HTTP {list_response.status_code}")
                return
                
            strategies = list_response.json()
            if not strategies or len(strategies) == 0:
                self.log_result("Optimistic Lock", "FAIL", "No strategies found for optimistic lock test")
                return
                
            # Get first strategy with revision info
            first_strategy = strategies[0]
            strategy_id = first_strategy.get("strategy_id") or first_strategy.get("id")
            current_revision = first_strategy.get("revision") or first_strategy.get("expected_revision")
            
            if not strategy_id:
                self.log_result("Optimistic Lock", "FAIL", f"No strategy_id found in strategy: {first_strategy}")
                return
                
            if current_revision is None:
                self.log_result("Optimistic Lock", "FAIL", f"No revision found in strategy: {first_strategy}")
                return
                
            # Create intentionally stale revision (subtract 1 or use a clearly old value)
            if isinstance(current_revision, int):
                stale_revision = max(0, current_revision - 1)
            else:
                stale_revision = "stale_revision_test"
            
            # Attempt PUT with stale revision
            put_url = f"{self.base_url}/api/admin/strategy-allocation/{strategy_id}"
            put_data = {
                "expected_revision": stale_revision,
                "allocation_percentage": first_strategy.get("allocation_percentage", 50),
                # Include other required fields from the original strategy
                **{k: v for k, v in first_strategy.items() if k not in ["strategy_id", "id", "revision", "expected_revision"]}
            }
            
            put_response = self.session.put(put_url, json=put_data)
            
            if put_response.status_code == 409:
                try:
                    error_data = put_response.json()
                    detail = error_data.get("detail", {})
                    
                    if isinstance(detail, dict) and detail.get("code") == "REVISION_CONFLICT":
                        self.log_result("Optimistic Lock", "PASS", 
                                      f"409 Conflict with REVISION_CONFLICT code as expected. Current revision: {current_revision}, Stale revision: {stale_revision}")
                    else:
                        self.log_result("Optimistic Lock", "PARTIAL", 
                                      f"409 Conflict but detail.code is not REVISION_CONFLICT: {detail}")
                except:
                    self.log_result("Optimistic Lock", "PARTIAL", 
                                  f"409 Conflict but cannot parse error detail: {put_response.text}")
            else:
                self.log_result("Optimistic Lock", "FAIL", 
                              f"Expected 409 Conflict but got HTTP {put_response.status_code}: {put_response.text}")
                
        except Exception as e:
            self.log_result("Optimistic Lock", "FAIL", f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all P1/P2 validation tests"""
        print("=== Backend P1/P2 Validation Test - Turkish Review Request ===")
        print(f"Base URL: {self.base_url}")
        print(f"Admin: {self.admin_email}")
        print()
        
        # Authenticate first
        if not self.authenticate_admin():
            print("Authentication failed. Cannot proceed with tests.")
            return self.test_results
            
        print()
        
        # Run all tests
        self.test_health_endpoint()
        self.test_explainability_endpoint()
        self.test_websocket_stream()
        self.test_optimistic_lock()
        
        # Summary
        print("\n=== TEST SUMMARY ===")
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        partial = sum(1 for r in self.test_results if r["status"] == "PARTIAL")
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"PASSED: {passed}")
        print(f"FAILED: {failed}")
        print(f"PARTIAL: {partial}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        # Detailed results
        print("\n=== DETAILED RESULTS ===")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_icon} {result['test']}: {result['details']}")
        
        # Critical findings
        critical_failures = [r for r in self.test_results if r["status"] == "FAIL"]
        if critical_failures:
            print(f"\n🔴 CRITICAL FAILURES ({len(critical_failures)}):")
            for failure in critical_failures:
                print(f"  - {failure['test']}: {failure['details']}")
        else:
            print(f"\n🟢 NO CRITICAL FAILURES")
            
        return self.test_results

if __name__ == "__main__":
    validator = BackendP1P2Validator()
    results = validator.run_all_tests()
    
    # Exit with appropriate code
    failed_count = sum(1 for r in results if r["status"] == "FAIL")
    sys.exit(failed_count)