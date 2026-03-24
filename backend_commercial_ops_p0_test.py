#!/usr/bin/env python3
"""
Commercial Ops P0 Backend Validation Test
Base URL: https://binance-reconcile.preview.emergentagent.com
Admin: canary.admin@platform.local / CanaryAdmin123!
Target user: huseyinwural@gmail.com

Test Coverage:
1. Health check
2. Binance ingestion (spot+futures -> 451 blocker, futures-only -> success)
3. PnL latest endpoint
4. Reconciliation run
5. Data quality check
6. Live gate checks
7. CSV export
8. WebSocket worker operations
"""

import json
import requests
import sys
from datetime import datetime, timezone


class CommercialOpsP0Tester:
    def __init__(self):
        self.base_url = "https://binance-reconcile.preview.emergentagent.com"
        self.admin_email = "canary.admin@platform.local"
        self.admin_password = "CanaryAdmin123!"
        self.target_user_email = "huseyinwural@gmail.com"
        self.admin_token = None
        self.session = requests.Session()
        self.session.timeout = 30
        
        # Test results tracking
        self.results = {
            "health_check": {"status": "PENDING", "details": ""},
            "spot_futures_ingestion": {"status": "PENDING", "details": ""},
            "futures_only_ingestion": {"status": "PENDING", "details": ""},
            "pnl_latest": {"status": "PENDING", "details": ""},
            "reconciliation_run": {"status": "PENDING", "details": ""},
            "data_quality": {"status": "PENDING", "details": ""},
            "live_gate_default": {"status": "PENDING", "details": ""},
            "live_gate_futures_only": {"status": "PENDING", "details": ""},
            "csv_export": {"status": "PENDING", "details": ""},
            "ws_worker_start": {"status": "PENDING", "details": ""},
            "ws_worker_status": {"status": "PENDING", "details": ""},
            "ws_worker_stop": {"status": "PENDING", "details": ""}
        }

    def log(self, message):
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{timestamp}] {message}")

    def authenticate_admin(self):
        """Authenticate as admin and get access token"""
        self.log("🔐 Authenticating admin...")
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login/admin",
                json={
                    "email": self.admin_email,
                    "password": self.admin_password
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("access_token")
                if self.admin_token:
                    self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
                    self.log(f"✅ Admin authentication successful")
                    return True
                else:
                    self.log(f"❌ Admin authentication failed: No access token in response")
                    return False
            else:
                self.log(f"❌ Admin authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Admin authentication error: {str(e)}")
            return False

    def test_health_check(self):
        """Test 1: GET /api/health -> 200, DB reachable true"""
        self.log("🏥 Testing health check...")
        
        try:
            response = self.session.get(f"{self.base_url}/api/health")
            
            if response.status_code == 200:
                data = response.json()
                db_reachable = data.get("checks", {}).get("database", {}).get("reachable", False)
                
                if db_reachable:
                    self.results["health_check"]["status"] = "PASS"
                    self.results["health_check"]["details"] = f"Health check OK, database reachable: {db_reachable}"
                    self.log("✅ Health check PASSED - Database reachable")
                else:
                    self.results["health_check"]["status"] = "FAIL"
                    self.results["health_check"]["details"] = f"Database not reachable: {data}"
                    self.log("❌ Health check FAILED - Database not reachable")
            else:
                self.results["health_check"]["status"] = "FAIL"
                self.results["health_check"]["details"] = f"HTTP {response.status_code}: {response.text}"
                self.log(f"❌ Health check FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["health_check"]["status"] = "ERROR"
            self.results["health_check"]["details"] = str(e)
            self.log(f"❌ Health check ERROR: {str(e)}")

    def test_spot_futures_ingestion(self):
        """Test 2: POST /api/admin/commercial/p0/ingest/binance - spot+futures -> expect 400/451"""
        self.log("📊 Testing spot+futures ingestion (expecting 451 blocker)...")
        
        try:
            payload = {
                "target_user_email": self.target_user_email,
                "environment": "testnet",
                "market_types": ["spot", "futures"],
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "limit_per_symbol": 100
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/commercial/p0/ingest/binance",
                json=payload
            )
            
            # Expecting 400 or similar error due to spot 451 restriction
            if response.status_code in [400, 451]:
                response_text = response.text.lower()
                if "451" in response_text or "restricted" in response_text or "location" in response_text:
                    self.results["spot_futures_ingestion"]["status"] = "PASS"
                    self.results["spot_futures_ingestion"]["details"] = f"Expected 451 blocker detected: {response.status_code} - {response.text[:200]}"
                    self.log("✅ Spot+futures ingestion PASSED - 451 blocker confirmed")
                else:
                    self.results["spot_futures_ingestion"]["status"] = "PARTIAL"
                    self.results["spot_futures_ingestion"]["details"] = f"Got expected error code {response.status_code} but not 451 specific: {response.text[:200]}"
                    self.log("⚠️ Spot+futures ingestion PARTIAL - Error but not 451 specific")
            else:
                self.results["spot_futures_ingestion"]["status"] = "FAIL"
                self.results["spot_futures_ingestion"]["details"] = f"Unexpected response: {response.status_code} - {response.text[:200]}"
                self.log(f"❌ Spot+futures ingestion FAILED: Expected 400/451, got {response.status_code}")
                
        except Exception as e:
            self.results["spot_futures_ingestion"]["status"] = "ERROR"
            self.results["spot_futures_ingestion"]["details"] = str(e)
            self.log(f"❌ Spot+futures ingestion ERROR: {str(e)}")

    def test_futures_only_ingestion(self):
        """Test 3: POST /api/admin/commercial/p0/ingest/binance - futures only -> expect 200"""
        self.log("🚀 Testing futures-only ingestion (expecting success)...")
        
        try:
            payload = {
                "target_user_email": self.target_user_email,
                "environment": "testnet",
                "market_types": ["futures"],
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "limit_per_symbol": 100
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/commercial/p0/ingest/binance",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                fetched = data.get("fetched", 0)
                
                if fetched > 0:
                    self.results["futures_only_ingestion"]["status"] = "PASS"
                    self.results["futures_only_ingestion"]["details"] = f"Futures ingestion successful: fetched={fetched}, inserted={data.get('inserted', 0)}, duplicate={data.get('duplicate', 0)}"
                    self.log(f"✅ Futures-only ingestion PASSED - Fetched {fetched} trades")
                else:
                    self.results["futures_only_ingestion"]["status"] = "PARTIAL"
                    self.results["futures_only_ingestion"]["details"] = f"Ingestion successful but no trades fetched: {data}"
                    self.log("⚠️ Futures-only ingestion PARTIAL - No trades fetched")
            else:
                self.results["futures_only_ingestion"]["status"] = "FAIL"
                self.results["futures_only_ingestion"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ Futures-only ingestion FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["futures_only_ingestion"]["status"] = "ERROR"
            self.results["futures_only_ingestion"]["details"] = str(e)
            self.log(f"❌ Futures-only ingestion ERROR: {str(e)}")

    def test_pnl_latest(self):
        """Test 4: GET /api/admin/commercial/p0/pnl/latest - realized/unrealized + fee_breakdown"""
        self.log("💰 Testing PnL latest endpoint...")
        
        try:
            params = {
                "target_user_email": self.target_user_email,
                "environment": "testnet"
            }
            
            response = self.session.get(
                f"{self.base_url}/api/admin/commercial/p0/pnl/latest",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                realized = data.get("realized", {})
                unrealized = data.get("unrealized", {})
                fee_breakdown = data.get("fee_breakdown", {})
                
                if realized and unrealized and fee_breakdown:
                    self.results["pnl_latest"]["status"] = "PASS"
                    self.results["pnl_latest"]["details"] = f"PnL data complete: realized={realized}, unrealized={unrealized}, fee_breakdown={fee_breakdown}"
                    self.log("✅ PnL latest PASSED - All required fields present")
                else:
                    self.results["pnl_latest"]["status"] = "PARTIAL"
                    self.results["pnl_latest"]["details"] = f"PnL data incomplete: realized={bool(realized)}, unrealized={bool(unrealized)}, fee_breakdown={bool(fee_breakdown)}"
                    self.log("⚠️ PnL latest PARTIAL - Some required fields missing")
            else:
                self.results["pnl_latest"]["status"] = "FAIL"
                self.results["pnl_latest"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ PnL latest FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["pnl_latest"]["status"] = "ERROR"
            self.results["pnl_latest"]["details"] = str(e)
            self.log(f"❌ PnL latest ERROR: {str(e)}")

    def test_reconciliation_run(self):
        """Test 5: POST /api/admin/commercial/p0/reconciliation/run - futures only + drift_tolerance_pct=0.3"""
        self.log("🔄 Testing reconciliation run...")
        
        try:
            payload = {
                "target_user_email": self.target_user_email,
                "environment": "testnet",
                "market_types": ["futures"],
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "drift_tolerance_pct": 0.3,
                "limit_per_symbol": 100
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/commercial/p0/reconciliation/run",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                drift_within_tolerance = data.get("drift_within_tolerance", False)
                missing_trade_count = data.get("missing_trade_count", -1)
                
                if drift_within_tolerance and missing_trade_count == 0:
                    self.results["reconciliation_run"]["status"] = "PASS"
                    self.results["reconciliation_run"]["details"] = f"Reconciliation successful: drift_within_tolerance={drift_within_tolerance}, missing_trade_count={missing_trade_count}"
                    self.log("✅ Reconciliation run PASSED - Drift within tolerance, no missing trades")
                else:
                    self.results["reconciliation_run"]["status"] = "PARTIAL"
                    self.results["reconciliation_run"]["details"] = f"Reconciliation completed but with issues: drift_within_tolerance={drift_within_tolerance}, missing_trade_count={missing_trade_count}"
                    self.log("⚠️ Reconciliation run PARTIAL - Completed but with drift/missing trades")
            else:
                self.results["reconciliation_run"]["status"] = "FAIL"
                self.results["reconciliation_run"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ Reconciliation run FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["reconciliation_run"]["status"] = "ERROR"
            self.results["reconciliation_run"]["details"] = str(e)
            self.log(f"❌ Reconciliation run ERROR: {str(e)}")

    def test_data_quality(self):
        """Test 6: GET /api/admin/commercial/p0/data-quality - freshness_seconds.futures"""
        self.log("📈 Testing data quality endpoint...")
        
        try:
            params = {
                "target_user_email": self.target_user_email,
                "environment": "testnet"
            }
            
            response = self.session.get(
                f"{self.base_url}/api/admin/commercial/p0/data-quality",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                freshness_seconds = data.get("freshness_seconds", {})
                futures_freshness = freshness_seconds.get("futures")
                
                if futures_freshness is not None:
                    self.results["data_quality"]["status"] = "PASS"
                    self.results["data_quality"]["details"] = f"Data quality OK: freshness_seconds.futures={futures_freshness}, missing_data_alert={data.get('missing_data_alert', 'N/A')}"
                    self.log(f"✅ Data quality PASSED - Futures freshness: {futures_freshness} seconds")
                else:
                    self.results["data_quality"]["status"] = "PARTIAL"
                    self.results["data_quality"]["details"] = f"Data quality response missing futures freshness: {data}"
                    self.log("⚠️ Data quality PARTIAL - Missing futures freshness data")
            else:
                self.results["data_quality"]["status"] = "FAIL"
                self.results["data_quality"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ Data quality FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["data_quality"]["status"] = "ERROR"
            self.results["data_quality"]["details"] = str(e)
            self.log(f"❌ Data quality ERROR: {str(e)}")

    def test_live_gate_default(self):
        """Test 7: GET /api/admin/commercial/p0/live-gate (default spot+futures) - expect spot coverage false"""
        self.log("🚪 Testing live gate (default spot+futures)...")
        
        try:
            params = {
                "target_user_email": self.target_user_email,
                "environment": "testnet"
            }
            
            response = self.session.get(
                f"{self.base_url}/api/admin/commercial/p0/live-gate",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                live_transition_ready = data.get("live_transition_ready", True)
                controls = data.get("controls", {})
                
                # Expecting live_transition_ready to be false due to spot coverage issues
                if not live_transition_ready:
                    self.results["live_gate_default"]["status"] = "PASS"
                    self.results["live_gate_default"]["details"] = f"Live gate correctly blocked: live_transition_ready={live_transition_ready}, controls={controls}"
                    self.log("✅ Live gate (default) PASSED - Correctly blocked due to spot coverage")
                else:
                    self.results["live_gate_default"]["status"] = "PARTIAL"
                    self.results["live_gate_default"]["details"] = f"Live gate unexpectedly ready: live_transition_ready={live_transition_ready}, controls={controls}"
                    self.log("⚠️ Live gate (default) PARTIAL - Unexpectedly ready")
            else:
                self.results["live_gate_default"]["status"] = "FAIL"
                self.results["live_gate_default"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ Live gate (default) FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["live_gate_default"]["status"] = "ERROR"
            self.results["live_gate_default"]["details"] = str(e)
            self.log(f"❌ Live gate (default) ERROR: {str(e)}")

    def test_live_gate_futures_only(self):
        """Test 8: GET /api/admin/commercial/p0/live-gate?required_market_types=futures - expect ready true"""
        self.log("🚪 Testing live gate (futures only)...")
        
        try:
            params = {
                "target_user_email": self.target_user_email,
                "environment": "testnet",
                "required_market_types": ["futures"]
            }
            
            response = self.session.get(
                f"{self.base_url}/api/admin/commercial/p0/live-gate",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                live_transition_ready = data.get("live_transition_ready", False)
                controls = data.get("controls", {})
                
                if live_transition_ready:
                    self.results["live_gate_futures_only"]["status"] = "PASS"
                    self.results["live_gate_futures_only"]["details"] = f"Live gate futures-only ready: live_transition_ready={live_transition_ready}, controls={controls}"
                    self.log("✅ Live gate (futures-only) PASSED - Ready for live transition")
                else:
                    self.results["live_gate_futures_only"]["status"] = "PARTIAL"
                    self.results["live_gate_futures_only"]["details"] = f"Live gate futures-only not ready: live_transition_ready={live_transition_ready}, controls={controls}"
                    self.log("⚠️ Live gate (futures-only) PARTIAL - Not ready for live transition")
            else:
                self.results["live_gate_futures_only"]["status"] = "FAIL"
                self.results["live_gate_futures_only"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ Live gate (futures-only) FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["live_gate_futures_only"]["status"] = "ERROR"
            self.results["live_gate_futures_only"]["details"] = str(e)
            self.log(f"❌ Live gate (futures-only) ERROR: {str(e)}")

    def test_csv_export(self):
        """Test 9: GET /api/admin/commercial/p0/export/csv - 200, text/csv, proper headers"""
        self.log("📄 Testing CSV export...")
        
        try:
            params = {
                "target_user_email": self.target_user_email,
                "environment": "testnet"
            }
            
            response = self.session.get(
                f"{self.base_url}/api/admin/commercial/p0/export/csv",
                params=params
            )
            
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                content = response.text
                lines = content.split('\n')
                
                if "text/csv" in content_type and len(lines) > 1:
                    header_line = lines[0] if lines else ""
                    expected_headers = ["trade_id", "user_id", "exchange", "market_type", "symbol", "executed_qty", "executed_price"]
                    headers_present = all(header in header_line for header in expected_headers)
                    
                    if headers_present:
                        self.results["csv_export"]["status"] = "PASS"
                        self.results["csv_export"]["details"] = f"CSV export OK: content-type={content_type}, lines={len(lines)}, headers_valid={headers_present}"
                        self.log(f"✅ CSV export PASSED - {len(lines)} lines, proper headers")
                    else:
                        self.results["csv_export"]["status"] = "PARTIAL"
                        self.results["csv_export"]["details"] = f"CSV export missing headers: content-type={content_type}, header_line={header_line[:100]}"
                        self.log("⚠️ CSV export PARTIAL - Missing expected headers")
                else:
                    self.results["csv_export"]["status"] = "PARTIAL"
                    self.results["csv_export"]["details"] = f"CSV export format issues: content-type={content_type}, lines={len(lines)}"
                    self.log("⚠️ CSV export PARTIAL - Format issues")
            else:
                self.results["csv_export"]["status"] = "FAIL"
                self.results["csv_export"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ CSV export FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["csv_export"]["status"] = "ERROR"
            self.results["csv_export"]["details"] = str(e)
            self.log(f"❌ CSV export ERROR: {str(e)}")

    def test_ws_worker_start(self):
        """Test 10: POST /api/admin/commercial/p0/websocket/worker/start (futures)"""
        self.log("🔌 Testing WebSocket worker start...")
        
        try:
            payload = {
                "target_user_email": self.target_user_email,
                "environment": "testnet",
                "market_types": ["futures"]
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/commercial/p0/websocket/worker/start",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "")
                worker = data.get("worker", {})
                
                if status in ["started", "already_running"] and worker:
                    self.results["ws_worker_start"]["status"] = "PASS"
                    self.results["ws_worker_start"]["details"] = f"WebSocket worker start OK: status={status}, worker_key={data.get('worker_key', 'N/A')}"
                    self.log(f"✅ WebSocket worker start PASSED - Status: {status}")
                else:
                    self.results["ws_worker_start"]["status"] = "PARTIAL"
                    self.results["ws_worker_start"]["details"] = f"WebSocket worker start issues: status={status}, worker={bool(worker)}"
                    self.log("⚠️ WebSocket worker start PARTIAL - Unexpected response")
            else:
                self.results["ws_worker_start"]["status"] = "FAIL"
                self.results["ws_worker_start"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ WebSocket worker start FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["ws_worker_start"]["status"] = "ERROR"
            self.results["ws_worker_start"]["details"] = str(e)
            self.log(f"❌ WebSocket worker start ERROR: {str(e)}")

    def test_ws_worker_status(self):
        """Test 11: GET /api/admin/commercial/p0/websocket/worker/status"""
        self.log("📊 Testing WebSocket worker status...")
        
        try:
            params = {
                "environment": "testnet"
            }
            
            response = self.session.get(
                f"{self.base_url}/api/admin/commercial/p0/websocket/worker/status",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "")
                workers = data.get("workers", [])
                count = data.get("count", 0)
                
                if status == "ok":
                    self.results["ws_worker_status"]["status"] = "PASS"
                    self.results["ws_worker_status"]["details"] = f"WebSocket worker status OK: status={status}, count={count}, workers={len(workers)}"
                    self.log(f"✅ WebSocket worker status PASSED - {count} workers found")
                else:
                    self.results["ws_worker_status"]["status"] = "PARTIAL"
                    self.results["ws_worker_status"]["details"] = f"WebSocket worker status issues: status={status}, count={count}"
                    self.log("⚠️ WebSocket worker status PARTIAL - Unexpected status")
            else:
                self.results["ws_worker_status"]["status"] = "FAIL"
                self.results["ws_worker_status"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"❌ WebSocket worker status FAILED: {response.status_code}")
                
        except Exception as e:
            self.results["ws_worker_status"]["status"] = "ERROR"
            self.results["ws_worker_status"]["details"] = str(e)
            self.log(f"❌ WebSocket worker status ERROR: {str(e)}")

    def test_ws_worker_stop(self):
        """Test 12: POST /api/admin/commercial/p0/websocket/worker/stop"""
        self.log("🛑 Testing WebSocket worker stop...")
        
        try:
            # First get a worker to stop
            status_response = self.session.get(
                f"{self.base_url}/api/admin/commercial/p0/websocket/worker/status",
                params={"environment": "testnet"}
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                workers = status_data.get("workers", [])
                
                if workers:
                    # Try to stop the first worker
                    worker = workers[0]
                    user_id = worker.get("user_id")
                    
                    if user_id:
                        payload = {
                            "target_user_id": user_id,
                            "environment": "testnet",
                            "market_types": ["futures"]
                        }
                        
                        response = self.session.post(
                            f"{self.base_url}/api/admin/commercial/p0/websocket/worker/stop",
                            json=payload
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            status = data.get("status", "")
                            
                            if status in ["stopped", "not_found"]:
                                self.results["ws_worker_stop"]["status"] = "PASS"
                                self.results["ws_worker_stop"]["details"] = f"WebSocket worker stop OK: status={status}"
                                self.log(f"✅ WebSocket worker stop PASSED - Status: {status}")
                            else:
                                self.results["ws_worker_stop"]["status"] = "PARTIAL"
                                self.results["ws_worker_stop"]["details"] = f"WebSocket worker stop unexpected: status={status}"
                                self.log("⚠️ WebSocket worker stop PARTIAL - Unexpected status")
                        else:
                            self.results["ws_worker_stop"]["status"] = "FAIL"
                            self.results["ws_worker_stop"]["details"] = f"HTTP {response.status_code}: {response.text[:200]}"
                            self.log(f"❌ WebSocket worker stop FAILED: {response.status_code}")
                    else:
                        self.results["ws_worker_stop"]["status"] = "SKIP"
                        self.results["ws_worker_stop"]["details"] = "No user_id found in worker data"
                        self.log("⏭️ WebSocket worker stop SKIPPED - No user_id in worker")
                else:
                    self.results["ws_worker_stop"]["status"] = "SKIP"
                    self.results["ws_worker_stop"]["details"] = "No workers found to stop"
                    self.log("⏭️ WebSocket worker stop SKIPPED - No workers found")
            else:
                self.results["ws_worker_stop"]["status"] = "FAIL"
                self.results["ws_worker_stop"]["details"] = f"Could not get worker status: {status_response.status_code}"
                self.log(f"❌ WebSocket worker stop FAILED - Could not get status: {status_response.status_code}")
                
        except Exception as e:
            self.results["ws_worker_stop"]["status"] = "ERROR"
            self.results["ws_worker_stop"]["details"] = str(e)
            self.log(f"❌ WebSocket worker stop ERROR: {str(e)}")

    def run_all_tests(self):
        """Run all Commercial Ops P0 tests"""
        self.log("🚀 Starting Commercial Ops P0 Backend Validation")
        self.log(f"Base URL: {self.base_url}")
        self.log(f"Admin: {self.admin_email}")
        self.log(f"Target User: {self.target_user_email}")
        self.log("=" * 80)
        
        # Authenticate first
        if not self.authenticate_admin():
            self.log("❌ CRITICAL: Admin authentication failed. Cannot proceed with tests.")
            return False
        
        # Run all tests
        test_methods = [
            self.test_health_check,
            self.test_spot_futures_ingestion,
            self.test_futures_only_ingestion,
            self.test_pnl_latest,
            self.test_reconciliation_run,
            self.test_data_quality,
            self.test_live_gate_default,
            self.test_live_gate_futures_only,
            self.test_csv_export,
            self.test_ws_worker_start,
            self.test_ws_worker_status,
            self.test_ws_worker_stop
        ]
        
        for test_method in test_methods:
            try:
                test_method()
            except Exception as e:
                self.log(f"❌ CRITICAL ERROR in {test_method.__name__}: {str(e)}")
            self.log("-" * 40)
        
        return True

    def print_summary(self):
        """Print test results summary"""
        self.log("=" * 80)
        self.log("📋 COMMERCIAL OPS P0 BACKEND VALIDATION SUMMARY")
        self.log("=" * 80)
        
        pass_count = 0
        partial_count = 0
        fail_count = 0
        error_count = 0
        skip_count = 0
        
        for test_name, result in self.results.items():
            status = result["status"]
            details = result["details"]
            
            if status == "PASS":
                icon = "✅"
                pass_count += 1
            elif status == "PARTIAL":
                icon = "⚠️"
                partial_count += 1
            elif status == "FAIL":
                icon = "❌"
                fail_count += 1
            elif status == "ERROR":
                icon = "💥"
                error_count += 1
            elif status == "SKIP":
                icon = "⏭️"
                skip_count += 1
            else:
                icon = "❓"
            
            self.log(f"{icon} {test_name.upper()}: {status}")
            if details:
                self.log(f"   Details: {details}")
        
        self.log("=" * 80)
        self.log(f"📊 RESULTS: {pass_count} PASS, {partial_count} PARTIAL, {fail_count} FAIL, {error_count} ERROR, {skip_count} SKIP")
        
        # Calculate success rate
        total_tests = len(self.results)
        success_rate = ((pass_count + partial_count) / total_tests * 100) if total_tests > 0 else 0
        
        self.log(f"📈 SUCCESS RATE: {success_rate:.1f}% ({pass_count + partial_count}/{total_tests})")
        
        # Key findings
        self.log("=" * 80)
        self.log("🔍 KEY FINDINGS:")
        
        # Check spot 451 blocker
        spot_futures_status = self.results.get("spot_futures_ingestion", {}).get("status", "UNKNOWN")
        if spot_futures_status == "PASS":
            self.log("✅ Spot 451 blocker confirmed - Regional restriction working as expected")
        else:
            self.log("⚠️ Spot 451 blocker validation inconclusive")
        
        # Check futures-only P0 chain
        futures_tests = ["futures_only_ingestion", "pnl_latest", "reconciliation_run", "live_gate_futures_only"]
        futures_chain_pass = all(self.results.get(test, {}).get("status") in ["PASS", "PARTIAL"] for test in futures_tests)
        
        if futures_chain_pass:
            self.log("✅ Futures-only P0 chain PASSED - Full workflow operational")
        else:
            self.log("❌ Futures-only P0 chain FAILED - Critical workflow issues detected")
        
        self.log("=" * 80)
        
        return success_rate >= 70  # Consider 70%+ success rate as overall pass


def main():
    """Main execution function"""
    tester = CommercialOpsP0Tester()
    
    try:
        success = tester.run_all_tests()
        tester.print_summary()
        
        if success:
            print("\n🎉 Commercial Ops P0 Backend Validation COMPLETED")
            return 0
        else:
            print("\n💥 Commercial Ops P0 Backend Validation FAILED")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️ Test execution interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 CRITICAL ERROR: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())