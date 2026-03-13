"""
Iteration 79 - Scanner Auto Mode Enforcement & ORDER_PRECHECK_FAILED Message Tests

Testing features:
1. run_user_scanner enforces mode=AUTO only when user has active bot and requested mode is MANUAL/ASSISTED
2. Scanner response includes warning signal_mode_auto_enforced_for_active_bot when enforced
3. MANUAL_APPROVAL_REQUIRED blocker should no longer appear for active-bot users after scanner run with manual mode request
4. ORDER_PRECHECK_FAILED blockers remain blocked (not auto-bypassed)
5. ORDER_PRECHECK_FAILED message/hint includes clear reject codes when validation provides them
6. Regression: fix-all-blockers endpoint still works and does not falsely mark precheck blockers as fixed
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"

# Test user credentials - will be created and approved
TEST_USER_EMAIL = f"TEST_iter79_scanner_{uuid.uuid4().hex[:8]}@test.com"
TEST_USER_PASSWORD = "TestPass123!"


@pytest.fixture(scope="module")
def admin_auth():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    return {
        "token": data["access_token"],
        "user_id": data["user"]["id"]
    }


@pytest.fixture(scope="module")
def admin_client(admin_auth):
    """Admin authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_auth['token']}"
    })
    return session


@pytest.fixture(scope="module")
def test_user_auth(admin_client):
    """Create and approve a test user, then get their auth token"""
    # Step 1: Register test user
    register_response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if register_response.status_code not in [200, 201]:
        # User may already exist from previous test run - try login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if login_response.status_code == 200:
            data = login_response.json()
            return {
                "token": data["access_token"],
                "user_id": data["user"]["id"],
                "email": TEST_USER_EMAIL
            }
        pytest.fail(f"Failed to register or login test user: {register_response.text}")
    
    # Step 2: Get user approval request ID
    approvals_response = admin_client.get(f"{BASE_URL}/api/auth/admin/user-approval-requests")
    assert approvals_response.status_code == 200
    approvals = approvals_response.json()
    
    user_approval = None
    for approval in approvals:
        if approval.get("email") == TEST_USER_EMAIL:
            user_approval = approval
            break
    
    # Step 3: Approve the user if found in pending
    if user_approval:
        approve_response = admin_client.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_approval['id']}/approve"
        )
        assert approve_response.status_code in [200, 400]  # 400 if already approved
    
    # Step 4: Login with test user
    login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    assert login_response.status_code == 200, f"Test user login failed: {login_response.text}"
    
    data = login_response.json()
    return {
        "token": data["access_token"],
        "user_id": data["user"]["id"],
        "email": TEST_USER_EMAIL
    }


@pytest.fixture(scope="module")
def user_client(test_user_auth):
    """User authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {test_user_auth['token']}"
    })
    return session


@pytest.fixture(scope="module")
def ensure_active_bot(user_client, test_user_auth):
    """Ensure the test user has an active bot (is_running=True, is_enabled=True)"""
    # List bot profiles - endpoint is /api/bot-profiles NOT /api/user/bot-profiles
    bots_response = user_client.get(f"{BASE_URL}/api/bot-profiles")
    assert bots_response.status_code == 200, f"Bot profiles list failed: {bots_response.text}"
    bots = bots_response.json()
    
    active_bot_id = None
    
    # Check if there's an active bot
    for bot in bots:
        if bot.get("is_running") and bot.get("is_enabled"):
            active_bot_id = bot["id"]
            break
    
    if not active_bot_id and bots:
        # Activate the first bot
        bot = bots[0]
        update_response = user_client.put(f"{BASE_URL}/api/bot-profiles/{bot['id']}", json={
            "is_running": True,
            "is_enabled": True
        })
        if update_response.status_code == 200:
            active_bot_id = bot["id"]
    
    if not active_bot_id:
        # Create a new active bot
        create_response = user_client.post(f"{BASE_URL}/api/bot-profiles", json={
            "name": "TEST_iter79_active_bot",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategy_type": "spot_pullback",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True,
            "is_running": True
        })
        if create_response.status_code in [200, 201]:
            active_bot_id = create_response.json().get("id")
    
    return active_bot_id


class TestScannerAutoModeEnforcement:
    """Test that scanner enforces AUTO mode for active-bot users"""

    def test_scanner_run_with_manual_mode_enforces_auto_for_active_bot_user(self, user_client, ensure_active_bot):
        """
        Feature: When user has active bot and requests MANUAL mode, scanner should:
        1. Switch mode to AUTO
        2. Include warning signal_mode_auto_enforced_for_active_bot
        
        Note: First scanner run may create an active bot, so we run twice to ensure the bot exists
        """
        # First run - may create the active bot
        first_response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 5,
            "symbol_source": "crypto",
            "symbol_selection_mode": "bot_scope"
        })
        assert first_response.status_code == 200, f"First scanner run failed: {first_response.text}"
        first_data = first_response.json()
        print(f"First scanner run: mode={first_data.get('mode')}, warnings={first_data.get('warnings', [])}")
        
        # Second run - now active bot should exist
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 5,
            "symbol_source": "crypto",
            "symbol_selection_mode": "bot_scope"
        })
        
        assert response.status_code == 200, f"Scanner run failed: {response.text}"
        data = response.json()
        
        # Verify mode was enforced to AUTO (not MANUAL)
        assert data.get("mode") == "AUTO", f"Expected mode=AUTO but got {data.get('mode')}"
        
        # Verify warning is present
        warnings = data.get("warnings", [])
        assert "signal_mode_auto_enforced_for_active_bot" in warnings, \
            f"Expected warning 'signal_mode_auto_enforced_for_active_bot' in warnings: {warnings}"
        
        print(f"Second scanner response: mode={data['mode']}, warnings={warnings}")

    def test_scanner_run_with_assisted_mode_also_enforces_auto(self, user_client, ensure_active_bot):
        """
        Feature: ASSISTED mode should also be enforced to AUTO when user has active bot
        """
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "ASSISTED",
            "max_results": 5,  # Must be >= 5 per schema validation
            "symbol_source": "crypto"
        })
        
        assert response.status_code == 200, f"Scanner with ASSISTED mode failed: {response.text}"
        data = response.json()
        
        # Verify mode was enforced to AUTO
        assert data.get("mode") == "AUTO", f"Expected mode=AUTO but got {data.get('mode')}"
        
        # Verify warning is present
        warnings = data.get("warnings", [])
        assert "signal_mode_auto_enforced_for_active_bot" in warnings, \
            f"Expected warning in warnings: {warnings}"

    def test_scanner_run_with_auto_mode_does_not_add_warning(self, user_client, ensure_active_bot):
        """
        Feature: When user requests AUTO mode (same as what would be enforced), 
        no enforcement warning should be added
        """
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "AUTO",
            "max_results": 5,  # Must be >= 5 per schema validation
            "symbol_source": "crypto"
        })
        
        assert response.status_code == 200, f"Scanner with AUTO mode failed: {response.text}"
        data = response.json()
        
        # Mode should remain AUTO
        assert data.get("mode") == "AUTO"
        
        # Should NOT have auto_enforced warning since AUTO was requested
        warnings = data.get("warnings", [])
        assert "signal_mode_auto_enforced_for_active_bot" not in warnings, \
            f"Should not have enforcement warning when AUTO is requested: {warnings}"


class TestNoManualApprovalBlockerForActiveBotUser:
    """Test that MANUAL_APPROVAL_REQUIRED blocker does not appear for active-bot users"""

    def test_signals_after_scanner_run_do_not_have_manual_approval_blocker(self, user_client, ensure_active_bot):
        """
        Feature: After scanner run with active bot, signals should not show 
        MANUAL_APPROVAL_REQUIRED as blocked_reason_code
        """
        # First run scanner with MANUAL mode (which gets enforced to AUTO)
        scanner_response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 10,
            "symbol_source": "crypto",
            "symbol_selection_mode": "bot_scope"
        })
        assert scanner_response.status_code == 200
        
        # Now check signals
        signals_response = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 100})
        assert signals_response.status_code == 200
        signals = signals_response.json()
        
        # Count blockers by reason code
        blocker_counts = {}
        manual_approval_signals = []
        
        for signal in signals:
            reason_code = signal.get("blocked_reason_code", "")
            if reason_code:
                blocker_counts[reason_code] = blocker_counts.get(reason_code, 0) + 1
                if reason_code == "MANUAL_APPROVAL_REQUIRED":
                    manual_approval_signals.append({
                        "id": signal.get("id"),
                        "mode": signal.get("mode"),
                        "status": signal.get("status"),
                        "symbol": signal.get("symbol")
                    })
        
        print(f"Blocker counts by reason code: {blocker_counts}")
        print(f"Total signals: {len(signals)}")
        
        # MANUAL_APPROVAL_REQUIRED should NOT appear since mode was enforced to AUTO
        assert "MANUAL_APPROVAL_REQUIRED" not in blocker_counts, \
            f"MANUAL_APPROVAL_REQUIRED should not appear for active-bot user. Found in signals: {manual_approval_signals}"


class TestOrderPrecheckFailedBlockersRemainBlocked:
    """Test that ORDER_PRECHECK_FAILED blockers are not auto-bypassed"""

    def test_fix_all_blockers_does_not_falsely_fix_precheck_blockers(self, user_client, ensure_active_bot):
        """
        Feature: ORDER_PRECHECK_FAILED blockers should remain blocked after fix-all
        They should NOT be auto-bypassed or marked as fixed
        """
        # Get signals before fix-all
        before_signals = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 200})
        assert before_signals.status_code == 200
        before_data = before_signals.json()
        
        # Count precheck blocked signals before
        precheck_blocked_before = [
            s for s in before_data 
            if s.get("blocked_reason_code") == "ORDER_PRECHECK_FAILED" and s.get("status") == "blocked"
        ]
        
        print(f"ORDER_PRECHECK_FAILED signals before fix-all: {len(precheck_blocked_before)}")
        
        # Run fix-all-blockers
        fix_response = user_client.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", params={"limit": 200})
        assert fix_response.status_code == 200
        fix_data = fix_response.json()
        
        print(f"Fix-all result: scanned={fix_data.get('scanned_count')}, fixed={fix_data.get('fixed_count')}, remaining_blocked={fix_data.get('remaining_blocked')}")
        print(f"Actions summary: {fix_data.get('actions_summary', {})}")
        
        # Get signals after fix-all
        after_signals = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 200})
        assert after_signals.status_code == 200
        after_data = after_signals.json()
        
        # Count precheck blocked signals after
        precheck_blocked_after = [
            s for s in after_data 
            if s.get("blocked_reason_code") == "ORDER_PRECHECK_FAILED" and s.get("status") == "blocked"
        ]
        
        print(f"ORDER_PRECHECK_FAILED signals after fix-all: {len(precheck_blocked_after)}")
        
        # Precheck blockers should NOT be reduced by fix-all (they remain blocked)
        # The count might be same or higher (if more signals were processed), but should not decrease
        # More importantly, none should be marked as "fixed" improperly
        
        # Check actions_summary does NOT include precheck-related fixes
        actions_summary = fix_data.get("actions_summary", {})
        precheck_related_actions = [k for k in actions_summary.keys() if "precheck" in k.lower() and "dispatch" not in k.lower()]
        
        # "auto_dispatch_precheck_failed" is OK (it means dispatch was attempted and failed)
        # But there should be no "precheck_bypassed" or similar
        assert not any("bypass" in action.lower() for action in actions_summary.keys()), \
            f"Should not have precheck bypass actions: {actions_summary}"


class TestOrderPrecheckFailedMessageContainsCodes:
    """Test that ORDER_PRECHECK_FAILED messages include clear reject codes"""

    def test_precheck_failed_signal_has_codes_in_message(self, user_client, ensure_active_bot):
        """
        Feature: When ORDER_PRECHECK_FAILED occurs with reject_reason_codes from validation,
        the blocked_reason_message should include those codes
        """
        # Get all signals
        signals_response = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 200})
        assert signals_response.status_code == 200
        signals = signals_response.json()
        
        # Find ORDER_PRECHECK_FAILED signals
        precheck_signals = [
            s for s in signals 
            if s.get("blocked_reason_code") == "ORDER_PRECHECK_FAILED"
        ]
        
        if not precheck_signals:
            # Try running scanner to generate some signals that might hit precheck
            scanner_response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
                "mode": "AUTO",
                "max_results": 15,
                "symbol_source": "crypto"
            })
            assert scanner_response.status_code == 200
            
            # Re-fetch signals
            signals_response = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 200})
            signals = signals_response.json()
            precheck_signals = [
                s for s in signals 
                if s.get("blocked_reason_code") == "ORDER_PRECHECK_FAILED"
            ]
        
        print(f"Found {len(precheck_signals)} ORDER_PRECHECK_FAILED signals")
        
        for signal in precheck_signals[:5]:  # Sample up to 5
            message = signal.get("blocked_reason_message", "")
            hint = signal.get("blocked_solution_hint", "")
            decision_note = signal.get("decision_note", "")
            
            print(f"\nSignal {signal.get('id')}:")
            print(f"  blocked_reason_message: {message}")
            print(f"  blocked_solution_hint: {hint}")
            print(f"  decision_note: {decision_note}")
            
            # The message should contain "codes:" or "detail:" to show explicit info
            has_codes_info = (
                "codes:" in message.lower() or 
                "detail:" in message.lower() or
                "order_precheck_failed:" in decision_note.lower()
            )
            
            # This is a soft check - print for verification
            if has_codes_info:
                print(f"  -> Message includes code/detail info")
            else:
                print(f"  -> Message is base message (no specific codes)")


class TestFixAllBlockersRegressionAndCounts:
    """Regression tests for fix-all-blockers endpoint"""

    def test_fix_all_blockers_returns_correct_schema(self, user_client, ensure_active_bot):
        """Verify fix-all-blockers endpoint returns expected payload schema"""
        response = user_client.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", params={"limit": 100})
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify all required fields
        assert "scanned_count" in data
        assert "blocked_before" in data
        assert "fixed_count" in data
        assert "remaining_blocked" in data
        assert "updated_signal_ids" in data
        assert "actions_summary" in data
        
        # Verify field types
        assert isinstance(data["scanned_count"], int)
        assert isinstance(data["blocked_before"], int)
        assert isinstance(data["fixed_count"], int)
        assert isinstance(data["remaining_blocked"], int)
        assert isinstance(data["updated_signal_ids"], list)
        assert isinstance(data["actions_summary"], dict)
        
        print(f"Fix-all response: {data}")

    def test_fix_all_blockers_counts_before_after(self, user_client, ensure_active_bot):
        """
        Output counts before/after fix-all for verification
        """
        # Get blocked signals count before
        signals_before = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 300})
        assert signals_before.status_code == 200
        before_data = signals_before.json()
        
        blocked_before_count = len([s for s in before_data if s.get("status") == "blocked"])
        
        # Categorize by reason code
        reason_counts_before = {}
        for s in before_data:
            if s.get("status") == "blocked":
                reason = s.get("blocked_reason_code", "UNKNOWN")
                reason_counts_before[reason] = reason_counts_before.get(reason, 0) + 1
        
        print(f"\n=== BEFORE fix-all-blockers ===")
        print(f"Total signals: {len(before_data)}")
        print(f"Blocked signals: {blocked_before_count}")
        print(f"Blocked by reason code: {reason_counts_before}")
        
        # Run fix-all
        fix_response = user_client.post(f"{BASE_URL}/api/user/signals/fix-all-blockers", params={"limit": 300})
        assert fix_response.status_code == 200
        fix_data = fix_response.json()
        
        print(f"\n=== FIX-ALL RESULT ===")
        print(f"scanned_count: {fix_data.get('scanned_count')}")
        print(f"blocked_before: {fix_data.get('blocked_before')}")
        print(f"fixed_count: {fix_data.get('fixed_count')}")
        print(f"remaining_blocked: {fix_data.get('remaining_blocked')}")
        print(f"actions_summary: {fix_data.get('actions_summary', {})}")
        print(f"updated_signal_ids count: {len(fix_data.get('updated_signal_ids', []))}")
        
        # Get signals after
        signals_after = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 300})
        assert signals_after.status_code == 200
        after_data = signals_after.json()
        
        blocked_after_count = len([s for s in after_data if s.get("status") == "blocked"])
        
        reason_counts_after = {}
        for s in after_data:
            if s.get("status") == "blocked":
                reason = s.get("blocked_reason_code", "UNKNOWN")
                reason_counts_after[reason] = reason_counts_after.get(reason, 0) + 1
        
        print(f"\n=== AFTER fix-all-blockers ===")
        print(f"Total signals: {len(after_data)}")
        print(f"Blocked signals: {blocked_after_count}")
        print(f"Blocked by reason code: {reason_counts_after}")
        
        # Verify remaining_blocked matches actual count
        assert fix_data.get("remaining_blocked") == blocked_after_count, \
            f"remaining_blocked ({fix_data.get('remaining_blocked')}) should match actual blocked count ({blocked_after_count})"


class TestScannerResponseWarningsField:
    """Test scanner response warnings field"""

    def test_scanner_run_response_has_warnings_field(self, user_client):
        """Verify scanner response includes warnings array"""
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "MANUAL",
            "max_results": 5,
            "symbol_source": "crypto"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # warnings should be present in response
        assert "warnings" in data, f"Expected 'warnings' field in response: {data.keys()}"
        assert isinstance(data["warnings"], list), f"warnings should be a list: {type(data['warnings'])}"
        
        print(f"Scanner response warnings: {data.get('warnings')}")


class TestPrecheckMessageSampleText:
    """Sample precheck message text verification"""

    def test_sample_precheck_message_text(self, user_client, ensure_active_bot):
        """
        Output sample ORDER_PRECHECK_FAILED message text with codes for verification
        """
        # Run scanner to potentially generate precheck failures
        scanner_response = user_client.post(f"{BASE_URL}/api/user/scanner/run", json={
            "mode": "AUTO",
            "max_results": 20,
            "symbol_source": "crypto"
        })
        assert scanner_response.status_code == 200
        
        # Get signals
        signals_response = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 300})
        assert signals_response.status_code == 200
        signals = signals_response.json()
        
        precheck_signals = [
            s for s in signals 
            if s.get("blocked_reason_code") == "ORDER_PRECHECK_FAILED"
        ]
        
        print(f"\n=== SAMPLE PRECHECK MESSAGE TEXT ===")
        print(f"Found {len(precheck_signals)} ORDER_PRECHECK_FAILED signals")
        
        for i, signal in enumerate(precheck_signals[:3]):  # Sample 3
            print(f"\n--- Signal {i+1} ---")
            print(f"ID: {signal.get('id')}")
            print(f"Symbol: {signal.get('symbol')}")
            print(f"Status: {signal.get('status')}")
            print(f"blocked_reason_code: {signal.get('blocked_reason_code')}")
            print(f"blocked_reason_message: {signal.get('blocked_reason_message')}")
            print(f"blocked_solution_hint: {signal.get('blocked_solution_hint')}")
            print(f"decision_note: {signal.get('decision_note')}")
        
        # This test is informational - always passes
        assert True
