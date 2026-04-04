#!/usr/bin/env python3
"""
Test Local Backend
"""

import requests
import json

def test_local_backend():
    """Test local backend"""
    base_url = "http://127.0.0.1:8001"
    
    # Login first
    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json',
        'User-Agent': 'Backend-Tester/1.0'
    })
    
    print("=== LOCAL BACKEND TEST ===")
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
    
    # Step 2: Exchange Connections Test
    print("2) Exchange Connections Test...")
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

if __name__ == "__main__":
    test_local_backend()