#!/usr/bin/env python3
"""
Strategy Allocation Frontend Validation Test

This test validates the Strategy Allocation frontend changes per Turkish review request:

Frontend requirements:
- /admin/strategy-allocation page should NOT show 'Strategy Ekle' panel
- State options should only be AKTİF/PASİF 
- Action column should only have Düzenle + Kaydet
- Row inputs should be disabled until Düzenle is clicked

Test credentials:
- Admin: canary.admin@platform.local / CanaryAdmin123!
- Test URL: https://trade-trace-engine.preview.emergentagent.com
"""

import time
import json
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def setup_driver():
    """Setup Chrome driver with appropriate options"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(10)
    return driver

def test_strategy_allocation_frontend():
    """Test frontend Strategy Allocation page"""
    
    base_url = "https://trade-trace-engine.preview.emergentagent.com"
    admin_email = "canary.admin@platform.local"
    admin_password = "CanaryAdmin123!"
    
    print("=== STRATEGY ALLOCATION FRONTEND VALIDATION ===")
    print(f"Base URL: {base_url}")
    print(f"Admin: {admin_email}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    test_results = {
        "overall_result": "UNKNOWN",
        "tests_passed": 0,
        "tests_total": 0,
        "detailed_results": [],
        "timestamp": datetime.now().isoformat()
    }
    
    driver = None
    
    try:
        driver = setup_driver()
        wait = WebDriverWait(driver, 30)
        
        # Test 1: Admin Login
        print("TEST 1: Admin Login")
        test_results["tests_total"] += 1
        
        driver.get(f"{base_url}/admin/login")
        
        # Fill login form
        email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='email']")))
        password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password'], input[name='password']")
        
        email_input.clear()
        email_input.send_keys(admin_email)
        password_input.clear()
        password_input.send_keys(admin_password)
        
        # Submit login
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button:contains('Giriş'), button:contains('Login')")
        login_button.click()
        
        # Wait for redirect to admin dashboard
        try:
            wait.until(lambda driver: "/admin/dashboard" in driver.current_url or "/admin/" in driver.current_url)
            print(f"✅ PASS - Admin login successful. Current URL: {driver.current_url}")
            test_results["tests_passed"] += 1
            test_results["detailed_results"].append({
                "test": "Admin Login",
                "status": "PASS",
                "details": f"Login successful, redirected to: {driver.current_url}"
            })
        except TimeoutException:
            print(f"❌ FAIL - Login redirect timeout. Current URL: {driver.current_url}")
            test_results["detailed_results"].append({
                "test": "Admin Login",
                "status": "FAIL",
                "details": f"Login redirect timeout. Current URL: {driver.current_url}"
            })
            return test_results
            
        print()
        
        # Test 2: Navigate to Strategy Allocation page
        print("TEST 2: Navigate to Strategy Allocation")
        test_results["tests_total"] += 1
        
        driver.get(f"{base_url}/admin/strategy-allocation")
        
        try:
            # Wait for page to load
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)  # Additional wait for dynamic content
            
            page_title = driver.title
            current_url = driver.current_url
            
            if "/admin/strategy-allocation" in current_url:
                print(f"✅ PASS - Successfully navigated to Strategy Allocation page")
                print(f"Page title: {page_title}")
                test_results["tests_passed"] += 1
                test_results["detailed_results"].append({
                    "test": "Navigate to Strategy Allocation",
                    "status": "PASS",
                    "details": f"Page loaded successfully. Title: {page_title}"
                })
            else:
                print(f"❌ FAIL - Wrong page loaded. Current URL: {current_url}")
                test_results["detailed_results"].append({
                    "test": "Navigate to Strategy Allocation",
                    "status": "FAIL",
                    "details": f"Wrong page loaded. Current URL: {current_url}"
                })
                return test_results
                
        except TimeoutException:
            print(f"❌ FAIL - Page load timeout")
            test_results["detailed_results"].append({
                "test": "Navigate to Strategy Allocation",
                "status": "FAIL",
                "details": "Page load timeout"
            })
            return test_results
            
        print()
        
        # Test 3: Verify NO 'Strategy Ekle' panel
        print("TEST 3: Verify NO 'Strategy Ekle' Panel")
        test_results["tests_total"] += 1
        
        try:
            # Look for various possible selectors for "Strategy Ekle" panel
            strategy_add_selectors = [
                "[data-testid*='strategy-add']",
                "[data-testid*='add-strategy']", 
                "button:contains('Strategy Ekle')",
                "button:contains('Ekle')",
                ".strategy-add-panel",
                ".add-strategy-panel",
                "*:contains('Strategy Ekle')",
                "*:contains('Yeni Strategy')"
            ]
            
            add_panel_found = False
            found_elements = []
            
            for selector in strategy_add_selectors:
                try:
                    if ":contains(" in selector:
                        # Use XPath for text content search
                        text_content = selector.split(':contains(')[1].split(')')[0].strip("'")
                        xpath_selector = f"//*[contains(text(), '{text_content}')]"
                        elements = driver.find_elements(By.XPATH, xpath_selector)
                    else:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    if elements:
                        for elem in elements:
                            if elem.is_displayed():
                                add_panel_found = True
                                found_elements.append(f"{selector}: {elem.text[:50]}")
                except:
                    continue
            
            if not add_panel_found:
                print(f"✅ PASS - NO 'Strategy Ekle' panel found (as required)")
                test_results["tests_passed"] += 1
                test_results["detailed_results"].append({
                    "test": "NO Strategy Ekle Panel",
                    "status": "PASS",
                    "details": "No 'Strategy Ekle' panel found on page (requirement met)"
                })
            else:
                print(f"❌ FAIL - 'Strategy Ekle' panel found: {found_elements}")
                test_results["detailed_results"].append({
                    "test": "NO Strategy Ekle Panel",
                    "status": "FAIL",
                    "details": f"Strategy Ekle panel found: {found_elements}"
                })
                
        except Exception as e:
            print(f"❌ FAIL - Error checking for Strategy Ekle panel: {str(e)}")
            test_results["detailed_results"].append({
                "test": "NO Strategy Ekle Panel",
                "status": "FAIL",
                "details": f"Error checking for panel: {str(e)}"
            })
            
        print()
        
        # Test 4: Verify State Options (AKTİF/PASİF only)
        print("TEST 4: Verify State Options (AKTİF/PASİF only)")
        test_results["tests_total"] += 1
        
        try:
            # Look for state dropdowns or select elements
            state_selectors = [
                "select[data-testid*='state']",
                "select[name*='state']",
                ".state-select",
                "select:contains('AKTİF')",
                "select:contains('PASİF')"
            ]
            
            state_options_valid = True
            invalid_options = []
            valid_options_found = []
            
            for selector in state_selectors:
                try:
                    if ":contains(" in selector:
                        # Skip contains selectors for now
                        continue
                    
                    state_selects = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for select_elem in state_selects:
                        if select_elem.is_displayed():
                            options = select_elem.find_elements(By.TAG_NAME, "option")
                            option_texts = [opt.text.strip() for opt in options if opt.text.strip()]
                            
                            valid_options_found.extend(option_texts)
                            
                            # Check if options are only AKTİF/PASİF (or ACTIVE/DISABLED)
                            allowed_options = {"AKTİF", "PASİF", "ACTIVE", "DISABLED", ""}
                            for option_text in option_texts:
                                if option_text and option_text not in allowed_options:
                                    invalid_options.append(option_text)
                                    state_options_valid = False
                                    
                except Exception as e:
                    continue
            
            if valid_options_found:
                if state_options_valid:
                    print(f"✅ PASS - State options are valid: {set(valid_options_found)}")
                    test_results["tests_passed"] += 1
                    test_results["detailed_results"].append({
                        "test": "State Options Validation",
                        "status": "PASS",
                        "details": f"Valid state options found: {set(valid_options_found)}"
                    })
                else:
                    print(f"❌ FAIL - Invalid state options found: {invalid_options}")
                    test_results["detailed_results"].append({
                        "test": "State Options Validation",
                        "status": "FAIL",
                        "details": f"Invalid state options: {invalid_options}"
                    })
            else:
                print(f"⚠️ WARNING - No state select elements found")
                test_results["detailed_results"].append({
                    "test": "State Options Validation",
                    "status": "WARNING",
                    "details": "No state select elements found on page"
                })
                
        except Exception as e:
            print(f"❌ FAIL - Error checking state options: {str(e)}")
            test_results["detailed_results"].append({
                "test": "State Options Validation",
                "status": "FAIL",
                "details": f"Error checking state options: {str(e)}"
            })
            
        print()
        
        # Test 5: Verify Action Column (Düzenle + Kaydet only)
        print("TEST 5: Verify Action Column (Düzenle + Kaydet only)")
        test_results["tests_total"] += 1
        
        try:
            # Look for action buttons
            action_button_selectors = [
                "button[data-testid*='edit']",
                "button[data-testid*='save']",
                "button:contains('Düzenle')",
                "button:contains('Kaydet')",
                "button:contains('Edit')",
                "button:contains('Save')",
                ".action-button",
                "td button",  # Buttons in table cells
                ".table button"
            ]
            
            action_buttons_found = []
            invalid_actions = []
            
            for selector in action_button_selectors:
                try:
                    if ":contains(" in selector:
                        # Use XPath for text content search
                        text_to_find = selector.split(':contains(')[1].split(')')[0].strip("'")
                        xpath_selector = f"//button[contains(text(), '{text_to_find}')]"
                        buttons = driver.find_elements(By.XPATH, xpath_selector)
                    else:
                        buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for button in buttons:
                        if button.is_displayed():
                            button_text = button.text.strip()
                            if button_text:
                                action_buttons_found.append(button_text)
                                
                                # Check if button text is allowed
                                allowed_actions = {"Düzenle", "Kaydet", "Edit", "Save"}
                                if button_text not in allowed_actions:
                                    invalid_actions.append(button_text)
                                    
                except Exception as e:
                    continue
            
            if action_buttons_found:
                unique_actions = set(action_buttons_found)
                if not invalid_actions:
                    print(f"✅ PASS - Action buttons are valid: {unique_actions}")
                    test_results["tests_passed"] += 1
                    test_results["detailed_results"].append({
                        "test": "Action Column Validation",
                        "status": "PASS",
                        "details": f"Valid action buttons found: {unique_actions}"
                    })
                else:
                    print(f"❌ FAIL - Invalid action buttons found: {set(invalid_actions)}")
                    test_results["detailed_results"].append({
                        "test": "Action Column Validation",
                        "status": "FAIL",
                        "details": f"Invalid action buttons: {set(invalid_actions)}"
                    })
            else:
                print(f"⚠️ WARNING - No action buttons found")
                test_results["detailed_results"].append({
                    "test": "Action Column Validation",
                    "status": "WARNING",
                    "details": "No action buttons found on page"
                })
                
        except Exception as e:
            print(f"❌ FAIL - Error checking action buttons: {str(e)}")
            test_results["detailed_results"].append({
                "test": "Action Column Validation",
                "status": "FAIL",
                "details": f"Error checking action buttons: {str(e)}"
            })
            
        print()
        
        # Test 6: Verify Row Inputs Disabled Until Edit
        print("TEST 6: Verify Row Inputs Disabled Until Edit")
        test_results["tests_total"] += 1
        
        try:
            # Look for input elements in table rows
            input_selectors = [
                "table input",
                "tr input",
                "td input",
                ".table input",
                "input[data-testid*='strategy']"
            ]
            
            disabled_inputs = []
            enabled_inputs = []
            
            for selector in input_selectors:
                try:
                    inputs = driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for input_elem in inputs:
                        if input_elem.is_displayed():
                            if input_elem.get_attribute("disabled") or input_elem.get_attribute("readonly"):
                                disabled_inputs.append(input_elem.get_attribute("name") or input_elem.get_attribute("data-testid") or "unnamed")
                            else:
                                enabled_inputs.append(input_elem.get_attribute("name") or input_elem.get_attribute("data-testid") or "unnamed")
                                
                except Exception as e:
                    continue
            
            if disabled_inputs or enabled_inputs:
                if len(disabled_inputs) > 0 and len(enabled_inputs) == 0:
                    print(f"✅ PASS - All row inputs are disabled: {disabled_inputs}")
                    test_results["tests_passed"] += 1
                    test_results["detailed_results"].append({
                        "test": "Row Inputs Disabled",
                        "status": "PASS",
                        "details": f"All inputs disabled: {disabled_inputs}"
                    })
                elif len(enabled_inputs) > 0:
                    print(f"⚠️ WARNING - Some inputs are enabled: {enabled_inputs}")
                    test_results["detailed_results"].append({
                        "test": "Row Inputs Disabled",
                        "status": "WARNING",
                        "details": f"Enabled inputs found: {enabled_inputs}, Disabled: {disabled_inputs}"
                    })
                else:
                    print(f"⚠️ WARNING - No inputs found to check")
                    test_results["detailed_results"].append({
                        "test": "Row Inputs Disabled",
                        "status": "WARNING",
                        "details": "No input elements found on page"
                    })
            else:
                print(f"⚠️ WARNING - No input elements found")
                test_results["detailed_results"].append({
                    "test": "Row Inputs Disabled",
                    "status": "WARNING",
                    "details": "No input elements found on page"
                })
                
        except Exception as e:
            print(f"❌ FAIL - Error checking input states: {str(e)}")
            test_results["detailed_results"].append({
                "test": "Row Inputs Disabled",
                "status": "FAIL",
                "details": f"Error checking input states: {str(e)}"
            })
            
        print()
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {str(e)}")
        test_results["detailed_results"].append({
            "test": "Frontend Test Execution",
            "status": "ERROR",
            "details": f"Critical error: {str(e)}"
        })
        
    finally:
        if driver:
            driver.quit()
    
    # Calculate overall result
    if test_results["tests_passed"] == test_results["tests_total"]:
        test_results["overall_result"] = "PASS"
    elif test_results["tests_passed"] > 0:
        test_results["overall_result"] = "PARTIAL_PASS"
    else:
        test_results["overall_result"] = "FAIL"
        
    print("=== FRONTEND TEST SUMMARY ===")
    print(f"Overall Result: {test_results['overall_result']}")
    print(f"Tests Passed: {test_results['tests_passed']}/{test_results['tests_total']}")
    print(f"Success Rate: {(test_results['tests_passed']/test_results['tests_total']*100):.1f}%")
    
    return test_results

if __name__ == "__main__":
    results = test_strategy_allocation_frontend()
    
    # Save results to file
    with open('/app/strategy_allocation_frontend_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Exit with appropriate code
    if results["overall_result"] == "PASS":
        sys.exit(0)
    else:
        sys.exit(1)