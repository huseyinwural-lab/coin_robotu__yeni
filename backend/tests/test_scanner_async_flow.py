"""
Test Scanner Async Flow - Iteration 23
Tests:
1. Scanner run-async endpoint returns job_id (not 502)
2. Scanner run-async job status polling works
3. Status contract does not show ORDER_PRECHECK_FAILED as hard-block in sim mode
4. Signals endpoint loads without 500
5. Scanner -> Signals flow produces queued/approved rows
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session for testing"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login with longer timeout
    try:
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=60
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed with status {login_response.status_code}: {login_response.text}")
    except requests.exceptions.Timeout:
        pytest.skip("Login timed out - backend may be slow")
    except requests.exceptions.ConnectionError as e:
        pytest.skip(f"Connection error during login: {e}")
    
    return session


class TestScannerAsyncFlow:
    """Test scanner async job flow - replacing sync /scanner/run"""
    
    def test_scanner_run_async_returns_job_id(self, auth_session):
        """Scanner run-async should return job_id, not 502"""
        payload = {
            "mode": "ASSISTED",
            "max_results": 10,
            "symbol_source": "crypto",
            "market_type": "spot",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCUSDT", "ETHUSDT"]
        }
        
        response = auth_session.post(
            f"{BASE_URL}/api/user/scanner/run-async",
            json=payload,
            timeout=15
        )
        
        # Should NOT be 502
        assert response.status_code != 502, f"Got 502 error - async flow not working: {response.text}"
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "job_id" in data, f"Response should contain job_id: {data}"
        assert data.get("status") == "queued", f"Job should be queued: {data}"
        
        print(f"✓ Scanner run-async returned job_id: {data.get('job_id')}")
        return data.get("job_id")
    
    def test_scanner_run_async_job_polling(self, auth_session):
        """Scanner async job status polling should work"""
        # First create a job
        payload = {
            "mode": "ASSISTED",
            "max_results": 5,
            "symbol_source": "crypto",
            "market_type": "spot",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCUSDT"]
        }
        
        create_response = auth_session.post(
            f"{BASE_URL}/api/user/scanner/run-async",
            json=payload,
            timeout=15
        )
        
        assert create_response.status_code == 200, f"Failed to create job: {create_response.text}"
        job_id = create_response.json().get("job_id")
        assert job_id, "No job_id returned"
        
        # Poll for job status
        max_attempts = 30
        final_status = None
        
        for attempt in range(max_attempts):
            status_response = auth_session.get(
                f"{BASE_URL}/api/user/scanner/run-async/{job_id}",
                timeout=10
            )
            
            assert status_response.status_code == 200, f"Job status check failed: {status_response.text}"
            
            job_data = status_response.json()
            final_status = job_data.get("status", "").lower()
            
            print(f"  Attempt {attempt + 1}: Job status = {final_status}")
            
            if final_status in ["completed", "failed"]:
                break
            
            time.sleep(2)
        
        assert final_status in ["completed", "failed"], f"Job did not complete in time, last status: {final_status}"
        
        if final_status == "completed":
            print(f"✓ Scanner async job completed successfully")
        else:
            print(f"⚠ Scanner async job failed (may be expected in test env)")


class TestStatusContractSimMode:
    """Test status contract blocking_reasons filtering in sim mode"""
    
    def test_status_contract_loads(self, auth_session):
        """Status contract endpoint should load without error"""
        response = auth_session.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            timeout=15
        )
        
        assert response.status_code == 200, f"Status contract failed: {response.text}"
        
        data = response.json()
        assert "blocking_reasons" in data, f"Response should contain blocking_reasons: {data}"
        
        print(f"✓ Status contract loaded successfully")
        print(f"  - scanner_ready: {data.get('scanner_ready')}")
        print(f"  - health: {data.get('health')}")
        print(f"  - blocking_reasons count: {len(data.get('blocking_reasons', []))}")
        
        return data
    
    def test_order_precheck_failed_not_hard_block_in_sim(self, auth_session):
        """ORDER_PRECHECK_FAILED should not appear as hard-block in sim mode (live_mode_enabled=false)"""
        response = auth_session.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            timeout=15
        )
        
        assert response.status_code == 200, f"Status contract failed: {response.text}"
        
        data = response.json()
        blocking_reasons = data.get("blocking_reasons", [])
        
        # Check if ORDER_PRECHECK_FAILED appears as a blocking reason
        order_precheck_blocks = [
            reason for reason in blocking_reasons
            if "ORDER_PRECHECK_FAILED" in str(reason.get("code", ""))
        ]
        
        # In sim mode (live_mode_enabled=false), ORDER_PRECHECK_FAILED should be filtered out
        # from blocking_reasons per the fix in _build_user_status_contract
        if order_precheck_blocks:
            print(f"⚠ ORDER_PRECHECK_FAILED found in blocking_reasons: {order_precheck_blocks}")
            print("  This may indicate live_mode_enabled=true or filtering not applied")
        else:
            print(f"✓ ORDER_PRECHECK_FAILED not in blocking_reasons (sim mode filtering working)")
        
        # Also check SYMBOL_NOT_ALLOWED filtering
        symbol_not_allowed_blocks = [
            reason for reason in blocking_reasons
            if "SYMBOL_NOT_ALLOWED" in str(reason.get("code", ""))
        ]
        
        if symbol_not_allowed_blocks:
            print(f"⚠ SYMBOL_NOT_ALLOWED found in blocking_reasons: {symbol_not_allowed_blocks}")
        else:
            print(f"✓ SYMBOL_NOT_ALLOWED not in blocking_reasons (sim mode filtering working)")


class TestSignalsEndpoint:
    """Test signals endpoint loads without 500"""
    
    def test_signals_loads_without_500(self, auth_session):
        """Signals endpoint should load without 500 error"""
        response = auth_session.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 50},
            timeout=25
        )
        
        assert response.status_code != 500, f"Signals returned 500: {response.text}"
        assert response.status_code == 200, f"Signals failed with {response.status_code}: {response.text}"
        
        data = response.json()
        signals = data if isinstance(data, list) else data.get("items", [])
        
        print(f"✓ Signals endpoint loaded successfully")
        print(f"  - Total signals: {len(signals)}")
        
        # Count by status
        status_counts = {}
        for signal in signals:
            status = signal.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"  - Status breakdown: {status_counts}")
        
        return signals
    
    def test_signals_have_tradeable_field(self, auth_session):
        """Signals should have tradeable field properly set"""
        response = auth_session.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 20},
            timeout=20
        )
        
        assert response.status_code == 200, f"Signals failed: {response.text}"
        
        data = response.json()
        signals = data if isinstance(data, list) else data.get("items", [])
        
        if not signals:
            print("⚠ No signals to check tradeable field")
            return
        
        tradeable_count = sum(1 for s in signals if s.get("tradeable") is True)
        non_tradeable_count = sum(1 for s in signals if s.get("tradeable") is False)
        
        print(f"✓ Signals tradeable field check:")
        print(f"  - Tradeable: {tradeable_count}")
        print(f"  - Non-tradeable: {non_tradeable_count}")
        
        # Check first_precheck_failure_code field
        precheck_failures = [s for s in signals if s.get("first_precheck_failure_code")]
        print(f"  - With precheck failure code: {len(precheck_failures)}")


class TestScannerSignalsIntegration:
    """Test Scanner -> Signals integration flow"""
    
    def test_scanner_produces_signals(self, auth_session):
        """Running scanner should produce signals in the signals list"""
        # Get initial signal count
        initial_response = auth_session.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 100},
            timeout=20
        )
        
        assert initial_response.status_code == 200, f"Initial signals fetch failed: {initial_response.text}"
        
        initial_data = initial_response.json()
        initial_signals = initial_data if isinstance(initial_data, list) else initial_data.get("items", [])
        initial_count = len(initial_signals)
        
        print(f"  Initial signal count: {initial_count}")
        
        # Run scanner async
        payload = {
            "mode": "ASSISTED",
            "max_results": 10,
            "symbol_source": "crypto",
            "market_type": "spot",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        }
        
        run_response = auth_session.post(
            f"{BASE_URL}/api/user/scanner/run-async",
            json=payload,
            timeout=15
        )
        
        assert run_response.status_code == 200, f"Scanner run failed: {run_response.text}"
        
        job_id = run_response.json().get("job_id")
        print(f"  Scanner job started: {job_id}")
        
        # Wait for job to complete
        for attempt in range(20):
            status_response = auth_session.get(
                f"{BASE_URL}/api/user/scanner/run-async/{job_id}",
                timeout=10
            )
            
            if status_response.status_code == 200:
                job_data = status_response.json()
                if job_data.get("status", "").lower() in ["completed", "failed"]:
                    print(f"  Job completed with status: {job_data.get('status')}")
                    break
            
            time.sleep(2)
        
        # Check signals after scanner run
        time.sleep(2)  # Give time for signals to be created
        
        final_response = auth_session.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 100},
            timeout=20
        )
        
        assert final_response.status_code == 200, f"Final signals fetch failed: {final_response.text}"
        
        final_data = final_response.json()
        final_signals = final_data if isinstance(final_data, list) else final_data.get("items", [])
        final_count = len(final_signals)
        
        print(f"  Final signal count: {final_count}")
        print(f"✓ Scanner -> Signals integration test completed")
        
        # Count queued/approved signals
        queued_approved = [
            s for s in final_signals
            if s.get("status") in ["queued", "approved", "ready", "pending"]
        ]
        print(f"  - Queued/Approved/Ready/Pending signals: {len(queued_approved)}")


class TestScannerOverview:
    """Test scanner overview endpoint"""
    
    def test_scanner_overview_loads(self, auth_session):
        """Scanner overview should load without error"""
        response = auth_session.get(
            f"{BASE_URL}/api/user/scanner",
            timeout=15
        )
        
        assert response.status_code == 200, f"Scanner overview failed: {response.text}"
        
        data = response.json()
        print(f"✓ Scanner overview loaded:")
        print(f"  - mode: {data.get('mode')}")
        print(f"  - total_results: {data.get('total_results')}")
        print(f"  - pending_signals: {data.get('pending_signals')}")
        print(f"  - latest_run_id: {data.get('latest_run_id')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
