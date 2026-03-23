#!/usr/bin/env python3
"""
Debug Strategy Structure
"""

import requests
import json

def debug_strategy_structure():
    BASE_URL = "https://exec-tuning.preview.emergentagent.com"
    
    session = requests.Session()
    session.timeout = 15
    
    super_admin_creds = {
        "email": "canary.admin@platform.local",
        "password": "CanaryAdmin123!"
    }
    
    try:
        # Login
        response = session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json=super_admin_creds,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
            
            # Get strategy list
            headers = {"Authorization": f"Bearer {token}"}
            response = session.get(f"{BASE_URL}/api/admin/futures/strategy-control/overview", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                print("Strategy overview response structure:")
                print(json.dumps(data, indent=2))
                
                strategies = data.get("strategies", [])
                if strategies:
                    print(f"\nFirst strategy structure:")
                    print(json.dumps(strategies[0], indent=2))
                    
                    # Try to find ID field
                    for key in strategies[0].keys():
                        if "id" in key.lower():
                            print(f"\nFound ID field '{key}': {strategies[0][key]}")
    
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    debug_strategy_structure()