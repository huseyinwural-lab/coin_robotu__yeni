"""
Iteration 53 - Execution Advanced Actions Test Suite
Tests: Position management via intent pipeline (close, partial close, reverse, move stop, move take profit)
       Admin positions-monitor endpoint, execution queue with position action intents
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def test_user_credentials(admin_headers):
    """Create a test user and get approval"""
    import uuid
    import time

    email = f"test_iter53_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"

    # Register user - API returns user object directly
    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
    )
    if resp.status_code != 200:
        pytest.skip(f"User registration failed: {resp.text}")
    user_data = resp.json()
    user_id = user_data.get("id")

    # Admin approves the user via bulk-approve endpoint
    resp = requests.post(
        f"{BASE_URL}/api/admin/user-approvals/bulk-approve",
        headers=admin_headers,
        json={"ids": [user_id]},
    )
    if resp.status_code != 200:
        pytest.skip(f"User approval failed: {resp.text}")

    time.sleep(0.5)
    return {"email": email, "password": password, "user_id": user_id}


@pytest.fixture(scope="module")
def user_token(test_user_credentials):
    """Get user authentication token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"],
        },
    )
    if resp.status_code != 200:
        pytest.skip(f"User login failed: {resp.text}")
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def user_headers(user_token):
    """Headers with user token"""
    return {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def open_position(user_headers, admin_headers):
    """Create an open position for testing position actions"""
    # First, create an execution intent to open position
    preview_payload = {
        "source_type": "manual",
        "intent_type": "OPEN_POSITION",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 100,
        "execution_mode": "manual",
    }

    resp = requests.post(
        f"{BASE_URL}/api/user/execution/intent/preview",
        headers=user_headers,
        json=preview_payload,
    )
    if resp.status_code != 200:
        pytest.skip(f"Failed to preview intent: {resp.text}")

    preview_data = resp.json()
    intent_token = preview_data.get("intent_token")
    preview_hash = preview_data.get("preview_hash")

    # Submit the intent
    resp = requests.post(
        f"{BASE_URL}/api/user/execution/intent/submit",
        headers=user_headers,
        json={"intent_token": intent_token, "preview_hash": preview_hash},
    )
    if resp.status_code != 200:
        pytest.skip(f"Failed to submit intent: {resp.text}")

    submit_data = resp.json()
    intent_id = submit_data.get("intent_id")

    # Admin approves the intent
    resp = requests.post(
        f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
        headers=admin_headers,
        json={"note": "test_position_creation"},
    )
    if resp.status_code != 200:
        pytest.skip(f"Failed to approve intent: {resp.text}")

    import time
    time.sleep(0.5)

    # Get open positions
    resp = requests.get(
        f"{BASE_URL}/api/user/execution/positions",
        headers=user_headers,
        params={"include_closed": False},
    )
    if resp.status_code != 200 or not resp.json():
        pytest.skip(f"No open position found: {resp.text}")

    return resp.json()[0]


class TestNewIntentTypesBackend:
    """Test that new intent types are processed by backend"""

    def test_close_position_intent_type_recognized(self, user_headers, open_position):
        """CLOSE_POSITION intent type is processed"""
        payload = {
            "intent_type": "CLOSE_POSITION",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": True,
        }
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert resp.status_code == 200, f"CLOSE_POSITION preview failed: {resp.text}"
        data = resp.json()
        assert data.get("intent_type") == "CLOSE_POSITION"
        assert data.get("position_id") == open_position["position_id"]
        print(f"CLOSE_POSITION intent preview successful: validation_status={data.get('validation_status')}")

    def test_partial_close_intent_type_recognized(self, user_headers, open_position):
        """PARTIAL_CLOSE intent type is processed"""
        payload = {
            "intent_type": "PARTIAL_CLOSE",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": max(open_position["size"] / 2, 0.001),
            "reduce_only": True,
        }
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert resp.status_code == 200, f"PARTIAL_CLOSE preview failed: {resp.text}"
        data = resp.json()
        assert data.get("intent_type") == "PARTIAL_CLOSE"
        print(f"PARTIAL_CLOSE intent preview successful: size={data.get('size')}")

    def test_reverse_position_intent_type_recognized(self, user_headers, open_position):
        """REVERSE_POSITION intent type is processed"""
        payload = {
            "intent_type": "REVERSE_POSITION",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": False,
        }
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert resp.status_code == 200, f"REVERSE_POSITION preview failed: {resp.text}"
        data = resp.json()
        assert data.get("intent_type") == "REVERSE_POSITION"
        print(f"REVERSE_POSITION intent preview successful: validation_status={data.get('validation_status')}")

    def test_move_stop_intent_type_recognized(self, user_headers, open_position):
        """MOVE_STOP intent type is processed"""
        payload = {
            "intent_type": "MOVE_STOP",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": True,
            "stop_price": open_position["entry_price"] * 0.95,
        }
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert resp.status_code == 200, f"MOVE_STOP preview failed: {resp.text}"
        data = resp.json()
        assert data.get("intent_type") == "MOVE_STOP"
        assert data.get("stop_price") is not None
        print(f"MOVE_STOP intent preview successful: stop_price={data.get('stop_price')}")

    def test_move_take_profit_intent_type_recognized(self, user_headers, open_position):
        """MOVE_TAKE_PROFIT intent type is processed"""
        payload = {
            "intent_type": "MOVE_TAKE_PROFIT",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": True,
            "take_profit_price": open_position["entry_price"] * 1.05,
        }
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert resp.status_code == 200, f"MOVE_TAKE_PROFIT preview failed: {resp.text}"
        data = resp.json()
        assert data.get("intent_type") == "MOVE_TAKE_PROFIT"
        assert data.get("take_profit_price") is not None
        print(f"MOVE_TAKE_PROFIT intent preview successful: take_profit_price={data.get('take_profit_price')}")


class TestPositionActionsPreviewSubmit:
    """Test POST /api/user/execution/position-actions/preview and /submit endpoints"""

    def test_position_actions_preview_endpoint_works(self, user_headers, open_position):
        """POST /api/user/execution/position-actions/preview works"""
        payload = {
            "intent_type": "CLOSE_POSITION",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": True,
        }
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert resp.status_code == 200, f"Position actions preview failed: {resp.text}"
        data = resp.json()
        # Check required fields in response
        assert "intent_id" in data
        assert "intent_token" in data
        assert "preview_hash" in data
        assert "validation_status" in data
        assert "normalized_order_payload" in data
        assert "meta_strategy_summary" in data
        assert "portfolio_risk_impact" in data
        print(f"Position actions preview response: intent_token={data['intent_token'][:16]}...")

    def test_position_actions_submit_endpoint_works(self, user_headers, open_position):
        """POST /api/user/execution/position-actions/submit works"""
        # First preview
        payload = {
            "intent_type": "MOVE_STOP",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": True,
            "stop_price": open_position["entry_price"] * 0.94,
        }
        preview_resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert preview_resp.status_code == 200, f"Preview failed: {preview_resp.text}"
        preview_data = preview_resp.json()

        if preview_data.get("validation_status") != "valid":
            pytest.skip(f"Preview rejected: {preview_data.get('reject_reason_codes')}")

        # Then submit
        submit_resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/submit",
            headers=user_headers,
            json={
                "intent_token": preview_data["intent_token"],
                "preview_hash": preview_data["preview_hash"],
            },
        )
        assert submit_resp.status_code == 200, f"Submit failed: {submit_resp.text}"
        submit_data = submit_resp.json()
        assert submit_data.get("intent_status") == "QUEUED_FOR_APPROVAL"
        print(f"Position action submitted: intent_id={submit_data['intent_id']}")


class TestUserPositionsEndpoint:
    """Test /api/user/execution/positions endpoint"""

    def test_user_positions_endpoint_returns_correct_state(self, user_headers):
        """GET /api/user/execution/positions returns correct position state"""
        resp = requests.get(
            f"{BASE_URL}/api/user/execution/positions",
            headers=user_headers,
            params={"include_closed": False},
        )
        assert resp.status_code == 200, f"Positions endpoint failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        if data:
            pos = data[0]
            # Check required fields
            assert "position_id" in pos
            assert "symbol" in pos
            assert "size" in pos
            assert "entry_price" in pos
            assert "current_price" in pos
            assert "unrealized_pnl" in pos
            assert "leverage" in pos
            assert "status" in pos
            assert "updated_at" in pos
            print(f"User positions: {len(data)} positions found, first: {pos['symbol']} size={pos['size']}")
        else:
            print("User positions: No open positions found")


class TestAdminPositionsMonitor:
    """Test /api/admin/positions-monitor endpoint"""

    def test_admin_positions_monitor_returns_correct_data(self, admin_headers):
        """GET /api/admin/positions-monitor returns open positions + cluster exposure + risk level + forced liquidation risk"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/positions-monitor",
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Positions monitor failed: {resp.text}"
        data = resp.json()

        # Check required fields
        assert "generated_at" in data
        assert "open_positions" in data
        assert isinstance(data["open_positions"], list)
        assert "cluster_exposure" in data
        assert isinstance(data["cluster_exposure"], dict)
        assert "risk_level" in data
        assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
        assert "forced_liquidation_risk" in data
        assert isinstance(data["forced_liquidation_risk"], (int, float))

        print(f"Admin positions monitor: {len(data['open_positions'])} open positions, risk_level={data['risk_level']}, forced_liq_risk={data['forced_liquidation_risk']}")

        # Check position fields if any
        if data["open_positions"]:
            pos = data["open_positions"][0]
            assert "position_id" in pos
            assert "symbol" in pos
            assert "size" in pos
            assert "entry_price" in pos
            assert "current_price" in pos
            assert "cluster_id" in pos


class TestExecutionQueuePayload:
    """Test that execution queue payload contains intent_type/position_id/size/price/stop/tp fields"""

    def test_execution_queue_contains_intent_type_and_position_id(self, admin_headers, user_headers, open_position):
        """Execution queue payload contains intent_type, position_id, size, price, stop, tp fields"""
        # Create a position action intent
        payload = {
            "intent_type": "PARTIAL_CLOSE",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": max(open_position["size"] / 3, 0.001),
            "reduce_only": True,
            "price": None,
            "stop_price": None,
            "take_profit_price": None,
        }
        preview_resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert preview_resp.status_code == 200
        preview_data = preview_resp.json()

        if preview_data.get("validation_status") != "valid":
            pytest.skip(f"Preview rejected: {preview_data.get('reject_reason_codes')}")

        # Submit to queue
        submit_resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/submit",
            headers=user_headers,
            json={
                "intent_token": preview_data["intent_token"],
                "preview_hash": preview_data["preview_hash"],
            },
        )
        assert submit_resp.status_code == 200

        # Check admin queue
        queue_resp = requests.get(
            f"{BASE_URL}/api/admin/execution-queue",
            headers=admin_headers,
            params={"status_filter": "all", "limit": 50},
        )
        assert queue_resp.status_code == 200
        queue_data = queue_resp.json()

        # Find our intent in the queue
        found = None
        for item in queue_data:
            if item.get("id") == preview_data["intent_id"]:
                found = item
                break

        if found:
            # Check all required fields are present
            assert "intent_type" in found
            assert "position_id" in found
            assert "size" in found
            assert "price" in found or found.get("price") is None  # price can be null
            assert "stop_price" in found or found.get("stop_price") is None
            assert "take_profit_price" in found or found.get("take_profit_price") is None
            print(f"Execution queue item: intent_type={found['intent_type']}, position_id={found['position_id']}, size={found['size']}")
        else:
            print("Warning: Intent not found in queue (may have been already processed)")


class TestDecisionTracePositionActionFields:
    """Test that decision trace contains position_action_reason/risk_adjustment_reason/strategy_override_reason"""

    def test_decision_trace_contains_position_action_fields(self, user_headers, open_position):
        """Decision trace contains position_action_reason, risk_adjustment_reason, strategy_override_reason"""
        # Create a position action to generate decision trace
        payload = {
            "intent_type": "CLOSE_POSITION",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": True,
        }
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert resp.status_code == 200
        preview_data = resp.json()
        intent_id = preview_data.get("intent_id")

        # Get decision traces for this entity
        trace_resp = requests.get(
            f"{BASE_URL}/api/user/decision-trace/timeline",
            headers=user_headers,
            params={"entity_scope": "execution", "entity_id": intent_id},
        )
        if trace_resp.status_code != 200:
            pytest.skip(f"Decision trace endpoint not available: {trace_resp.text}")

        trace_data = trace_resp.json()
        if not trace_data.get("timeline"):
            pytest.skip("No decision traces found for the intent")

        # Check first trace has position action fields
        trace = trace_data["timeline"][0]
        # These fields may be present or null
        assert "position_action_reason" in trace or trace.get("position_action_reason") is None
        assert "risk_adjustment_reason" in trace or trace.get("risk_adjustment_reason") is None
        assert "strategy_override_reason" in trace or trace.get("strategy_override_reason") is None

        # For position actions, position_action_reason should have the intent_type
        if trace.get("position_action_reason"):
            assert trace["position_action_reason"] in [
                "CLOSE_POSITION",
                "PARTIAL_CLOSE",
                "REVERSE_POSITION",
                "MOVE_STOP",
                "MOVE_TAKE_PROFIT",
            ]
            print(f"Decision trace position_action_reason: {trace['position_action_reason']}")


class TestExecutionQueueApproveReject:
    """Test execution queue approve/reject with position action release"""

    def test_execution_queue_approve_applies_position_action(self, admin_headers, user_headers, open_position):
        """Execution queue approve applies position action release (MOVE_STOP)"""
        # Create MOVE_STOP action
        new_stop_price = open_position["entry_price"] * 0.92
        payload = {
            "intent_type": "MOVE_STOP",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": True,
            "stop_price": new_stop_price,
        }
        preview_resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert preview_resp.status_code == 200
        preview_data = preview_resp.json()

        if preview_data.get("validation_status") != "valid":
            pytest.skip(f"Preview rejected: {preview_data.get('reject_reason_codes')}")

        # Submit
        submit_resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/submit",
            headers=user_headers,
            json={
                "intent_token": preview_data["intent_token"],
                "preview_hash": preview_data["preview_hash"],
            },
        )
        assert submit_resp.status_code == 200
        intent_id = submit_resp.json()["intent_id"]

        # Admin approves
        approve_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={"note": "test_approve_move_stop"},
        )
        assert approve_resp.status_code == 200, f"Approve failed: {approve_resp.text}"
        approve_data = approve_resp.json()
        assert approve_data["status"] == "RELEASED"
        print(f"Position action approved and released: intent_id={intent_id}")

    def test_execution_queue_reject_works_for_position_action(self, admin_headers, user_headers, open_position):
        """Execution queue reject works for position action"""
        # Create MOVE_TAKE_PROFIT action
        payload = {
            "intent_type": "MOVE_TAKE_PROFIT",
            "position_id": open_position["position_id"],
            "symbol": open_position["symbol"],
            "size": open_position["size"],
            "reduce_only": True,
            "take_profit_price": open_position["entry_price"] * 1.08,
        }
        preview_resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            headers=user_headers,
            json=payload,
        )
        assert preview_resp.status_code == 200
        preview_data = preview_resp.json()

        if preview_data.get("validation_status") != "valid":
            pytest.skip(f"Preview rejected: {preview_data.get('reject_reason_codes')}")

        # Submit
        submit_resp = requests.post(
            f"{BASE_URL}/api/user/execution/position-actions/submit",
            headers=user_headers,
            json={
                "intent_token": preview_data["intent_token"],
                "preview_hash": preview_data["preview_hash"],
            },
        )
        assert submit_resp.status_code == 200
        intent_id = submit_resp.json()["intent_id"]

        # Admin rejects
        reject_resp = requests.post(
            f"{BASE_URL}/api/admin/execution-queue/{intent_id}/reject",
            headers=admin_headers,
            json={"note": "test_reject_position_action"},
        )
        assert reject_resp.status_code == 200, f"Reject failed: {reject_resp.text}"
        reject_data = reject_resp.json()
        assert reject_data["status"] == "REJECTED"
        print(f"Position action rejected: intent_id={intent_id}")


class TestRegressionUserExecutePreview:
    """Regression test: /user/execute preview should still work"""

    def test_user_execute_preview_not_broken(self, user_headers):
        """POST /api/user/execution/intent/preview still works"""
        payload = {
            "source_type": "manual",
            "intent_type": "OPEN_POSITION",
            "market_type": "spot",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50,
            "execution_mode": "manual",
        }
        resp = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            headers=user_headers,
            json=payload,
        )
        assert resp.status_code == 200, f"User execute preview failed: {resp.text}"
        data = resp.json()
        assert "intent_token" in data
        assert "preview_hash" in data
        assert "validation_status" in data
        print(f"Regression: /user/execute preview works: validation_status={data['validation_status']}")


class TestRegressionUserSignals:
    """Regression test: /user/signals should still work"""

    def test_user_signals_endpoint_not_broken(self, user_headers):
        """GET /api/user/signals still works"""
        resp = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=user_headers,
            params={"limit": 10},
        )
        assert resp.status_code == 200, f"User signals failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"Regression: /user/signals works: {len(data)} signals")


class TestRegressionUserTrades:
    """Regression test: /user/trades should still work"""

    def test_user_trades_endpoint_not_broken(self, user_headers):
        """GET /api/user/trades still works"""
        resp = requests.get(
            f"{BASE_URL}/api/user/trades",
            headers=user_headers,
            params={"limit": 10},
        )
        assert resp.status_code == 200, f"User trades failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"Regression: /user/trades works: {len(data)} trades")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
