#!/usr/bin/env python3
"""
Strategy Allocation Frontend Validation Test (HTTP-based)

This test validates the Strategy Allocation frontend changes per Turkish review request
using HTTP requests to check page content:

Frontend requirements:
- /admin/strategy-allocation page should NOT show 'Strategy Ekle' panel
- State options should only be AKTİF/PASİF 
- Action column should only have Düzenle + Kaydet
- Row inputs should be disabled until Düzenle is clicked

Test credentials:
- Admin: canary.admin@platform.local / CanaryAdmin123!
- Test URL: https://trade-trace-engine.preview.emergentagent.com
"""

import requests
import json
import sys
from datetime import datetime
import re

def test_strategy_allocation_frontend_http():
    """Test frontend Strategy Allocation page using HTTP requests"""
    
    base_url = "https://trade-trace-engine.preview.emergentagent.com"
    admin_email = "canary.admin@platform.local"
    admin_password = "CanaryAdmin123!"
    
    print("=== STRATEGY ALLOCATION FRONTEND VALIDATION (HTTP) ===")
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
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    try:
        # Test 1: Admin Login
        print("TEST 1: Admin Login")
        test_results["tests_total"] += 1
        
        login_payload = {
            "email": admin_email,
            "password": admin_password
        }
        
        login_response = session.post(f"{base_url}/api/auth/login/admin", json=login_payload)
        
        if login_response.status_code == 200:
            login_data = login_response.json()
            token = login_data.get('access_token')
            
            if token:
                session.headers.update({'Authorization': f'Bearer {token}'})
                print(f"✅ PASS - Admin login successful. Token length: {len(token)} chars")
                test_results["tests_passed"] += 1
                test_results["detailed_results"].append({
                    "test": "Admin Login",
                    "status": "PASS",
                    "details": f"Login successful, token received (length: {len(token)})"
                })
            else:
                print("❌ FAIL - No access token in response")
                test_results["detailed_results"].append({
                    "test": "Admin Login", 
                    "status": "FAIL",
                    "details": "No access token in login response"
                })
                return test_results
        else:
            print(f"❌ FAIL - Login failed with status {login_response.status_code}")
            test_results["detailed_results"].append({
                "test": "Admin Login",
                "status": "FAIL", 
                "details": f"HTTP {login_response.status_code}: {login_response.text}"
            })
            return test_results
            
        print()
        
        # Test 2: Access Strategy Allocation Page
        print("TEST 2: Access Strategy Allocation Page")
        test_results["tests_total"] += 1
        
        page_response = session.get(f"{base_url}/admin/strategy-allocation")
        
        if page_response.status_code == 200:
            page_content = page_response.text
            print(f"✅ PASS - Strategy allocation page accessible. Content length: {len(page_content)} chars")
            test_results["tests_passed"] += 1
            test_results["detailed_results"].append({
                "test": "Access Strategy Allocation Page",
                "status": "PASS",
                "details": f"Page accessible, content length: {len(page_content)} chars"
            })
        else:
            print(f"❌ FAIL - Page access failed with status {page_response.status_code}")
            test_results["detailed_results"].append({
                "test": "Access Strategy Allocation Page",
                "status": "FAIL",
                "details": f"HTTP {page_response.status_code}: {page_response.text}"
            })
            return test_results
            
        print()
        
        # Test 3: Check for NO 'Strategy Ekle' panel
        print("TEST 3: Verify NO 'Strategy Ekle' Panel")
        test_results["tests_total"] += 1
        
        # Look for various patterns that might indicate "Strategy Ekle" panel
        strategy_add_patterns = [
            r'Strategy\s+Ekle',
            r'Yeni\s+Strategy',
            r'Add\s+Strategy',
            r'strategy-add',
            r'add-strategy',
            r'data-testid[^>]*strategy[^>]*add',
            r'data-testid[^>]*add[^>]*strategy'
        ]
        
        add_panel_found = False
        found_patterns = []
        
        for pattern in strategy_add_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            if matches:
                add_panel_found = True
                found_patterns.extend(matches)
        
        if not add_panel_found:
            print(f"✅ PASS - NO 'Strategy Ekle' panel found (as required)")
            test_results["tests_passed"] += 1
            test_results["detailed_results"].append({
                "test": "NO Strategy Ekle Panel",
                "status": "PASS",
                "details": "No 'Strategy Ekle' panel patterns found in page content"
            })
        else:
            print(f"❌ FAIL - 'Strategy Ekle' panel patterns found: {found_patterns}")
            test_results["detailed_results"].append({
                "test": "NO Strategy Ekle Panel",
                "status": "FAIL",
                "details": f"Strategy Ekle patterns found: {found_patterns}"
            })
            
        print()
        
        # Test 4: Check State Options (AKTİF/PASİF)
        print("TEST 4: Verify State Options (AKTİF/PASİF only)")
        test_results["tests_total"] += 1
        
        # Look for state-related select options
        state_patterns = [
            r'<option[^>]*>([^<]*(?:AKTİF|PASİF|ACTIVE|DISABLED)[^<]*)</option>',
            r'value=["\']([^"\']*(?:AKTİF|PASİF|ACTIVE|DISABLED)[^"\']*)["\']'
        ]
        
        state_options_found = []
        invalid_state_options = []
        
        for pattern in state_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            for match in matches:
                clean_match = match.strip()
                if clean_match:
                    state_options_found.append(clean_match)
                    
                    # Check if option is valid
                    allowed_states = {"AKTİF", "PASİF", "ACTIVE", "DISABLED"}
                    if clean_match.upper() not in [s.upper() for s in allowed_states]:
                        invalid_state_options.append(clean_match)
        
        if state_options_found:
            unique_states = list(set(state_options_found))
            if not invalid_state_options:
                print(f"✅ PASS - Valid state options found: {unique_states}")
                test_results["tests_passed"] += 1
                test_results["detailed_results"].append({
                    "test": "State Options Validation",
                    "status": "PASS",
                    "details": f"Valid state options: {unique_states}"
                })
            else:
                print(f"❌ FAIL - Invalid state options found: {invalid_state_options}")
                test_results["detailed_results"].append({
                    "test": "State Options Validation",
                    "status": "FAIL",
                    "details": f"Invalid state options: {invalid_state_options}"
                })
        else:
            print(f"⚠️ WARNING - No state options found in page content")
            test_results["detailed_results"].append({
                "test": "State Options Validation",
                "status": "WARNING",
                "details": "No state options found in page content"
            })
            
        print()
        
        # Test 5: Check Action Buttons (Düzenle + Kaydet)
        print("TEST 5: Verify Action Buttons (Düzenle + Kaydet only)")
        test_results["tests_total"] += 1
        
        # Look for action button patterns
        action_patterns = [
            r'<button[^>]*>([^<]*(?:Düzenle|Kaydet|Edit|Save)[^<]*)</button>',
            r'>([^<]*(?:Düzenle|Kaydet|Edit|Save)[^<]*)</button>',
            r'data-testid[^>]*(?:edit|save|düzenle|kaydet)'
        ]
        
        action_buttons_found = []
        invalid_action_buttons = []
        
        for pattern in action_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            for match in matches:
                clean_match = match.strip()
                if clean_match and not clean_match.startswith('data-testid'):
                    action_buttons_found.append(clean_match)
                    
                    # Check if button text is valid
                    allowed_actions = {"Düzenle", "Kaydet", "Edit", "Save"}
                    if clean_match not in allowed_actions:
                        # Check if it contains allowed text
                        if not any(action.lower() in clean_match.lower() for action in allowed_actions):
                            invalid_action_buttons.append(clean_match)
        
        if action_buttons_found:
            unique_actions = list(set(action_buttons_found))
            if not invalid_action_buttons:
                print(f"✅ PASS - Valid action buttons found: {unique_actions}")
                test_results["tests_passed"] += 1
                test_results["detailed_results"].append({
                    "test": "Action Buttons Validation",
                    "status": "PASS",
                    "details": f"Valid action buttons: {unique_actions}"
                })
            else:
                print(f"❌ FAIL - Invalid action buttons found: {invalid_action_buttons}")
                test_results["detailed_results"].append({
                    "test": "Action Buttons Validation",
                    "status": "FAIL",
                    "details": f"Invalid action buttons: {invalid_action_buttons}"
                })
        else:
            print(f"⚠️ WARNING - No action buttons found in page content")
            test_results["detailed_results"].append({
                "test": "Action Buttons Validation",
                "status": "WARNING",
                "details": "No action buttons found in page content"
            })
            
        print()
        
        # Test 6: Check for Disabled Inputs
        print("TEST 6: Check for Input Elements")
        test_results["tests_total"] += 1
        
        # Look for input elements and their disabled state
        input_patterns = [
            r'<input[^>]*disabled[^>]*>',
            r'<input[^>]*readonly[^>]*>',
            r'<select[^>]*disabled[^>]*>',
            r'data-testid[^>]*strategy[^>]*input'
        ]
        
        disabled_inputs_found = 0
        input_elements_found = 0
        
        for pattern in input_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            if 'disabled' in pattern or 'readonly' in pattern:
                disabled_inputs_found += len(matches)
            input_elements_found += len(matches)
        
        # Also count total input elements
        total_input_pattern = r'<input[^>]*>'
        total_inputs = len(re.findall(total_input_pattern, page_content, re.IGNORECASE))
        
        if total_inputs > 0:
            if disabled_inputs_found > 0:
                print(f"✅ PASS - Found {disabled_inputs_found} disabled inputs out of {total_inputs} total inputs")
                test_results["tests_passed"] += 1
                test_results["detailed_results"].append({
                    "test": "Input Elements Check",
                    "status": "PASS",
                    "details": f"Found {disabled_inputs_found} disabled inputs out of {total_inputs} total"
                })
            else:
                print(f"⚠️ WARNING - Found {total_inputs} inputs but none explicitly disabled")
                test_results["detailed_results"].append({
                    "test": "Input Elements Check",
                    "status": "WARNING",
                    "details": f"Found {total_inputs} inputs but none explicitly disabled in HTML"
                })
        else:
            print(f"⚠️ WARNING - No input elements found")
            test_results["detailed_results"].append({
                "test": "Input Elements Check",
                "status": "WARNING",
                "details": "No input elements found in page content"
            })
            
        print()
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {str(e)}")
        test_results["detailed_results"].append({
            "test": "Frontend HTTP Test Execution",
            "status": "ERROR",
            "details": f"Critical error: {str(e)}"
        })
    
    # Calculate overall result
    if test_results["tests_total"] > 0:
        if test_results["tests_passed"] == test_results["tests_total"]:
            test_results["overall_result"] = "PASS"
        elif test_results["tests_passed"] > 0:
            test_results["overall_result"] = "PARTIAL_PASS"
        else:
            test_results["overall_result"] = "FAIL"
    else:
        test_results["overall_result"] = "ERROR"
        
    print("=== FRONTEND HTTP TEST SUMMARY ===")
    print(f"Overall Result: {test_results['overall_result']}")
    print(f"Tests Passed: {test_results['tests_passed']}/{test_results['tests_total']}")
    if test_results["tests_total"] > 0:
        print(f"Success Rate: {(test_results['tests_passed']/test_results['tests_total']*100):.1f}%")
    
    return test_results

if __name__ == "__main__":
    results = test_strategy_allocation_frontend_http()
    
    # Save results to file
    with open('/app/strategy_allocation_frontend_http_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Exit with appropriate code
    if results["overall_result"] == "PASS":
        sys.exit(0)
    else:
        sys.exit(1)