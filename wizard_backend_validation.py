#!/usr/bin/env python3
"""
Wizard Backend Validation Test
Turkish Review Request: Wizard backend doğrulaması

Test Requirements:
1) POST /api/user/strategy-templates - User rolüyle custom template oluşturabiliyor mu? 200 beklenir.
2) GET /api/strategy-templates - Yeni oluşturulan template listede dönüyor mu?
3) POST /api/bot-profiles - Wizard payload (exchange, market_type, symbols, strategy_template_id, strategy_template_ids) ile bot oluşturma 200.
4) POST /api/bot-profiles/{id}/start - Oluşan bot start çağrısı 200.
5) Hata sözlüğü için teknik kod üreten bir örnek response olduğunda (örn invalid payload), response detail alınıp frontend çevrilebilir formatta mı (string/array) dönüyor kontrol notu.

Base URL: https://trade-trace-engine.preview.emergentagent.com
User: review.user@platform.local / ReviewUser123!
"""

import requests
import json
import sys
import uuid
from datetime import datetime

# Configuration
BACKEND_URL = "https://trade-trace-engine.preview.emergentagent.com"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"

class WizardBackendValidator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Wizard-Backend-Validator/1.0'
        })
        self.user_token = None
        self.results = []
        self.created_template_id = None
        self.created_bot_id = None
        
    def log_result(self, test_name, success, details, response_data=None):
        """Log test result"""
        result = {
            'test': test_name,
            'success': success,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        if response_data:
            result['response_data'] = response_data
        self.results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
        print(f"  Details: {details}")
        if response_data:
            print(f"  Response: {json.dumps(response_data, indent=2)[:500]}...")
        print()
        
    def test_user_login(self):
        """Test: User login with review.user@platform.local / ReviewUser123!"""
        try:
            payload = {
                "email": USER_EMAIL,
                "password": USER_PASSWORD,
                "panel": "user"
            }
            
            response = self.session.post(f"{BACKEND_URL}/api/auth/login", json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'access_token' in data:
                    self.user_token = data['access_token']
                    self.log_result(
                        "User Login", 
                        True, 
                        f"Login successful. Token length: {len(self.user_token)} chars"
                    )
                    return True
                else:
                    self.log_result(
                        "User Login", 
                        False, 
                        f"No access_token in response: {data}"
                    )
                    return False
            else:
                self.log_result(
                    "User Login", 
                    False, 
                    f"HTTP {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_result(
                "User Login", 
                False, 
                f"Exception: {str(e)}"
            )
            return False
    
    def test_create_strategy_template(self):
        """Test 1: POST /api/user/strategy-templates - User rolüyle custom template oluşturabiliyor mu? 200 beklenir."""
        if not self.user_token:
            self.log_result(
                "Create Strategy Template", 
                False, 
                "No user token available"
            )
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.user_token}'}
            
            # Create a unique template name
            template_name = f"test_template_{uuid.uuid4().hex[:8]}"
            
            payload = {
                "name": template_name,
                "description": "Test template created by wizard backend validation",
                "strategy_type": "momentum",
                "parameters": {
                    "rsi_period": 14,
                    "rsi_oversold": 30,
                    "rsi_overbought": 70,
                    "stop_loss_pct": 2.0,
                    "take_profit_pct": 4.0
                },
                "risk_profile": "medium",
                "market_types": ["spot", "futures"],
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "is_public": False
            }
            
            response = self.session.post(
                f"{BACKEND_URL}/api/user/strategy-templates", 
                json=payload,
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'id' in data:
                    self.created_template_id = data['id']
                    self.log_result(
                        "Create Strategy Template", 
                        True, 
                        f"Template created successfully. ID: {self.created_template_id}",
                        data
                    )
                    return True
                else:
                    self.log_result(
                        "Create Strategy Template", 
                        False, 
                        f"No ID in response: {data}",
                        data
                    )
                    return False
            else:
                try:
                    error_data = response.json()
                except:
                    error_data = response.text
                    
                self.log_result(
                    "Create Strategy Template", 
                    False, 
                    f"HTTP {response.status_code}: Expected 200",
                    error_data
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Create Strategy Template", 
                False, 
                f"Exception: {str(e)}"
            )
            return False
    
    def test_get_strategy_templates(self):
        """Test 2: GET /api/strategy-templates - Yeni oluşturulan template listede dönüyor mu?"""
        if not self.user_token:
            self.log_result(
                "Get Strategy Templates", 
                False, 
                "No user token available"
            )
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.user_token}'}
            
            response = self.session.get(
                f"{BACKEND_URL}/api/strategy-templates", 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if our created template is in the list
                template_found = False
                if self.created_template_id and isinstance(data, list):
                    for template in data:
                        if template.get('id') == self.created_template_id:
                            template_found = True
                            break
                elif self.created_template_id and isinstance(data, dict) and 'templates' in data:
                    for template in data['templates']:
                        if template.get('id') == self.created_template_id:
                            template_found = True
                            break
                
                if template_found:
                    self.log_result(
                        "Get Strategy Templates", 
                        True, 
                        f"Template list retrieved successfully. Created template found in list. Total templates: {len(data) if isinstance(data, list) else len(data.get('templates', []))}",
                        {"total_count": len(data) if isinstance(data, list) else len(data.get('templates', [])), "created_template_found": True}
                    )
                    return True
                elif self.created_template_id:
                    self.log_result(
                        "Get Strategy Templates", 
                        False, 
                        f"Template list retrieved but created template not found. Total templates: {len(data) if isinstance(data, list) else len(data.get('templates', []))}",
                        {"total_count": len(data) if isinstance(data, list) else len(data.get('templates', [])), "created_template_found": False}
                    )
                    return False
                else:
                    self.log_result(
                        "Get Strategy Templates", 
                        True, 
                        f"Template list retrieved successfully (no template to verify). Total templates: {len(data) if isinstance(data, list) else len(data.get('templates', []))}",
                        {"total_count": len(data) if isinstance(data, list) else len(data.get('templates', [])), "created_template_found": "N/A"}
                    )
                    return True
            else:
                try:
                    error_data = response.json()
                except:
                    error_data = response.text
                    
                self.log_result(
                    "Get Strategy Templates", 
                    False, 
                    f"HTTP {response.status_code}: {response.text}",
                    error_data
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Get Strategy Templates", 
                False, 
                f"Exception: {str(e)}"
            )
            return False
    
    def test_create_bot_profile(self):
        """Test 3: POST /api/bot-profiles - Wizard payload ile bot oluşturma 200."""
        if not self.user_token:
            self.log_result(
                "Create Bot Profile", 
                False, 
                "No user token available"
            )
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.user_token}'}
            
            # Create bot with wizard payload
            bot_name = f"test_bot_{uuid.uuid4().hex[:8]}"
            
            payload = {
                "name": bot_name,
                "description": "Test bot created by wizard backend validation",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "strategy_template_id": self.created_template_id if self.created_template_id else "default_template_id",
                "strategy_template_ids": [self.created_template_id] if self.created_template_id else ["default_template_id"],
                "strategy_type": "momentum",  # Required field
                "risk_profile": "medium",
                "initial_balance": 1000.0,
                "max_positions": 3,
                "is_active": False
            }
            
            response = self.session.post(
                f"{BACKEND_URL}/api/bot-profiles", 
                json=payload,
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'id' in data:
                    self.created_bot_id = data['id']
                    self.log_result(
                        "Create Bot Profile", 
                        True, 
                        f"Bot profile created successfully. ID: {self.created_bot_id}",
                        data
                    )
                    return True
                else:
                    self.log_result(
                        "Create Bot Profile", 
                        False, 
                        f"No ID in response: {data}",
                        data
                    )
                    return False
            else:
                try:
                    error_data = response.json()
                except:
                    error_data = response.text
                    
                self.log_result(
                    "Create Bot Profile", 
                    False, 
                    f"HTTP {response.status_code}: Expected 200",
                    error_data
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Create Bot Profile", 
                False, 
                f"Exception: {str(e)}"
            )
            return False
    
    def test_start_bot_profile(self):
        """Test 4: POST /api/bot-profiles/{id}/start - Oluşan bot start çağrısı 200."""
        if not self.user_token:
            self.log_result(
                "Start Bot Profile", 
                False, 
                "No user token available"
            )
            return False
            
        if not self.created_bot_id:
            self.log_result(
                "Start Bot Profile", 
                False, 
                "No bot ID available (bot creation may have failed)"
            )
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.user_token}'}
            
            response = self.session.post(
                f"{BACKEND_URL}/api/bot-profiles/{self.created_bot_id}/start", 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                except:
                    data = response.text
                    
                self.log_result(
                    "Start Bot Profile", 
                    True, 
                    f"Bot started successfully. Bot ID: {self.created_bot_id}",
                    data
                )
                return True
            else:
                try:
                    error_data = response.json()
                except:
                    error_data = response.text
                    
                self.log_result(
                    "Start Bot Profile", 
                    False, 
                    f"HTTP {response.status_code}: Expected 200",
                    error_data
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Start Bot Profile", 
                False, 
                f"Exception: {str(e)}"
            )
            return False
    
    def test_error_response_format(self):
        """Test 5: Hata sözlüğü için teknik kod üreten bir örnek response - frontend çevrilebilir format kontrolü."""
        if not self.user_token:
            self.log_result(
                "Error Response Format", 
                False, 
                "No user token available"
            )
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.user_token}'}
            
            # Send invalid payload to trigger error response
            invalid_payload = {
                "name": "",  # Empty name should trigger validation error
                "exchange": "invalid_exchange",  # Invalid exchange
                "market_type": "invalid_market",  # Invalid market type
                "symbols": [],  # Empty symbols array
                "strategy_template_id": "non_existent_id"  # Non-existent template ID
            }
            
            response = self.session.post(
                f"{BACKEND_URL}/api/bot-profiles", 
                json=invalid_payload,
                headers=headers, 
                timeout=30
            )
            
            # We expect this to fail with 400 or 422
            if response.status_code in [400, 422]:
                try:
                    error_data = response.json()
                    
                    # Check if response detail is in frontend-translatable format
                    detail = error_data.get('detail', None)
                    
                    is_translatable = False
                    format_type = "unknown"
                    
                    if isinstance(detail, str):
                        is_translatable = True
                        format_type = "string"
                    elif isinstance(detail, list):
                        is_translatable = True
                        format_type = "array"
                    elif isinstance(detail, dict):
                        # Check if it has message/code structure
                        if 'message' in detail or 'code' in detail:
                            is_translatable = True
                            format_type = "structured_dict"
                        else:
                            format_type = "unstructured_dict"
                    
                    self.log_result(
                        "Error Response Format", 
                        is_translatable, 
                        f"Error response format check. Status: {response.status_code}, Format: {format_type}, Translatable: {is_translatable}",
                        {"status_code": response.status_code, "detail": detail, "format_type": format_type, "is_translatable": is_translatable}
                    )
                    return is_translatable
                    
                except Exception as parse_error:
                    self.log_result(
                        "Error Response Format", 
                        False, 
                        f"Could not parse error response as JSON: {str(parse_error)}",
                        {"status_code": response.status_code, "raw_response": response.text}
                    )
                    return False
            else:
                self.log_result(
                    "Error Response Format", 
                    False, 
                    f"Expected 400/422 error but got {response.status_code}",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Error Response Format", 
                False, 
                f"Exception: {str(e)}"
            )
            return False
    
    def run_all_tests(self):
        """Run all wizard backend validation tests"""
        print("=" * 80)
        print("WIZARD BACKEND VALIDATION TEST")
        print("Turkish Review Request: Wizard backend doğrulaması")
        print(f"Backend URL: {BACKEND_URL}")
        print(f"User: {USER_EMAIL}")
        print(f"Test Time: {datetime.now().isoformat()}")
        print("=" * 80)
        print()
        
        # Test: User Login (prerequisite)
        user_login_success = self.test_user_login()
        
        # Test 1: Create Strategy Template
        template_create_success = self.test_create_strategy_template()
        
        # Test 2: Get Strategy Templates
        template_list_success = self.test_get_strategy_templates()
        
        # Test 3: Create Bot Profile
        bot_create_success = self.test_create_bot_profile()
        
        # Test 4: Start Bot Profile
        bot_start_success = self.test_start_bot_profile()
        
        # Test 5: Error Response Format
        error_format_success = self.test_error_response_format()
        
        # Summary
        total_tests = 5  # Not counting login as it's a prerequisite
        passed_tests = sum([
            template_create_success,
            template_list_success,
            bot_create_success,
            bot_start_success,
            error_format_success
        ])
        
        print("=" * 80)
        print("WIZARD BACKEND VALIDATION SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        print()
        
        # Turkish summary as requested
        print("TURKISH SUMMARY (PASS/FAIL kısa rapor):")
        print(f"1) POST /api/user/strategy-templates (User custom template): {'✅ PASS' if template_create_success else '❌ FAIL'}")
        print(f"2) GET /api/strategy-templates (Template listede görünüyor): {'✅ PASS' if template_list_success else '❌ FAIL'}")
        print(f"3) POST /api/bot-profiles (Wizard payload ile bot oluşturma): {'✅ PASS' if bot_create_success else '❌ FAIL'}")
        print(f"4) POST /api/bot-profiles/{{id}}/start (Bot start çağrısı): {'✅ PASS' if bot_start_success else '❌ FAIL'}")
        print(f"5) Error response format (Frontend çevrilebilir format): {'✅ PASS' if error_format_success else '❌ FAIL'}")
        print()
        
        if passed_tests == total_tests:
            print("🎉 TÜM TESTLER BAŞARILI - All wizard backend validation tests passed!")
        else:
            print("⚠️ BAZI TESTLER BAŞARISIZ - Some tests failed, see details above.")
        
        print()
        return passed_tests == total_tests

def main():
    validator = WizardBackendValidator()
    success = validator.run_all_tests()
    
    # Save results to file
    with open('/app/wizard_validation_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'backend_url': BACKEND_URL,
            'user_email': USER_EMAIL,
            'overall_success': success,
            'results': validator.results
        }, f, indent=2)
    
    print(f"Results saved to: /app/wizard_validation_results.json")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())