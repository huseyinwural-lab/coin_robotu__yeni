#!/usr/bin/env python3
"""
Frontend Smoke Test for P1+P2 Readiness Hardening
"""

import requests
from datetime import datetime

# Configuration
BASE_URL = "https://futures-health-check.preview.emergentagent.com"

def test_frontend_accessibility():
    """Test frontend page accessibility"""
    print("=" * 80)
    print("P1+P2 READINESS HARDENING - FRONTEND SMOKE TEST")
    print("=" * 80)
    
    try:
        # Test the admin futures live-readiness page
        frontend_url = f"{BASE_URL}/admin/futures/live-readiness"
        print(f"Testing URL: {frontend_url}")
        
        response = requests.get(frontend_url, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Content Length: {len(response.text)} characters")
        
        if response.status_code == 200:
            content = response.text
            
            # Check for HTML structure
            has_html = "<html" in content
            has_body = "<body" in content
            has_react_root = "root" in content
            
            # Check for admin/readiness related content
            has_admin_content = "admin" in content.lower()
            has_readiness_content = "readiness" in content.lower()
            has_futures_content = "futures" in content.lower()
            
            # Check for React app indicators
            has_react_scripts = "react" in content.lower()
            has_js_bundle = ".js" in content
            
            print(f"\nContent Analysis:")
            print(f"- Has HTML structure: {has_html}")
            print(f"- Has body tag: {has_body}")
            print(f"- Has React root: {has_react_root}")
            print(f"- Has admin content: {has_admin_content}")
            print(f"- Has readiness content: {has_readiness_content}")
            print(f"- Has futures content: {has_futures_content}")
            print(f"- Has React scripts: {has_react_scripts}")
            print(f"- Has JS bundle: {has_js_bundle}")
            
            # Show first 500 characters
            print(f"\nFirst 500 characters:")
            print(content[:500])
            
            # Determine if this is a blank page
            is_blank = len(content.strip()) < 1000 and not (has_admin_content or has_readiness_content)
            
            if is_blank:
                print(f"\n❌ RESULT: Page appears to be blank or minimal content")
                print(f"   Content length: {len(content)} chars")
                print(f"   Admin content detected: {has_admin_content}")
                print(f"   Readiness content detected: {has_readiness_content}")
            else:
                print(f"\n✅ RESULT: Page loads successfully with content")
                print(f"   Content length: {len(content)} chars")
                print(f"   HTML structure: {has_html and has_body}")
                print(f"   React app: {has_react_root or has_react_scripts}")
        else:
            print(f"\n❌ RESULT: HTTP {response.status_code} - Page not accessible")
            print(f"Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"\n❌ RESULT: Exception occurred")
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    test_frontend_accessibility()