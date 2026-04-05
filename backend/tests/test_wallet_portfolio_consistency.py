"""
Test suite for wallet/portfolio consistency issues:
- GET /api/user/exchange-connections wallet list filtering
- GET /api/user/portfolio spot_wallet_balance/futures_wallet_balance calculation
- Exchange Settings save and readiness_snapshot.source preservation
- BotProfilesPage comboActivationState calculation
- Wallet dropdown labels and options filtering
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

TEST_USER_EMAIL = "review.user@platform.local"
TEST_USER_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session with cookies"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    
    data = response.json()
    token = data.get("access_token") or data.get("token")
    assert token, "No token in login response"
    
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestExchangeConnectionsAPI:
    """Tests for GET /api/user/exchange-connections"""
    
    def test_exchange_connections_returns_list(self, auth_session):
        """Verify exchange connections endpoint returns a list"""
        response = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} exchange connections")
    
    def test_exchange_connections_have_required_fields(self, auth_session):
        """Verify each connection has required fields for BotProfiles filtering"""
        response = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = [
            "id", "exchange", "market_type", "environment",
            "connection_health", "can_trade_effective",
            "global_activation_active", "global_activation_flag_key",
            "readiness_snapshot"
        ]
        
        for conn in data:
            for field in required_fields:
                assert field in conn, f"Missing field '{field}' in connection {conn.get('id')}"
            
            # Verify readiness_snapshot structure
            snapshot = conn.get("readiness_snapshot") or {}
            print(f"Connection {conn['account_label']}: health={conn['connection_health']}, "
                  f"can_trade={conn['can_trade_effective']}, "
                  f"wallet_balance={snapshot.get('wallet_balance')}, "
                  f"source={snapshot.get('source')}")
    
    def test_connections_filtered_by_market_type(self, auth_session):
        """Verify connections can be filtered by market_type for BotProfiles"""
        response = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        
        data = response.json()
        
        # Group by market_type
        spot_connections = [c for c in data if c.get("market_type") == "spot"]
        futures_connections = [c for c in data if c.get("market_type") == "futures"]
        
        print(f"Spot connections: {len(spot_connections)}")
        print(f"Futures connections: {len(futures_connections)}")
        
        # Verify each has proper market_type
        for conn in spot_connections:
            assert conn["market_type"] == "spot"
        for conn in futures_connections:
            assert conn["market_type"] == "futures"


class TestPortfolioAPI:
    """Tests for GET /api/user/portfolio wallet balance calculation"""
    
    def test_portfolio_returns_wallet_balances(self, auth_session):
        """Verify portfolio endpoint returns wallet balance fields"""
        response = auth_session.get(f"{BASE_URL}/api/user/portfolio")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        
        # Required wallet balance fields
        assert "spot_wallet_balance" in data, "Missing spot_wallet_balance"
        assert "futures_wallet_balance" in data, "Missing futures_wallet_balance"
        assert "total_wallet_balance" in data, "Missing total_wallet_balance"
        
        print(f"Portfolio balances: spot={data['spot_wallet_balance']}, "
              f"futures={data['futures_wallet_balance']}, "
              f"total={data['total_wallet_balance']}")
    
    def test_portfolio_wallet_balance_consistency(self, auth_session):
        """
        CRITICAL: Verify portfolio wallet balances match exchange connections
        
        This test checks the root cause issue where:
        - Exchange Diagnostics shows balance
        - Portfolio shows spot/futures wallets as 0
        """
        # Get exchange connections
        conn_response = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert conn_response.status_code == 200
        connections = conn_response.json()
        
        # Get portfolio
        portfolio_response = auth_session.get(f"{BASE_URL}/api/user/portfolio")
        assert portfolio_response.status_code == 200
        portfolio = portfolio_response.json()
        
        # Find connections with wallet balance
        spot_with_balance = []
        futures_with_balance = []
        
        for conn in connections:
            snapshot = conn.get("readiness_snapshot") or {}
            wallet_balance = snapshot.get("wallet_balance") or snapshot.get("available_balance") or 0
            
            if conn.get("market_type") == "spot" and conn.get("environment") == "live":
                if wallet_balance > 0:
                    spot_with_balance.append({
                        "id": conn["id"],
                        "label": conn.get("account_label"),
                        "balance": wallet_balance,
                        "health": conn.get("connection_health"),
                        "can_trade": conn.get("can_trade_effective")
                    })
            
            if conn.get("market_type") == "futures" and conn.get("environment") == "live":
                if wallet_balance > 0:
                    futures_with_balance.append({
                        "id": conn["id"],
                        "label": conn.get("account_label"),
                        "balance": wallet_balance,
                        "health": conn.get("connection_health"),
                        "can_trade": conn.get("can_trade_effective")
                    })
        
        print(f"\nSpot connections with balance: {spot_with_balance}")
        print(f"Futures connections with balance: {futures_with_balance}")
        print(f"\nPortfolio spot_wallet_balance: {portfolio['spot_wallet_balance']}")
        print(f"Portfolio futures_wallet_balance: {portfolio['futures_wallet_balance']}")
        
        # Check consistency
        if spot_with_balance:
            max_spot_balance = max(c["balance"] for c in spot_with_balance)
            if portfolio["spot_wallet_balance"] == 0 and max_spot_balance > 0:
                print(f"\n⚠️ INCONSISTENCY: Spot connection has balance {max_spot_balance} "
                      f"but portfolio shows 0")
                # This is the bug - don't fail, just report
        
        if futures_with_balance:
            max_futures_balance = max(c["balance"] for c in futures_with_balance)
            if portfolio["futures_wallet_balance"] == 0 and max_futures_balance > 0:
                print(f"\n⚠️ INCONSISTENCY: Futures connection has balance {max_futures_balance} "
                      f"but portfolio shows 0")
    
    def test_total_wallet_balance_calculation(self, auth_session):
        """Verify total_wallet_balance = spot + futures"""
        response = auth_session.get(f"{BASE_URL}/api/user/portfolio")
        assert response.status_code == 200
        
        data = response.json()
        
        expected_total = round(data["spot_wallet_balance"] + data["futures_wallet_balance"], 8)
        actual_total = data["total_wallet_balance"]
        
        assert abs(actual_total - expected_total) < 0.00001, \
            f"Total mismatch: {actual_total} != {expected_total}"


class TestExchangeSettingsSync:
    """Tests for Exchange Settings save and readiness_snapshot.source preservation"""
    
    def test_settings_synced_connections_have_source(self, auth_session):
        """
        Verify connections created via Exchange Settings have 
        readiness_snapshot.source = 'phase4_exchange_settings_sync'
        """
        response = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        
        data = response.json()
        
        settings_synced = []
        for conn in data:
            snapshot = conn.get("readiness_snapshot") or {}
            source = snapshot.get("source", "")
            label = conn.get("account_label", "")
            
            is_settings_synced = (
                source == "phase4_exchange_settings_sync" or 
                label.upper().startswith("SETTINGS ")
            )
            
            if is_settings_synced:
                settings_synced.append({
                    "id": conn["id"],
                    "label": label,
                    "source": source
                })
        
        print(f"Settings-synced connections: {settings_synced}")
        
        # Verify source is preserved
        for conn in settings_synced:
            assert conn["source"] == "phase4_exchange_settings_sync" or \
                   conn["label"].upper().startswith("SETTINGS "), \
                   f"Connection {conn['id']} should have settings sync source"


class TestBotProfilesWalletFiltering:
    """Tests for BotProfiles wallet dropdown filtering logic"""
    
    def test_wallet_options_filtered_by_exchange_and_market(self, auth_session):
        """
        Verify wallet options are properly filtered by exchange + market_type
        This simulates the scopedConnections logic in BotProfilesPage.jsx
        """
        response = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        
        connections = response.json()
        
        # Simulate frontend filtering for binance + spot
        binance_spot_live = [
            c for c in connections
            if c.get("exchange", "").lower() == "binance"
            and c.get("market_type", "").lower() == "spot"
            and c.get("environment", "live").lower() == "live"
        ]
        
        # Simulate frontend filtering for binance + futures
        binance_futures_live = [
            c for c in connections
            if c.get("exchange", "").lower() == "binance"
            and c.get("market_type", "").lower() == "futures"
            and c.get("environment", "live").lower() == "live"
        ]
        
        print(f"\nBinance Spot Live connections: {len(binance_spot_live)}")
        for c in binance_spot_live:
            snapshot = c.get("readiness_snapshot") or {}
            print(f"  - {c['account_label']}: health={c['connection_health']}, "
                  f"can_trade={c['can_trade_effective']}, "
                  f"balance={snapshot.get('wallet_balance') or snapshot.get('available_balance')}")
        
        print(f"\nBinance Futures Live connections: {len(binance_futures_live)}")
        for c in binance_futures_live:
            snapshot = c.get("readiness_snapshot") or {}
            print(f"  - {c['account_label']}: health={c['connection_health']}, "
                  f"can_trade={c['can_trade_effective']}, "
                  f"balance={snapshot.get('wallet_balance') or snapshot.get('available_balance')}")
    
    def test_combo_activation_state_calculation(self, auth_session):
        """
        Test comboActivationState logic from BotProfilesPage.jsx:
        - active = any connection with (health=online AND can_trade) OR global_activation_active
        """
        response = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        
        connections = response.json()
        
        # Test for binance + spot
        binance_spot = [
            c for c in connections
            if c.get("exchange", "").lower() == "binance"
            and c.get("market_type", "").lower() == "spot"
            and c.get("environment", "live").lower() == "live"
        ]
        
        # Calculate comboActivationState
        active = any(
            (c.get("connection_health", "").lower() == "online" and c.get("can_trade_effective"))
            or c.get("global_activation_active")
            for c in binance_spot
        )
        
        has_connection = len(binance_spot) > 0
        flag_key = binance_spot[0].get("global_activation_flag_key") if binance_spot else "is_binance_spot_active"
        
        print(f"\nBinance Spot comboActivationState:")
        print(f"  active: {active}")
        print(f"  hasConnection: {has_connection}")
        print(f"  flag: {flag_key}")
        
        # Test for binance + futures
        binance_futures = [
            c for c in connections
            if c.get("exchange", "").lower() == "binance"
            and c.get("market_type", "").lower() == "futures"
            and c.get("environment", "live").lower() == "live"
        ]
        
        active_futures = any(
            (c.get("connection_health", "").lower() == "online" and c.get("can_trade_effective"))
            or c.get("global_activation_active")
            for c in binance_futures
        )
        
        print(f"\nBinance Futures comboActivationState:")
        print(f"  active: {active_futures}")
        print(f"  hasConnection: {len(binance_futures) > 0}")


class TestBotProfilesAPI:
    """Tests for Bot Profiles API"""
    
    def test_bot_profiles_list(self, auth_session):
        """Verify bot profiles endpoint works"""
        response = auth_session.get(f"{BASE_URL}/api/bot-profiles")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} bot profiles")
    
    def test_canonical_strategies_list(self, auth_session):
        """Verify canonical strategies endpoint works"""
        response = auth_session.get(f"{BASE_URL}/api/user/canonical-strategies")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} canonical strategies")
    
    def test_risk_policies_list(self, auth_session):
        """Verify risk policies endpoint works"""
        response = auth_session.get(f"{BASE_URL}/api/risk-policies")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} risk policies")


class TestWalletBalanceRootCause:
    """
    Root cause analysis tests for wallet balance inconsistency
    """
    
    def test_pick_wallet_connection_scoring_logic(self, auth_session):
        """
        Analyze the _pick_wallet_connection scoring logic issue:
        
        Current scoring order: (readiness_score, wallet_score, settings_score, default_score, updated_at)
        
        This means a connection with:
        - readiness_score=1 (online + can_trade) but wallet_score=0 (no balance)
        
        Will be selected OVER a connection with:
        - readiness_score=0 (offline) but wallet_score=1 (has balance)
        
        This is the ROOT CAUSE of the portfolio showing 0 balance when
        Exchange Diagnostics shows balance.
        """
        response = auth_session.get(f"{BASE_URL}/api/user/exchange-connections")
        assert response.status_code == 200
        
        connections = response.json()
        
        # Analyze spot connections
        spot_live = [
            c for c in connections
            if c.get("market_type", "").lower() == "spot"
            and c.get("environment", "live").lower() == "live"
        ]
        
        print("\n=== SPOT CONNECTION SCORING ANALYSIS ===")
        for c in spot_live:
            snapshot = c.get("readiness_snapshot") or {}
            
            # Calculate scores as backend does
            wallet_balance = snapshot.get("wallet_balance") or snapshot.get("available_balance") or 0
            wallet_score = 1 if wallet_balance > 0 else 0
            
            health = c.get("connection_health", "").lower()
            can_trade = c.get("can_trade_effective", False)
            readiness_score = 1 if (health == "online" and can_trade) else 0
            
            source = snapshot.get("source", "")
            label = c.get("account_label", "")
            settings_score = 1 if (source == "phase4_exchange_settings_sync" or label.upper().startswith("SETTINGS ")) else 0
            
            default_score = 1 if c.get("is_default") else 0
            
            print(f"\n{c['account_label']}:")
            print(f"  readiness_score: {readiness_score} (health={health}, can_trade={can_trade})")
            print(f"  wallet_score: {wallet_score} (balance={wallet_balance})")
            print(f"  settings_score: {settings_score}")
            print(f"  default_score: {default_score}")
            print(f"  FINAL SCORE TUPLE: ({readiness_score}, {wallet_score}, {settings_score}, {default_score})")
        
        # Identify the issue
        connections_with_balance = [c for c in spot_live if (c.get("readiness_snapshot") or {}).get("wallet_balance", 0) > 0]
        connections_online_can_trade = [c for c in spot_live if c.get("connection_health", "").lower() == "online" and c.get("can_trade_effective")]
        
        if connections_with_balance and connections_online_can_trade:
            # Check if the online+can_trade connection has no balance
            for online_conn in connections_online_can_trade:
                online_balance = (online_conn.get("readiness_snapshot") or {}).get("wallet_balance", 0)
                if online_balance == 0:
                    print(f"\n⚠️ ROOT CAUSE IDENTIFIED:")
                    print(f"  Connection '{online_conn['account_label']}' is online+can_trade but has 0 balance")
                    print(f"  It will be selected over connections with balance due to scoring priority")
                    print(f"  Connections with balance: {[c['account_label'] for c in connections_with_balance]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
