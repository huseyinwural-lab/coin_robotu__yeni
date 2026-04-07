#!/usr/bin/env python3
"""
Release Gate Investigation Test - Full Response Analysis
"""

import requests
import json
import time
from datetime import datetime

# Test configuration
PREVIEW_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def log_test(message):
    """Log test messages with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def test_admin_login():
    """Test admin login and get session cookies"""
    log_test("=== TESTING ADMIN LOGIN ===")
    
    login_url = f"{PREVIEW_URL}/api/auth/login/admin"
    login_data = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    try:
        response = requests.post(login_url, json=login_data, timeout=30)
        log_test(f"Admin login status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token', '')
            device_id = data.get('device_id', '')
            log_test(f"Login successful - Token length: {len(token)}")
            log_test(f"Device ID: {device_id}")
            
            # Get session cookies
            cookies = response.cookies
            device_cookie = cookies.get('device_id', '')
            log_test(f"Device cookie: {device_cookie}")
            
            return {
                'token': token,
                'device_id': device_id,
                'device_cookie': device_cookie,
                'cookies': cookies,
                'headers': {
                    'Authorization': f'Bearer {token}',
                    'X-Session-Device': device_cookie,  # Use cookie device ID
                    'Content-Type': 'application/json'
                }
            }
        else:
            log_test(f"Login failed: {response.text}")
            return None
            
    except Exception as e:
        log_test(f"Login error: {str(e)}")
        return None

def test_full_response_analysis(auth_data):
    """Get full response data from both endpoints"""
    log_test("=== FULL RESPONSE ANALYSIS ===")
    
    # Test remediate config endpoint
    url1 = f"{PREVIEW_URL}/api/admin/system/remediate-config"
    
    try:
        response1 = requests.get(
            url1, 
            headers=auth_data['headers'],
            cookies=auth_data['cookies'],
            timeout=30
        )
        
        log_test(f"Remediate config status: {response1.status_code}")
        
        if response1.status_code == 200:
            data1 = response1.json()
            log_test("FULL Remediate config response:")
            log_test(json.dumps(data1, indent=2))
        else:
            log_test(f"Remediate config failed: {response1.text}")
            
    except Exception as e:
        log_test(f"Remediate config error: {str(e)}")
    
    # Test production gate endpoint
    url2 = f"{PREVIEW_URL}/api/phase4/admin/production-gate?refresh_checks=true"
    
    try:
        response2 = requests.get(
            url2, 
            headers=auth_data['headers'],
            cookies=auth_data['cookies'],
            timeout=30
        )
        
        log_test(f"Production gate status: {response2.status_code}")
        
        if response2.status_code == 200:
            data2 = response2.json()
            log_test("FULL Production gate response:")
            log_test(json.dumps(data2, indent=2))
        else:
            log_test(f"Production gate failed: {response2.text}")
            
    except Exception as e:
        log_test(f"Production gate error: {str(e)}")

def test_browser_simulation():
    """Simulate browser request with all headers"""
    log_test("=== BROWSER SIMULATION TEST ===")
    
    auth_data = test_admin_login()
    if not auth_data:
        log_test("Cannot simulate browser - login failed")
        return
    
    # Browser-like headers
    browser_headers = {
        'Authorization': f'Bearer {auth_data["token"]}',
        'X-Session-Device': auth_data['device_cookie'],
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': f'{PREVIEW_URL}/admin/dashboard',
        'Origin': PREVIEW_URL
    }
    
    url = f"{PREVIEW_URL}/api/admin/system/remediate-config"
    
    try:
        response = requests.get(
            url, 
            headers=browser_headers,
            cookies=auth_data['cookies'],
            timeout=30
        )
        
        log_test(f"Browser simulation status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            log_test("Browser simulation response:")
            log_test(json.dumps(data, indent=2))
        else:
            log_test(f"Browser simulation failed: {response.text}")
            
    except Exception as e:
        log_test(f"Browser simulation error: {str(e)}")

def main():
    """Main test execution"""
    log_test("Starting Full Release Gate Analysis")
    log_test(f"Target URL: {PREVIEW_URL}")
    log_test(f"Admin credentials: {ADMIN_EMAIL}")
    
    # Test 1: Admin login and get session data
    auth_data = test_admin_login()
    if not auth_data:
        log_test("CRITICAL: Admin login failed - cannot proceed with tests")
        return
    
    # Test 2: Get full response data
    test_full_response_analysis(auth_data)
    
    # Test 3: Browser simulation
    test_browser_simulation()
    
    log_test("Full Release Gate Analysis completed")

if __name__ == "__main__":
    main()