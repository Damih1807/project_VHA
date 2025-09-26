#!/usr/bin/env python3
"""
Script để migrate permissions cho các user hiện tại
Đảm bảo tất cả user đều có đầy đủ các trường permission cần thiết
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from models.models_db import db, Users
from models.user_types import get_user_role, validate_and_merge_permissions, get_default_permissions

def migrate_user_permissions():
    """Migrate permissions cho tất cả user hiện tại"""
    with app.app_context():
        users = Users.query.all()
        migrated_count = 0
        error_count = 0
        
        print(f"Found {len(users)} users to migrate...")
        
        for user in users:
            try:
                # Lấy role hiện tại của user
                user_role = get_user_role(user.role)
                
                # Lấy permissions hiện tại (có thể None hoặc thiếu trường)
                current_permissions = user.permissions or {}
                
                # Merge với default permissions
                new_permissions = validate_and_merge_permissions(user_role, current_permissions)
                
                # Cập nhật nếu có thay đổi
                if current_permissions != new_permissions:
                    user.permissions = new_permissions
                    migrated_count += 1
                    print(f"Migrated user {user.username} ({user.email})")
                    print(f"  Old permissions: {current_permissions}")
                    print(f"  New permissions: {new_permissions}")
                    print()
                
            except Exception as e:
                error_count += 1
                print(f"Error migrating user {user.username}: {str(e)}")
        
        # Commit tất cả thay đổi
        if migrated_count > 0:
            db.session.commit()
            print(f"Successfully migrated {migrated_count} users")
        
        if error_count > 0:
            print(f"Failed to migrate {error_count} users")
        
        print("Migration completed!")

def validate_all_user_permissions():
    """Validate permissions của tất cả user"""
    with app.app_context():
        users = Users.query.all()
        valid_count = 0
        invalid_count = 0
        
        print(f"Validating permissions for {len(users)} users...")
        
        for user in users:
            try:
                user_role = get_user_role(user.role)
                current_permissions = user.permissions or {}
                
                # Kiểm tra xem permissions có đầy đủ không
                expected_permissions = get_default_permissions(user_role)
                
                missing_permissions = []
                for perm_key in expected_permissions.keys():
                    if perm_key not in current_permissions:
                        missing_permissions.append(perm_key)
                
                if missing_permissions:
                    invalid_count += 1
                    print(f"User {user.username} ({user.email}) missing permissions: {missing_permissions}")
                else:
                    valid_count += 1
                    
            except Exception as e:
                invalid_count += 1
                print(f"Error validating user {user.username}: {str(e)}")
        
        print(f"Validation completed: {valid_count} valid, {invalid_count} invalid")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate user permissions")
    parser.add_argument("--validate-only", action="store_true", help="Only validate, don't migrate")
    parser.add_argument("--migrate-only", action="store_true", help="Only migrate, don't validate")
    
    args = parser.parse_args()
    
    if args.validate_only:
        validate_all_user_permissions()
    elif args.migrate_only:
        migrate_user_permissions()
    else:
        # Mặc định chạy cả validate và migrate
        print("=== VALIDATION PHASE ===")
        validate_all_user_permissions()
        print("\n=== MIGRATION PHASE ===")
        migrate_user_permissions()
        print("\n=== FINAL VALIDATION ===")
        validate_all_user_permissions()
