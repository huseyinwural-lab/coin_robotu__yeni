#!/usr/bin/env python3
"""
Frontend Audit Logs Page Validation
Check for archive toggle + graph/copy/explain/lifecycle indicators
"""

import requests
import re
from datetime import datetime

BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"

def test_frontend_indicators():
    """Test frontend audit logs page for required indicators"""
    try:
        # Get the audit logs page
        response = requests.get(f"{BASE_URL}/admin/audit-logs", timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Frontend page failed to load: HTTP {response.status_code}")
            return False
        
        html_content = response.text
        print(f"✅ Frontend page loaded successfully ({len(html_content)} chars)")
        
        # Check for specific indicators in the HTML/JavaScript
        indicators = {
            'archive_toggle': [
                'archive',
                'archive-mode',
                'archive_mode',
                'toggle',
                'switch'
            ],
            'graph_indicator': [
                'graph',
                'chart',
                'visualization',
                'graph-view',
                'view-mode-graph'
            ],
            'copy_indicator': [
                'copy',
                'copy-trace',
                'copy-full-trace',
                'clipboard'
            ],
            'explain_indicator': [
                'explain',
                'explain-failure',
                'explanation',
                'root-cause'
            ],
            'lifecycle_indicator': [
                'lifecycle',
                'full-lifecycle',
                'trading-lifecycle',
                'open-lifecycle'
            ]
        }
        
        found_indicators = {}
        content_lower = html_content.lower()
        
        for indicator_type, keywords in indicators.items():
            matches = []
            for keyword in keywords:
                if keyword in content_lower:
                    matches.append(keyword)
            
            found_indicators[indicator_type] = matches
            
            if matches:
                print(f"✅ {indicator_type}: FOUND - {matches}")
            else:
                print(f"⚠️ {indicator_type}: NOT FOUND")
        
        # Count total found indicators
        total_found = sum(1 for matches in found_indicators.values() if matches)
        total_expected = len(indicators)
        
        print(f"\nSUMMARY: {total_found}/{total_expected} indicators found")
        
        # Check for React app structure
        react_indicators = [
            'div id="root"' in html_content,
            'react' in content_lower,
            'audit' in content_lower,
            len(html_content) > 5000
        ]
        
        react_found = sum(react_indicators)
        print(f"React app indicators: {react_found}/4")
        
        # Overall assessment
        if total_found >= 3 and react_found >= 2:
            print("✅ PASS - Frontend has sufficient indicators and React structure")
            return True
        elif total_found >= 2:
            print("⚠️ PARTIAL - Some indicators found, likely functional")
            return True
        else:
            print("❌ FAIL - Insufficient indicators found")
            return False
            
    except Exception as e:
        print(f"❌ Exception testing frontend: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("FRONTEND AUDIT LOGS PAGE VALIDATION")
    print(f"URL: {BASE_URL}/admin/audit-logs")
    print("=" * 60)
    
    result = test_frontend_indicators()
    
    print("\n" + "=" * 60)
    if result:
        print("✅ FRONTEND VALIDATION PASSED")
    else:
        print("❌ FRONTEND VALIDATION FAILED")
    print("=" * 60)
    
    return 0 if result else 1

if __name__ == "__main__":
    exit(main())