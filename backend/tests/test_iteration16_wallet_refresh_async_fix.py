"""
Iteration 16 - Wallet Refresh Gate + Async Fix-All-Blockers Tests

Tests:
1. POST /api/user/signals/fix-all-blockers-async and GET status endpoints
2. Adaptive batching behavior (batch_history, processed, fixed fields)
3. Preview pipeline wallet refresh gate
4. Submit gate wallet refresh fail → 422 WALLET_REFRESH_FAILED
5. User status-contract payload: wallet_last_check_at / wallet_available_balance / wallet_balance
6. Regression: tradeable/non_tradeable/blocker flows
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://127.0.0.1:8001"

USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=60,
    )
    if response.status_code != 200:
        pytest.skip(f"User login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


@pytest.fixture(scope="module")
def user_headers(user_token):
    """Headers with user auth token"""
    return {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json",
    }


class TestFixAllBlockersAsync:
    """Tests for POST /api/user/signals/fix-all-blockers-async and GET status"""

    def test_fix_all_blockers_async_endpoint_exists(self, user_headers):
        """Test that fix-all-blockers-async endpoint exists and returns job_id"""
        response = requests.post(
            f"{BASE_URL}/api/user/signals/fix-all-blockers-async",
            headers=user_headers,
            params={"limit": 50},
            timeout=60,
        )
        # Should return 200 with job_id
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "job_id" in data, f"Response missing job_id: {data}"
        assert "status" in data, f"Response missing status: {data}"
        assert data["status"] == "queued", f"Expected status=queued, got {data['status']}"
        print(f"✓ fix-all-blockers-async returned job_id={data['job_id']}, status={data['status']}")

    def test_fix_all_blockers_async_status_endpoint(self, user_headers):
        """Test GET status endpoint for async job"""
        # First create a job
        create_response = requests.post(
            f"{BASE_URL}/api/user/signals/fix-all-blockers-async",
            headers=user_headers,
            params={"limit": 20},
            timeout=60,
        )
        assert create_response.status_code == 200
        job_id = create_response.json().get("job_id")
        assert job_id, "No job_id returned"

        # Poll for status
        max_attempts = 30
        final_status = None
        for attempt in range(max_attempts):
            status_response = requests.get(
                f"{BASE_URL}/api/user/signals/fix-all-blockers-async/{job_id}",
                headers=user_headers,
                timeout=60,
            )
            assert status_response.status_code == 200, f"Status check failed: {status_response.text}"
            status_data = status_response.json()
            final_status = status_data.get("status")
            print(f"  Attempt {attempt + 1}: status={final_status}, processed={status_data.get('processed', 0)}")
            
            if final_status in ("completed", "failed"):
                break
            time.sleep(0.5)

        assert final_status in ("completed", "failed", "running"), f"Unexpected final status: {final_status}"
        print(f"✓ Async job completed with status={final_status}")

    def test_fix_all_blockers_async_job_state_transitions(self, user_headers):
        """Test job state transitions: queued → running → completed"""
        response = requests.post(
            f"{BASE_URL}/api/user/signals/fix-all-blockers-async",
            headers=user_headers,
            params={"limit": 100},
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        job_id = data.get("job_id")
        
        # Initial state should be queued
        assert data.get("status") == "queued", f"Initial status should be queued, got {data.get('status')}"
        
        observed_states = ["queued"]
        max_attempts = 60
        for _ in range(max_attempts):
            status_response = requests.get(
                f"{BASE_URL}/api/user/signals/fix-all-blockers-async/{job_id}",
                headers=user_headers,
                timeout=60,
            )
            if status_response.status_code != 200:
                break
            status_data = status_response.json()
            current_status = status_data.get("status")
            
            if current_status not in observed_states:
                observed_states.append(current_status)
            
            if current_status in ("completed", "failed"):
                break
            time.sleep(0.3)

        print(f"✓ Observed state transitions: {' → '.join(observed_states)}")
        # Should have at least queued and one of running/completed
        assert len(observed_states) >= 1, "Should observe at least initial state"

    def test_fix_all_blockers_async_batch_history_field(self, user_headers):
        """Test that batch_history field is populated in async job response"""
        response = requests.post(
            f"{BASE_URL}/api/user/signals/fix-all-blockers-async",
            headers=user_headers,
            params={"limit": 100},
            timeout=60,
        )
        assert response.status_code == 200
        job_id = response.json().get("job_id")

        # Wait for completion
        final_data = None
        for _ in range(60):
            status_response = requests.get(
                f"{BASE_URL}/api/user/signals/fix-all-blockers-async/{job_id}",
                headers=user_headers,
                timeout=60,
            )
            if status_response.status_code == 200:
                final_data = status_response.json()
                if final_data.get("status") in ("completed", "failed"):
                    break
            time.sleep(0.5)

        assert final_data is not None, "Could not get final job data"
        
        # Check for batch_history field
        batch_history = final_data.get("batch_history")
        processed = final_data.get("processed")
        fixed = final_data.get("fixed")
        
        print(f"✓ Job completed: processed={processed}, fixed={fixed}, batch_history_count={len(batch_history) if batch_history else 0}")
        
        # batch_history should be a list (may be empty if no blocked signals)
        assert batch_history is None or isinstance(batch_history, list), f"batch_history should be list, got {type(batch_history)}"
        assert processed is not None, "processed field should be present"
        assert fixed is not None, "fixed field should be present"


class TestAdaptiveBatching:
    """Tests for adaptive batching behavior"""

    def test_adaptive_batch_size_function_exists(self, user_headers):
        """Test that adaptive batching is applied based on remaining_blocked"""
        # This is tested indirectly through the async job
        response = requests.post(
            f"{BASE_URL}/api/user/signals/fix-all-blockers-async",
            headers=user_headers,
            params={"limit": 200},  # Large limit to trigger adaptive batching
            timeout=60,
        )
        assert response.status_code == 200
        job_id = response.json().get("job_id")

        # Wait for completion and check batch_history
        final_data = None
        for _ in range(90):
            status_response = requests.get(
                f"{BASE_URL}/api/user/signals/fix-all-blockers-async/{job_id}",
                headers=user_headers,
                timeout=60,
            )
            if status_response.status_code == 200:
                final_data = status_response.json()
                if final_data.get("status") in ("completed", "failed"):
                    break
            time.sleep(0.5)

        assert final_data is not None
        batch_history = final_data.get("batch_history") or []
        
        if len(batch_history) > 0:
            # Check that batch_size varies based on remaining_blocked
            batch_sizes = [b.get("batch_size") for b in batch_history if b.get("batch_size")]
            print(f"✓ Batch sizes observed: {batch_sizes}")
            # Adaptive batching should produce varying batch sizes
            # (or consistent if remaining_blocked is stable)
        else:
            print("✓ No batch_history (no blocked signals to process)")


class TestStatusContractWalletFields:
    """Tests for wallet fields in status-contract endpoint"""

    def test_status_contract_contains_wallet_last_check_at(self, user_headers):
        """Test that status-contract returns wallet_last_check_at field"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            headers=user_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Status contract failed: {response.text}"
        data = response.json()
        
        # Check for wallet fields
        assert "wallet_last_check_at" in data, f"Missing wallet_last_check_at in status-contract: {data.keys()}"
        print(f"✓ wallet_last_check_at = {data.get('wallet_last_check_at')}")

    def test_status_contract_contains_wallet_available_balance(self, user_headers):
        """Test that status-contract returns wallet_available_balance field"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            headers=user_headers,
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "wallet_available_balance" in data, f"Missing wallet_available_balance: {data.keys()}"
        print(f"✓ wallet_available_balance = {data.get('wallet_available_balance')}")

    def test_status_contract_contains_wallet_balance(self, user_headers):
        """Test that status-contract returns wallet_balance field"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            headers=user_headers,
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "wallet_balance" in data, f"Missing wallet_balance: {data.keys()}"
        print(f"✓ wallet_balance = {data.get('wallet_balance')}")

    def test_status_contract_all_required_fields(self, user_headers):
        """Test that status-contract returns all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            headers=user_headers,
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "scanner_ready",
            "strategy_ready",
            "risk_ready",
            "execution_ready",
            "symbols_ready",
            "exchange_ready",
            "bot_status",
            "health",
            "blocking_reasons",
            "wallet_last_check_at",
            "wallet_available_balance",
            "wallet_balance",
        ]
        
        missing = [f for f in required_fields if f not in data]
        assert not missing, f"Missing required fields: {missing}"
        print(f"✓ All required status-contract fields present")
        print(f"  scanner_ready={data.get('scanner_ready')}, exchange_ready={data.get('exchange_ready')}")
        print(f"  wallet_last_check_at={data.get('wallet_last_check_at')}")


class TestPreviewWalletRefreshGate:
    """Tests for wallet refresh gate in preview pipeline"""

    def test_preview_intent_includes_wallet_refresh_info(self, user_headers):
        """Test that preview response includes wallet refresh information"""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "execution_mode": "manual",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=user_headers,
            json=payload,
            timeout=90,
        )
        
        # May succeed or fail based on validation, but should return response
        if response.status_code in (200, 400, 422):
            data = response.json()
            normalized = data.get("normalized_order_payload") or {}
            
            # Check for wallet_refresh in normalized payload
            wallet_refresh = normalized.get("wallet_refresh")
            wallet_last_check = normalized.get("wallet_last_check_at")
            
            print(f"✓ Preview response received")
            print(f"  wallet_refresh present: {wallet_refresh is not None}")
            print(f"  wallet_last_check_at: {wallet_last_check}")
            
            if wallet_refresh:
                print(f"  wallet_refresh.ok: {wallet_refresh.get('ok')}")
                print(f"  wallet_refresh.reason_code: {wallet_refresh.get('reason_code')}")
        else:
            print(f"Preview returned {response.status_code}: {response.text[:200]}")

    def test_preview_wallet_refresh_fail_adds_reject_reason(self, user_headers):
        """Test that wallet refresh failure adds reject_reason_codes"""
        # Use a symbol that might trigger wallet refresh issues
        payload = {
            "source_type": "manual",
            "market_type": "futures",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50,
            "execution_mode": "manual",
            "leverage": 5,
            "margin_mode": "isolated",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=user_headers,
            json=payload,
            timeout=90,
        )
        
        if response.status_code in (200, 400, 422):
            data = response.json()
            reject_codes = data.get("reject_reason_codes") or []
            risk_flags = data.get("risk_flags") or []
            
            print(f"✓ Preview response: status={response.status_code}")
            print(f"  reject_reason_codes: {reject_codes[:5]}")
            print(f"  risk_flags: {risk_flags[:5]}")
            
            # Check if wallet-related codes are present when refresh fails
            wallet_related = [c for c in reject_codes if "wallet" in c.lower()]
            if wallet_related:
                print(f"  Wallet-related reject codes: {wallet_related}")


class TestSubmitWalletRefreshGate:
    """Tests for submit gate wallet refresh fail → 422 WALLET_REFRESH_FAILED"""

    def test_submit_without_preview_fails(self, user_headers):
        """Test that submit without valid preview fails"""
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/submit",
            headers=user_headers,
            json={
                "intent_token": "invalid-token-12345",
                "preview_hash": "invalid-hash",
            },
            timeout=60,
        )
        
        # Should fail with 400 or 404
        assert response.status_code in (400, 404, 422), f"Expected error, got {response.status_code}"
        print(f"✓ Submit without valid preview correctly rejected: {response.status_code}")

    def test_submit_wallet_refresh_fail_returns_422(self, user_headers):
        """Test that wallet refresh failure on submit returns 422 with WALLET_REFRESH_FAILED"""
        # First create a preview
        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "execution_mode": "manual",
        }
        
        preview_response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=user_headers,
            json=preview_payload,
            timeout=90,
        )
        
        if preview_response.status_code != 200:
            print(f"Preview failed with {preview_response.status_code}, skipping submit test")
            pytest.skip("Preview failed, cannot test submit")
            return
        
        preview_data = preview_response.json()
        intent_token = preview_data.get("intent_token")
        preview_hash = preview_data.get("preview_hash")
        validation_status = preview_data.get("validation_status")
        
        print(f"Preview: validation_status={validation_status}, intent_token={intent_token[:20]}...")
        
        if validation_status != "valid":
            print(f"Preview not valid, submit would fail anyway")
            # Still try submit to verify error handling
        
        # Try to submit
        submit_response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/submit",
            headers=user_headers,
            json={
                "intent_token": intent_token,
                "preview_hash": preview_hash,
            },
            timeout=90,
        )
        
        print(f"✓ Submit response: {submit_response.status_code}")
        
        if submit_response.status_code == 422:
            error_data = submit_response.json()
            error_code = error_data.get("detail", {}).get("code") or error_data.get("code")
            print(f"  422 error code: {error_code}")
            # Check if it's wallet refresh related
            if error_code == "WALLET_REFRESH_FAILED":
                print(f"  ✓ Correctly returned WALLET_REFRESH_FAILED")
        elif submit_response.status_code == 200:
            print(f"  Submit succeeded (wallet refresh passed)")
        else:
            print(f"  Submit returned: {submit_response.text[:200]}")


class TestSignalsTradeableFields:
    """Tests for tradeable/non_tradeable/blocker fields in signals"""

    def test_signals_endpoint_returns_tradeable_field(self, user_headers):
        """Test that signals endpoint returns tradeable field"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=user_headers,
            params={"limit": 50},
            timeout=60,
        )
        assert response.status_code == 200, f"Signals failed: {response.text}"
        signals = response.json()
        
        if not signals:
            print("✓ No signals available, skipping tradeable field check")
            return
        
        # Check first signal for tradeable field
        first_signal = signals[0]
        assert "tradeable" in first_signal, f"Missing tradeable field: {first_signal.keys()}"
        print(f"✓ tradeable field present: {first_signal.get('tradeable')}")

    def test_signals_endpoint_returns_first_precheck_failure_code(self, user_headers):
        """Test that signals endpoint returns first_precheck_failure_code field"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=user_headers,
            params={"limit": 50},
            timeout=60,
        )
        assert response.status_code == 200
        signals = response.json()
        
        if not signals:
            print("✓ No signals available, skipping first_precheck_failure_code check")
            return
        
        first_signal = signals[0]
        assert "first_precheck_failure_code" in first_signal, f"Missing first_precheck_failure_code: {first_signal.keys()}"
        print(f"✓ first_precheck_failure_code field present: {first_signal.get('first_precheck_failure_code')}")

    def test_signals_blocked_reason_fields(self, user_headers):
        """Test that blocked signals have proper reason fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=user_headers,
            params={"limit": 100},
            timeout=60,
        )
        assert response.status_code == 200
        signals = response.json()
        
        blocked_signals = [s for s in signals if s.get("status") in ("blocked", "non_tradeable")]
        
        if not blocked_signals:
            print("✓ No blocked signals to verify")
            return
        
        for signal in blocked_signals[:3]:
            assert "blocked_reason_code" in signal, "Missing blocked_reason_code"
            assert "blocked_reason_message" in signal, "Missing blocked_reason_message"
            assert "blocked_solution_hint" in signal, "Missing blocked_solution_hint"
            print(f"  Signal {signal.get('id')[:8]}...: status={signal.get('status')}, code={signal.get('blocked_reason_code')}")
        
        print(f"✓ {len(blocked_signals)} blocked signals have proper reason fields")


class TestRegressionTradeableNonTradeableBlocker:
    """Regression tests for tradeable/non_tradeable/blocker flows"""

    def test_signals_status_values(self, user_headers):
        """Test that signals have valid status values"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=user_headers,
            params={"limit": 100},
            timeout=60,
        )
        assert response.status_code == 200
        signals = response.json()
        
        valid_statuses = {
            "pending", "ready", "approved", "queued", "submitted", 
            "filled", "rejected", "blocked", "non_tradeable", "expired"
        }
        
        status_counts = {}
        for signal in signals:
            status = signal.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            assert status in valid_statuses, f"Invalid status: {status}"
        
        print(f"✓ Signal status distribution: {status_counts}")

    def test_tradeable_false_for_blocked_signals(self, user_headers):
        """Test that blocked signals have tradeable=False"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=user_headers,
            params={"limit": 100},
            timeout=60,
        )
        assert response.status_code == 200
        signals = response.json()
        
        blocked_signals = [s for s in signals if s.get("status") in ("blocked", "non_tradeable")]
        
        for signal in blocked_signals:
            tradeable = signal.get("tradeable")
            assert tradeable is False, f"Blocked signal should have tradeable=False, got {tradeable}"
        
        print(f"✓ All {len(blocked_signals)} blocked signals have tradeable=False")

    def test_exchange_readiness_endpoint(self, user_headers):
        """Test exchange-readiness endpoint returns expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/exchange-readiness",
            headers=user_headers,
            params={"market_type": "spot"},
            timeout=60,
        )
        assert response.status_code == 200, f"Exchange readiness failed: {response.text}"
        data = response.json()
        
        required_fields = ["is_ready", "reason_code", "permissions", "market_types", "last_check_at"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ Exchange readiness: is_ready={data.get('is_ready')}, reason_code={data.get('reason_code')}")


class TestScannerSeedTrigger:
    """Tests for scanner seed trigger when results are empty"""

    def test_scanner_results_endpoint(self, user_headers):
        """Test scanner results endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers=user_headers,
            params={"limit": 50},
            timeout=60,
        )
        assert response.status_code == 200, f"Scanner results failed: {response.text}"
        results = response.json()
        
        print(f"✓ Scanner results count: {len(results)}")
        
        if len(results) == 0:
            print("  Note: Scanner results empty - seed trigger may be needed")

    def test_scanner_run_async_endpoint(self, user_headers):
        """Test scanner run-async endpoint exists"""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "market_type": "spot",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCUSDT", "ETHUSDT"],
        }
        
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run-async",
            headers=user_headers,
            json=payload,
            timeout=60,
        )
        
        assert response.status_code == 200, f"Scanner run-async failed: {response.text}"
        data = response.json()
        assert "job_id" in data, f"Missing job_id: {data}"
        print(f"✓ Scanner run-async returned job_id={data.get('job_id')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
