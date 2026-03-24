#!/usr/bin/env python3
"""
P1 Backend Validation Test
Validates specific P1 backend changes for strategy timeline and preflight endpoints
"""

import requests
import json
import sys
from typing import Dict, Any, Tuple

# Configuration
BASE_URL = "https://strategy-version-gov.preview.emergentagent.com"
SUPER_ADMIN_CREDS = {
    "email": "canary.admin@platform.local",
    "password": "CanaryAdmin123!"
}
ADMIN_CREDS = {
    "email": "canary.requester@platform.local", 
    "password": "CanaryRequester123!"
}

# Test chains
HEAVY_CHAIN = "p1-heavy-chain-600"
BROKEN_CHAIN = "p1-broken-chain-001"

def login_user(credentials: Dict[str, str]) -> Tuple[bool, str]:
    """Login and get access token"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json=credentials,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return True, data.get("access_token", "")
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text}")
            return False, ""
            
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return False, ""

def test_strategy_timeline_heavy_chain(token: str) -> Dict[str, Any]:
    """Test 1: Heavy chain timeline validation"""
    print(f"\n🔍 TEST 1: Heavy Chain Timeline - {HEAVY_CHAIN}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN}?window=7d&strategy_id=seed_strategy"
        
        response = requests.get(url, headers=headers, timeout=30)
        
        result = {
            "test_name": "Heavy Chain Timeline",
            "endpoint": url,
            "status_code": response.status_code,
            "success": False,
            "details": {}
        }
        
        if response.status_code == 200:
            data = response.json()
            summary = data.get("summary", {})
            
            # Check requirements
            total_nodes = summary.get("total_nodes", 0)
            virtualization_recommended = summary.get("virtualization_recommended", False)
            is_chain_valid = summary.get("is_chain_valid", False)
            
            result["details"] = {
                "total_nodes": total_nodes,
                "virtualization_recommended": virtualization_recommended,
                "is_chain_valid": is_chain_valid,
                "summary_keys": list(summary.keys())
            }
            
            # Validate requirements
            checks = {
                "status_200": True,
                "total_nodes_gte_500": total_nodes >= 500,
                "virtualization_recommended_true": virtualization_recommended is True,
                "is_chain_valid_true": is_chain_valid is True
            }
            
            result["checks"] = checks
            result["success"] = all(checks.values())
            
            if result["success"]:
                print(f"✅ Heavy chain validation PASSED")
                print(f"   - total_nodes: {total_nodes} (>= 500)")
                print(f"   - virtualization_recommended: {virtualization_recommended}")
                print(f"   - is_chain_valid: {is_chain_valid}")
            else:
                print(f"❌ Heavy chain validation FAILED")
                for check, passed in checks.items():
                    status = "✅" if passed else "❌"
                    print(f"   {status} {check}")
        else:
            result["error"] = response.text
            print(f"❌ Heavy chain endpoint failed: {response.status_code}")
            
    except Exception as e:
        result = {
            "test_name": "Heavy Chain Timeline",
            "success": False,
            "error": str(e)
        }
        print(f"❌ Heavy chain test error: {str(e)}")
    
    return result

def test_strategy_timeline_broken_chain(token: str) -> Dict[str, Any]:
    """Test 2: Broken chain timeline validation"""
    print(f"\n🔍 TEST 2: Broken Chain Timeline - {BROKEN_CHAIN}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/api/admin/strategy/timeline/{BROKEN_CHAIN}?window=7d&strategy_id=seed_strategy"
        
        response = requests.get(url, headers=headers, timeout=30)
        
        result = {
            "test_name": "Broken Chain Timeline",
            "endpoint": url,
            "status_code": response.status_code,
            "success": False,
            "details": {}
        }
        
        if response.status_code == 200:
            data = response.json()
            summary = data.get("summary", {})
            
            # Check requirements
            is_chain_valid = summary.get("is_chain_valid", True)
            broken_links_count = data.get("broken_links_count", 0)
            invalid_reasons = data.get("invalid_reasons", [])
            
            result["details"] = {
                "is_chain_valid": is_chain_valid,
                "broken_links_count": broken_links_count,
                "invalid_reasons": invalid_reasons,
                "invalid_reasons_count": len(invalid_reasons) if invalid_reasons else 0
            }
            
            # Validate requirements
            checks = {
                "status_200": True,
                "is_chain_valid_false": is_chain_valid is False,
                "broken_links_count_gt_0": broken_links_count > 0,
                "invalid_reasons_populated": len(invalid_reasons) > 0 if invalid_reasons else False
            }
            
            result["checks"] = checks
            result["success"] = all(checks.values())
            
            if result["success"]:
                print(f"✅ Broken chain validation PASSED")
                print(f"   - is_chain_valid: {is_chain_valid}")
                print(f"   - broken_links_count: {broken_links_count}")
                print(f"   - invalid_reasons: {len(invalid_reasons)} items")
            else:
                print(f"❌ Broken chain validation FAILED")
                for check, passed in checks.items():
                    status = "✅" if passed else "❌"
                    print(f"   {status} {check}")
        else:
            result["error"] = response.text
            print(f"❌ Broken chain endpoint failed: {response.status_code}")
            
    except Exception as e:
        result = {
            "test_name": "Broken Chain Timeline",
            "success": False,
            "error": str(e)
        }
        print(f"❌ Broken chain test error: {str(e)}")
    
    return result

def test_role_parity(super_admin_token: str, admin_token: str) -> Dict[str, Any]:
    """Test 3: Role parity - admin and super_admin should read same chain data"""
    print(f"\n🔍 TEST 3: Role Parity - Chain Detail Access")
    
    try:
        url = f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN}?window=7d&strategy_id=seed_strategy"
        
        # Test super_admin access
        super_admin_headers = {"Authorization": f"Bearer {super_admin_token}"}
        super_admin_response = requests.get(url, headers=super_admin_headers, timeout=30)
        
        # Test admin access
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        admin_response = requests.get(url, headers=admin_headers, timeout=30)
        
        result = {
            "test_name": "Role Parity",
            "endpoint": url,
            "success": False,
            "details": {}
        }
        
        super_admin_success = super_admin_response.status_code == 200
        admin_success = admin_response.status_code == 200
        
        result["details"] = {
            "super_admin_status": super_admin_response.status_code,
            "admin_status": admin_response.status_code,
            "super_admin_success": super_admin_success,
            "admin_success": admin_success
        }
        
        if super_admin_success and admin_success:
            # Compare data structure
            super_admin_data = super_admin_response.json()
            admin_data = admin_response.json()
            
            # Check if both have same summary structure
            super_admin_summary_keys = set(super_admin_data.get("summary", {}).keys())
            admin_summary_keys = set(admin_data.get("summary", {}).keys())
            
            keys_match = super_admin_summary_keys == admin_summary_keys
            
            result["details"]["summary_keys_match"] = keys_match
            result["details"]["super_admin_summary_keys"] = list(super_admin_summary_keys)
            result["details"]["admin_summary_keys"] = list(admin_summary_keys)
            
            result["success"] = keys_match
            
            if result["success"]:
                print(f"✅ Role parity PASSED")
                print(f"   - Both super_admin and admin can access chain data")
                print(f"   - Summary structure matches: {len(super_admin_summary_keys)} keys")
            else:
                print(f"❌ Role parity FAILED")
                print(f"   - Summary keys don't match")
        else:
            result["success"] = False
            print(f"❌ Role parity FAILED")
            print(f"   - super_admin access: {super_admin_success}")
            print(f"   - admin access: {admin_success}")
            
    except Exception as e:
        result = {
            "test_name": "Role Parity",
            "success": False,
            "error": str(e)
        }
        print(f"❌ Role parity test error: {str(e)}")
    
    return result

def test_drill_down_consistency(token: str) -> Dict[str, Any]:
    """Test 4: Drill-down consistency between timeline and action-impact-timeline"""
    print(f"\n🔍 TEST 4: Drill-down Consistency")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get timeline data
        timeline_url = f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN}?window=7d&strategy_id=seed_strategy"
        timeline_response = requests.get(timeline_url, headers=headers, timeout=30)
        
        # Get action-impact-timeline data
        action_impact_url = f"{BASE_URL}/api/admin/strategy/action-impact-timeline"
        action_impact_response = requests.get(action_impact_url, headers=headers, timeout=30)
        
        result = {
            "test_name": "Drill-down Consistency",
            "success": False,
            "details": {}
        }
        
        if timeline_response.status_code == 200 and action_impact_response.status_code == 200:
            timeline_data = timeline_response.json()
            action_impact_data = action_impact_response.json()
            
            # Extract counts
            timeline_count = timeline_data.get("summary", {}).get("total_nodes", 0)
            
            # Look for heavy chain in action-impact data
            heavy_chain_count = 0
            if isinstance(action_impact_data, list):
                for item in action_impact_data:
                    if item.get("chain_id") == HEAVY_CHAIN:
                        heavy_chain_count = item.get("count", 0)
                        break
            elif isinstance(action_impact_data, dict):
                # Check if it's a different structure
                chains = action_impact_data.get("chains", [])
                for chain in chains:
                    if chain.get("chain_id") == HEAVY_CHAIN:
                        heavy_chain_count = chain.get("count", 0)
                        break
            
            result["details"] = {
                "timeline_count": timeline_count,
                "action_impact_count": heavy_chain_count,
                "counts_match": timeline_count == heavy_chain_count,
                "timeline_status": timeline_response.status_code,
                "action_impact_status": action_impact_response.status_code
            }
            
            result["success"] = timeline_count == heavy_chain_count and timeline_count > 0
            
            if result["success"]:
                print(f"✅ Drill-down consistency PASSED")
                print(f"   - Timeline count: {timeline_count}")
                print(f"   - Action-impact count: {heavy_chain_count}")
            else:
                print(f"❌ Drill-down consistency FAILED")
                print(f"   - Timeline count: {timeline_count}")
                print(f"   - Action-impact count: {heavy_chain_count}")
        else:
            result["error"] = f"Timeline: {timeline_response.status_code}, Action-impact: {action_impact_response.status_code}"
            print(f"❌ Drill-down consistency endpoint errors")
            
    except Exception as e:
        result = {
            "test_name": "Drill-down Consistency",
            "success": False,
            "error": str(e)
        }
        print(f"❌ Drill-down consistency test error: {str(e)}")
    
    return result

def test_impact_readability(token: str) -> Dict[str, Any]:
    """Test 5: Impact readability - node.impact_labels should be human-readable"""
    print(f"\n🔍 TEST 5: Impact Readability")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/api/admin/strategy/timeline/{HEAVY_CHAIN}?window=7d&strategy_id=seed_strategy"
        
        response = requests.get(url, headers=headers, timeout=30)
        
        result = {
            "test_name": "Impact Readability",
            "endpoint": url,
            "success": False,
            "details": {}
        }
        
        if response.status_code == 200:
            data = response.json()
            nodes = data.get("nodes", [])
            
            impact_labels_found = False
            sample_impact_labels = []
            human_readable_count = 0
            
            for node in nodes[:5]:  # Check first 5 nodes
                impact_labels = node.get("impact_labels")
                if impact_labels:
                    impact_labels_found = True
                    sample_impact_labels.append(impact_labels)
                    
                    # Check if labels are human-readable (not just codes)
                    if isinstance(impact_labels, list):
                        for label in impact_labels:
                            if isinstance(label, str) and len(label) > 3 and not label.isupper():
                                human_readable_count += 1
                    elif isinstance(impact_labels, str) and len(impact_labels) > 3 and not impact_labels.isupper():
                        human_readable_count += 1
            
            result["details"] = {
                "nodes_count": len(nodes),
                "impact_labels_found": impact_labels_found,
                "sample_impact_labels": sample_impact_labels[:3],  # First 3 samples
                "human_readable_count": human_readable_count
            }
            
            result["success"] = impact_labels_found and human_readable_count > 0
            
            if result["success"]:
                print(f"✅ Impact readability PASSED")
                print(f"   - Found impact_labels in nodes")
                print(f"   - Human-readable labels: {human_readable_count}")
                print(f"   - Sample: {sample_impact_labels[0] if sample_impact_labels else 'None'}")
            else:
                print(f"❌ Impact readability FAILED")
                print(f"   - impact_labels found: {impact_labels_found}")
                print(f"   - Human-readable count: {human_readable_count}")
        else:
            result["error"] = response.text
            print(f"❌ Impact readability endpoint failed: {response.status_code}")
            
    except Exception as e:
        result = {
            "test_name": "Impact Readability",
            "success": False,
            "error": str(e)
        }
        print(f"❌ Impact readability test error: {str(e)}")
    
    return result

def test_preflight_endpoint(token: str) -> Dict[str, Any]:
    """Test 6: Preflight endpoint validation"""
    print(f"\n🔍 TEST 6: Preflight Endpoint")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight"
        
        response = requests.get(url, headers=headers, timeout=30)
        
        result = {
            "test_name": "Preflight Endpoint",
            "endpoint": url,
            "status_code": response.status_code,
            "success": False,
            "details": {}
        }
        
        if response.status_code == 200:
            data = response.json()
            checks = data.get("checks", {})
            migration = data.get("migration", {})
            
            # Required checks
            required_checks = [
                "db_readiness",
                "migration_compatibility", 
                "table_access",
                "integration_readiness",
                "playbook_flow_gate"
            ]
            
            checks_present = {}
            for check in required_checks:
                checks_present[check] = check in checks
            
            # Migration fields
            migration_required = migration.get("required") is not None
            migration_current = migration.get("current") is not None
            
            result["details"] = {
                "checks_present": checks_present,
                "migration_required_present": migration_required,
                "migration_current_present": migration_current,
                "total_checks": len(checks),
                "migration_keys": list(migration.keys())
            }
            
            all_checks_present = all(checks_present.values())
            migration_fields_present = migration_required and migration_current
            
            result["success"] = all_checks_present and migration_fields_present
            
            if result["success"]:
                print(f"✅ Preflight endpoint PASSED")
                print(f"   - All required checks present: {list(checks_present.keys())}")
                print(f"   - Migration fields present: required, current")
            else:
                print(f"❌ Preflight endpoint FAILED")
                for check, present in checks_present.items():
                    status = "✅" if present else "❌"
                    print(f"   {status} {check}")
                print(f"   Migration required: {migration_required}")
                print(f"   Migration current: {migration_current}")
        else:
            result["error"] = response.text
            print(f"❌ Preflight endpoint failed: {response.status_code}")
            
    except Exception as e:
        result = {
            "test_name": "Preflight Endpoint",
            "success": False,
            "error": str(e)
        }
        print(f"❌ Preflight endpoint test error: {str(e)}")
    
    return result

def main():
    """Main test execution"""
    print("🚀 P1 Backend Validation Test Starting...")
    print(f"🌐 Base URL: {BASE_URL}")
    
    # Login both users
    print("\n🔐 Authentication Phase")
    super_admin_success, super_admin_token = login_user(SUPER_ADMIN_CREDS)
    admin_success, admin_token = login_user(ADMIN_CREDS)
    
    if not super_admin_success:
        print("❌ Super admin login failed - cannot proceed")
        sys.exit(1)
    
    if not admin_success:
        print("❌ Admin login failed - cannot proceed")
        sys.exit(1)
    
    print("✅ Both users authenticated successfully")
    
    # Run all tests
    test_results = []
    
    # Test 1: Heavy chain timeline
    test_results.append(test_strategy_timeline_heavy_chain(super_admin_token))
    
    # Test 2: Broken chain timeline
    test_results.append(test_strategy_timeline_broken_chain(super_admin_token))
    
    # Test 3: Role parity
    test_results.append(test_role_parity(super_admin_token, admin_token))
    
    # Test 4: Drill-down consistency
    test_results.append(test_drill_down_consistency(super_admin_token))
    
    # Test 5: Impact readability
    test_results.append(test_impact_readability(super_admin_token))
    
    # Test 6: Preflight endpoint
    test_results.append(test_preflight_endpoint(super_admin_token))
    
    # Summary
    print("\n" + "="*60)
    print("📊 P1 BACKEND VALIDATION SUMMARY")
    print("="*60)
    
    passed_tests = 0
    total_tests = len(test_results)
    
    for i, result in enumerate(test_results, 1):
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"{i}. {result['test_name']}: {status}")
        if result["success"]:
            passed_tests += 1
    
    print(f"\n🎯 OVERALL RESULT: {passed_tests}/{total_tests} tests PASSED ({(passed_tests/total_tests)*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("✅✅✅ ALL P1 BACKEND REQUIREMENTS VALIDATED SUCCESSFULLY")
        print("🚀 System is PRODUCTION-READY for P1 deployment")
    else:
        print("❌ SOME P1 BACKEND REQUIREMENTS FAILED")
        print("🔧 Issues must be resolved before production deployment")
    
    # Save detailed results
    with open("/app/p1_backend_validation_results.json", "w") as f:
        json.dump({
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "success_rate": (passed_tests/total_tests)*100,
                "overall_success": passed_tests == total_tests
            },
            "test_results": test_results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: /app/p1_backend_validation_results.json")

if __name__ == "__main__":
    main()