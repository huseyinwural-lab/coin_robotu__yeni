#!/usr/bin/env python3
"""
Simple login test to isolate the 500 error issue
"""

import sys
import os
sys.path.append('/app/backend')

from sqlalchemy.orm import Session
from db import SessionLocal
from models import User, UserRole
from core.users.user_registry import user_login_with_policy
from schemas import LoginRequest

def test_login():
    """Test login functionality directly"""
    db = SessionLocal()
    
    try:
        # Test data
        test_credentials = [
            ("canary.admin@example.com", "CanaryAdmin123!"),
            ("canary.requester@example.com", "CanaryRequester123!"),
            ("canary.ops@example.com", "CanaryOps123!")
        ]
        
        for email, password in test_credentials:
            print(f"\nTesting login for: {email}")
            
            # Check if user exists
            user = db.query(User).filter(User.email == email).first()
            if not user:
                print(f"  ❌ User not found: {email}")
                continue
                
            print(f"  ✓ User found: {user.email}, role: {user.role}, active: {user.is_active}")
            
            # Try login
            try:
                payload = LoginRequest(email=email, password=password)
                session = user_login_with_policy(
                    db, 
                    payload, 
                    allowed_roles={UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS}
                )
                print(f"  ✅ Login successful for {email}")
                print(f"     Token: {session.access_token[:50]}...")
                
            except Exception as e:
                print(f"  ❌ Login failed for {email}: {str(e)}")
                import traceback
                traceback.print_exc()
                
    except Exception as e:
        print(f"Database error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_login()