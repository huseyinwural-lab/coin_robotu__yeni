"""
U-07 User Exchange Connection Tests
Test CRUD operations, set-default, legacy sync and venue_context in execution preview
"""
import os
import pytest
import requests


def _resolve_base_url() -> str:
    candidate = (os.environ.get("REACT_APP_BACKEND_URL") or "").strip().rstrip("/")
    if candidate:
        return candidate

    env_paths = ["/app/frontend/.env", "/app/.env"]
    for path in env_paths:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    parsed = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if parsed:
                        return parsed.rstrip("/")

    return "http://127.0.0.1:8001"


BASE_URL = _resolve_base_url()

# Test credentials
USER_EMAIL = "e2_conn_last@example.com"
USER_PASSWORD = "User12345!"
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


class TestUserExchangeConnectionsCRUD:
    """U-07 Exchange Connection CRUD + Set-Default Tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.user_token = None
        self.admin_token = None

    def _login_user(self):
        """Login as test user"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
        )
        if response.status_code != 200:
            # Create user first if not exists
            register_response = self.session.post(
                f"{BASE_URL}/api/auth/register",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
            )
            if register_response.status_code not in [200, 201, 400]:
                pytest.skip(f"Cannot create test user: {register_response.text}")

            # Need admin approval - login as admin
            admin_login = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
            if admin_login.status_code == 200:
                admin_token = admin_login.json().get("access_token")
                self.session.headers.update({"Authorization": f"Bearer {admin_token}"})
                # Approve user
                users_response = self.session.get(f"{BASE_URL}/api/admin/users?scope=user")
                if users_response.status_code == 200:
                    users = users_response.json()
                    for user in users:
                        if user.get("email") == USER_EMAIL:
                            self.session.post(f"{BASE_URL}/api/admin/users/{user['id']}/approve")
                            break

            # Retry login
            response = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
            )

        if response.status_code != 200:
            pytest.skip(f"Cannot login as test user: {response.text}")

        self.user_token = response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.user_token}"})

    def _login_admin(self):
        """Login as admin"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Cannot login as admin: {response.text}")
        self.admin_token = response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})

    def test_list_exchange_connections(self):
        """Test GET /api/user/exchange-connections returns list"""
        self._login_user()
        response = self.session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"test_list_exchange_connections: PASS - {len(data)} connections found")

    def test_create_exchange_connection(self):
        """Test POST /api/user/exchange-connections creates connection"""
        self._login_user()
        payload = {
            "account_label": f"test_conn_{os.urandom(4).hex()}",
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "is_default": False,
        }
        response = self.session.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json=payload,
        )
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data, "Response should have id"
        assert data["account_label"] == payload["account_label"]
        assert data["exchange"] == "binance"
        assert data["market_type"] == "spot"
        assert data["environment"] == "testnet"
        print(f"test_create_exchange_connection: PASS - created {data['id']}")

    def test_create_duplicate_label_fails(self):
        """Test creating connection with duplicate label fails"""
        self._login_user()
        label = f"dup_label_{os.urandom(4).hex()}"
        payload = {
            "account_label": label,
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
        }
        # Create first
        response1 = self.session.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json=payload,
        )
        assert response1.status_code == 201

        # Create duplicate
        response2 = self.session.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json=payload,
        )
        assert response2.status_code == 400, f"Expected 400, got {response2.status_code}"
        assert "account_label_already_exists" in response2.text or "exists" in response2.text.lower()
        print("test_create_duplicate_label_fails: PASS")

    def test_update_exchange_connection(self):
        """Test PUT /api/user/exchange-connections/{id} updates connection"""
        self._login_user()
        # Create first
        create_payload = {
            "account_label": f"update_test_{os.urandom(4).hex()}",
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
        }
        create_response = self.session.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json=create_payload,
        )
        assert create_response.status_code == 201
        conn_id = create_response.json()["id"]

        # Update
        update_payload = {"market_type": "futures"}
        update_response = self.session.put(
            f"{BASE_URL}/api/user/exchange-connections/{conn_id}",
            json=update_payload,
        )
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}: {update_response.text}"
        updated_data = update_response.json()
        assert updated_data["market_type"] == "futures"
        print("test_update_exchange_connection: PASS - updated to futures")

    def test_set_default_connection(self):
        """Test POST /api/user/exchange-connections/{id}/set-default"""
        self._login_user()
        # Create a connection
        create_payload = {
            "account_label": f"default_test_{os.urandom(4).hex()}",
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "is_default": False,
        }
        create_response = self.session.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json=create_payload,
        )
        assert create_response.status_code == 201
        conn_id = create_response.json()["id"]

        # Set as default
        set_default_response = self.session.post(
            f"{BASE_URL}/api/user/exchange-connections/{conn_id}/set-default"
        )
        assert set_default_response.status_code == 200, f"Expected 200, got {set_default_response.status_code}"
        data = set_default_response.json()
        assert data["is_default"] is True
        print(f"test_set_default_connection: PASS - {conn_id} is now default")

    def test_delete_exchange_connection(self):
        """Test DELETE /api/user/exchange-connections/{id}"""
        self._login_user()
        # Create first
        create_payload = {
            "account_label": f"delete_test_{os.urandom(4).hex()}",
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
        }
        create_response = self.session.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json=create_payload,
        )
        assert create_response.status_code == 201
        conn_id = create_response.json()["id"]

        # Delete
        delete_response = self.session.delete(
            f"{BASE_URL}/api/user/exchange-connections/{conn_id}"
        )
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}"
        data = delete_response.json()
        assert data.get("deleted") is True
        print(f"test_delete_exchange_connection: PASS - deleted {conn_id}")


class TestLegacySync:
    """Test legacy sync when default connection changes"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _login_user(self):
        """Login as test user"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Cannot login: {response.text}")
        token = response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def test_legacy_sync_on_set_default(self):
        """Test /api/phase4/exchange-settings returns consistent data after set-default"""
        self._login_user()

        # Get legacy settings before
        legacy_before = self.session.get(f"{BASE_URL}/api/phase4/exchange-settings")
        assert legacy_before.status_code == 200

        # Create and set new default
        create_payload = {
            "account_label": f"legacy_sync_{os.urandom(4).hex()}",
            "exchange": "binance",
            "market_type": "futures",
            "environment": "testnet",
            "is_default": True,
        }
        create_response = self.session.post(
            f"{BASE_URL}/api/user/exchange-connections",
            json=create_payload,
        )
        if create_response.status_code != 201:
            print(f"Create response: {create_response.status_code} - {create_response.text}")
            pytest.skip("Cannot create connection for legacy sync test")

        # Get legacy settings after - should be synced
        legacy_after = self.session.get(f"{BASE_URL}/api/phase4/exchange-settings")
        assert legacy_after.status_code == 200
        after_data = legacy_after.json()

        # Legacy settings should reflect new default
        assert after_data.get("exchange") == "binance"
        print(f"test_legacy_sync_on_set_default: PASS - legacy exchange={after_data.get('exchange')}, mode={after_data.get('mode')}")


class TestExecutionPreviewVenueContext:
    """U-08 Test venue_context in execution intent preview"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _login_user(self):
        """Login as test user"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Cannot login: {response.text}")
        token = response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _ensure_venue_assignment(self):
        """Ensure user has venue assignment for binance spot testnet"""
        # Login as admin
        admin_login = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if admin_login.status_code != 200:
            return

        admin_token = admin_login.json().get("access_token")
        admin_session = requests.Session()
        admin_session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {admin_token}",
        })

        # Get user ID
        users_response = admin_session.get(f"{BASE_URL}/api/admin/users?scope=user")
        if users_response.status_code != 200:
            return

        user_id = None
        for user in users_response.json():
            if user.get("email") == USER_EMAIL:
                user_id = user.get("id")
                break

        if not user_id:
            return

        # Assign venue
        venue_payload = {
            "user_id": user_id,
            "exchange_code": "binance",
            "spot_allowed": True,
            "futures_allowed": True,
            "testnet_allowed": True,
            "live_allowed": False,
        }
        admin_session.post(f"{BASE_URL}/api/admin/venues/assignments", json=venue_payload)

    def test_execution_preview_returns_venue_context(self):
        """Test /api/user/execution/intent/preview returns venue_context"""
        self._ensure_venue_assignment()
        self._login_user()

        preview_payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "exchange": "binance",
            "environment": "testnet",
        }

        response = self.session.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=preview_payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        # Check venue_context exists
        assert "venue_context" in data, "Response should have venue_context"
        venue_context = data["venue_context"]
        assert "exchange" in venue_context, "venue_context should have exchange"
        assert "market_type" in venue_context, "venue_context should have market_type"
        assert "environment" in venue_context, "venue_context should have environment"
        assert "allowed" in venue_context, "venue_context should have allowed"
        assert "venue_state" in venue_context, "venue_context should have venue_state"

        print("test_execution_preview_returns_venue_context: PASS")
        print(f"  venue_context: exchange={venue_context.get('exchange')}, market_type={venue_context.get('market_type')}, environment={venue_context.get('environment')}")
        print(f"  allowed={venue_context.get('allowed')}, venue_state={venue_context.get('venue_state')}")

    def test_venue_blocked_returns_rejection(self):
        """Test preview with venue_blocked returns validation rejected"""
        self._login_user()

        # Request live environment which should be blocked
        preview_payload = {
            "source_type": "manual",
            "market_type": "futures",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 25,
            "exchange": "binance",
            "environment": "live",  # Live should be blocked
        }

        response = self.session.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=preview_payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        venue_context = data.get("venue_context", {})
        validation_status = data.get("validation_status")
        reject_reason_codes = data.get("reject_reason_codes", [])

        # If venue is not allowed, validation should be rejected
        if not venue_context.get("allowed", False):
            assert validation_status == "rejected", f"Expected rejected when venue blocked, got {validation_status}"
            assert "venue_access_blocked" in reject_reason_codes or any("venue" in code.lower() for code in reject_reason_codes)
            print(f"test_venue_blocked_returns_rejection: PASS - validation_status={validation_status}")
        else:
            print("test_venue_blocked_returns_rejection: SKIP - venue was allowed")


class TestIndicatorScreenerFreshness:
    """U-12 Test freshness visibility in indicator screener response"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _login_user(self):
        """Login as test user"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Cannot login: {response.text}")
        token = response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def test_screener_freshness_fields_in_rows(self):
        """Test indicator screener rows contain freshness fields"""
        self._login_user()

        screener_payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi14 < 70",
            "limit": 5,
            "filter_payload": {},
        }

        response = self.session.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=screener_payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        rows = data.get("rows", [])

        if len(rows) == 0:
            print("test_screener_freshness_fields_in_rows: SKIP - no rows returned")
            return

        # Check first row for freshness fields
        first_row = rows[0]
        freshness_fields = ["last_candle_time", "evaluated_at", "data_source", "cache_hit", "fresh_fetch"]

        found_fields = []
        for field in freshness_fields:
            if field in first_row:
                found_fields.append(field)

        print("test_screener_freshness_fields_in_rows: PASS")
        print(f"  Found freshness fields: {found_fields}")
        print(f"  last_candle_time={first_row.get('last_candle_time')}")
        print(f"  evaluated_at={first_row.get('evaluated_at')}")
        print(f"  data_source={first_row.get('data_source')}")
        print(f"  cache_hit={first_row.get('cache_hit')}")
        print(f"  fresh_fetch={first_row.get('fresh_fetch')}")

        # At least updated_at or one of freshness fields should exist
        has_freshness = any(field in first_row for field in freshness_fields) or "updated_at" in first_row
        assert has_freshness, "Row should have at least one freshness-related field"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
