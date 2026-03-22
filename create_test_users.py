#!/usr/bin/env python3
"""
Create missing test users for Strategy Intelligence governance flow testing
"""

import sys
import os
sys.path.append('/app/backend')

from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash
from db import SessionLocal
from models import User, UserRole

def create_test_users():
    """Create the missing test users"""
    db = SessionLocal()
    
    try:
        # Check existing users
        existing_users = db.query(User).all()
        existing_emails = {user.email for user in existing_users}
        
        print(f"Existing users: {[user.email for user in existing_users]}")
        
        # Users to create
        users_to_create = [
            {
                "email": "canary.requester@platform.local",
                "password": "CanaryRequester123!",
                "role": UserRole.ADMIN
            },
            {
                "email": "canary.ops@platform.local", 
                "password": "CanaryOps123!",
                "role": UserRole.OPS
            }
        ]
        
        created_count = 0
        for user_data in users_to_create:
            if user_data["email"] not in existing_emails:
                # Create new user
                new_user = User(
                    email=user_data["email"],
                    password_hash=generate_password_hash(user_data["password"]),
                    role=user_data["role"],
                    approval_status="approved"  # Pre-approve the test users
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
            print(f"  - {user.email}: {user.role} (status: {user.approval_status})")
            
    except Exception as e:
        print(f"Error creating users: {e}")
        db.rollback()
        return False
    finally:
        db.close()
    
    return True

if __name__ == "__main__":
    success = create_test_users()
    sys.exit(0 if success else 1)