#!/usr/bin/env python3
"""
Browser UI vs API Response Comparison Test
Testing the discrepancy between UI showing blockage and API showing PASS
"""

import requests
import json
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Test configuration
PREVIEW_URL = "https://trade-trace-engine.preview.emergentagent.com"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"

def log_test(message):
    """Log test messages with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def setup_browser():
    """Setup Chrome browser with options"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        log_test(f"Browser setup failed: {str(e)}")
        return None

def test_ui_admin_login_and_remediation(driver):
    """Test admin login and access remediation modal"""
    log_test("=== TESTING UI ADMIN LOGIN AND REMEDIATION ===")
    
    try:
        # Navigate to admin login
        driver.get(f"{PREVIEW_URL}/admin/login")
        log_test("Navigated to admin login page")
        
        # Wait for login form
        wait = WebDriverWait(driver, 30)
        email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
        password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        
        # Fill credentials
        email_field.clear()
        email_field.send_keys(ADMIN_EMAIL)
        password_field.clear()
        password_field.send_keys(ADMIN_PASSWORD)
        
        # Submit login
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()
        
        # Wait for redirect to dashboard
        wait.until(lambda d: "/admin/dashboard" in d.current_url or "/admin/" in d.current_url)
        log_test(f"Login successful - Current URL: {driver.current_url}")
        
        # Navigate to execution readiness page (where remediation modal would be)
        driver.get(f"{PREVIEW_URL}/admin/execution-readiness")
        time.sleep(3)
        
        # Look for release gate status elements
        try:
            # Look for any elements containing "final_release_gate" or "NO_GO"
            page_source = driver.page_source.lower()
            
            if "final_release_gate_no_go" in page_source:
                log_test("❌ FOUND: 'final_release_gate_no_go' text in UI")
            else:
                log_test("✅ NOT FOUND: 'final_release_gate_no_go' text in UI")
            
            if "no_go" in page_source:
                log_test("❌ FOUND: 'no_go' text in UI")
            else:
                log_test("✅ NOT FOUND: 'no_go' text in UI")
            
            # Look for specific release gate elements
            release_gate_elements = driver.find_elements(By.CSS_SELECTOR, "[data-testid*='release-gate'], [data-testid*='final-release'], [class*='release-gate'], [class*='final-release']")
            
            if release_gate_elements:
                log_test(f"Found {len(release_gate_elements)} release gate related elements:")
                for i, element in enumerate(release_gate_elements[:5]):  # Show first 5
                    try:
                        text = element.text.strip()
                        tag = element.tag_name
                        classes = element.get_attribute("class")
                        testid = element.get_attribute("data-testid")
                        log_test(f"  Element {i+1}: <{tag}> class='{classes}' data-testid='{testid}' text='{text[:100]}'")
                    except:
                        log_test(f"  Element {i+1}: Could not read element details")
            else:
                log_test("No release gate related elements found")
            
            # Get browser cookies for comparison
            cookies = driver.get_cookies()
            log_test(f"Browser cookies: {len(cookies)} cookies found")
            for cookie in cookies:
                if 'device_id' in cookie['name'] or 'session' in cookie['name'].lower():
                    log_test(f"  {cookie['name']}: {cookie['value'][:20]}...")
            
            return True
            
        except Exception as e:
            log_test(f"Error checking UI elements: {str(e)}")
            return False
            
    except Exception as e:
        log_test(f"UI test failed: {str(e)}")
        return False

def test_api_with_browser_session(driver):
    """Test API endpoints using browser session cookies"""
    log_test("=== TESTING API WITH BROWSER SESSION ===")
    
    try:
        # Get cookies from browser
        browser_cookies = driver.get_cookies()
        cookies_dict = {cookie['name']: cookie['value'] for cookie in browser_cookies}
        
        # Get authorization token from localStorage or sessionStorage
        token = driver.execute_script("return localStorage.getItem('access_token') || sessionStorage.getItem('access_token')")
        
        if not token:
            # Try to get token from cookies or other storage
            log_test("No token found in localStorage/sessionStorage, checking other sources...")
            return False
        
        log_test(f"Found token in browser storage: {len(token)} characters")
        
        # Test remediate config endpoint with browser session
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': f'{PREVIEW_URL}/admin/execution-readiness'
        }
        
        # Add device ID if available
        device_id = cookies_dict.get('device_id')
        if device_id:
            headers['X-Session-Device'] = device_id
        
        url = f"{PREVIEW_URL}/api/admin/system/remediate-config"
        
        response = requests.get(url, headers=headers, cookies=cookies_dict, timeout=30)
        
        log_test(f"API response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            log_test("API Response (Browser Session):")
            log_test(f"  final_release_gate_decision: {data.get('final_release_gate_decision', 'NOT_FOUND')}")
            log_test(f"  release_gate_status: {data.get('release_gate_status', 'NOT_FOUND')}")
            
            # Check if there's a discrepancy
            final_decision = data.get('final_release_gate_decision', '')
            release_status = data.get('release_gate_status', '')
            
            if final_decision == 'NO_GO' and release_status == 'PASS':
                log_test("🔍 DISCREPANCY DETECTED: final_release_gate_decision=NO_GO but release_gate_status=PASS")
            
            return data
        else:
            log_test(f"API failed: {response.text}")
            return None
            
    except Exception as e:
        log_test(f"API test with browser session failed: {str(e)}")
        return None

def test_production_gate_ui_vs_api(driver):
    """Test production gate page UI vs API"""
    log_test("=== TESTING PRODUCTION GATE UI VS API ===")
    
    try:
        # Navigate to production gate page
        driver.get(f"{PREVIEW_URL}/admin/phase4-live")
        time.sleep(3)
        
        # Check UI for blockage messages
        page_source = driver.page_source.lower()
        
        ui_shows_blocked = False
        if "blocked" in page_source or "no_go" in page_source or "fail" in page_source:
            ui_shows_blocked = True
            log_test("❌ UI shows blockage indicators")
        else:
            log_test("✅ UI does not show blockage indicators")
        
        # Get API response for comparison
        browser_cookies = driver.get_cookies()
        cookies_dict = {cookie['name']: cookie['value'] for cookie in browser_cookies}
        
        token = driver.execute_script("return localStorage.getItem('access_token') || sessionStorage.getItem('access_token')")
        
        if token:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            device_id = cookies_dict.get('device_id')
            if device_id:
                headers['X-Session-Device'] = device_id
            
            url = f"{PREVIEW_URL}/api/phase4/admin/production-gate?refresh_checks=true"
            response = requests.get(url, headers=headers, cookies=cookies_dict, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                api_deploy_allowed = data.get('deploy_allowed', False)
                api_effective_state = data.get('effective_state', '')
                
                log_test(f"API Response: deploy_allowed={api_deploy_allowed}, effective_state={api_effective_state}")
                
                # Compare UI vs API
                if ui_shows_blocked and api_deploy_allowed:
                    log_test("🔍 MAJOR DISCREPANCY: UI shows blocked but API allows deployment")
                elif not ui_shows_blocked and not api_deploy_allowed:
                    log_test("🔍 MAJOR DISCREPANCY: UI shows OK but API blocks deployment")
                else:
                    log_test("✅ UI and API are consistent")
                
                return {
                    'ui_shows_blocked': ui_shows_blocked,
                    'api_deploy_allowed': api_deploy_allowed,
                    'api_effective_state': api_effective_state
                }
        
        return None
        
    except Exception as e:
        log_test(f"Production gate UI vs API test failed: {str(e)}")
        return None

def main():
    """Main test execution"""
    log_test("Starting Browser UI vs API Comparison Test")
    
    # Setup browser
    driver = setup_browser()
    if not driver:
        log_test("CRITICAL: Browser setup failed - cannot proceed")
        return
    
    try:
        # Test 1: UI admin login and check for remediation modal
        ui_result = test_ui_admin_login_and_remediation(driver)
        
        if ui_result:
            # Test 2: API with browser session
            api_result = test_api_with_browser_session(driver)
            
            # Test 3: Production gate UI vs API
            gate_result = test_production_gate_ui_vs_api(driver)
            
            # Summary
            log_test("=== FINAL ANALYSIS ===")
            log_test("This test compared UI behavior with API responses using the same browser session")
            log_test("Key findings will help identify if the issue is:")
            log_test("1. Frontend caching old responses")
            log_test("2. Different session/cookie handling between UI and direct API calls")
            log_test("3. UI rendering stale data")
            log_test("4. API returning different responses in different contexts")
        
    finally:
        driver.quit()
        log_test("Browser closed")

if __name__ == "__main__":
    main()