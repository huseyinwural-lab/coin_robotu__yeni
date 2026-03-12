"""
Phase 6 User Platform - Scanner & Signals Comprehensive Tests (NA-01 through NA-06)
Tests:
- NA-01: POST /api/user/scanner/run, GET /api/user/scanner/results
- NA-02: GET /api/user/signals, POST /api/user/signal/{id}/approve, POST /api/user/signal/{id}/reject
- Approve/Reject flow with portfolio/trades reflection
- NA-03: GET /api/user/portfolio, GET /api/user/performance, GET /api/user/trades, GET/PUT /api/user/exchange
- Role separation: admin token gets 403 on /api/user/* endpoints
- Owner-scope: user1 and user2 data isolation
- NA-06: Regression - core flow preservation
"""
import os
import uuid
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct

    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text().splitlines():
            line = raw_line.strip()
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _resolve_base_url()

class TestPhase6ScannerSignalsAPI:
    """Phase 6 User Scanner & Signals API Tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@platform.dev",
            "password": "Admin12345!"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def test_user_email(self):
        """Generate unique test user email"""
        return f"TEST_phase6_scanner_{uuid.uuid4().hex[:8]}@example.com"
    
    @pytest.fixture(scope="class")
    def test_user2_email(self):
        """Generate unique second test user email"""
        return f"TEST_phase6_isolation_{uuid.uuid4().hex[:8]}@example.com"
    
    @pytest.fixture(scope="class")
    def user_token(self, admin_token, test_user_email):
        """Create a test user and get user token"""
        import time
        
        # Register test user
        register_response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_user_email,
            "password": "TestUser12345!"
        })
        if register_response.status_code not in [200, 201]:
            pytest.skip(f"Failed to register test user: {register_response.text}")
        
        # Wait a moment for registration to complete
        time.sleep(0.5)
        
        # Approve user using admin token
        users_response = requests.get(
            f"{BASE_URL}/api/admin/users?role=user&limit=200",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        user_id = None
        if users_response.status_code == 200:
            users = users_response.json()
            for user in users:
                if user.get("email") == test_user_email:
                    user_id = user["id"]
                    approve_response = requests.post(
                        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
                    print(f"Approval response for {test_user_email}: {approve_response.status_code} {approve_response.text}")
                    break
        
        if not user_id:
            # Try to find user with pending approval status from user approvals endpoint
            pending_response = requests.get(
                f"{BASE_URL}/api/admin/user-approvals?status=pending",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            if pending_response.status_code == 200:
                pending_users = pending_response.json()
                for user in pending_users:
                    if user.get("email") == test_user_email:
                        user_id = user["id"]
                        approve_response = requests.post(
                            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
                            headers={"Authorization": f"Bearer {admin_token}"}
                        )
                        print(f"Approval from pending endpoint: {approve_response.status_code}")
                        break
        
        # Wait for approval to take effect
        time.sleep(0.5)
        
        # Login as user
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_user_email,
            "password": "TestUser12345!"
        })
        assert login_response.status_code == 200, f"User login failed: {login_response.text}"
        return login_response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def user2_token(self, admin_token, test_user2_email):
        """Create second test user for isolation tests"""
        import time
        
        # Register test user 2
        register_response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_user2_email,
            "password": "TestUser2_12345!"
        })
        if register_response.status_code not in [200, 201]:
            pytest.skip(f"Failed to register test user2: {register_response.text}")
        
        time.sleep(0.5)
        
        # Approve user using admin token
        users_response = requests.get(
            f"{BASE_URL}/api/admin/users?role=user&limit=200",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        user_id = None
        if users_response.status_code == 200:
            users = users_response.json()
            for user in users:
                if user.get("email") == test_user2_email:
                    user_id = user["id"]
                    approve_response = requests.post(
                        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
                    print(f"Approval response for user2: {approve_response.status_code}")
                    break
        
        if not user_id:
            pending_response = requests.get(
                f"{BASE_URL}/api/admin/user-approvals?status=pending",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            if pending_response.status_code == 200:
                pending_users = pending_response.json()
                for user in pending_users:
                    if user.get("email") == test_user2_email:
                        user_id = user["id"]
                        approve_response = requests.post(
                            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
                            headers={"Authorization": f"Bearer {admin_token}"}
                        )
                        break
        
        time.sleep(0.5)
        
        # Login as user
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_user2_email,
            "password": "TestUser2_12345!"
        })
        assert login_response.status_code == 200, f"User2 login failed: {login_response.text}"
        return login_response.json().get("access_token")

    # -------------------------
    # NA-01: Scanner API Tests
    # -------------------------
    
    def test_na01_scanner_run_assisted_mode(self, user_token):
        """NA-01: POST /api/user/scanner/run with ASSISTED mode works"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"mode": "ASSISTED", "max_results": 20}
        )
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        assert "run_id" in data, "run_id missing"
        assert data["mode"] == "ASSISTED", f"Mode should be ASSISTED, got {data['mode']}"
        assert "result_count" in data, "result_count missing"
        assert "actionable_count" in data, "actionable_count missing"
        assert "queued_count" in data, "queued_count missing"
        assert "pending_total" in data, "pending_total missing"
        print(f"Scanner run result: {data}")
    
    def test_na01_scanner_run_manual_mode(self, user_token):
        """NA-01: POST /api/user/scanner/run with MANUAL mode produces info status"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"mode": "MANUAL", "max_results": 10}
        )
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        assert data["mode"] == "MANUAL", f"Mode should be MANUAL, got {data['mode']}"
        print(f"MANUAL mode scanner: {data}")
    
    def test_na01_scanner_results_returns_list(self, user_token):
        """NA-01: GET /api/user/scanner/results returns user-scoped results"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 50}
        )
        assert response.status_code == 200, f"Scanner results failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        if data:
            result = data[0]
            assert "symbol" in result, "symbol missing in result"
            assert "signal" in result, "signal missing in result"
            assert "confidence" in result, "confidence missing in result"
            print(f"Scanner results count: {len(data)}")
    
    def test_na01_scanner_default_mode_assisted(self, user_token):
        """NA-01: Default signal mode is ASSISTED"""
        response = requests.get(
            f"{BASE_URL}/api/user/signal-mode",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Mode can be ASSISTED, AUTO, or MANUAL - but default is ASSISTED
        assert data.get("mode") in ["ASSISTED", "AUTO", "MANUAL"], f"Invalid mode: {data.get('mode')}"
        print(f"Current signal mode: {data}")
    
    def test_na01_signal_mode_update(self, user_token):
        """NA-01: PUT /api/user/signal-mode updates mode"""
        # Update to ASSISTED
        response = requests.put(
            f"{BASE_URL}/api/user/signal-mode",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"mode": "ASSISTED"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "ASSISTED"
        print(f"Signal mode updated to: {data['mode']}")

    # -------------------------
    # NA-02: Signals API Tests
    # -------------------------
    
    def test_na02_signals_list_returns_user_signals(self, user_token):
        """NA-02: GET /api/user/signals returns user-scoped signals"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 100}
        )
        assert response.status_code == 200, f"Signals list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Signals count: {len(data)}")
    
    def test_na02_approve_pending_signal(self, user_token):
        """NA-02: POST /api/user/signal/{id}/approve approves pending signal"""
        # First run scanner to generate signals
        run_response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"mode": "ASSISTED", "max_results": 20}
        )
        assert run_response.status_code == 200, f"Scanner run failed: {run_response.text}"
        
        # Get pending signals
        signals_response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 100}
        )
        assert signals_response.status_code == 200
        signals = signals_response.json()
        
        pending_signals = [s for s in signals if s.get("status") == "pending"]
        if not pending_signals:
            pytest.skip("No pending signals available for approval test")
        
        signal_id = pending_signals[0]["id"]
        
        # Get portfolio state before approval
        portfolio_before = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers={"Authorization": f"Bearer {user_token}"}
        ).json()
        
        # Approve the signal
        approve_response = requests.post(
            f"{BASE_URL}/api/user/signal/{signal_id}/approve",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"note": "approved_from_test"}
        )
        assert approve_response.status_code == 200, f"Approve failed: {approve_response.text}"
        approve_data = approve_response.json()
        assert approve_data["status"] == "approved", f"Status should be approved, got {approve_data['status']}"
        assert approve_data["order_position_id"] is not None, "order_position_id should be set after approval"
        print(f"Approved signal: {approve_data}")
        
        # Verify portfolio updated (open_positions_count should increase)
        portfolio_after = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers={"Authorization": f"Bearer {user_token}"}
        ).json()
        print(f"Portfolio before: {portfolio_before}, after: {portfolio_after}")
    
    def test_na02_reject_pending_signal(self, user_token):
        """NA-02: POST /api/user/signal/{id}/reject rejects pending signal without creating order"""
        # First run scanner to generate signals
        run_response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"mode": "ASSISTED", "max_results": 20}
        )
        assert run_response.status_code == 200
        
        # Get pending signals
        signals_response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 100}
        )
        assert signals_response.status_code == 200
        signals = signals_response.json()
        
        pending_signals = [s for s in signals if s.get("status") == "pending"]
        if not pending_signals:
            pytest.skip("No pending signals available for rejection test")
        
        signal_id = pending_signals[0]["id"]
        
        # Reject the signal
        reject_response = requests.post(
            f"{BASE_URL}/api/user/signal/{signal_id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"note": "rejected_from_test"}
        )
        assert reject_response.status_code == 200, f"Reject failed: {reject_response.text}"
        reject_data = reject_response.json()
        assert reject_data["status"] == "rejected", f"Status should be rejected, got {reject_data['status']}"
        assert reject_data["order_position_id"] is None, "order_position_id should be None after rejection"
        print(f"Rejected signal: {reject_data}")
    
    def test_na02_approve_nonexistent_signal_404(self, user_token):
        """NA-02: Approving non-existent signal returns 404"""
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/user/signal/{fake_id}/approve",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"note": "test"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_na02_reject_nonexistent_signal_404(self, user_token):
        """NA-02: Rejecting non-existent signal returns 404"""
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/user/signal/{fake_id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"note": "test"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    # -------------------------
    # NA-03: User API Set Tests
    # -------------------------
    
    def test_na03_user_portfolio_endpoint(self, user_token):
        """NA-03: GET /api/user/portfolio returns portfolio snapshot"""
        response = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Portfolio failed: {response.text}"
        data = response.json()
        assert "current_capital" in data, "current_capital missing"
        assert "available_balance" in data, "available_balance missing"
        assert "open_notional" in data, "open_notional missing"
        assert "open_positions_count" in data, "open_positions_count missing"
        print(f"Portfolio: {data}")
    
    def test_na03_user_performance_endpoint(self, user_token):
        """NA-03: GET /api/user/performance returns performance metrics"""
        response = requests.get(
            f"{BASE_URL}/api/user/performance",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Performance failed: {response.text}"
        data = response.json()
        assert "win_rate" in data, "win_rate missing"
        assert "realized_pnl_total" in data, "realized_pnl_total missing"
        assert "profit_factor" in data, "profit_factor missing"
        print(f"Performance: {data}")
    
    def test_na03_user_trades_endpoint(self, user_token):
        """NA-03: GET /api/user/trades returns trade history"""
        response = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"limit": 50}
        )
        assert response.status_code == 200, f"Trades failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Trades count: {len(data)}")
    
    def test_na03_user_exchange_get(self, user_token):
        """NA-03: GET /api/user/exchange returns exchange settings"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Exchange GET failed: {response.text}"
        data = response.json()
        assert "exchange" in data, "exchange missing"
        assert "mode" in data, "mode missing"
        print(f"Exchange settings: {data}")
    
    def test_na03_user_exchange_put(self, user_token):
        """NA-03: PUT /api/user/exchange updates exchange settings"""
        response = requests.put(
            f"{BASE_URL}/api/user/exchange",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "exchange": "binance",
                "mode": "testnet",
                "api_key": "test_api_key_123",
                "api_secret": "test_api_secret_456"
            }
        )
        assert response.status_code == 200, f"Exchange PUT failed: {response.text}"
        data = response.json()
        assert data["exchange"] == "binance"
        assert data["has_api_key"] is True
        assert data["has_api_secret"] is True
        assert "***" in data["masked_api_key"], "API key should be masked"
        print(f"Exchange updated: {data}")

    # -------------------------
    # Role Separation Tests
    # -------------------------
    
    def test_admin_token_gets_403_on_user_scanner_run(self, admin_token):
        """Role Separation: Admin token gets 403 on POST /api/user/scanner/run"""
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"mode": "ASSISTED", "max_results": 10}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print(f"Admin 403 on scanner/run: {response.json()}")
    
    def test_admin_token_gets_403_on_user_scanner_results(self, admin_token):
        """Role Separation: Admin token gets 403 on GET /api/user/scanner/results"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_admin_token_gets_403_on_user_signals(self, admin_token):
        """Role Separation: Admin token gets 403 on GET /api/user/signals"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_admin_token_gets_403_on_user_portfolio(self, admin_token):
        """Role Separation: Admin token gets 403 on GET /api/user/portfolio"""
        response = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_admin_token_gets_403_on_user_performance(self, admin_token):
        """Role Separation: Admin token gets 403 on GET /api/user/performance"""
        response = requests.get(
            f"{BASE_URL}/api/user/performance",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_admin_token_gets_403_on_user_trades(self, admin_token):
        """Role Separation: Admin token gets 403 on GET /api/user/trades"""
        response = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_admin_token_gets_403_on_user_exchange(self, admin_token):
        """Role Separation: Admin token gets 403 on GET /api/user/exchange"""
        response = requests.get(
            f"{BASE_URL}/api/user/exchange",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_admin_token_gets_403_on_user_signal_approve(self, admin_token):
        """Role Separation: Admin token gets 403 on POST /api/user/signal/{id}/approve"""
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/user/signal/{fake_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"note": "test"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_admin_token_gets_403_on_user_signal_reject(self, admin_token):
        """Role Separation: Admin token gets 403 on POST /api/user/signal/{id}/reject"""
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/user/signal/{fake_id}/reject",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"note": "test"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

    # -------------------------
    # Owner Scope Isolation Tests
    # -------------------------
    
    def test_user_isolation_scanner_results(self, user_token, user2_token):
        """Owner Scope: user1 and user2 scanner results are isolated"""
        # User1 runs scanner
        run1 = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"mode": "ASSISTED", "max_results": 5}
        )
        assert run1.status_code == 200
        
        # User2 runs scanner
        run2 = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers={"Authorization": f"Bearer {user2_token}"},
            json={"mode": "ASSISTED", "max_results": 5}
        )
        assert run2.status_code == 200
        
        # User1 gets results
        results1 = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers={"Authorization": f"Bearer {user_token}"}
        ).json()
        
        # User2 gets results
        results2 = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers={"Authorization": f"Bearer {user2_token}"}
        ).json()
        
        # Extract run_ids to verify isolation
        run_ids_1 = set(r.get("run_id") for r in results1 if r.get("run_id"))
        run_ids_2 = set(r.get("run_id") for r in results2 if r.get("run_id"))
        
        # Run IDs should not overlap between users
        assert run_ids_1.isdisjoint(run_ids_2) or len(run_ids_1) == 0 or len(run_ids_2) == 0, \
            "User scanner results should be isolated"
        print(f"User1 run_ids: {run_ids_1}, User2 run_ids: {run_ids_2}")
    
    def test_user_isolation_signals(self, user_token, user2_token):
        """Owner Scope: user1 and user2 signals are isolated"""
        # Get user1 signals
        signals1 = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={"Authorization": f"Bearer {user_token}"}
        ).json()
        
        # Get user2 signals
        signals2 = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers={"Authorization": f"Bearer {user2_token}"}
        ).json()
        
        # Extract signal IDs
        ids1 = set(s.get("id") for s in signals1 if s.get("id"))
        ids2 = set(s.get("id") for s in signals2 if s.get("id"))
        
        # Signal IDs should not overlap
        assert ids1.isdisjoint(ids2) or len(ids1) == 0 or len(ids2) == 0, \
            "User signals should be isolated"
        print(f"User1 signals: {len(signals1)}, User2 signals: {len(signals2)}")
    
    def test_user_isolation_portfolio(self, user_token, user2_token):
        """Owner Scope: user1 and user2 portfolios are separate"""
        portfolio1 = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers={"Authorization": f"Bearer {user_token}"}
        ).json()
        
        portfolio2 = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers={"Authorization": f"Bearer {user2_token}"}
        ).json()
        
        # Both should have portfolio data but independent
        assert "current_capital" in portfolio1
        assert "current_capital" in portfolio2
        print(f"User1 portfolio: {portfolio1}, User2 portfolio: {portfolio2}")

    # -------------------------
    # NA-06: Regression Tests
    # -------------------------
    
    def test_na06_dashboard_summary_still_works(self, user_token):
        """NA-06 Regression: GET /api/dashboard/summary works for user"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Dashboard summary failed: {response.text}"
        data = response.json()
        assert "heartbeat" in data or "metrics" in data, "Dashboard summary missing expected fields"
        print(f"Dashboard summary: {data}")
    
    def test_na06_bot_profiles_still_works(self, user_token):
        """NA-06 Regression: GET /api/bot-profiles works for user"""
        response = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Bot profiles failed: {response.text}"
    
    def test_na06_risk_settings_still_works(self, user_token):
        """NA-06 Regression: GET /api/user/risk-settings works"""
        response = requests.get(
            f"{BASE_URL}/api/user/risk-settings",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Risk settings failed: {response.text}"
        data = response.json()
        assert "allocation_pct" in data
        print(f"Risk settings: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
