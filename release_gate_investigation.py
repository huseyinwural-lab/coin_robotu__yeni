#!/usr/bin/env python3
"""
Release Gate Investigation Test
Testing the discrepancy between backend endpoints showing PASS and UI showing blockage
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
            log_test(f"Session cookies: {dict(cookies)}")
            
            return {
                'token': token,
                'device_id': device_id,
                'cookies': cookies,
                'headers': {
                    'Authorization': f'Bearer {token}',
                    'X-Session-Device': device_id,
                    'Content-Type': 'application/json'
                }
            }
        else:
            log_test(f"Login failed: {response.text}")
            return None
            
    except Exception as e:
        log_test(f"Login error: {str(e)}")
        return None

def test_remediate_config_endpoint(auth_data):
    """Test /api/admin/system/remediate-config endpoint"""
    log_test("=== TESTING REMEDIATE CONFIG ENDPOINT ===")
    
    url = f"{PREVIEW_URL}/api/admin/system/remediate-config"
    
    try:
        # Test with session cookies and headers
        response = requests.get(
            url, 
            headers=auth_data['headers'],
            cookies=auth_data['cookies'],
            timeout=30
        )
        
        log_test(f"Remediate config status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            log_test("Remediate config response:")
            log_test(f"  release_gate_status: {data.get('release_gate_status', 'NOT_FOUND')}")
            log_test(f"  preflight: {data.get('preflight', 'NOT_FOUND')}")
            log_test(f"  secret: {data.get('secret', 'NOT_FOUND')}")
            log_test(f"  final_decision: {data.get('final_decision', 'NOT_FOUND')}")
            log_test(f"  reason_codes: {data.get('reason_codes', 'NOT_FOUND')}")
            
            return data
        else:
            log_test(f"Remediate config failed: {response.text}")
            return None
            
    except Exception as e:
        log_test(f"Remediate config error: {str(e)}")
        return None

def test_production_gate_endpoint(auth_data):
    """Test /api/phase4/admin/production-gate endpoint"""
    log_test("=== TESTING PRODUCTION GATE ENDPOINT ===")
    
    url = f"{PREVIEW_URL}/api/phase4/admin/production-gate?refresh_checks=true"
    
    try:
        # Test with session cookies and headers
        response = requests.get(
            url, 
            headers=auth_data['headers'],
            cookies=auth_data['cookies'],
            timeout=30
        )
        
        log_test(f"Production gate status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            log_test("Production gate response:")
            log_test(f"  configured: {data.get('configured', 'NOT_FOUND')}")
            log_test(f"  effective: {data.get('effective', 'NOT_FOUND')}")
            log_test(f"  deploy_allowed: {data.get('deploy_allowed', 'NOT_FOUND')}")
            log_test(f"  blocked_reason_codes: {data.get('blocked_reason_codes', 'NOT_FOUND')}")
            
            return data
        else:
            log_test(f"Production gate failed: {response.text}")
            return None
            
    except Exception as e:
        log_test(f"Production gate error: {str(e)}")
        return None

def test_curl_comparison(auth_data):
    """Test same endpoints with curl-like requests (no cookies)"""
    log_test("=== TESTING CURL COMPARISON (NO COOKIES) ===")
    
    # Test remediate config without cookies
    url1 = f"{PREVIEW_URL}/api/admin/system/remediate-config"
    headers_only = {
        'Authorization': f'Bearer {auth_data["token"]}',
        'Content-Type': 'application/json'
    }
    
    try:
        response1 = requests.get(url1, headers=headers_only, timeout=30)
        log_test(f"Remediate config (no cookies) status: {response1.status_code}")
        
        if response1.status_code == 200:
            data1 = response1.json()
            log_test(f"  final_decision (no cookies): {data1.get('final_decision', 'NOT_FOUND')}")
        else:
            log_test(f"  Error: {response1.text}")
    except Exception as e:
        log_test(f"Remediate config (no cookies) error: {str(e)}")
    
    # Test production gate without cookies
    url2 = f"{PREVIEW_URL}/api/phase4/admin/production-gate?refresh_checks=true"
    
    try:
        response2 = requests.get(url2, headers=headers_only, timeout=30)
        log_test(f"Production gate (no cookies) status: {response2.status_code}")
        
        if response2.status_code == 200:
            data2 = response2.json()
            log_test(f"  effective (no cookies): {data2.get('effective', 'NOT_FOUND')}")
        else:
            log_test(f"  Error: {response2.text}")
    except Exception as e:
        log_test(f"Production gate (no cookies) error: {str(e)}")

def test_session_device_mismatch():
    """Test for session/device mismatch issues"""
    log_test("=== TESTING SESSION/DEVICE MISMATCH ===")
    
    # First login to get valid token
    auth_data = test_admin_login()
    if not auth_data:
        log_test("Cannot test session mismatch - login failed")
        return
    
    # Test with wrong device ID
    wrong_headers = {
        'Authorization': f'Bearer {auth_data["token"]}',
        'X-Session-Device': 'wrong_device_id_12345',
        'Content-Type': 'application/json'
    }
    
    url = f"{PREVIEW_URL}/api/admin/system/remediate-config"
    
    try:
        response = requests.get(url, headers=wrong_headers, timeout=30)
        log_test(f"Wrong device ID status: {response.status_code}")
        
        if response.status_code == 401:
            log_test("  Detected session_device_mismatch (401 error)")
        elif response.status_code == 200:
            log_test("  No device ID validation (200 OK)")
        else:
            log_test(f"  Unexpected response: {response.text}")
            
    except Exception as e:
        log_test(f"Session mismatch test error: {str(e)}")

def test_cache_headers():
    """Test for cache-related headers"""
    log_test("=== TESTING CACHE HEADERS ===")
    
    auth_data = test_admin_login()
    if not auth_data:
        log_test("Cannot test cache headers - login failed")
        return
    
    url = f"{PREVIEW_URL}/api/admin/system/remediate-config"
    
    try:
        response = requests.get(
            url, 
            headers=auth_data['headers'],
            cookies=auth_data['cookies'],
            timeout=30
        )
        
        log_test(f"Cache headers test status: {response.status_code}")
        log_test("Response headers:")
        
        cache_headers = ['cache-control', 'etag', 'last-modified', 'expires']
        for header in cache_headers:
            value = response.headers.get(header, 'NOT_FOUND')
            log_test(f"  {header}: {value}")
            
    except Exception as e:
        log_test(f"Cache headers test error: {str(e)}")

def main():
    """Main test execution"""
    log_test("Starting Release Gate Investigation Test")
    log_test(f"Target URL: {PREVIEW_URL}")
    log_test(f"Admin credentials: {ADMIN_EMAIL}")
    
    # Test 1: Admin login and get session data
    auth_data = test_admin_login()
    if not auth_data:
        log_test("CRITICAL: Admin login failed - cannot proceed with tests")
        return
    
    # Test 2: Test remediate config endpoint
    remediate_data = test_remediate_config_endpoint(auth_data)
    
    # Test 3: Test production gate endpoint  
    production_data = test_production_gate_endpoint(auth_data)
    
    # Test 4: Compare with curl-like requests (no cookies)
    test_curl_comparison(auth_data)
    
    # Test 5: Test session/device mismatch
    test_session_device_mismatch()
    
    # Test 6: Test cache headers
    test_cache_headers()
    
    # Summary
    log_test("=== TEST SUMMARY ===")
    if remediate_data:
        log_test(f"Remediate Config - final_decision: {remediate_data.get('final_decision', 'NOT_FOUND')}")
    if production_data:
        log_test(f"Production Gate - effective: {production_data.get('effective', 'NOT_FOUND')}")
    
    log_test("Release Gate Investigation Test completed")

if __name__ == "__main__":
    main()