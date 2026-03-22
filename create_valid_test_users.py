#!/usr/bin/env python3
"""
Create test users with valid email domains for Strategy Intelligence governance flow testing
"""

import sys
import os
sys.path.append('/app/backend')

from sqlalchemy.orm import Session
from db import SessionLocal
from models import User, UserRole
from core.security import hash_password

def create_valid_test_users():
    """Create test users with valid email domains"""
    db = SessionLocal()
    
    try:
        # Users to create with valid email domains
        users_to_create = [
            {
                "email": "canary.admin@example.com",
                "password": "CanaryAdmin123!",
                "role": UserRole.SUPER_ADMIN
            },
            {
                "email": "canary.requester@example.com",
                "password": "CanaryRequester123!",
                "role": UserRole.ADMIN
            },
            {
                "email": "canary.ops@example.com", 
                "password": "CanaryOps123!",
                "role": UserRole.OPS
            }
        ]
        
        # Check existing users
        existing_users = db.query(User).all()
        existing_emails = {user.email for user in existing_users}
        
        print(f"Existing users: {[user.email for user in existing_users]}")
        
        created_count = 0
        for user_data in users_to_create:
            if user_data["email"] not in existing_emails:
                # Create new user
                new_user = User(
                    email=user_data["email"],
                    password_hash=hash_password(user_data["password"]),
                    role=user_data["role"],
                    approval_status="approved",
                    is_active=True
                )
                
                db.add(new_user)
                created_count += 1
                print(f"Created user: {user_data['email']} with role {user_data['role']}")
            else:
                print(f"User already exists: {user_data['email']}")
        
        if created_count > 0:
            db.commit()
            print(f"Successfully created {created_count} users")
        else:
            print("No new users needed to be created")
            
        # Verify final user list
        final_users = db.query(User).all()
        print(f"\nFinal user list:")
        for user in final_users:
            print(f"  - {user.email}: {user.role} (status: {user.approval_status}, active: {user.is_active})")
            
    except Exception as e:
        print(f"Error creating users: {e}")
        db.rollback()
        return False
    finally:
        db.close()
    
    return True

if __name__ == "__main__":
    success = create_valid_test_users()
    sys.exit(0 if success else 1)