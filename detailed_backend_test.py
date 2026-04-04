#!/usr/bin/env python3
"""
Detailed Backend API Testing for Turkish Review Request
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

def test_detailed_backend():
    """Detailed test with full response data"""
    base_url = "https://trade-trace-engine.preview.emergentagent.com"
    
    # Login first
    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json',
        'User-Agent': 'Backend-Tester/1.0'
    })
    
    print("=== DETAILED BACKEND TEST ===")
    print(f"Base URL: {base_url}")
    print()
    
    # Step 1: Login
    print("1) User Login...")
    login_url = f"{base_url}/api/auth/login"
    login_payload = {
        "email": "review.user@platform.local",
        "password": "ReviewUser123!",
        "panel": "user"
    }
    
    try:
        login_response = session.post(login_url, json=login_payload, timeout=30)
        print(f"   Status: {login_response.status_code}")
        
        if login_response.status_code == 200:
            login_data = login_response.json()
            token = login_data.get('access_token')
            if token:
                session.headers['Authorization'] = f'Bearer {token}'
                print(f"   Token length: {len(token)}")
                print("   ✓ Login successful")
            else:
                print("   ✗ No access_token in response")
                return
        else:
            print(f"   ✗ Login failed: {login_response.text}")
            return
    except Exception as e:
        print(f"   ✗ Login error: {e}")
        return
    
    print()
    
    # Step 2: Portfolio Test
    print("2) Portfolio Wallet Fields Test...")
    portfolio_url = f"{base_url}/api/user/portfolio"
    
    try:
        portfolio_response = session.get(portfolio_url, timeout=30)
        print(f"   Status: {portfolio_response.status_code}")
        
        if portfolio_response.status_code == 200:
            portfolio_data = portfolio_response.json()
            print(f"   Response keys: {list(portfolio_data.keys())}")
            
            # Check wallet fields
            wallet_fields = ['total_wallet_balance', 'spot_wallet_balance', 'futures_wallet_balance']
            found_fields = {}
            
            for field in wallet_fields:
                if field in portfolio_data:
                    found_fields[field] = portfolio_data[field]
                    print(f"   ✓ {field}: {portfolio_data[field]}")
                else:
                    print(f"   ✗ {field}: NOT FOUND")
            
            print(f"   Found {len(found_fields)}/3 required wallet fields")
        else:
            print(f"   ✗ Portfolio failed: {portfolio_response.text}")
    except Exception as e:
        print(f"   ✗ Portfolio error: {e}")
    
    print()
    
    # Step 3: Exchange Connections Test
    print("3) Exchange Connections Test...")
    connections_url = f"{base_url}/api/user/exchange-connections"
    
    try:
        connections_response = session.get(connections_url, timeout=30)
        print(f"   Status: {connections_response.status_code}")
        
        if connections_response.status_code == 200:
            connections_data = connections_response.json()
            connections = connections_data if isinstance(connections_data, list) else connections_data.get('connections', [])
            
            print(f"   Total connections: {len(connections)}")
            
            live_connections = []
            spot_live = False
            futures_live = False
            binance_live = False
            
            for i, conn in enumerate(connections):
                if isinstance(conn, dict):
                    venue = conn.get('venue', '')
                    market_type = conn.get('market_type', '')
                    environment = conn.get('environment', '')
                    label = conn.get('label', '')
                    is_active = conn.get('is_active', False)
                    
                    print(f"   Connection {i+1}: venue={venue}, market_type={market_type}, env={environment}, label={label}, active={is_active}")
                    
                    # Check if it's live
                    is_live = 'live' in venue.lower() or environment == 'live'
                    
                    if is_live:
                        live_connections.append(conn)
                        
                        if 'spot' in market_type.lower():
                            spot_live = True
                        elif 'futures' in market_type.lower():
                            futures_live = True
                        
                        if 'binance' in venue.lower():
                            binance_live = True
            
            print(f"   Live connections found: {len(live_connections)}")
            print(f"   Spot live available: {spot_live}")
            print(f"   Futures live available: {futures_live}")
            print(f"   Binance live available: {binance_live}")
            
        else:
            print(f"   ✗ Connections failed: {connections_response.text}")
    except Exception as e:
        print(f"   ✗ Connections error: {e}")
    
    print()
    
    # Step 4: Bot Profiles Test (for filter logic)
    print("4) Bot Profiles Test (for filter logic)...")
    bot_profiles_url = f"{base_url}/api/bot-profiles"
    
    try:
        bot_response = session.get(bot_profiles_url, timeout=30)
        print(f"   Status: {bot_response.status_code}")
        
        if bot_response.status_code == 200:
            bot_data = bot_response.json()
            print(f"   Response type: {type(bot_data)}")
            
            if isinstance(bot_data, list):
                print(f"   Bot profiles count: {len(bot_data)}")
                if len(bot_data) > 0:
                    sample_bot = bot_data[0]
                    print(f"   Sample bot keys: {list(sample_bot.keys())}")
                    
                    # Look for exchange connection info
                    if 'selected_exchange_connection_id' in sample_bot:
                        print(f"   ✓ selected_exchange_connection_id found")
                    if 'selected_exchange_connection_label' in sample_bot:
                        print(f"   ✓ selected_exchange_connection_label found")
            elif isinstance(bot_data, dict):
                print(f"   Bot data keys: {list(bot_data.keys())}")
        else:
            print(f"   ✗ Bot profiles failed: {bot_response.text}")
    except Exception as e:
        print(f"   ✗ Bot profiles error: {e}")

if __name__ == "__main__":
    test_detailed_backend()